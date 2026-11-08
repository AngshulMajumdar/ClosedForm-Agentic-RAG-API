"""Fit closed-form empirical-Bayes bucket/action estimates from real LLM traces.

Input CSV columns: bucket,action,correct,cost_usd,latency_ms
Each action must have outcomes on calibration data from the *actual deployed*
model, prompts, retriever, and context-window policy. Do not train on test QA.
"""
import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path


def pct95(xs):
    xs=sorted(xs)
    if not xs:return None
    return xs[math.ceil(.95*len(xs))-1]


def fit(rows,shrinkage:float=10.0,gap_threshold:float=.07)->dict:
    grouped=defaultdict(list)
    global_data=defaultdict(list)
    for r in rows:
        a=str(r["action"]);b=str(r["bucket"])
        if not a or not b:raise ValueError("Missing bucket or action")
        if r.get("state", "ok")!="ok":
            raise ValueError("Failed requests must be rerun before calibration")
        if (str(r.get("unpriced_calls", "0")) not in ("0", "0.0", "")
            or str(r.get("unreported_usage_calls", "0")) not in ("0", "0.0", "")
            or str(r.get("unpriced_retrieval_calls", "0")) not in ("0", "0.0", "")):
            raise ValueError("Provider usage or LLM/retriever price missing; cannot estimate costs")
        hit=float(r["correct"]);cost=float(r["cost_usd"])
        # Once the first retrieval is complete, the controller decides which
        # additional steps to execute; forecast only the *remaining* latency.
        lat=float(r.get("post_preflight_ms") or r["latency_ms"])
        if not 0<=hit<=1 or cost<0 or lat<0:raise ValueError("Invalid calibration label/cost/latency")
        item=(hit,cost,lat)
        grouped[(a,b)].append(item);global_data[a].append(item)
    actions={}
    for a,data in global_data.items():
        p0=(sum(row[0] for row in data)+1)/(len(data)+2)
        buckets={b:(sum(row[0] for row in items)+shrinkage*p0)/(len(items)+shrinkage)
                 for (action,b),items in grouped.items() if action==a}
        actions[a]={"global_quality":p0,"quality_by_bucket":buckets,
                    "counts_by_bucket":{b:len(items) for (action,b),items in grouped.items() if action==a},
                    "expected_cost_usd":sum(row[1] for row in data)/len(data),
                    "latency_p95_ms":pct95([row[2] for row in data]),
                    "n_calibration":len(data)}
    return {"format_version":1,"shrinkage":shrinkage,"gap_threshold":gap_threshold,
            "calibration_warning":"Valid only for the same model/retriever/actions/prompts as these real traces.",
            "actions":actions}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--traces",required=True)
    p.add_argument("--output",default="config/policy.json")
    p.add_argument("--shrinkage",type=float,default=10.)
    p.add_argument("--gap-threshold",type=float,default=.07)
    args=p.parse_args()
    if args.shrinkage<=0:raise ValueError("shrinkage must be positive")
    with open(args.traces,newline="",encoding="utf-8") as f:rows=list(csv.DictReader(f))
    if not rows:raise ValueError("Empty calibration traces")
    obj=fit(rows,args.shrinkage,args.gap_threshold)
    dest=Path(args.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(obj,indent=2),encoding="utf-8")
    print("Wrote",dest,"actions",list(obj["actions"]))

if __name__=="__main__":main()
