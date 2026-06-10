# Draft

ICML 2026 AI4Math workshop paper, "Cost-Effective Automated Judging of Natural-Language Mathematical Proofs."

Source lives in `icml2026_format/`:
- `working_draft.tex` — submitted (anonymized) version
- `arxiv_preprint.tex` — de-anonymized arXiv version (`[preprint]` mode)
- `working_draft.bib` — shared bibliography

## Compile

From `icml2026_format/`:

```bash
# full build (run when citations/references change)
pdflatex working_draft && bibtex working_draft && pdflatex working_draft && pdflatex working_draft

# small text edits only (no citation changes)
pdflatex working_draft && pdflatex working_draft
```

Swap `working_draft` for `arxiv_preprint` to build the arXiv version. Add `-interaction=nonstopmode` to avoid halting on the first error.
