#!/usr/bin/env python3
"""Re-judge the single void call: gpt-oss × first-proof-4-official."""
import json, os, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
import litellm
from problemset_70 import load_70_problems

load_dotenv()

KEY = os.getenv("OPENROUTER_API_KEY_seedgen")
JUDGE = "openrouter/deepseek/deepseek-v4-pro"
ROOT = Path(__file__).parent.parent
prompt = (ROOT / "prompts" / "pipeline" / "judge_gt.md").read_text().strip()
problems = load_70_problems()

trial_path = ROOT / "experiments/results/seed_full_phase2_20260504_20260505_002924/seed_full/gpt-oss-120b/first-proof-4-official.json"
with open(trial_path) as f: t = json.load(f)
candidate = t.get("best_solution") or ""
prob = problems["first-proof-4-official"]

user = (prompt
        .replace("{problem}", prob["text"])
        .replace("{ground_truth}", prob["ground_truth"])
        .replace("{candidate}", candidate))

print(f"candidate len={len(candidate)} chars  ground_truth len={len(prob['ground_truth'])} chars")

score = None
verdict_text = ""
for attempt in range(3):
    t0 = time.time()
    try:
        resp = litellm.completion(
            model=JUDGE, messages=[{"role":"user","content":user}],
            max_tokens=32000, api_key=KEY, timeout=1800,
        )
        verdict_text = resp.choices[0].message.content or ""
        elapsed = time.time() - t0
        usage = resp.usage
        if not verdict_text:
            print(f"  attempt {attempt+1}: EMPTY ({elapsed:.1f}s)"); continue
        m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", verdict_text, re.I)
        score = int(m.group(1)) if m else None
        print(f"  attempt {attempt+1}: out_tok={usage.completion_tokens} elapsed={elapsed:.1f}s score={score}")
        break
    except Exception as e:
        print(f"  attempt {attempt+1}: error {e}")

print(f"\nFinal v4-pro score for gpt-oss × first-proof-4-official: {score}")
if verdict_text:
    print("\n--- last 400 chars of verdict ---")
    print(verdict_text[-400:])
