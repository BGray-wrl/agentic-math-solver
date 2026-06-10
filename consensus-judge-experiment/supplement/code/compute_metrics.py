#!/usr/bin/env python3
"""Regenerate every table in the paper from the raw per-instance judge scores.

Reproduces (and writes to ../results/tables/):
  Table 1  validation, n=200, 5 judges + cheap consensus
  Table 2  full benchmark, n=1000, 3 cheap judges + pairs + majority + all-three
  Table 3  run-to-run variance over 4 runs + self-consensus columns
  Table A1 Gemini 3.1 Pro, default vs high reasoning
  plus extended tables (confusion matrices, all consensus configs, prior sample,
  calibration bias, provider mix) used in EXTENDED_RESULTS.md.

Only the Python standard library is required. Bootstrap CIs use a fixed seed;
point estimates are exact, interval endpoints may vary by ~0.005 with the RNG.

    python compute_metrics.py
"""
import csv, json, glob, math, random, statistics as st
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
OUT = Path(__file__).resolve().parent.parent / "results" / "tables"
OUT.mkdir(parents=True, exist_ok=True)
csv.field_size_limit(10**7)

# Per-200-gradings cost (USD): measured OpenRouter usage.cost sums from the runs
# (see README "Costs"). Cost is provider/run dependent and is not recomputed here.
COST = {"GPT-OSS-120B": 0.32, "DeepSeek-V4-Flash": 0.70, "Gemma-4-31B": 0.71,
        "Cheap consensus (trio)": 1.73, "Claude Opus 4.7": 32.45,
        "Gemini 3.1 Pro": 28.61, "Gemini 3.1 Pro (default)": 7.07}

CHEAP_COLS = {"GPT-OSS-120B": "gpt_oss_120b_xhigh_score",
              "DeepSeek-V4-Flash": "deepseek_v4_flash_default_score",
              "Gemma-4-31B": "gemma_4_31b_it_high_score"}

# ---------------------------------------------------------------- loaders
def _num(x):
    return float(x) if x not in (None, "") else None

def load_consensus_analysis():
    """Per-instance scores for prior(200)+validation(200). Returns rows list."""
    return list(csv.DictReader(open(DATA / "consensus_analysis.csv", newline="")))

def json_scores(path):
    """{grading_id: score}, {grading_id: human} from a run JSON."""
    d = json.load(open(path)); sc = {}; hu = {}
    for r in d["results"]:
        sc[r["grading_id"]] = r["score"]
        hu[r["grading_id"]] = r.get("human_points", r.get("human"))
    return sc, hu

# ---------------------------------------------------------------- metrics
def avg_rank(vals):
    order = sorted(range(len(vals)), key=lambda i: vals[i]); ranks = [0.0] * len(vals); i = 0
    while i < len(vals):
        j = i
        while j + 1 < len(vals) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2.0 + 1
        i = j + 1
    return ranks

def pearson(xs, ys):
    if len(xs) < 2: return 0.0
    mx, my = st.mean(xs), st.mean(ys)
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = math.sqrt(sum((a - mx) ** 2 for a in xs)); dy = math.sqrt(sum((b - my) ** 2 for b in ys))
    return num / (dx * dy) if dx and dy else 0.0

def spearman(js, hs):
    return pearson(avg_rank(js), avg_rank(hs))

def confusion(scores, human, gids=None):
    """scores: {gid: float|None}. Returns dict of metrics over valid gids."""
    gids = gids if gids is not None else scores.keys()
    tp = fp = tn = fn = 0; js = []; hs = []
    for g in gids:
        s = scores.get(g)
        if s is None: continue
        hp = human[g] >= 6; jp = s >= 6
        tp += jp and hp; fp += jp and not hp; tn += (not jp) and (not hp); fn += (not jp) and hp
        js.append(s); hs.append(human[g])
    n = tp + fp + tn + fn
    prec = tp / (tp + fp) if tp + fp else float("nan")
    rec = tp / (tp + fn) if tp + fn else float("nan")
    f1 = 2 * prec * rec / (prec + rec) if prec == prec and rec == rec and prec + rec else float("nan")
    return dict(n=n, agree=(tp + tn) / n if n else float("nan"), prec=prec, rec=rec, f1=f1,
                tp=tp, fp=fp, tn=tn, fn=fn, rho=spearman(js, hs) if len(js) > 1 else float("nan"))

def boot_ci(scores, human, B=1000, seed=0):
    valid = [g for g in scores if scores[g] is not None]
    n = len(valid); random.seed(seed); ags = []
    for _ in range(B):
        idx = [valid[random.randrange(n)] for _ in range(n)]
        c = sum(1 for g in idx if (scores[g] >= 6) == (human[g] >= 6))
        ags.append(c / n)
    ags.sort()
    return ags[int(.025 * B)], ags[int(.975 * B)]

def majority(members, human, gids):
    out = {}
    for g in gids:
        vals = [m[g] for m in members if m.get(g) is not None]
        out[g] = (6.0 if sum(v >= 6 for v in vals) * 2 > len(vals) else 0.0) if vals else None
    return out

def unanimous(members, human, gids):
    out = {}
    for g in gids:
        vals = [m[g] for m in members if m.get(g) is not None]
        if len(vals) < len(members): out[g] = None          # require all members valid
        else: out[g] = 6.0 if all(v >= 6 for v in vals) else 0.0
    return out

def fmt(x, d=3):
    return "—" if x is None or (isinstance(x, float) and x != x) else f"{x:.{d}f}"

# ---------------------------------------------------------------- load data
rows = load_consensus_analysis()
val = [r for r in rows if r["sample"] == "validation"]
pri = [r for r in rows if r["sample"] == "prior"]
human_val = {r["grading_id"]: int(float(r["human_score"])) for r in val}
human_pri = {r["grading_id"]: int(float(r["human_score"])) for r in pri}

def col_scores(rowset, col):
    return {r["grading_id"]: _num(r[col]) for r in rowset}

val_gptoss = col_scores(val, CHEAP_COLS["GPT-OSS-120B"])
val_deepseek = col_scores(val, CHEAP_COLS["DeepSeek-V4-Flash"])
val_gemma = col_scores(val, CHEAP_COLS["Gemma-4-31B"])
val_opus = col_scores(val, "claude_opus_4_7_score")
val_gemini_def = col_scores(val, "gemini_3_1_pro_score")
val_gemini_high, _ = json_scores(DATA / "gemini_high_validation.json")

# full benchmark (400 + 600)
full = {"GPT-OSS-120B": {}, "DeepSeek-V4-Flash": {}, "Gemma-4-31B": {}}
human_full = {}
for r in rows:
    g = r["grading_id"]; human_full[g] = int(float(r["human_score"]))
    for name, col in CHEAP_COLS.items():
        full[name][g] = _num(r[col])
for name, fn in [("GPT-OSS-120B", "remaining600_gpt-oss-120b.json"),
                 ("DeepSeek-V4-Flash", "remaining600_deepseek-v4-flash.json"),
                 ("Gemma-4-31B", "remaining600_gemma-4-31b-it.json")]:
    sc, hu = json_scores(DATA / fn)
    for g, s in sc.items():
        full[name][g] = s; human_full.setdefault(g, hu[g])
full_gids = list(human_full)

# replicates
reps = {"DeepSeek-V4-Flash": [], "GPT-OSS-120B": [], "Gemma-4-31B": []}
repfile = {"DeepSeek-V4-Flash": "judge_deepseek-v4-flash_default_rep{}_20260526_021655.json",
           "GPT-OSS-120B": "judge_gpt-oss-120b_xhigh_rep{}_20260526_021655.json",
           "Gemma-4-31B": "judge_gemma-4-31b-it_high_rep{}_20260526_021655.json"}
for name, pat in repfile.items():
    for k in (1, 2, 3):
        sc, _ = json_scores(DATA / "multi_seed" / pat.format(k)); reps[name].append(sc)

# =============================================================== TABLE 1
print("\n================ TABLE 1  (validation, n=200) ================")
trio_val = majority([val_gemma, val_gptoss, val_deepseek], human_val, list(human_val))
t1 = [("GPT-OSS-120B", "xhigh", val_gptoss, True),
      ("DeepSeek-V4-Flash", "default", val_deepseek, True),
      ("Cheap consensus (trio)", "—", trio_val, False),
      ("Claude Opus 4.7", "adaptive", val_opus, True),
      ("Gemini 3.1 Pro", "high", val_gemini_high, True),
      ("Gemma-4-31B", "high", val_gemma, True)]
hdr = f"{'judge':24s} {'reason':8s} {'agree':>6} {'95% CI':>14} {'prec':>5} {'rec':>5} {'F1':>5} {'rho':>5} {'cost/200':>8}"
print(hdr)
rows_out = [["judge", "reasoning", "pass_agree", "ci_lo", "ci_hi", "precision", "recall", "f1", "spearman_rho", "cost_per_200"]]
for name, reason, sc, show_rho in t1:
    m = confusion(sc, human_val); lo, hi = boot_ci(sc, human_val, B=1000)
    rho = fmt(m["rho"]) if show_rho else "—"
    cost = COST[name]
    print(f"{name:24s} {reason:8s} {m['agree']:6.3f} [{lo:.3f},{hi:.3f}] {fmt(m['prec']):>5} {fmt(m['rec']):>5} {fmt(m['f1']):>5} {rho:>5} {'$'+format(cost,'.2f'):>8}")
    rows_out.append([name, reason, f"{m['agree']:.3f}", f"{lo:.3f}", f"{hi:.3f}", fmt(m["prec"]),
                     fmt(m["rec"]), fmt(m["f1"]), rho, f"{cost:.2f}"])
csv.writer(open(OUT / "table1_validation.csv", "w", newline="")).writerows(rows_out)

# =============================================================== TABLE 2
print("\n================ TABLE 2  (full benchmark, n=1000) ================")
g_, o_, d_ = full["Gemma-4-31B"], full["GPT-OSS-120B"], full["DeepSeek-V4-Flash"]
t2 = [("DeepSeek-V4-Flash", d_, True), ("GPT-OSS-120B", o_, True), ("Gemma-4-31B", g_, True),
      ("DeepSeek + GPT-OSS", unanimous([d_, o_], human_full, full_gids), False),
      ("DeepSeek + Gemma", unanimous([d_, g_], human_full, full_gids), False),
      ("GPT-OSS + Gemma", unanimous([o_, g_], human_full, full_gids), False),
      ("Majority vote (trio)", majority([g_, o_, d_], human_full, full_gids), False),
      ("All-three-pass", unanimous([d_, o_, g_], human_full, full_gids), False)]
print(f"{'system':22s} {'n':>4} {'agree':>6} {'95% CI':>14} {'prec':>5} {'rec':>5} {'F1':>5} {'rho':>5}")
rows_out = [["system", "n", "pass_agree", "ci_lo", "ci_hi", "precision", "recall", "f1", "spearman_rho"]]
for name, sc, show_rho in t2:
    m = confusion(sc, human_full); lo, hi = boot_ci(sc, human_full, B=2000)
    rho = fmt(m["rho"]) if show_rho else "—"
    print(f"{name:22s} {m['n']:4d} {m['agree']:6.3f} [{lo:.3f},{hi:.3f}] {fmt(m['prec']):>5} {fmt(m['rec']):>5} {fmt(m['f1']):>5} {rho:>5}")
    rows_out.append([name, m["n"], f"{m['agree']:.3f}", f"{lo:.3f}", f"{hi:.3f}", fmt(m["prec"]),
                     fmt(m["rec"]), fmt(m["f1"]), rho])
csv.writer(open(OUT / "table2_full1000.csv", "w", newline="")).writerows(rows_out)

# =============================================================== TABLE 3
print("\n================ TABLE 3  (run-to-run, validation) ================")
orig = {"DeepSeek-V4-Flash": val_deepseek, "GPT-OSS-120B": val_gptoss, "Gemma-4-31B": val_gemma}
def pa(sc, human=human_val):
    m = confusion(sc, human); return m["agree"]
def self_rule(name, rule):
    rr = reps[name]; gids = [g for g in human_val if all(g in r and r[g] is not None for r in rr)]
    sc = (majority if rule == "maj" else unanimous)(rr, human_val, gids)
    return confusion(sc, human_val, gids)["agree"]
print(f"{'system':22s} {'orig':>5} {'rep1':>5} {'rep2':>5} {'rep3':>5} {'mean':>5} {'std':>5} {'selfMaj':>7} {'selfAll3':>8}")
rows_out = [["system", "orig", "rep1", "rep2", "rep3", "mean", "std", "self_maj", "self_all3"]]
single = ["DeepSeek-V4-Flash", "GPT-OSS-120B", "Gemma-4-31B"]
for name in single:
    runs = [pa(orig[name])] + [pa(reps[name][k]) for k in range(3)]
    mean = st.mean(runs); std = st.stdev(runs)  # sample std (n-1), matches the paper
    sm, sa = self_rule(name, "maj"), self_rule(name, "all3")
    print(f"{name:22s} " + " ".join(f"{x:5.3f}" for x in runs) + f" {mean:5.3f} {std:5.3f} {sm:7.3f} {sa:8.3f}")
    rows_out.append([name] + [f"{x:.3f}" for x in runs] + [f"{mean:.3f}", f"{std:.3f}", f"{sm:.3f}", f"{sa:.3f}"])
# consensus rows (no self-consensus)
for label, rule in [("Majority vote (trio)", majority), ("All-three-pass", unanimous)]:
    runs = []
    for k in range(-1, 3):
        members = [orig["Gemma-4-31B"], orig["GPT-OSS-120B"], orig["DeepSeek-V4-Flash"]] if k == -1 else \
                  [reps["Gemma-4-31B"][k], reps["GPT-OSS-120B"][k], reps["DeepSeek-V4-Flash"][k]]
        gids = list(human_val)
        runs.append(pa(rule(members, human_val, gids)))
    mean = st.mean(runs); std = st.stdev(runs)
    print(f"{label:22s} " + " ".join(f"{x:5.3f}" for x in runs) + f" {mean:5.3f} {std:5.3f} {'—':>7} {'—':>8}")
    rows_out.append([label] + [f"{x:.3f}" for x in runs] + [f"{mean:.3f}", f"{std:.3f}", "—", "—"])
csv.writer(open(OUT / "table3_runtorun.csv", "w", newline="")).writerows(rows_out)

# =============================================================== TABLE A1
print("\n================ TABLE A1  (Gemini default vs high, n=200) ================")
def mean_reason_csv():  # gemini default reasoning tokens from trials_validation.csv if present
    return None
gh = json.load(open(DATA / "gemini_high_validation.json"))
rt_high = int(st.mean([r["usage"]["reasoning_tokens"] for r in gh["results"]
                       if r.get("usage") and r["score"] is not None]))
rows_out = [["setting", "mean_reasoning_tokens", "pass_agree", "f1", "spearman_rho", "cost_per_200"]]
for setting, sc, rt, cost in [("default", val_gemini_def, "~2400", COST["Gemini 3.1 Pro (default)"]),
                              ("high", val_gemini_high, rt_high, COST["Gemini 3.1 Pro"])]:
    m = confusion(sc, human_val)
    print(f"  {setting:8s} reason~{str(rt):>6} agree={m['agree']:.3f} F1={fmt(m['f1'])} rho={fmt(m['rho'])} ${cost:.2f}")
    rows_out.append([setting, rt, f"{m['agree']:.3f}", fmt(m["f1"]), fmt(m["rho"]), f"{cost:.2f}"])
csv.writer(open(OUT / "tableA1_gemini_reasoning.csv", "w", newline="")).writerows(rows_out)

# =============================================================== EXTENDED
# (E1) confusion matrices for every validation system
ext = [["scope", "system", "n", "tp", "fp", "tn", "fn", "precision", "recall", "f1", "pass_agree"]]
for name, sc in [("GPT-OSS-120B", val_gptoss), ("DeepSeek-V4-Flash", val_deepseek),
                 ("Gemma-4-31B", val_gemma), ("Claude Opus 4.7", val_opus),
                 ("Gemini 3.1 Pro (high)", val_gemini_high), ("Cheap consensus (trio)", trio_val)]:
    m = confusion(sc, human_val)
    ext.append(["validation", name, m["n"], m["tp"], m["fp"], m["tn"], m["fn"],
                fmt(m["prec"]), fmt(m["rec"]), fmt(m["f1"]), f"{m['agree']:.3f}"])
for name, sc, _ in t2:
    m = confusion(sc, human_full)
    ext.append(["full1000", name, m["n"], m["tp"], m["fp"], m["tn"], m["fn"],
                fmt(m["prec"]), fmt(m["rec"]), fmt(m["f1"]), f"{m['agree']:.3f}"])
csv.writer(open(OUT / "ext_confusion_matrices.csv", "w", newline="")).writerows(ext)

# (E2) self-consensus full P/R/F1 (validation, rep1-3)
ext = [["model", "rule", "n", "precision", "recall", "f1", "pass_agree"]]
for name in single:
    rr = reps[name]; gids = [g for g in human_val if all(g in r and r[g] is not None for r in rr)]
    for rule, lab in [("maj", "self-majority"), ("all3", "self-all-3")]:
        sc = (majority if rule == "maj" else unanimous)(rr, human_val, gids)
        m = confusion(sc, human_val, gids)
        ext.append([name, lab, m["n"], fmt(m["prec"]), fmt(m["rec"]), fmt(m["f1"]), f"{m['agree']:.3f}"])
csv.writer(open(OUT / "ext_self_consensus.csv", "w", newline="")).writerows(ext)

# (E3) prior/exploratory sample (cheap judges + gemini default)
ext = [["system", "n", "pass_agree", "precision", "recall", "f1", "spearman_rho"]]
pri_scores = {"GPT-OSS-120B": col_scores(pri, CHEAP_COLS["GPT-OSS-120B"]),
              "DeepSeek-V4-Flash": col_scores(pri, CHEAP_COLS["DeepSeek-V4-Flash"]),
              "Gemma-4-31B": col_scores(pri, CHEAP_COLS["Gemma-4-31B"]),
              "Gemini 3.1 Pro (default)": col_scores(pri, "gemini_3_1_pro_score")}
pri_scores["Cheap consensus (trio)"] = majority(
    [pri_scores["Gemma-4-31B"], pri_scores["GPT-OSS-120B"], pri_scores["DeepSeek-V4-Flash"]], human_pri, list(human_pri))
for name, sc in pri_scores.items():
    m = confusion(sc, human_pri)
    rho = "—" if name == "Cheap consensus (trio)" else fmt(m["rho"])
    ext.append([name, m["n"], f"{m['agree']:.3f}", fmt(m["prec"]), fmt(m["rec"]), fmt(m["f1"]), rho])
csv.writer(open(OUT / "ext_prior_sample.csv", "w", newline="")).writerows(ext)

# (E4) calibration bias: mean(judge - human) per judge (validation)
ext = [["system", "n", "mean_delta", "note"]]
for name, sc in [("GPT-OSS-120B", val_gptoss), ("DeepSeek-V4-Flash", val_deepseek),
                 ("Gemma-4-31B", val_gemma), ("Claude Opus 4.7", val_opus),
                 ("Gemini 3.1 Pro (high)", val_gemini_high)]:
    ds = [sc[g] - human_val[g] for g in human_val if sc.get(g) is not None]
    note = "over-credits" if st.mean(ds) > 0.15 else "under-credits" if st.mean(ds) < -0.15 else "~calibrated"
    ext.append([name, len(ds), f"{st.mean(ds):+.3f}", note])
csv.writer(open(OUT / "ext_calibration_bias.csv", "w", newline="")).writerows(ext)

# (E5) provider mix (from multi-seed summary)
summ = json.load(open(DATA / "multi_seed" / "summary_noseed_reps.json"))
ext = [["judge", "provider", "call_count"]]
for jid, mix in summ.get("provider_mix", {}).items():
    for prov, cnt in sorted(mix.items(), key=lambda kv: -kv[1]):
        ext.append([jid, prov, cnt])
csv.writer(open(OUT / "ext_provider_mix.csv", "w", newline="")).writerows(ext)

print(f"\nWrote {len(list(OUT.glob('*.csv')))} CSVs to {OUT}")
