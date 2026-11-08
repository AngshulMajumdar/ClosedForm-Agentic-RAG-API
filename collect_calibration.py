"""Collect matched real-model RAG outcomes for production calibration.

Every training question is executed with *each* configured macro-action.
This harness does not make LLM-based routing decisions: it forces each action
for unbiased paired calibration data. DO NOT run on the test benchmark split.

Input JSONL rows: {"question": "...", "answers": ["..."]}
Example:
  python collect_calibration.py --api http://127.0.0.1:7860 \
    --questions calibration_train.jsonl --out calibration_traces.csv \
    --token-env API_TOKEN --concurrency 4

Usage cost and tokens come from the upstream model API's response. The output
cost excludes external retriever API fees unless those are accounted separately.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import time
from collections import Counter
from pathlib import Path

import httpx

ACTION_SPEC={
    "retrieve_fast":(1,0),
    "retrieve_strong":(1,0),
    "iterative_strong":(2,1),
}


def normalize(s):
    s=re.sub(r"[^a-z0-9\s]"," ",s.lower())
    return " ".join(re.sub(r"\b(a|an|the)\b"," ",s).split())


def answer_exact(pred,golds):
    return int(any(normalize(pred)==normalize(g) for g in golds))


async def main():
    p=argparse.ArgumentParser()
    p.add_argument("--api",required=True)
    p.add_argument("--questions",required=True)
    p.add_argument("--out",default="calibration_traces.csv")
    p.add_argument("--raw-jsonl",default="calibration_raw.jsonl")
    p.add_argument("--token-env",default="API_TOKEN")
    p.add_argument("--concurrency",type=int,default=4)
    p.add_argument("--deadline-ms",type=int,default=120000)
    args=p.parse_args()
    token=os.getenv(args.token_env)
    if not token:raise ValueError(f"Set API secret environment variable {args.token_env}")
    if args.concurrency<1 or args.concurrency>128:raise ValueError("concurrency must be 1..128")
    questions=[json.loads(s) for s in Path(args.questions).read_text(encoding="utf-8").splitlines() if s.strip()]
    if not questions:raise ValueError("No calibration questions provided")
    for q in questions:
        if not isinstance(q.get("question"),str) or not q.get("answers"):
            raise ValueError("Each row requires 'question' and nonempty 'answers'")
    semaphore=asyncio.Semaphore(args.concurrency)
    observed=[];raw=[]
    async with httpx.AsyncClient(timeout=args.deadline_ms/1000+10,headers={"authorization":"Bearer "+token}) as client:
        async def run(index:int,question:dict,action:str):
            calls,extra=ACTION_SPEC[action]
            forecast={"id":action,"predicted_accuracy":1.0,"expected_cost_usd":0.0,
                      "latency_p95_ms":0.0,"llm_calls":calls,"retrieval_calls":extra}
            payload={"question":question["question"],"allowed_actions":[action],
                     "action_forecasts":{action:forecast},
                     "budgets":{"deadline_ms":args.deadline_ms,"max_llm_calls":calls,
                                "max_retrieval_calls":1+extra,"stop_utility":-1.0}}
            async with semaphore:
                started=time.perf_counter()
                try:
                    r=await client.post(args.api.rstrip("/")+"/v1/answer",json=payload)
                    r.raise_for_status()
                    answer=r.json()
                    state="ok"
                except (httpx.HTTPError,ValueError) as e:
                    answer={"error":str(e)[:300]};state="error"
            elapsed=(time.perf_counter()-started)*1000
            row={"qid":index,"bucket":answer.get("bucket", ""),"action":action,
                 "correct":answer_exact(answer.get("answer") or "",question["answers"]) if state=="ok" else "",
                 "cost_usd":(answer.get("resources") or {}).get("total_estimated_cost_usd",""),
                 "latency_ms":answer.get("elapsed_ms",round(elapsed,2)),
                 "post_preflight_ms":answer.get("post_preflight_ms",""),
                 "state":state,"model_calls":(answer.get("resources") or {}).get("model_calls",""),
                 "unpriced_calls":(answer.get("resources") or {}).get("unpriced_calls",""),
                 "unpriced_retrieval_calls":(answer.get("resources") or {}).get("unpriced_retrieval_calls",""),
                 "unreported_usage_calls":(answer.get("resources") or {}).get("unreported_usage_calls",""),
                 "input_tokens":(answer.get("resources") or {}).get("input_tokens",""),
                 "output_tokens":(answer.get("resources") or {}).get("output_tokens","")}
            return row,{"qid":index,"action":action,"question":question["question"],
                        "gold":question["answers"],"response":answer}
        tasks=[asyncio.create_task(run(i,q,a)) for i,q in enumerate(questions) for a in ACTION_SPEC]
        for k,task in enumerate(asyncio.as_completed(tasks),1):
            row,item=await task;observed.append(row);raw.append(item)
            if k%50==0:print("Completed",k,"of",len(tasks),"calls",flush=True)
    # Sorting makes the output deterministic in row order even under concurrency.
    observed.sort(key=lambda x:(x["qid"],x["action"]))
    raw.sort(key=lambda x:(x["qid"],x["action"]))
    fields=list(observed[0])
    with open(args.out,"w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(observed)
    with open(args.raw_jsonl,"w",encoding="utf-8") as f:
        for item in raw:f.write(json.dumps(item,ensure_ascii=False)+"\n")
    errs=sum(r["state"]!="ok" for r in observed)
    missing=sum((int(r["unpriced_calls"])>0 or int(r["unpriced_retrieval_calls"])>0)
                for r in observed if r["state"]=="ok")
    print(json.dumps({"rows":len(observed),"failed":errs,"unpriced":missing,
                      "csv":args.out,"raw":args.raw_jsonl}),flush=True)
    if errs or missing:
        print("Do NOT fit calibration directly: rerun failed rows and configure current prices + provider usage reporting.",flush=True)


if __name__=="__main__":
    asyncio.run(main())
