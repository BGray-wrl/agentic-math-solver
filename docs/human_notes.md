

## Things I want to test:
- best of n generation & prioritization
- alpha-evolve style iteration on problems
> AlphaEvolve’s core claim is that in domains where you can write a cheap evaluator, an LLM can function as a mutation operator in an evolutionary loop that reliably improves candidates over time—often outperforming one-shot reasoning because feedback is grounded in executable tests
- Try 'warm-up' problems in context to activate the 'relevant template'
    - "Teach the system the envariant structure on an easier instance; then lift" gpt deep research
- Generate seed ideas, solve conditioned on each idea, iterate up to three times through verify--> revise loops (OAI firstproof v1, check doc & details)
- develop explicit falsifiable rules
- Mixing and matching model families
- Decomposition into sub-tasks
- Adversarial self-correction (not just verifier)
- Try "Plan Mode"
- Try 'cross-pollination of ideas
- Try 'adversarial framings' including one requiring a competition-style formulation
- Try different frontier models using the same approach (when all converge --> strong signal of correctness)
- Early stopping for messy proofs *Solution sketching in natural language before any formalism. Force the generator to first produce a 2-3 sentence informal argument for why the result should be true, before attempting any formal reasoning. Rate these sketches for plausibility*
- Instruct against specifically Halucinations
- Find closest solved problem and start there
- Numbered exploration with mandatory journaling (and/or extract patterns from heuristic solutions if applicable) (from Claude's Cycles)

### Verification
- 'Graduated Verification' is just esclation ladder try llm then symbolic/python then lean on the hardest step then full lean (for when hitting aristotle for formalization)
- Counterexample hunting where appropriate
- 'Symbolic sanity checks' just try a bunch of cheap tests on lemmas

