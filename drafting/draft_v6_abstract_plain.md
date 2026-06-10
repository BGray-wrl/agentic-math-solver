# Abstract (plain-language version)

AI models can now write mathematical proofs, and a number of recent papers propose elaborate ways to organize multiple model calls into "pipelines" — for instance, one model writes a proof, a second critiques it, a third revises. These pipelines cost more (more model calls means more compute), and their authors report that they work better than running a model once. We tested whether the gains hold up when you compare fairly: against the obvious baseline of running the model the *same number of times* and picking the best output.

On 70 problems (60 competition-style, 10 hard 2026 research problems — several of which were only first solved this year, often with AI assistance), four findings:

1. **The write/critique/revise pipeline does not beat the obvious baseline** of running the model three times. On one cheap model with heavy reasoning, it actively hurts.
2. **A larger pipeline does beat three runs on cheap models with reasoning turned on** — the most striking architecture lift we saw. But at its fair baseline of nine runs (since it uses nine model calls), the gain disappears. Sampling more is a stronger baseline than scaffolding harder.
3. **Which automated grader you use changes the answer.** A lenient grader calls "correct" on roughly a third of the cases strict graders call "wrong," flipping conclusions about which pipeline wins on cheap models.
4. **Solve rates fall off sharply with difficulty:** 86% on warmup problems, near zero on research-frontier ones.

Practical recommendation, within the cost regime we tested: spend extra compute on more samples before adding pipeline depth, keep the model's reasoning mode on where available, and check results against two graders before believing them.
