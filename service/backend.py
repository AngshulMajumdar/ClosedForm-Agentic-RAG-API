from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx
from .config import Model


class UpstreamError(RuntimeError):
    pass


@dataclass
class ChatResult:
    text: str
    prompt_tokens: int
    output_tokens: int
    elapsed_ms: float
    price_usd: float | None
    usage_source: str


class RemoteClient:
    def __init__(self, timeout_sec: float = 90.0, max_connections: int = 128,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.http = httpx.AsyncClient(timeout=timeout_sec,
                                      limits=httpx.Limits(max_connections=max_connections, max_keepalive_connections=min(max_connections,32)),
                                      transport=transport, follow_redirects=False)

    async def close(self) -> None:
        await self.http.aclose()

    async def chat(self, model: Model, messages: list[dict], max_tokens: int, timeout_sec: float) -> ChatResult:
        if max_tokens < 1: raise ValueError("max_tokens must be positive")
        headers={"content-type":"application/json"}
        if model.api_key:headers["authorization"]="Bearer "+model.api_key
        payload={"model":model.model_id,"messages":messages,"max_tokens":max_tokens,"temperature":0}
        began=time.perf_counter()
        try:
            response=await self.http.post(model.base_url + "/chat/completions",json=payload,
                                          headers=headers,timeout=max(.05,timeout_sec))
            response.raise_for_status()
            parsed=response.json()
            content=parsed["choices"][0]["message"].get("content")
            if isinstance(content,list):
                content=" ".join(p.get("text","") for p in content if isinstance(p,dict))
            if not isinstance(content,str): raise ValueError("No text content returned")
            usage=parsed.get("usage") or {}
            # Missing usage is reported as unknown, not silently replaced with a fictitious charge.
            pt=usage.get("prompt_tokens")
            ot=usage.get("completion_tokens")
            known=isinstance(pt,int) and isinstance(ot,int)
            price=(pt*model.price_input_per_1m+ot*model.price_output_per_1m)/1e6 if known and model.priced else None
            return ChatResult(content, int(pt) if known else 0,int(ot) if known else 0,
                              (time.perf_counter()-began)*1000,price,"provider" if known else "missing")
        except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError) as e:
            raise UpstreamError(f"Model backend '{model.alias}' failed: {type(e).__name__}") from e

    async def retrieve(self, url: str, api_key: str, query: str, top_k: int,
                       timeout_sec: float) -> list[dict[str,Any]]:
        if not url.startswith("https://") and not (url.startswith("http://") and __import__("os").getenv("ALLOW_HTTP_ENDPOINTS")=="1"):
            raise ValueError("Retriever URL must use https")
        headers={"content-type":"application/json"}
        if api_key:headers["authorization"]="Bearer "+api_key
        try:
            r=await self.http.post(url,json={"query":query,"top_k":top_k},headers=headers,
                                   timeout=max(.05,timeout_sec))
            r.raise_for_status()
            raw=r.json()
            docs=raw["documents"] if isinstance(raw,dict) else raw
            if not isinstance(docs,list):raise ValueError("Retriever must return documents array")
            clean=[]
            for d in docs[:top_k]:
                if not isinstance(d,dict) or not isinstance(d.get("text"),str):continue
                score=d.get("score",0.0)
                clean.append({"id":str(d.get("id",len(clean)))[:100],"text":d["text"][:5000],
                              "score":float(score) if isinstance(score,(int,float)) else 0.0,
                              "title":str(d.get("title",""))[:180]})
            return clean
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
            raise UpstreamError(f"Retriever backend failed: {type(e).__name__}") from e
