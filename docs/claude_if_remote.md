## Instance & API
- **OpenRouter API key**: loaded from `.env` as `OPENROUTER_API_KEY` — use for inference
IF REMOTE INSTANCE CONNECTED (TODO update/confirm instance details)
- **GPU**: UPDATE (e.g A100 SXM4, 80GB VRAM, CUDA 13.0)
- **CPU**: UPDATE (e.g. Xeon Platinum 8470, 26 allocated cores, 128.9GB RAM)
- **Disk**: UPDATE (e.g. 45.6GB container storage — monitor with `df -h`, clean up large checkpoints when no longer needed)


## Teacher Templates (OLD)
### Model Template
`teacher_template.py` — Load HuggingFace model and extract logits

Default script loads the new `Qwen/Qwen3.5-2B` model (VLM, `AutoModelForImageTextToText`) and runs MNIST images through it to extract **raw digit logits** (not softmaxed) for distillation.

```bash
uv run python teacher_template.py --n 500   # subset
uv run python teacher_template.py            # full 60k train set
uv run python teacher_template.py --hidden   # also save last hidden states
```

Outputs to `checkpoints/teacher/`:
- `teacher_logits.npy` — shape `(N, 10)`, raw logits over digit tokens `'0'`–`'9'`
- `true_labels.npy`    — shape `(N,)`, ground truth
- `hidden_states.npy`  — shape `(N, hidden_dim)` if `--hidden` flag used

Key design: uses **native image** (PIL → VLM vision encoder), not ASCII text. Native image achieves ~95% top-1 vs ~13% for all text representations. Digit logits extracted from first-token generation scores at positions corresponding to token IDs for `'0'`–`'9'`.

**Known bug**: `get_hidden_states()` applies softmax before saving (returns probabilities), while `get_soft_label()` correctly returns raw logits. If using `--hidden`, the saved `teacher_logits.npy` will contain probabilities, not raw logits — this breaks the distillation loss which expects raw logits. Fix `get_hidden_states()` to return raw logits, or only use the default (non-`--hidden`) path.

**Status**: Teacher logits have not been generated yet — `checkpoints/teacher/` is empty. Run `teacher_template.py` first before distillation.