"""Conservative authenticated *route-only* network test; never calls LLMs.

Run from repo root:
    python benchmarks/load_route.py --requests 50 --concurrency 4

Use only against systems you own or are authorized to load test. Default limits
are deliberately low; no production throughput is implied by these results.
"""
import argparse
import asyncio
import statistics
import time

from closedform_rag import APIError, AsyncClosedFormRAGClient

CANDIDATES = [
    {"id":f"tier-{i}","predicted_accuracy":0.55 + 0.01*i,
     "expected_cost_usd":0.0005 + i*0.0003,"latency_p95_ms":250+i*75,
     "llm_calls":1+(i>13),"retrieval_calls":0}
    for i in range(20)
]


async def run(requests: int, concurrency: int, base_url: str | None):
    opts = {"route_retries":0}
    if base_url:opts["base_url"] = base_url
    async with AsyncClosedFormRAGClient(**opts) as client:
        gate=asyncio.Semaphore(concurrency)
        seconds=[]
        errors={}
        async def one(_: int):
            async with gate:
                t=time.perf_counter()
                try:
                    result=await client.route(CANDIDATES,
                        {"max_expected_cost_usd":.01,"deadline_ms":3000,"max_llm_calls":2})
                    if result.get("decision_llm_calls")!=0:
                        raise RuntimeError("Unexpected LLM orchestrator call")
                except Exception as ex:
                    status=ex.status_code if isinstance(ex,APIError) else type(ex).__name__
                    errors[str(status)]=errors.get(str(status),0)+1
                finally:
                    seconds.append(time.perf_counter()-t)
        start=time.perf_counter()
        await asyncio.gather(*(one(i) for i in range(requests)))
        elapsed=time.perf_counter()-start
    observed=sorted(seconds)
    print({"requests":requests,"concurrency":concurrency,"elapsed_s":round(elapsed,4),
           "successful":requests-sum(errors.values()),"errors":errors,
           "request_per_s_observed":round(requests/elapsed,2),
           "mean_ms":round(statistics.mean(observed)*1000,2),
           "p95_ms":round(observed[min(len(observed)-1,int(.95*len(observed)))]*1000,2)})


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--requests",type=int,default=50)
    parser.add_argument("--concurrency",type=int,default=4)
    parser.add_argument("--base-url",default=None)
    args=parser.parse_args()
    if not 1<=args.requests<=10000 or not 1<=args.concurrency<=100:
        parser.error("Requests must be 1-10000 and concurrency 1-100; use authorized targets only")
    asyncio.run(run(args.requests,args.concurrency,args.base_url))
