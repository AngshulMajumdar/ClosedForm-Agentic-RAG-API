"""Tiny local test-only retriever; replace with Qdrant/Elastic/Azure AI Search in production.

Run: uvicorn examples.retriever_stub:app --host 127.0.0.1 --port 7861
"""
import re
from fastapi import FastAPI
from pydantic import BaseModel, Field

app=FastAPI(title="Local test retriever (not suitable for large corpora)")
DOCUMENTS=[
    {"id":"a","title":"Tokyo","text":"Tokyo is the capital of Japan and its largest city."},
    {"id":"b","title":"Japan","text":"Japan is an island country in East Asia. Tokyo is its capital."},
    {"id":"c","title":"Kyoto","text":"Kyoto served as the capital of Japan in the past."},
    {"id":"d","title":"Osaka","text":"Osaka is a major Japanese city and commercial center."}
]
class Req(BaseModel):
    query: str = Field(min_length=1,max_length=2000)
    top_k: int = Field(3,ge=1,le=100)

def toks(s):return set(re.findall(r"[a-z0-9]+",s.lower()))-{ "what", "is", "the", "of", "a", "and", "which", "in" }

@app.post("/search")
def search(req:Req):
    words=toks(req.query)
    scored=[]
    for d in DOCUMENTS:
        match=len(words&toks(d["text"]+" "+d["title"]))
        scored.append((match,d))
    scored.sort(key=lambda p:(-p[0],p[1]["id"]))
    return {"documents":[dict(**d,score=round(hit/max(1,len(words)),5)) for hit,d in scored[:req.top_k]]}
