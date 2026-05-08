# Candidate Figure Gallery

These are exploratory, NeurIPS-style candidate visuals generated from the local result buckets.
They are intended as a menu; pick a small handful rather than including all of them.

- `candidate_01_judge_flip_deltas.png`: Heatmap of G-V-R minus pass@3 by model and judge; highlights the judge-dependent sign flip.
- `candidate_02_pass_confusion_matrices.png`: Pass/fail confusion matrices for strict judges versus Gemini; shows one-sided Gemini lenience.
- `candidate_03_phase1_score_distributions.png`: Phase 1 score distributions by architecture under the canonical judge; visual support for near-null architecture effects.
- `candidate_04_sampling_frontier_vs_seed_full.png`: Pass@k mean-score frontier with seed_full stars at k=9 equivalent; direct baseline comparison.
- `candidate_05_marginal_passn_gains.png`: Incremental pass-rate gains from k=1->3, 3->5, and 5->7; shows scaling still has slope.
- `candidate_06_answerbench_cost_accuracy_pareto.png`: AnswerBench capability versus cost, including the small expensive-model calibration bucket.
- `candidate_07_judge_calibration_pareto.png`: GradingBench judge agreement versus cost; supports the canonical judge choice.
- `candidate_08_role_swap_top_cells.png`: Top role-swap cells at reasoning=max; compact view of model-role variation.
- `candidate_09_research_problem_judge_gap.png`: Research-problem pass counts by judge; localizes where lenient judging changes the story.
- `candidate_10_difficulty_mode_heatmap.png`: Mean score by difficulty and architecture; compact visual of the difficulty gradient.

Regenerate with `.venv/bin/python codex_draft_and_work/plots/make_candidate_gallery.py` from the repository root.
A thumbnail overview is available as `contact_sheet.png`.
