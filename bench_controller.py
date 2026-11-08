"""Local CPU-only microbenchmark for scoring, not model-serving QPS.

Run: python bench_controller.py --requests 100000 --actions 20
"""
import argparse
import statistics
import time
from service.policy import Candidate,Limits,select

p=argparse.ArgumentParser()
p.add_argument("--requests",type=int,default=50000)
p.add_argument("--actions",type=int,default=20)
a=p.parse_args()
assert a.actions>0 and a.requests>0
options=[Candidate(f"a{i}",.65+i%6/100,.0002+i*.0001,600+i*30,1+(i%2)) for i in range(a.actions)]
lim=Limits(max_expected_cost_usd=.02,deadline_ms=4000,max_llm_calls=2,price_per_usd=3,price_per_second=.03)
lat=[]
for i in range(a.requests):
    start=time.perf_counter_ns()
    result=select(options,lim)
    lat.append((time.perf_counter_ns()-start)/1e6)
assert result["decision_llm_calls"]==0
lat.sort()
print({"calls":a.requests,"actions_per_call":a.actions,"mean_ms":round(statistics.mean(lat),6),
       "p50_ms":round(lat[int(.5*len(lat))],6),"p95_ms":round(lat[int(.95*len(lat))],6),
       "p99_ms":round(lat[int(.99*len(lat))],6),"controller_llm_calls":0,
       "note":"Local CPU-only numerical benchmark; does not test provider throughput."})
