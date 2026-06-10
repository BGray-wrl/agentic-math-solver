

## Things I want to test:
- alpha-evolve style iteration on problems
> AlphaEvolve’s core claim is that in domains where you can write a cheap evaluator, an LLM can function as a mutation operator in an evolutionary loop that reliably improves candidates over time—often outperforming one-shot reasoning because feedback is grounded in executable tests
- develop explicit falsifiable rules
- Mixing and matching model families
- Adversarial self-correction (not just verifier)
- Try "Plan Mode"
- Try 'cross-pollination of ideas
- Instruct against specifically Halucinations
- Find closest solved problem and start there
- Numbered exploration with mandatory journaling (and/or extract patterns from heuristic solutions if applicable) (from Claude's Cycles)
- >After your generator produces any computational solution (even via heuristic search for small cases), route it through a dedicated analysis pass that asks: "What pattern do you see in these solutions? What do the successful cases have in common? Can you express the regularity as a general construction?" This is different from verification — it's pattern induction, and it sits between generation and formalization.


### Generation
- Some sort of 'if approach class N fails after K attempts, escalate to class N+1.'
- best of n generation & prioritization
- Generate seed ideas, solve conditioned on each idea, iterate up to three times through verify--> revise loops (OAI firstproof v1, check doc & details)
- Decomposition into sub-tasks
- Try different frontier models using the same approach (when all converge --> strong signal of correctness)
- Try 'warm-up' problems in context to activate the 'relevant template'
    - "Teach the system the envariant structure on an easier instance; then lift" gpt deep research
- systematic context de-identification (don't frame as open problem)
- Early stopping for messy proofs *Solution sketching in natural language before any formalism. Force the generator to first produce a 2-3 sentence informal argument for why the result should be true, before attempting any formal reasoning. Rate these sketches for plausibility*


### Revision
- Try 'adversarial framings' including one requiring a competition-style formulation


### Verification
- 'Graduated Verification' is just esclation ladder try llm then symbolic/python then lean on the hardest step then full lean (for when hitting aristotle for formalization)
- Counterexample hunting where appropriate; adversarial self-correction as the verification step
- 'Symbolic sanity checks' just try a bunch of cheap tests on lemmas

## Other:
- Epoch AI has a fairly clever idea: a default 'solve' prompt --> 'you have XXX/YYY tokens remaining' in a loop as long as there's space to keep reasoning --> 'reflection prompt to extract method and other important context'. It worked on one of the 'openquestions' (Ramsey Problems)
- OAI had a pretty simple 'seed ideas' setup, 
>The framework is simple:
>• Generate a small number of seed ideas.
>• Prompt the model to solve the given problem using each of the seed ideas.
>• Repeat up to 3 times:
>   – Verify (i) correctness of the proof and (ii) validity of any cited material and bibliographic references.
>   – If gaps are found, prompt the model to revise the drafted solution.
>• If the verifications pass, typeset the resulting solution.


## To Actually Set Up
- Epoch's method (see epoch prompts)
- OAI's method (see OAI prompts)
- Mix different models (e.g. randomize deepseek vs nemotron for each generation/revision stage in the pipeline)
- Seed different starting ideas and carry on from there
- Try generating with a 'proof sketch' or 'core intuition' first
- Try forcing decomposition, then telling the model to solve each piece step-by-step



## Things AI forgets or gets wrong when it vibe codes llm pipelines
- Basic retries
- max token numbers (for heavy reasoning math requests)
- Plain prompts 


## Full set:
- 60 IMO-proofbench problems
- Erdos 397, 333, 654, 659, 1051
- Ramsey Hypergraphs
- FP 10, 5, 6

---
# Final Polished EXPs to run

## Primary
1. Seed Ideas Generate-Only + Full 4-Way Comparison - 2026-03-28T02:37:00
Big one. Compare generate vs generate pipeline, vs generate seed vs generate seed pipeline. Should offer clear & powerful results
| Model | Generate | Full Pipeline | Seed+Generate | Seed+Full |


2. Model Diversity Experiment - 2026-03-28T11:28:00
Model Diversity Experiment: try same-power models and different-power models in the generator-verifier loop


3. Try Best-of-N Experiment - 2026-04-05T12:06:00
Combine into 1?



## Secondary

4. Ideator Capability Scaling - 2026-03-30T18:43:00
try OAI/Gemini/DS families 

5. Pruning Ideation Experiment - 2026-04-05T12:04:00
Can we predict best ideator? Preliminary results say not
Try it with different models









