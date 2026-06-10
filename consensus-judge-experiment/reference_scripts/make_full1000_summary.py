#!/usr/bin/env python3
"""Write the full-1000 per-system metrics summary (with bootstrap 95% CIs) to CSV.
Sources: consensus_analysis.csv (400, fully patched) + judge_remaining600_*.json (600).
All three cheap judges at 1000/1000 coverage."""
import csv, json, glob, math, random, statistics as st

human={}; gemma={}; oss={}; ds={}
f=lambda x: float(x) if x not in (None,"") else None
for r in csv.DictReader(open("consensus_analysis.csv")):
    g=r["grading_id"]; human[g]=int(float(r["human_score"]))
    gemma[g]=f(r["gemma_4_31b_it_high_score"]); oss[g]=f(r["gpt_oss_120b_xhigh_score"]); ds[g]=f(r["deepseek_v4_flash_default_score"])
def load(pat,d):
    for r in json.load(open(sorted(glob.glob(pat))[-1]))["results"]:
        g=r["grading_id"]; human.setdefault(g,r["human_points"]); d[g]=r["score"]
load("judge_remaining600_gemma-4-31b-it_high_*",gemma)
load("judge_remaining600_gpt-oss-120b_xhigh_*",oss)
load("judge_remaining600_deepseek-v4-flash_default_*",ds)
GIDS=list(human)

def pearson(xs,ys):
    mx,my=st.mean(xs),st.mean(ys); n=sum((a-mx)*(b-my) for a,b in zip(xs,ys))
    dx=math.sqrt(sum((a-mx)**2 for a in xs)); dy=math.sqrt(sum((b-my)**2 for b in ys))
    return n/(dx*dy) if dx and dy else 0.0
def single(m): return lambda g:(m[g]>=6,m[g]) if m.get(g) is not None else None
def pair(a,b):
    def fn(g):
        if a.get(g) is None or b.get(g) is None: return None
        return (a[g]>=6 and b[g]>=6, None)
    return fn
def allp(a,b,c):
    def fn(g):
        if any(x.get(g) is None for x in (a,b,c)): return None
        return (a[g]>=6 and b[g]>=6 and c[g]>=6, None)
    return fn
def maj(a,b,c):
    def fn(g):
        vals=[x[g] for x in (a,b,c) if x.get(g) is not None]
        if not vals: return None
        return (sum(1 for v in vals if v>=6)*2>len(vals), sum(vals)/len(vals))
    return fn

def metrics(fn, wr, B=2000, seed=1):
    tp=fp=tn=fn_=0; rs=[]; hs=[]; valid=[]
    for g in GIDS:
        d=fn(g)
        if d is None: continue
        valid.append(g); jp,sc=d; hp=human[g]>=6
        tp+=jp and hp; fp+=jp and not hp; tn+=(not jp)and(not hp); fn_+=(not jp)and hp
        if sc is not None: rs.append(sc); hs.append(human[g])
    n=tp+fp+tn+fn_
    prec=tp/(tp+fp) if tp+fp else float('nan'); rec=tp/(tp+fn_) if tp+fn_ else 0
    f1=2*prec*rec/(prec+rec) if prec==prec and prec and rec else 0
    random.seed(seed); ags=[]; f1s=[]
    for _ in range(B):
        idx=[valid[random.randrange(n)] for _ in range(n)]
        a=b=c=e=0
        for g in idx:
            jp,_=fn(g); hp=human[g]>=6
            a+=jp and hp; b+=jp and not hp; c+=(not jp)and(not hp); e+=(not jp)and hp
        ags.append((a+c)/n)
        p=a/(a+b) if a+b else 0; rc=a/(a+e) if a+e else 0
        f1s.append(2*p*rc/(p+rc) if p and rc else 0)
    ags.sort(); f1s.sort()
    return dict(n=n, pass_agree=round((tp+tn)/n,4),
                pa_ci_lo=round(ags[int(.025*B)],4), pa_ci_hi=round(ags[int(.975*B)],4),
                precision=round(prec,4), recall=round(rec,4), f1=round(f1,4),
                f1_ci_lo=round(f1s[int(.025*B)],4), f1_ci_hi=round(f1s[int(.975*B)],4),
                pearson_r=round(pearson(rs,hs),4) if wr and len(rs)>1 else "",
                tp=tp, fp=fp, tn=tn, fn=fn_)

SYSTEMS=[
    ("GPT-OSS-120B @ xhigh","individual","single",single(oss),True),
    ("DeepSeek-V4-Flash","individual","single",single(ds),True),
    ("Gemma-4-31B @ high","individual","single",single(gemma),True),
    ("oss + gemma","pair","unanimous_pass",pair(oss,gemma),False),
    ("ds + gemma","pair","unanimous_pass",pair(ds,gemma),False),
    ("ds + oss","pair","unanimous_pass",pair(ds,oss),False),
    ("Majority vote (trio)","combined","majority_vote",maj(gemma,oss,ds),True),
    ("All-three-pass","combined","unanimous_pass",allp(ds,oss,gemma),False),
]
cols=["system","group","rule","n","pass_agree","pa_ci_lo","pa_ci_hi","precision","recall",
      "f1","f1_ci_lo","f1_ci_hi","pearson_r","tp","fp","tn","fn"]
out="consensus_judges_full1000_metrics_20260525.csv"
with open(out,"w",newline="") as fh:
    w=csv.DictWriter(fh,fieldnames=cols); w.writeheader()
    for name,grp,rule,fn,wr in SYSTEMS:
        m=metrics(fn,wr); m.update(system=name,group=grp,rule=rule); w.writerow(m)
print(f"wrote {out} ({len(SYSTEMS)} systems, n=1000, bootstrap 95% CI B=2000)")
