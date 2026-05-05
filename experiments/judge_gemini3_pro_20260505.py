#!/usr/bin/env python3
"""Frontier baseline: gemini-3.1-pro-preview as judge with reasoning enabled.
Same n=200 sample as the cheap-trio analysis. $20 hard cost cap — abort and
publish partial results if exceeded.
"""
from __future__ import annotations
import argparse, concurrent.futures, csv, itertools, json, math, os, random, re
import statistics as st, sys, threading, time
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import litellm  # noqa: E402

ROOT = Path(__file__).parent.parent
PROMPTS_DIR = ROOT / "prompts" / "pipeline"
RESULTS_DIR = Path(__file__).parent / "results"
DATA_CSV = ROOT / "benchmarks" / "IMO-bench" / "gradingbench.csv"

JUDGE = "openrouter/google/gemini-3.1-pro-preview"
# Pricing best-effort — gemini-3.1-pro-preview on OpenRouter is roughly
# $1.25/M input, $10/M output. We track via OpenRouter usage so the actual
# cost is what gets billed, but use this as a fast pre-filter.
PRICE_INPUT_PER_M  = 1.25
PRICE_OUTPUT_PER_M = 10.00
EXTRA_BODY = {"reasoning": {"enabled": True}}  # let provider pick budget

N_DEFAULT = 200
SEED = 42
MAX_WORKERS = 80
MAX_TOKENS = 32768
TIMEOUT = 900
ROLL_EVERY_N = 10           # tight rolling — we want to watch cost
ROLL_EVERY_S = 30.0
COST_CAP = 20.0              # HARD ABORT


load_dotenv()
def _filter_live_keys(keys):
    import requests
    live = []
    for i, k in enumerate(keys):
        try:
            r = requests.get("https://openrouter.ai/api/v1/key",
                             headers={"Authorization": f"Bearer {k}"}, timeout=8)
            if not r.ok: live.append(k); continue
            d = r.json().get("data", {}) or {}
            limit = d.get("limit"); usage = d.get("usage", 0) or 0
            if limit is not None and usage >= limit:
                print(f"[startup] key#{i}: EXHAUSTED ({usage:.2f}/{limit}) — dropped")
            else:
                rem = (limit - usage) if limit else "unlimited"
                print(f"[startup] key#{i}: live (usage={usage:.2f}/{limit}, remain={rem})")
                live.append(k)
        except Exception as e:
            print(f"[startup] key#{i}: probe failed ({e}), including"); live.append(k)
    return live

KEYS = _filter_live_keys([k for k in [
    os.getenv("OPENROUTER_API_KEY"),
    os.getenv("OPENROUTER_API_KEY_X"),
    os.getenv("OPENROUTER_API_KEY_X2"),
] if k])
if not KEYS: raise SystemExit("No live keys")
_iter = itertools.cycle(KEYS); _lock = threading.Lock()
def next_key():
    with _lock: return next(_iter)


def _ts(): return datetime.now(timezone.utc).strftime("%H:%M:%S")
def _now(): return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
def _mmss(s): s = max(0, int(s)); return f"{s//60:02d}:{s%60:02d}"


def call_judge(prompt: str, retries: int = 2, backoff: float = 4.0):
    last = None
    for attempt in range(retries + 1):
        try:
            resp = litellm.completion(
                model=JUDGE, messages=[{"role": "user", "content": prompt}],
                max_tokens=MAX_TOKENS, api_key=next_key(), timeout=TIMEOUT,
                extra_body=EXTRA_BODY,
            )
            msg = resp.choices[0].message
            content = msg.content or getattr(msg, "reasoning", None) or getattr(msg, "reasoning_content", None)
            if content is None: raise ValueError("None content")
            usage = resp.usage
            cd = getattr(usage, "completion_tokens_details", None)
            return content, {
                "prompt_tokens":     int(getattr(usage, "prompt_tokens", 0) or 0),
                "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
                "total_tokens":      int(getattr(usage, "total_tokens", 0) or 0),
                "reasoning_tokens":  int(getattr(cd, "reasoning_tokens", 0) or 0) if cd else 0,
            }
        except Exception as e:
            last = e
            err = str(e)
            if "402" in err or "credit" in err.lower() or "insufficient" in err.lower() or "Key limit" in err:
                raise
            if attempt < retries: time.sleep(backoff * (2 ** attempt))
    raise last


def parse_score(text):
    if not text: return None
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", text, re.I)
    if m:
        v = int(m.group(1)); return v if 0<=v<=7 else None
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", text, re.I)
    return int(m.group(1)) if m else None


def bucket(s): return 0 if s<=0 else (1 if s<=3 else (6 if s<=6 else 7))
def pearson(xs, ys):
    if len(xs)<2: return 0
    mx,my=st.mean(xs),st.mean(ys)
    n=sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    dx=math.sqrt(sum((x-mx)**2 for x in xs)); dy=math.sqrt(sum((y-my)**2 for y in ys))
    return n/(dx*dy) if dx>0 and dy>0 else 0
def pct(v,p):
    if not v: return 0
    s=sorted(v); k=(len(s)-1)*p/100; f,c=math.floor(k),math.ceil(k)
    return s[int(k)] if f==c else s[f]*(c-k)+s[c]*(k-f)


def stats_block(results):
    valid = [r for r in results if r.get("score") is not None]
    n=len(results); nv=len(valid)
    if nv == 0: return {"n": n, "n_valid": 0}
    h=[r["human_points"] for r in valid]; j=[r["score"] for r in valid]
    abs_d=[abs(a-b) for a,b in zip(j,h)]; deltas=[a-b for a,b in zip(j,h)]
    h_pass=[x>=6 for x in h]; j_pass=[x>=6 for x in j]
    agr6=sum(1 for a,b in zip(h_pass,j_pass) if a==b)/nv
    raw=sum(1 for a,b in zip(h,j) if a==b)/nv
    bk=sum(1 for a,b in zip(h,j) if bucket(a)==b)/nv
    r=pearson([float(x) for x in j],[float(x) for x in h])
    lat=[rr["elapsed"] for rr in results]
    rts=[rr["usage"].get("reasoning_tokens",0) for rr in valid if rr.get("usage")]
    cost=sum(rr["cost"] for rr in results)
    return {"n":n,"n_valid":nv,"mean_J":round(st.mean(j),3),"mean_H":round(st.mean(h),3),
            "mean_abs_dev":round(st.mean(abs_d),3),"mean_delta":round(st.mean(deltas),3),
            "pearson_r":round(r,3),"pass_agree_at_6":round(agr6,4),
            "exact_raw":round(raw,4),"exact_bucketed":round(bk,4),
            "cost_usd":round(cost,4),
            "latency_p50":round(pct(lat,50),1),"latency_p95":round(pct(lat,95),1),
            "mean_rt":int(st.mean(rts)) if rts else 0,
            "p95_rt":int(pct(rts,95)) if rts else 0}


def print_rolling(results, n_total, t0, cost_state):
    el=time.time()-t0; nd=len(results)
    eta=(el/max(nd,1))*(n_total-nd) if nd else 0
    s=stats_block(results)
    print(f"\n=== ROLLING [elapsed {_mmss(el)}, {nd}/{n_total} done, ETA ~{_mmss(eta)}, $spent={cost_state['spent']:.2f}/${COST_CAP}] ===", flush=True)
    if s.get("n_valid",0):
        print(f"  n_v={s['n_valid']} mJ={s['mean_J']:.2f} mH={s['mean_H']:.2f} "
              f"|D|={s['mean_abs_dev']:.2f} r={s['pearson_r']:.2f} "
              f">=6agr={s['pass_agree_at_6']*100:.1f}% raw={s['exact_raw']*100:.1f}% buck={s['exact_bucketed']*100:.1f}% "
              f"${s['cost_usd']:.2f} p50={s['latency_p50']:.1f}s p95={s['latency_p95']:.1f}s "
              f"rt~{s['mean_rt']}/{s['p95_rt']}", flush=True)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--n",type=int,default=N_DEFAULT)
    args=ap.parse_args()
    judge_template=(PROMPTS_DIR/"judge_gt.md").read_text()
    rows=[]
    with open(DATA_CSV,newline="") as f:
        for r in csv.DictReader(f):
            rows.append({"grading_id":r["Grading ID"],"problem_id":r["Problem ID"],
                         "problem":r["Problem"],"solution":r["Solution"],
                         "response":r["Response"],"human_points":int(r["Points"]),
                         "source":r["Problem Source"]})
    sample=random.Random(SEED).sample(rows,min(args.n,len(rows)))
    print(f"  {len(rows)} -> sampled {len(sample)} (seed={SEED})", flush=True)
    print(f"  judge: {JUDGE}  reasoning: ENABLED  workers: {MAX_WORKERS}", flush=True)
    print(f"  HARD COST CAP: ${COST_CAP}\n", flush=True)

    out_path=RESULTS_DIR/f"judge_gemini3_pro_20260505_{_now()}.json"
    out_partial=out_path.with_name(out_path.stem+"_partial.json")
    cost_state={"spent":0.0,"capped":False}; cost_lock=threading.Lock()

    def worker(rec):
        with cost_lock:
            if cost_state["spent"] >= COST_CAP or cost_state["capped"]:
                return {"grading_id":rec["grading_id"],"human_points":rec["human_points"],
                        "score":None,"error":"cost cap","cost":0.0,"elapsed":0.0,"capped":True}
        prompt=(judge_template
                .replace("{problem}",rec["problem"])
                .replace("{ground_truth}",rec["solution"])
                .replace("{candidate}",rec["response"]))
        t0=time.time()
        try:
            content,usage=call_judge(prompt)
            el=round(time.time()-t0,2)
            score=parse_score(content)
            cost = round((PRICE_INPUT_PER_M*usage["prompt_tokens"] + PRICE_OUTPUT_PER_M*usage["completion_tokens"]) / 1_000_000, 6)
            with cost_lock:
                cost_state["spent"]+=cost
                if cost_state["spent"]>=COST_CAP and not cost_state["capped"]:
                    cost_state["capped"]=True
                    print(f"\n[!! COST CAP HIT: ${cost_state['spent']:.2f} >= ${COST_CAP} — no new submissions !!]\n", flush=True)
            d=(score-rec["human_points"]) if score is not None else None
            ds=f"D={d:+d}" if d is not None else "D=NA"
            print(f"[{_ts()}] {rec['grading_id']:<8} pts={rec['human_points']} score={score} {ds}  ${cost:.4f}  {el}s  rt={usage.get('reasoning_tokens',0)}  cum=${cost_state['spent']:.2f}", flush=True)
            return {"grading_id":rec["grading_id"],"problem_id":rec["problem_id"],
                    "human_points":rec["human_points"],"source":rec["source"],
                    "score":score,"verdict":content,"usage":usage,
                    "cost":cost,"elapsed":el}
        except Exception as e:
            el=round(time.time()-t0,2)
            print(f"[{_ts()}] FAIL {rec['grading_id']}: {str(e)[:120]}", flush=True)
            return {"grading_id":rec["grading_id"],"human_points":rec["human_points"],
                    "score":None,"error":str(e),"cost":0.0,"elapsed":el}

    results=[]; t0=time.time(); last_n,last_t=0,t0
    print(f"Starting at {_ts()} UTC ...\n", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs=[ex.submit(worker,r) for r in sample]
        for fut in concurrent.futures.as_completed(futs):
            try: results.append(fut.result())
            except Exception as e: print(f"outer fail: {e}", flush=True)
            now=time.time()
            if (len(results)-last_n)>=ROLL_EVERY_N or (now-last_t)>=ROLL_EVERY_S:
                print_rolling(results,len(sample),t0,cost_state)
                with open(out_partial.with_suffix(".tmp"),"w") as f:
                    json.dump({"is_partial":True,"n_done":len(results),"n_total":len(sample),
                               "elapsed_s":round(now-t0,1),"cost_capped":cost_state["capped"],
                               "stats":stats_block(results),"results":results},f,ensure_ascii=False)
                os.replace(out_partial.with_suffix(".tmp"),out_partial)
                last_n,last_t=len(results),now

    el=round(time.time()-t0,1); s=stats_block(results)
    print(f"\n{'='*100}\nFINAL gemini-3.1-pro  n_sampled={len(sample)} done={len(results)} "
          f"valid={s.get('n_valid',0)} wall={_mmss(el)} ({el}s) cost=${cost_state['spent']:.2f} {'[CAPPED]' if cost_state['capped'] else ''}\n{'='*100}\n", flush=True)
    print_rolling(results,len(sample),t0,cost_state)
    final={"experiment":"judge_gemini3_pro_20260505","is_partial":False,
           "date":datetime.now(timezone.utc).isoformat(),"judge":JUDGE,
           "extra_body":EXTRA_BODY,"price_input_per_M":PRICE_INPUT_PER_M,"price_output_per_M":PRICE_OUTPUT_PER_M,
           "cost_capped":cost_state["capped"],"cost_cap":COST_CAP,
           "n_sampled":len(sample),"n_done":len(results),
           "wall_clock_s":el,"total_cost_usd":round(cost_state["spent"],4),
           "stats":s,"results":results}
    with open(out_path,"w") as f:
        json.dump(final,f,indent=2,ensure_ascii=False)
    print(f"Saved: {out_path}", flush=True)
    if out_partial.exists():
        try: out_partial.unlink()
        except OSError: pass


if __name__=="__main__":
    main()
