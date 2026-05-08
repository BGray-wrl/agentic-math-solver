#!/usr/bin/env python3
"""
Export the full agentic-math-solver experiment corpus as a single JSONL dataset.

One row per (experiment, condition, model, problem_id) trial.  Includes:

  - Phase 1   seed-ideas 4-way (6 models × 70 problems × 3 modes)
  - Phase 2   seed_full on cheap models (2 × 70 × 1)
  - Phase 3   v4-flash seed_full (1 × 70 × 1)
  - Roleswap  cross-model seed_full (8 conditions × 70)
  - Scaling   best-of-N curves on PB-Advanced (2 × 30 × 1, branches k=0..6)

Each row carries a `judges` dict with up to three entries: v4pro, gemini, v4flash.
Per-branch judges are nested under `branches[].judges`.  Score-source is tracked
in `judges.<j>.source` so downstream consumers can audit which regrade run a
particular score came from.

Output: results/dataset_20260505.jsonl
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
from problemset_70 import load_70_problems, SPECIAL_10  # noqa: E402

RESULTS  = ROOT / "experiments" / "results"
OUT_DIR  = ROOT / "results"
OUT      = OUT_DIR / "dataset_20260505.jsonl"

# ============================================================================
# Source paths (run dirs + regrade artifacts)
# ============================================================================

PHASE1_DIR    = RESULTS / "seed_ideas_full_compare_20260504_20260504_101225"
PHASE2_DIR    = RESULTS / "seed_full_phase2_20260504_20260505_002924"
PHASE3_DIR    = RESULTS / "seed_full_v4flash_phase3_20260505_20260505_021635"
ROLESWAP_DIR  = RESULTS / "seed_full_role_swap_20260505_20260505_032032"
SCALING_DIR   = RESULTS / "scaling_oss_gemma_20260505_20260505_033250"

# Late-arriving experiments (added 2026-05-05 evening, all v4-flash inline judge)
PHASE1_REASONING_DIR  = RESULTS / "phase1_reasoning_20260505_20260505_114334"
SCALING_REASONING_DIR = RESULTS / "scaling_reasoning_20260505_20260505_114334"
SCALING_V4FLASH_DIR   = RESULTS / "best_of_n_v4flash_20260504_20260505_115611"
GPT5_NANO_PASS3_DIR   = RESULTS / "gpt54nano_pass3_20260504_20260505_115611"

# Flex-budget sweep + composed-critic (added 2026-05-06 morning, v4-flash inline judge)
ROLESWAP_REASONING_DIR  = RESULTS / "role_swap_reasoning_20260505_20260505_114334"
FLEX_CROSS_IDEATOR_DIR  = RESULTS / "cross_ideator_v4flash_20260505_20260505_120545"
FLEX_STRONG_CRITIC_DIR  = RESULTS / "strong_critic_v4flash_20260505_20260505_121438"
FLEX_PASSN_DIR          = RESULTS / "passN_v4flash_20260505_20260505_120944"
FLEX_COMPOSED_DIR       = RESULTS / "composed_critic_passN_20260505_20260505_193921"

# Gemini regrades (Phase 1)
P1_GEMINI_TRIAL_DIR   = RESULTS / "regrade_gemini_20260504_20260504_221221"
P1_GEMINI_BRANCH_DIR  = RESULTS / "regrade_branches_gemini_20260504_20260504_222334"

# v4-pro regrades / patches
P1_V4PRO_PATCH_FILE   = RESULTS / "regrade_p1_parse_fails_20260505_051120.json"
P2_V4PRO_TRIAL_FILE   = RESULTS / "regrade_phase2_full_v4pro_20260505_033600.json"
P2_V4PRO_BRANCH_FILE  = RESULTS / "regrade_phase2_v4pro_20260505_022346.json"
P3_V4PRO_TRIAL_DIR    = RESULTS / "regrade_phase3_v4pro_20260505_043627"

# v4-flash regrade (this build's input)
V4FLASH_DIR = RESULTS / "v4flash_judge_20260505"


# ============================================================================
# Utilities
# ============================================================================

def short(m: str) -> str:
    return m.split("/")[-1] if m else "_no_model"


def safe_load(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.load(open(path))
    except Exception:
        return None


def empty_judge() -> dict:
    return {"score": None, "verdict": None, "source": None}


def make_judges() -> dict:
    return {"v4pro": empty_judge(), "gemini": empty_judge(), "v4flash": empty_judge()}


# ============================================================================
# Regrade lookup tables (preloaded once, so per-row reads are O(1))
# ============================================================================

class Lookups:
    def __init__(self):
        # Phase 1 v4-pro parse-failure patches: dict[(model, mode, pid, branch_idx)] -> score
        self.p1_parse_patch_branch: dict[tuple, int] = {}   # branch_idx as int
        self.p1_parse_patch_trial:  dict[tuple, int] = {}   # trial-level (branch == "full")

        patch = safe_load(P1_V4PRO_PATCH_FILE)
        if patch and "results" in patch:
            for r in patch["results"]:
                if r.get("v4pro_score_new") is None: continue
                key = (r["model"], r["mode"], r["problem_id"])
                if r.get("branch") == "full":
                    self.p1_parse_patch_trial[key] = r["v4pro_score_new"]
                else:
                    bi = r.get("branch_idx")
                    if bi is not None:
                        self.p1_parse_patch_branch[(*key, int(bi))] = r["v4pro_score_new"]

        # Phase 2 trial-level v4-pro regrade
        self.p2_v4pro_trial: dict[tuple, dict] = {}
        p2 = safe_load(P2_V4PRO_TRIAL_FILE)
        if p2 and "results" in p2:
            for r in p2["results"]:
                if r.get("v4pro_score") is None: continue
                self.p2_v4pro_trial[(r["model"], r["problem_id"])] = {
                    "score":   r["v4pro_score"],
                    "verdict": r.get("v4pro_verdict"),
                    "source":  "regrade_phase2_full_v4pro_20260505",
                }

        # Phase 2 frontier branch v4-pro regrade (10 branches)
        self.p2_v4pro_branch: dict[tuple, dict] = {}
        p2b = safe_load(P2_V4PRO_BRANCH_FILE)
        if p2b and "results" in p2b:
            for r in p2b["results"]:
                if r.get("v4pro_score") is None: continue
                self.p2_v4pro_branch[(r["model"], r["problem_id"], int(r["idea_idx"]))] = {
                    "score":   r["v4pro_score"],
                    "verdict": r.get("v4pro_verdict"),
                    "source":  "regrade_phase2_v4pro_frontier_20260505",
                }

    # ----- Phase 1 v4-pro: trial level -----
    def phase1_v4pro_trial(self, mode: str, model: str, pid: str, trial: dict) -> dict:
        # Default = inline trial.score; patch if parse-fail recovery exists for this trial
        # (only relevant for full mode where a single judge call may have parse-failed)
        sc = trial.get("score")
        verdict = trial.get("best_verdict")
        source = "phase1_inline"
        # Patch (only full-mode trial-level recoveries are stored under (model, mode, pid))
        patched = self.p1_parse_patch_trial.get((model, mode, pid))
        if patched is not None and patched != sc:
            sc = patched
            source = "phase1_inline+parsefail_patch"
        return {"score": sc, "verdict": verdict, "source": source}

    # ----- Phase 1 v4-pro: branch level -----
    def phase1_v4pro_branch(
        self, mode: str, model: str, pid: str, branch_idx: int, branch: dict,
    ) -> dict:
        sc = branch.get("score")
        verdict = branch.get("verdict")
        source = "phase1_inline"
        patched = self.p1_parse_patch_branch.get((model, mode, pid, branch_idx))
        if patched is not None and patched != sc:
            sc = patched
            source = "phase1_inline+parsefail_patch"
        return {"score": sc, "verdict": verdict, "source": source}

    # ----- Phase 1 gemini: trial level -----
    def phase1_gemini_trial(self, mode: str, model: str, pid: str) -> dict:
        p = P1_GEMINI_TRIAL_DIR / mode / short(model) / f"{pid}.json"
        d = safe_load(p)
        if not d or d.get("error") or d.get("gemini_score") is None:
            return {"score": None, "verdict": None, "source": None}
        return {
            "score":   d["gemini_score"],
            "verdict": d.get("gemini_verdict"),
            "source":  "regrade_gemini_20260504",
        }

    # ----- Phase 1 gemini: branch level -----
    def phase1_gemini_branch(self, mode: str, model: str, pid: str, k: int) -> dict:
        # Branch regrade naming: <pid>__k{k}.json (works for both generate and seed_generate
        # in the original regrade run; matches the existing exporter's logic)
        p = P1_GEMINI_BRANCH_DIR / mode / short(model) / f"{pid}__k{k}.json"
        d = safe_load(p)
        if not d or d.get("error") or d.get("gemini_score") is None:
            return {"score": None, "verdict": None, "source": None}
        return {
            "score":   d["gemini_score"],
            "verdict": d.get("gemini_verdict"),
            "source":  "regrade_branches_gemini_20260504",
        }

    # ----- Phase 2 v4-pro: trial level -----
    def phase2_v4pro_trial(self, model: str, pid: str) -> dict:
        d = self.p2_v4pro_trial.get((model, pid))
        return d if d else empty_judge()

    # ----- Phase 2 v4-pro: branch level (frontier only) -----
    def phase2_v4pro_branch(self, model: str, pid: str, idea_idx: int) -> dict:
        d = self.p2_v4pro_branch.get((model, pid, idea_idx))
        return d if d else empty_judge()

    # ----- Phase 3 v4-pro: trial level (truncation-fixed regrade) -----
    def phase3_v4pro_trial(self, pid: str) -> dict:
        p = P3_V4PRO_TRIAL_DIR / f"{pid}.json"
        d = safe_load(p)
        if not d or d.get("v4pro_score") is None:
            return empty_judge()
        return {
            "score":   d["v4pro_score"],
            "verdict": d.get("v4pro_verdict"),
            "source":  "regrade_phase3_v4pro_truncated_20260505",
        }

    # ----- v4-flash: any cell -----
    def v4flash(self, sub_path: str) -> dict:
        """sub_path is the path relative to V4FLASH_DIR (e.g.  'phase1/generate/gpt-oss-120b/PB-Basic-001__trial.json')"""
        p = V4FLASH_DIR / sub_path
        d = safe_load(p)
        if not d or d.get("v4flash_score") is None or not d.get("has_tag", False):
            return empty_judge()
        return {
            "score":   d["v4flash_score"],
            "verdict": d.get("v4flash_verdict"),
            "source":  "regrade_v4flash_20260505",
        }


# ============================================================================
# Per-experiment row builders
# ============================================================================

def base_row(problem: dict, pid: str, experiment: str, condition: str) -> dict:
    return {
        "experiment":     experiment,
        "condition":      condition,
        "model":          None,
        "problem_id":     pid,
        "problem_text":   problem["text"],
        "ground_truth":   problem["ground_truth"],
        "category":       problem.get("category"),
        "level":          problem.get("level"),
        "source":         problem.get("source"),
        "is_special_10":  pid in SPECIAL_10,
        "started_at":     None,
        "completed_at":   None,
        "elapsed_s":      None,
        "cost_usd":       None,
        "error":          None,
        "final_solution": None,
        "judges":         make_judges(),
        "branches":       [],
        "mode_extras":    None,
    }


def trim_branch_judges(b: dict, k: int | None, idea_idx: int | None) -> dict:
    """Return a fresh per-branch dict with empty judges nested in."""
    return {
        "k":                k,
        "idea_idx":         idea_idx,
        "idea":             b.get("idea"),
        "solution":         b.get("solution") or b.get("final_solution"),
        "initial_solution": b.get("initial_solution"),
        "final_solution":   b.get("final_solution"),
        "loop_log":         b.get("loop_log"),
        "stopped_early":    b.get("stopped_early"),
        "judges":           make_judges(),
    }


# ----- Phase 1 -----

def phase1_rows(problems: dict, lk: Lookups):
    for mode in ("generate", "full", "seed_generate"):
        mode_dir = PHASE1_DIR / mode
        if not mode_dir.exists(): continue
        for model_dir in sorted(mode_dir.iterdir()):
            if not model_dir.is_dir(): continue
            for trial_path in sorted(model_dir.glob("*.json")):
                pid = trial_path.stem
                t = safe_load(trial_path)
                if t is None:
                    # trial_missing — emit a stub row for completeness
                    r = base_row(problems[pid], pid, "phase1", mode)
                    r["model"] = None
                    r["error"] = "trial_missing"
                    yield r
                    continue
                model = t["model"]
                r = base_row(problems[pid], pid, "phase1", mode)
                r["model"]        = model
                r["started_at"]   = t.get("started_at")
                r["completed_at"] = t.get("completed_at")
                r["elapsed_s"]    = t.get("elapsed_s")
                r["cost_usd"]     = t.get("cost_usd")
                r["error"]        = t.get("error")
                r["final_solution"] = t.get("best_solution")
                r["mode_extras"]    = t.get("mode_extras")

                if not t.get("error"):
                    r["judges"]["v4pro"]   = lk.phase1_v4pro_trial(mode, model, pid, t)
                    r["judges"]["gemini"]  = lk.phase1_gemini_trial(mode, model, pid)
                    r["judges"]["v4flash"] = lk.v4flash(
                        f"phase1/{mode}/{short(model)}/{pid}__trial.json"
                    )

                # Branches (only generate/seed_generate get per-branch in Phase 1)
                if not t.get("error"):
                    for b in t.get("branches", []) or []:
                        if mode == "generate":
                            k = b.get("k", 0)
                            br = trim_branch_judges(b, k=k, idea_idx=None)
                            br["judges"]["v4pro"]   = lk.phase1_v4pro_branch(mode, model, pid, k, b)
                            br["judges"]["gemini"]  = lk.phase1_gemini_branch(mode, model, pid, k)
                            br["judges"]["v4flash"] = lk.v4flash(
                                f"phase1/{mode}/{short(model)}/{pid}__k{k}.json"
                            )
                        elif mode == "seed_generate":
                            idx = b.get("idea_idx", 0)
                            br = trim_branch_judges(b, k=None, idea_idx=idx)
                            br["judges"]["v4pro"]   = lk.phase1_v4pro_branch(mode, model, pid, idx, b)
                            br["judges"]["gemini"]  = lk.phase1_gemini_branch(mode, model, pid, idx)
                            br["judges"]["v4flash"] = lk.v4flash(
                                f"phase1/{mode}/{short(model)}/{pid}__idea{idx}.json"
                            )
                        else:  # full — single branch, no per-branch regrade. Branch judges = trial judges.
                            br = trim_branch_judges(b, k=b.get("k", 0), idea_idx=None)
                            # The trial-level v4pro/gemini IS the branch judgment for full mode.
                            # Copy them in for consumer convenience; mark source clearly.
                            for j in ("v4pro", "gemini", "v4flash"):
                                trial_j = r["judges"][j]
                                br["judges"][j] = {**trial_j}  # shallow copy
                        r["branches"].append(br)

                yield r


# ----- Phase 2 -----

def phase2_rows(problems: dict, lk: Lookups):
    base = PHASE2_DIR / "seed_full"
    if not base.exists(): return
    for model_dir in sorted(base.iterdir()):
        if not model_dir.is_dir(): continue
        for trial_path in sorted(model_dir.glob("*.json")):
            pid = trial_path.stem
            t = safe_load(trial_path)
            if t is None:
                r = base_row(problems[pid], pid, "phase2", "seed_full")
                r["error"] = "trial_missing"
                yield r
                continue
            model = t["model"]
            r = base_row(problems[pid], pid, "phase2", "seed_full")
            r["model"]        = model
            r["started_at"]   = t.get("started_at")
            r["completed_at"] = t.get("completed_at")
            r["elapsed_s"]    = t.get("elapsed_s")
            r["cost_usd"]     = t.get("cost_usd")
            r["error"]        = t.get("error")
            r["final_solution"] = t.get("best_solution")
            r["mode_extras"]    = t.get("mode_extras")

            if not t.get("error"):
                r["judges"]["v4pro"]   = lk.phase2_v4pro_trial(model, pid)
                # Phase 2 used gemini as primary judge: its score is the trial.score
                r["judges"]["gemini"]  = {
                    "score":   t.get("score"),
                    "verdict": t.get("best_verdict"),
                    "source":  "phase2_inline",
                }
                r["judges"]["v4flash"] = lk.v4flash(
                    f"phase2/{short(model)}/{pid}__trial.json"
                )

                for b in t.get("branches", []) or []:
                    idx = b.get("idea_idx", 0)
                    br = trim_branch_judges(b, k=None, idea_idx=idx)
                    br["judges"]["gemini"] = {
                        "score":   b.get("score"),
                        "verdict": b.get("verdict"),
                        "source":  "phase2_inline",
                    }
                    br["judges"]["v4pro"]   = lk.phase2_v4pro_branch(model, pid, idx)
                    br["judges"]["v4flash"] = lk.v4flash(
                        f"phase2/{short(model)}/{pid}__idea{idx}.json"
                    )
                    r["branches"].append(br)
            yield r


# ----- Phase 3 -----

def phase3_rows(problems: dict, lk: Lookups):
    base = PHASE3_DIR / "seed_full" / "deepseek-v4-flash"
    if not base.exists(): return
    for trial_path in sorted(base.glob("*.json")):
        pid = trial_path.stem
        t = safe_load(trial_path)
        if t is None:
            r = base_row(problems[pid], pid, "phase3", "seed_full")
            r["error"] = "trial_missing"
            yield r
            continue
        model = t["model"]
        r = base_row(problems[pid], pid, "phase3", "seed_full")
        r["model"]        = model
        r["started_at"]   = t.get("started_at")
        r["completed_at"] = t.get("completed_at")
        r["elapsed_s"]    = t.get("elapsed_s")
        r["cost_usd"]     = t.get("cost_usd")
        r["error"]        = t.get("error")
        r["final_solution"] = t.get("best_solution")
        r["mode_extras"]    = t.get("mode_extras")

        if not t.get("error"):
            r["judges"]["gemini"] = {
                "score":   t.get("score"),
                "verdict": t.get("best_verdict"),
                "source":  "phase3_inline",
            }
            r["judges"]["v4pro"]   = lk.phase3_v4pro_trial(pid)
            r["judges"]["v4flash"] = lk.v4flash(f"phase3/{pid}__trial.json")

            for b in t.get("branches", []) or []:
                idx = b.get("idea_idx", 0)
                br = trim_branch_judges(b, k=None, idea_idx=idx)
                br["judges"]["gemini"] = {
                    "score":   b.get("score"),
                    "verdict": b.get("verdict"),
                    "source":  "phase3_inline",
                }
                # No per-branch v4-pro regrade exists for Phase 3
                br["judges"]["v4flash"] = lk.v4flash(f"phase3/{pid}__idea{idx}.json")
                r["branches"].append(br)
        yield r


# ----- Roleswap -----

def roleswap_rows(problems: dict, lk: Lookups):
    base = ROLESWAP_DIR / "trials"
    if not base.exists(): return
    for cond_dir in sorted(base.iterdir()):
        if not cond_dir.is_dir(): continue
        condition = cond_dir.name
        for trial_path in sorted(cond_dir.glob("*.json")):
            pid = trial_path.stem
            t = safe_load(trial_path)
            if t is None:
                r = base_row(problems[pid], pid, "roleswap", condition)
                r["error"] = "trial_missing"
                yield r
                continue
            roles = t.get("roles") or {}
            primary = roles.get("generator") or ""
            r = base_row(problems[pid], pid, "roleswap", condition)
            r["model"]        = primary
            r["roles"]        = roles                                  # extra field for roleswap
            r["started_at"]   = t.get("started_at")
            r["completed_at"] = t.get("completed_at")
            r["elapsed_s"]    = t.get("elapsed_s")
            r["cost_usd"]     = t.get("cost_usd")
            r["error"]        = t.get("error")
            r["final_solution"] = t.get("best_solution")
            r["mode_extras"]    = t.get("mode_extras")

            if not t.get("error"):
                # gemini was the primary judge
                r["judges"]["gemini"] = {
                    "score":   t.get("score"),
                    "verdict": t.get("best_verdict"),
                    "source":  "roleswap_inline",
                }
                r["judges"]["v4flash"] = lk.v4flash(
                    f"roleswap/{condition}/{pid}__trial.json"
                )

                # Per-branch loop (v4-pro escalation is stored under branch.judge.escalate_*)
                trial_v4pro_max = None
                trial_v4pro_branch_idx = None
                for b in t.get("branches", []) or []:
                    idx = b.get("idea_idx", 0)
                    br = trim_branch_judges(b, k=None, idea_idx=idx)
                    br["judges"]["gemini"] = {
                        "score":   b.get("score"),
                        "verdict": b.get("verdict"),
                        "source":  "roleswap_inline",
                    }
                    judge_b = b.get("judge") or {}
                    # Roleswap stores v4-pro escalation as escalate_judge / escalate_score
                    if (judge_b.get("escalated")
                        and judge_b.get("escalate_score") is not None
                        and "v4-pro" in (judge_b.get("escalate_judge") or "")):
                        es = judge_b["escalate_score"]
                        br["judges"]["v4pro"] = {
                            "score":   es,
                            "verdict": judge_b.get("escalate_verdict"),
                            "source":  "roleswap_v4pro_escalation",
                        }
                        if trial_v4pro_max is None or es > trial_v4pro_max:
                            trial_v4pro_max = es
                            trial_v4pro_branch_idx = idx
                    br["judges"]["v4flash"] = lk.v4flash(
                        f"roleswap/{condition}/{pid}__idea{idx}.json"
                    )
                    r["branches"].append(br)

                # Trial-level v4-pro: use max branch v4-pro escalation (special-10 only).
                # Surface only when at least one branch had escalation.
                if trial_v4pro_max is not None:
                    r["judges"]["v4pro"] = {
                        "score":   trial_v4pro_max,
                        "verdict": (
                            r["branches"][trial_v4pro_branch_idx]["judges"]["v4pro"]["verdict"]
                            if trial_v4pro_branch_idx is not None
                            and trial_v4pro_branch_idx < len(r["branches"]) else None
                        ),
                        "source":  "roleswap_v4pro_escalation_max_branch",
                    }
            yield r


# ----- Scaling -----

def scaling_rows(problems: dict, lk: Lookups):
    base = SCALING_DIR / "trials"
    if not base.exists(): return
    for model_dir in sorted(base.iterdir()):
        if not model_dir.is_dir(): continue
        ms = model_dir.name
        for trial_path in sorted(model_dir.glob("*.json")):
            pid = trial_path.stem
            t = safe_load(trial_path)
            if t is None: continue
            model = t.get("model", "")
            r = base_row(problems[pid], pid, "scaling", "best_of_n")
            r["model"]        = model
            r["started_at"]   = t.get("started_at")
            r["completed_at"] = t.get("completed_at")
            r["elapsed_s"]    = t.get("elapsed_s")
            r["cost_usd"]     = t.get("cost_usd")
            # No trial-level final_solution / judges — best-of-N is computed off branches
            r["mode_extras"] = {"n_existing": t.get("n_existing"), "n_new": t.get("n_new")}

            for b in t.get("branches", []) or []:
                k = b.get("k")
                if k is None: continue
                br = trim_branch_judges(b, k=k, idea_idx=None)
                br["solution"] = b.get("solution")
                # Inline gemini + v4pro scores from the scaling run
                if b.get("gemini_score") is not None:
                    br["judges"]["gemini"] = {
                        "score":   b["gemini_score"],
                        "verdict": b.get("gemini_verdict"),
                        "source":  f"scaling_inline_{b.get('source', 'unknown')}",
                    }
                if b.get("v4pro_score") is not None:
                    br["judges"]["v4pro"] = {
                        "score":   b["v4pro_score"],
                        "verdict": b.get("v4pro_verdict"),
                        "source":  f"scaling_inline_{b.get('source', 'unknown')}",
                    }
                br["judges"]["v4flash"] = lk.v4flash(
                    f"scaling/{ms}/{pid}__k{k}.json"
                )
                r["branches"].append(br)
            yield r


# ----- Phase 1 reasoning re-run (gpt-oss + gemma, 4 modes, judged by v4-flash inline) -----

def phase1_reasoning_rows(problems: dict, lk: Lookups):
    base = PHASE1_REASONING_DIR
    if not base.exists(): return
    for mode in ("generate", "full", "seed_generate", "seed_full"):
        mode_dir = base / mode
        if not mode_dir.exists(): continue
        for model_dir in sorted(mode_dir.iterdir()):
            if not model_dir.is_dir(): continue
            for trial_path in sorted(model_dir.glob("*.json")):
                pid = trial_path.stem
                t = safe_load(trial_path)
                if t is None:
                    r = base_row(problems[pid], pid, "phase1_reasoning", mode)
                    r["error"] = "trial_missing"
                    yield r
                    continue
                model = t.get("model", "")
                r = base_row(problems[pid], pid, "phase1_reasoning", mode)
                r["model"]        = model
                r["started_at"]   = t.get("started_at")
                r["completed_at"] = t.get("completed_at")
                r["elapsed_s"]    = t.get("elapsed_s")
                r["cost_usd"]     = t.get("cost_usd")
                r["error"]        = t.get("error")
                r["final_solution"] = t.get("best_solution")
                r["mode_extras"]    = t.get("mode_extras")

                if not t.get("error"):
                    r["judges"]["v4flash"] = {
                        "score":   t.get("score"),
                        "verdict": t.get("best_verdict"),
                        "source":  "phase1_reasoning_inline",
                    }
                    for b in t.get("branches", []) or []:
                        if mode == "generate":
                            br = trim_branch_judges(b, k=b.get("k", 0), idea_idx=None)
                        elif mode in ("seed_generate", "seed_full"):
                            br = trim_branch_judges(b, k=None, idea_idx=b.get("idea_idx", 0))
                        else:  # full
                            br = trim_branch_judges(b, k=b.get("k", 0), idea_idx=None)
                        br["judges"]["v4flash"] = {
                            "score":   b.get("score"),
                            "verdict": b.get("verdict"),
                            "source":  "phase1_reasoning_inline",
                        }
                        r["branches"].append(br)
                yield r


# ----- Scaling reasoning re-run (gpt-oss + gemma, k=0..8, judged by v4-flash inline) -----

def scaling_reasoning_rows(problems: dict, lk: Lookups):
    base = SCALING_REASONING_DIR / "trials"
    if not base.exists(): return
    for model_dir in sorted(base.iterdir()):
        if not model_dir.is_dir(): continue
        for trial_path in sorted(model_dir.glob("*.json")):
            pid = trial_path.stem
            t = safe_load(trial_path)
            if t is None: continue
            model = t.get("model", "")
            r = base_row(problems[pid], pid, "scaling_reasoning", "best_of_n_reasoning")
            r["model"]        = model
            r["started_at"]   = t.get("started_at")
            r["completed_at"] = t.get("completed_at")
            r["elapsed_s"]    = t.get("elapsed_s")
            r["cost_usd"]     = t.get("cost_usd")
            r["mode_extras"]  = {"n_existing": t.get("n_existing"), "n_new": t.get("n_new"),
                                  "reasoning": "high"}

            for b in t.get("branches", []) or []:
                k = b.get("k")
                if k is None: continue
                br = trim_branch_judges(b, k=k, idea_idx=None)
                br["solution"] = b.get("solution")
                if b.get("v4flash_score") is not None:
                    br["judges"]["v4flash"] = {
                        "score":   b["v4flash_score"],
                        "verdict": b.get("v4flash_verdict"),
                        "source":  "scaling_reasoning_inline",
                    }
                r["branches"].append(br)
            yield r


# ----- Scaling on v4-flash (70-problem, k=0..6, judged by v4-flash inline) -----

def scaling_v4flash_rows(problems: dict, lk: Lookups):
    base = SCALING_V4FLASH_DIR
    if not base.exists(): return
    # Files are flat: <pid>__k{k}.json. Group by problem_id.
    by_pid: dict[str, list[tuple[int, dict]]] = {}
    for f in sorted(base.glob("*__k*.json")):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        m = re.match(r"(.+)__k(\d+)$", f.stem)
        if not m: continue
        pid = m.group(1)
        k = int(m.group(2))
        by_pid.setdefault(pid, []).append((k, d))

    for pid, branches_raw in sorted(by_pid.items()):
        if pid not in problems: continue
        # All branches use the same model (deepseek-v4-flash) per the writeup
        model = branches_raw[0][1].get("model", "openrouter/deepseek/deepseek-v4-flash")
        r = base_row(problems[pid], pid, "scaling_v4flash", "best_of_n_v4flash")
        r["model"] = model
        r["mode_extras"] = {"reused_phase1_k": [k for k, b in branches_raw if b.get("reused")]}

        for k, b in sorted(branches_raw):
            br = trim_branch_judges(b, k=k, idea_idx=None)
            br["solution"] = b.get("solution")
            if b.get("score") is not None:
                br["judges"]["v4flash"] = {
                    "score":   b["score"],
                    "verdict": b.get("verdict"),
                    "source":  "scaling_v4flash_inline",
                }
            r["branches"].append(br)
        yield r


# ----- gpt-5.4-nano pass@3 with reasoning xhigh (judged by v4-flash inline) -----

def gpt5_nano_pass3_rows(problems: dict, lk: Lookups):
    base = GPT5_NANO_PASS3_DIR
    if not base.exists(): return
    by_pid: dict[str, list[tuple[int, dict]]] = {}
    for f in sorted(base.glob("*__k*.json")):
        try: d = json.load(open(f))
        except Exception: continue
        m = re.match(r"(.+)__k(\d+)$", f.stem)
        if not m: continue
        pid = m.group(1)
        k = int(m.group(2))
        by_pid.setdefault(pid, []).append((k, d))

    for pid, branches_raw in sorted(by_pid.items()):
        if pid not in problems: continue
        model = branches_raw[0][1].get("model", "openrouter/openai/gpt-5.4-nano")
        r = base_row(problems[pid], pid, "gpt5_nano_pass3", "pass3_xhigh")
        r["model"] = model
        r["mode_extras"] = {"reasoning_effort": "xhigh"}

        for k, b in sorted(branches_raw):
            br = trim_branch_judges(b, k=k, idea_idx=None)
            br["solution"] = b.get("solution")
            if b.get("score") is not None:
                br["judges"]["v4flash"] = {
                    "score":   b["score"],
                    "verdict": b.get("verdict"),
                    "source":  "gpt5_nano_pass3_inline",
                }
            r["branches"].append(br)
        yield r


# ----- Role-swap reasoning re-run (8 conditions × 70 problems, gpt-oss × gemma with reasoning ON, v4-flash inline) -----

def roleswap_reasoning_rows(problems: dict, lk: Lookups):
    base = ROLESWAP_REASONING_DIR / "trials"
    if not base.exists(): return
    for cond_dir in sorted(base.iterdir()):
        if not cond_dir.is_dir(): continue
        condition = cond_dir.name
        for trial_path in sorted(cond_dir.glob("*.json")):
            pid = trial_path.stem
            t = safe_load(trial_path)
            if t is None or pid not in problems: continue
            roles = t.get("roles") or {}
            primary = roles.get("generator") or ""
            r = base_row(problems[pid], pid, "roleswap_reasoning", condition)
            r["model"]        = primary
            r["roles"]        = roles
            r["started_at"]   = t.get("started_at")
            r["completed_at"] = t.get("completed_at")
            r["elapsed_s"]    = t.get("elapsed_s")
            r["cost_usd"]     = t.get("cost_usd")
            r["error"]        = t.get("error")
            r["final_solution"] = t.get("best_solution")
            r["mode_extras"]    = t.get("mode_extras")

            if not t.get("error"):
                r["judges"]["v4flash"] = {
                    "score":   t.get("score"),
                    "verdict": t.get("best_verdict"),
                    "source":  "roleswap_reasoning_inline",
                }
                for b in t.get("branches", []) or []:
                    idx = b.get("idea_idx", 0)
                    br = trim_branch_judges(b, k=None, idea_idx=idx)
                    if b.get("score") is not None:
                        br["judges"]["v4flash"] = {
                            "score":   b["score"],
                            "verdict": b.get("verdict"),
                            "source":  "roleswap_reasoning_inline",
                        }
                    r["branches"].append(br)
            yield r


# ----- Flex cross-ideator (self vs v4-pro ideator → v4-flash, judged by v4-flash inline) -----

def flex_cross_ideator_rows(problems: dict, lk: Lookups):
    base = FLEX_CROSS_IDEATOR_DIR / "trials"
    if not base.exists(): return
    for cond_dir in sorted(base.iterdir()):
        if not cond_dir.is_dir(): continue
        condition = cond_dir.name
        for trial_path in sorted(cond_dir.glob("*.json")):
            pid = trial_path.stem
            t = safe_load(trial_path)
            if t is None or pid not in problems: continue
            r = base_row(problems[pid], pid, "flex_cross_ideator", condition)
            r["model"]        = "openrouter/deepseek/deepseek-v4-flash"  # the generator
            r["started_at"]   = t.get("started_at")
            r["completed_at"] = t.get("completed_at")
            r["elapsed_s"]    = t.get("elapsed_s")
            r["cost_usd"]     = t.get("cost_usd")
            r["error"]        = t.get("error")
            r["final_solution"] = t.get("best_solution")
            r["mode_extras"]    = t.get("mode_extras")

            if not t.get("error"):
                r["judges"]["v4flash"] = {
                    "score":   t.get("score"),
                    "verdict": t.get("best_verdict"),
                    "source":  "flex_cross_ideator_inline",
                }
                for b in t.get("branches", []) or []:
                    idx = b.get("idea_idx", 0)
                    br = trim_branch_judges(b, k=None, idea_idx=idx)
                    if b.get("score") is not None:
                        br["judges"]["v4flash"] = {
                            "score":   b["score"],
                            "verdict": b.get("verdict"),
                            "source":  "flex_cross_ideator_inline",
                        }
                    r["branches"].append(br)
            yield r


# ----- Flex strong-critic (v4-flash gen + v4-pro V↔R, no branches, judged by v4-flash inline) -----

def flex_strong_critic_rows(problems: dict, lk: Lookups):
    base = FLEX_STRONG_CRITIC_DIR / "trials"
    if not base.exists(): return
    for cond_dir in sorted(base.iterdir()):
        if not cond_dir.is_dir(): continue
        condition = cond_dir.name
        for trial_path in sorted(cond_dir.glob("*.json")):
            pid = trial_path.stem
            t = safe_load(trial_path)
            if t is None or pid not in problems: continue
            r = base_row(problems[pid], pid, "flex_strong_critic", condition)
            r["model"]        = t.get("generator_model", "openrouter/deepseek/deepseek-v4-flash")
            r["started_at"]   = t.get("started_at")
            r["elapsed_s"]    = t.get("elapsed_s")
            r["cost_usd"]     = t.get("cost_usd")
            r["error"]        = t.get("error")
            r["final_solution"] = t.get("final_solution")
            r["mode_extras"]    = {
                "generator_model": t.get("generator_model"),
                "critic_model":    t.get("critic_model"),
                "loop_log":        t.get("loop_log"),
                "stopped_early":   t.get("stopped_early"),
            }
            if not t.get("error") and t.get("score") is not None:
                r["judges"]["v4flash"] = {
                    "score":   t["score"],
                    "verdict": t.get("verdict"),
                    "source":  "flex_strong_critic_inline",
                }
            yield r


# ----- Flex passN (best-of-N up to k=7, v4-flash inline) -----

def flex_passn_rows(problems: dict, lk: Lookups):
    base = FLEX_PASSN_DIR / "samples"
    if not base.exists(): return
    for pid_dir in sorted(base.iterdir()):
        if not pid_dir.is_dir(): continue
        pid = pid_dir.name
        if pid not in problems: continue
        # Each k file is one branch
        branches_raw: list[tuple[int, dict]] = []
        for kf in sorted(pid_dir.glob("k*.json")):
            try: d = json.load(open(kf))
            except Exception: continue
            k = d.get("k", int(kf.stem.replace("k","")))
            branches_raw.append((k, d))
        if not branches_raw: continue
        r = base_row(problems[pid], pid, "flex_passn", "best_of_n_v4flash_20")
        r["model"] = "openrouter/deepseek/deepseek-v4-flash"
        r["mode_extras"] = {"max_k": max(k for k,_ in branches_raw)}
        for k, b in sorted(branches_raw):
            br = trim_branch_judges(b, k=k, idea_idx=None)
            br["solution"] = b.get("solution")
            if b.get("score") is not None:
                br["judges"]["v4flash"] = {
                    "score":   b["score"],
                    "verdict": b.get("verdict"),
                    "source":  "flex_passn_inline",
                }
            r["branches"].append(br)
        yield r


# ----- Flex composed-critic (pass@8 best → v4-pro V↔R) -----

def flex_composed_rows(problems: dict, lk: Lookups):
    base = FLEX_COMPOSED_DIR / "trials"
    if not base.exists(): return
    for trial_path in sorted(base.glob("*.json")):
        pid = trial_path.stem
        t = safe_load(trial_path)
        if t is None or pid not in problems: continue
        r = base_row(problems[pid], pid, "flex_composed_critic", "pass8_then_vp_critic")
        r["model"]        = "openrouter/deepseek/deepseek-v4-flash"  # the generator
        r["started_at"]   = t.get("started_at") if "started_at" in t else None
        r["completed_at"] = t.get("completed_at")
        r["elapsed_s"]    = t.get("elapsed_s")
        r["cost_usd"]     = t.get("cost_usd")
        r["error"]        = t.get("error")
        r["final_solution"] = t.get("final_solution")
        r["mode_extras"]    = {
            "starter_k":         t.get("starter_k"),
            "starter_score":     t.get("starter_score"),
            "post_critic_score": t.get("post_critic_score"),
            "starter_solution":  t.get("starter_solution"),
            "delta":             t.get("delta"),
            "loop_log":          t.get("loop_log"),
            "stopped_early":     t.get("stopped_early"),
        }
        # The trial-level v4flash score here is the post-critic score
        post = t.get("post_critic_score")
        if post is not None:
            r["judges"]["v4flash"] = {
                "score":   post,
                "verdict": t.get("verdict"),
                "source":  "flex_composed_critic_inline_post",
            }
        yield r


# ============================================================================
# Main
# ============================================================================

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    problems = load_70_problems()
    lk = Lookups()

    counts: dict[str, int] = {}
    judge_counts: dict[str, dict[str, int]] = {}

    builders = [
        ("phase1",            phase1_rows),
        ("phase2",            phase2_rows),
        ("phase3",            phase3_rows),
        ("roleswap",          roleswap_rows),
        ("scaling",           scaling_rows),
        ("phase1_reasoning",     phase1_reasoning_rows),
        ("scaling_reasoning",    scaling_reasoning_rows),
        ("scaling_v4flash",      scaling_v4flash_rows),
        ("gpt5_nano_pass3",      gpt5_nano_pass3_rows),
        ("roleswap_reasoning",   roleswap_reasoning_rows),
        ("flex_cross_ideator",   flex_cross_ideator_rows),
        ("flex_strong_critic",   flex_strong_critic_rows),
        ("flex_passn",           flex_passn_rows),
        ("flex_composed_critic", flex_composed_rows),
    ]

    n_total = 0
    with open(OUT, "w", encoding="utf-8") as f:
        for name, fn in builders:
            n_exp = 0
            jc = {"v4pro": 0, "gemini": 0, "v4flash": 0}
            jbc = {"v4pro": 0, "gemini": 0, "v4flash": 0}
            for row in fn(problems, lk):
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                n_exp += 1
                for j in ("v4pro", "gemini", "v4flash"):
                    if row["judges"][j]["score"] is not None:
                        jc[j] += 1
                    for b in row.get("branches", []) or []:
                        if b["judges"][j]["score"] is not None:
                            jbc[j] += 1
            counts[name] = n_exp
            judge_counts[name] = {"trial": jc, "branch": jbc}
            print(f"  {name:<10} -> {n_exp} rows  trial-judges {jc}  branch-judges {jbc}")
            n_total += n_exp

    size_mb = OUT.stat().st_size / 1024 / 1024
    print(f"\nWrote {n_total} rows -> {OUT}  ({size_mb:.1f} MB)")
    print(f"Counts by experiment: {counts}")


if __name__ == "__main__":
    main()
