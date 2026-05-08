**Abstract**

* **\[Placeholder \- Update only at later pass\].** \[We empirically study natural-language mathematical proof generation in large language models. Across a dataset of competition-grade and research-grade problems we systematically compare inference-time methods, including best-of-n generation, seeded ideation, verification, and self-revision across multi-stage pipelines. We examine how generation and evaluation methodology, including judge selection, affect accuracy under cost constraints. Our findings aim to clarify which techniques are more and less useful for AI-assisted mathematical reasoning.\]  
* Main findings \[TODO IMPORTANT This is very important but currently still just a guess.  Update at later Pass\]: Pass@k is the correct baseline, and it is important to compare like-to-like in tokens/cost. Calibrated judging is very important. And \[some general batched notes on architecture design; maybe about strong verifiers\] 

**Introduction**

* \[**Placeholder \-** draw from previous literature review work, maybe with a few additions. Update at a later pass, only with further context.\]

**Background**

* **Model Capability & Saturation**  
  * Very briefly review how models have gotten better and better at math, from saturating GSM8 and Math 500 and AIMIE \[TODO check/improve references\] through to winning gold at IMO, through to genuinely novel and impactful solutions. Three prominent examples of which are:  
    * Donald Knuth's claude’s cycles from Anthropic and   
    * DeepMind's \[TODO pick key problem from Aletheia or AlphaEvolve\]  
    * the very recent impactful finding \[TODO finalize, maybe Erdős 1196 from OpenAI\]  
* **Benchmarks & Problems**  
  * **Erdos problems database.** Short overview of Erdős problems as a kind of frontier math tier five community sandbox to toy with models. Big caveats about actual model novelty though \[todo Tao quote about breakthrough\]  
  * **First Proof Challenge**. Note about the open first proof challenge: The team issued a general challenge about AI's capability in math. They selected 10 hidden research problems from their own work that had never before been released, opened them to community submissions, and eventually released personal results, including correct answers, after receiving submissions.  
  * **Epoch’s Frontier Math Open Problems.** A List of truly meaningful and unsolved open problems in mathematics for AI to eventually progress on once it saturates all established math benchmarks.  
  * **IMO-Bench.** Excellent split between easily verifiable answers, IMO level proofs, and graded judges.  
  * **Problem Difficulty**  
    * E.g. ProofBench ranges from ‘pre-IMO’ to ‘IMO-hard’  
    * Consider Epoch, DeepMind grading schemas. They look similar; some type of trivial finding, reproduction, somehow meaningful results, genuinely impactful result and a breakthrough (we've never seen a breakthrough) \[TODO check against sources\]  
* **Relevant Architectures**  
  * **pass@x.** Simply trying a problem over and over again can improve results.  
    * TODO: Find Citation.  
  * **Generator-verifier-revisor loop**. This is the architecture that Huang and Yang and Aletheia used to elicit powerful IMO solutions, Leading to x out of ten claimed successes on the first proof set.   
    * TODO: Cytolethia and IMO Gold Paper  
  * **Seeded Ideation**. This is the method OpenAI used to lead them to claim X out of 10 successes on the first proof set.  
    * TODO site OAI paper  
* **Scope note:**  
  * There are many other relevant architectures and techniques here, including the hill-climbing approach detailed in Alpha Evolve and the formal verification accomplished by Aristotle. We believe these are powerful and important techniques, but they are outside the scope of this paper. We focus on natural language proof generation. This is because natural language proofs are the only universally applicable solution method.   
    * Many problems do not lend themselves to the kind of iterative refinement technique demonstrated in Alpha Evolve,   
    * and Lean’s MathLib library is currently constrained to a subset of proof domains. (Reference Erdős problems that have not been formally verified).  
* \[NOTE: You may need to shuffle some things between here and the introduction; use judgment to do it as appropriate. Note you'll be pulling nearly all of it from my prior written lit review.\]

**Methodology & Architecture**

* **Main 4-architecture Cross Comparison**  
  * **Essentials:** Generation & judge.  
    * We use a hardened judge prompt lightly adapted from the one DeepMind released as their auto-proof grader.  
    * We also lightly adapt the generator from \[todo check generator source\].  
    * \[TODO add anything else essential\]  
  * **Pass@k**  
    * We use the standard pass@K methodology for solving problems.  
    * \[TODO: check against code architecture. Though there isn’t too much here.  
  * **Pipeline Architecture**  
    * We emulated DeepMind’s published architecture for the Aletheia agent, including a generator-verifier-revisor setup with different system prompts.  
    * This is similar to \[IMO Gold people\].  
    * \[TODO detail against code\]  
  * **Ideator**  
    * We used OpenAI’s method for the First Proof challenge submission, down to the prompts provided   
    * \[TODO detail against code\]  
  * **Pipeline x ideator**  
    * We use both the ideator and the pipeline, seeding three ideas and running each through a 3-step verification loop.   
    * We hypothesized that this will be the most successful of the four.  
    * We do note that this triples the consumed tokens, meaning that pass@6 is the correct comparison here. We evaluate scaling pass@k progression up to pass@7 and, in some cases, pass@9 on a subset of models (Gemma 4, gpt-oss, DeepSeek V4 Flash).  
    * \[TODO detail against code\]  
* **Establishing Eval Set: IMO ProofBench \+ Research 2026**  
  * We augmented DeepMind’s IMO-Proofbench with 10 frontier-level problems from recent math challenges & discoveries.  
    * Note we do *not* claim novelty here. We are using DeepMind's IMO proof bench and slightly augmenting it with 10 research questions-and-answers that other researchers (primarily from DeepMind) have released. We name the dataset primarily for notation convenience.  
    * Erdős Problems: 333, 397, 654, 659, 1051  
    * FirstProof: 4, 5, 6, 10\.  
    * FrontierMath OpenProblems: ramsey-hypergraphs (the only one that’s been solved by any AI model).  
  * **Name & Notation Details:** We call it IMO-ProofBench-Plus-R26. Some naming schema details throughout the paper/for personal reference:  
    * *IMO-ProofBench, ProofBench, or PB refers to the 60 problems*  
      * *ProofBench-Advanced, or PB-Advanced, for the 30 more difficult PB problems*  
      * *ProofBench-Basic, or PB-Basic, for the 30 less difficult PB problems*  
    * *Research-2026 or R26 for just the 10 frontier problems*  
    * *IMO-ProofBench-Plus-R26, ProofBench+R26, PB+R26 for all 70*  
  * **Augmentation Justification:**  
    * We chose to add these problems Because:  
      * A. It's important to evaluate models right up to the cusp of what they're capable of.  
      * B. We know that these are problems that models are capable of solving because they were first solved by models, giving us an excellent test bed for us to test model uplift for problems that are in the general capability space of AI writ large.  
      * C. all ten were solved only in 2026, providing either some or absolute protection against data leakage, considering that the solutions were absolutely unknown until this year.  
        * Note some models were released after Public solution release. We think it is less likely for these problems to be in the training set of said solutions Because they would have to have been added in the final stage of training, which is likely when they're doing RL, we don't see evidence that they were all in the training set and because empirically these problems were extremely difficult and solutions were rare.  
      * D. These additional problems give us a new range of difficulty and domain space.  
    * *Selection.* We selected problems partly based on breadth of difficulty, partly breadth of category, partly personal familiarity with the problem, and partly preliminary findings. For example, we wanted one first proof problem of difficulty ‘research-easy’ and we found that Q9 would occasionally trigger safety flags due to perceived similarity with certain offensive cryptography techniques.  
  * **Difficulty Grading for Research-26.** We grade each problem on a relative difficulty metric for cross-difficulty analysis.  
    * NOTE: state whether basic/advanced are different here.  
    * We manually sorted the first proof problems on a 1-4 difficulty  
      * 1 was for 9 and 10, because they themselves reported that GPT-5.2 Pro could solve these. research-easy  
      * 2 were problems that multiple Frontier submissions claimed to have solved. research-medium  
      * 3 were problems that at least one major submission claimed to have solved. research-hard  
      * 4 was for problems that no team claimed to have solved.  
    * We used DeepMind’s superhuman team’s difficulty ratings for the Erdos problems, and Epoch’s rating for the Ramsey hypergraphs problem (Which is graded similarly to deepmind’s)  
    * Altogether:  
      * Problem	Difficulty	Provenance note  
      * Erdős 397	comp-hard	AI alongside competition literature (from chinese math comp)  
      * Erdős 333	research-easy	AI alongside prior literature  
      * Erdős 654	research-easy	AI standalone, one formulation  
      * Erdős 659	research-easy	AI alongside prior literature / independent solution  
      * FirstProof 10	research-easy	known-private-solution challenge  
      * Erdős 1051	research-medium	AI standalone, full Lean solution  
      * FirstProof 5	research-medium	known-private-solution challenge  
      * FirstProof 4	research-hard	solved only in less-clean frontier/internal setting  
      * FirstProof 6	research-hard	solved only in less-clean frontier/internal setting  
      * Ramsey Hypergraphs	research-frontier	AI-assisted open-problem solution, publishable

**Setup/Staging Results**

* **Judge Calibration.** DeepSeek v4 Flash is an impressive and cheap judge.  
  * We calibrated it on GradingBench extensively.  
  * \[Short table/plot of the gradingbench results cross model\].   
  * \[Plot of key cost/accuracy/relevant metric tradeoff\]  
  * \[TODO Maybe on final pass: comprehensive analysis for appendix\]  
  * ~~We also found that a consensus vote of DeepSeek v4 flash, gemma 4, and gpt-oss was a shockingly strong judge, competitive with the true frontier.~~  
    * ~~\[TODO Maybe cut this and save for a different paper\]~~  
  * DeepSeek v4 results are strong, and on the Pareto frontier for our use case. *We used DeepSeek V4 Flash as our default judge.*  
    * Across accuracy, speed, and latency; across f1, precision, recall  
  * In some cases we also used   
    * Gemini 3 Flash no reasoning (for speed \+ cost \+ recall),   
    * DeepSeek v4 Pro (for extra accuracy),   
    * gpt 5.4 nano (for precision, DS self-judge; note this one is expensive)  
    * As augmentation/extra check judges.   
  * \[NOTE: see results/gradingbench\_calibration\]  
  * \[TODO: review all of this; highlight key items\]  
* **Math Capability Calibration**  
  * Deep Seek v4 Pro, ds v4 Flash, gemma 4 31b, oss 120b are all very strong here (for pricepoint)  
  * Qwen 3.6 Plus? & gpt 5.4 nano (xhigh) & gemini 3 flash also evaluated  
  * \[TODO short table\]  
  * Identify the models we picked for the big sweep.  
  * Identify the models we picked for the small sweep.  
  * Identify the models we dropped.  
  * Note that this is a very simple eval test, but that AnswerBench has clearly stated and verifiable answers. We still used LLM as a judge, but in this case, LLM's judgment is matching whether ‘4’ or ‘the null set’ was provided as the proper output answer. We trust the LLM judge here.  
  * \[NOTE: see results/answerbench\_calibration\]  
  * \[TODO: review all of this; highlight key items\]

**Main Results**

* **\[GENERAL NOTE & TODO:** this is, at best, currently a rough guess. It will take some serious analysis to finish it. You should NOT assume something here is correct unless you’ve checked it yourself; be adversarial. The north star of the project is to be as accurate and valuable as possible.\]   
* \[NOTE: see results/architecture for everything here\]  
* \[NOTE: if something new and major comes up in this updated analysis, you are welcome to add it. Use best judgement about what counts as ‘main.’\]

* **Simple Scaling is difficult to beat.** Generator-verifier loop and seeded ideation do not meaningfully improve over pass@3.  
  * This may be especially true for small/weak models \[or for strong models? Check \+ more analysis TODO\]  
  * Comparing like-to-like requires pass@3 and pass@9  
  * Table comparing pass@3 uplift to pass@1 and comparing seeded ideation and pipeline to pass@1  
  * Other: Gemini as a judge likes the pipeline and tended to grade post-pipeline higher; DeepSeek (more reliable judge) did not. See Judge choice in Secondary.  
    * When we swapped we saw a dramatic reduction in improvement.  
  * \[TODO: make sure this remains true from final collected dataset\]

* **PLACEHOLDER analysis/result when accounting for problem difficulty**  
  * Publish findings from when I evaluate results & accuracy accounting for problem difficulty.  
  * \[TODO: grade based on accuracy \* difficulty || *or pick a better cross-metric.* I identified this as the simplest one, but there could be better\]  
  * \[TODO: grade based on cutoff difficulty; look at only ProofBench-Advanced. Filter out all ProofBench-basic, and grade with only tier 1 ProofBench-Advanced & research-grade problems\]  
  * \[TODO: decide if this is valuable or something to move to another section, pending result quality\].

* **Cheap Models can crack the Frontier**  
  * We found that under the correct conditions, cheap models can crack genuinely novel research questions.   
  * Report analysis of **all** claimed ‘research grade’ solutions; where they came from & more.  
  * Report results of additional tests with DeepSeek v4 Pro (full pipeline) on frontier problems.  
  * \[TODO everything relevant here\].  
  * \[TODO probe all results for legitimately every single claimed solution to the ten research-grade questions. This includes results from scaling, diversity, and roleswap alongside architecture\].

**Secondary Results**

* **Cross-model diversity experiment.** Model diversity is not universally useful, but appears to help at the frontier.  
  * Long sweep, mixing OSS with GEMMA. We found that model diversity significantly uplifted the quality of the models on hard problems, although we note that this finding is not as robust as the others.   
  * We ran into budget constraints preventing us from evaluating larger models.  
  * This is a secondary result only because we were cost-constrained to use it on merely OSS and Gemma.  
  * \[TODO: run a basic check of the finding with   
    * We have Low Confidence for this   
  * Alternative explanation: an advanced verifier can help uplift a pipeline. Unclear. \[TODO check findings; maybe cut or move to appendix or put in own subsection\]  
  * \[NOTE: see results/roleswap\]

* **Scaling pass@k appears to offer continued improvements.** We experimented with scaling pass@k to see if capability continued to improve on Gemma and OSS, and to a lesser extent on DeepSeek Flash.  
  * We generally found \[TODO determine findings & analysis\]  
  * \[NOTE: see results/scaling\]

* **Judge Choice can meaningfully change the headline**.  
  * A comment on DeepSeek vs Gemini Flash as judge, how important it was, and how that could potentially flip key results.

**Tertiary Results//Other Interesting Findings**

* **Reasoning is Key**  
  * Differences between oss & gemma with vs without reasoning are gigantic on AnswerBench, GradingBench, and IMO-plus-ProofBench \[short accuracy table for OSS, Gemma, DS with/out reasoning\].  
  * Compare this to the pipeline uplift, and we see that reasoning mode is way more important.   
  * This is one of the clearest findings. This is also well-known in the literature, so it's a tertiary finding, but something to reinforce.

* **Consumed Resources**  
  * Across the main 7x60, we had \[TODO calculate tokens, dollars, latency\].  
  * Note that our personal metric/constraint was price. We worked with a budget of $1000 (ignoring human time/cost). Caveat that this likely undershoots costs as some logs were missed; OR details \[$800+ TODO check/update\]

* **Errors & Audit Analysis**   
  * **General \[NOTE/TODO for Errors/audit:** everything here can be done in a later pass\]  
  * **Error Rate across Experiments.** We noted the following error rate:   
    * \[TODO calculate error rate\]  
    * \[TODO calculate & report error breakdown\]  
  * **Check TODO:** Analysis of frontier problem-solves based on judge calibration AND bayesian priors. Make sure it's not the ‘we tested 1000 people on something with a 1% false positive rate.  
    * \[Note: if analysis does identify this, note and regrade with consensus cross-model judging or whatever appropriate\]  
  * **Meaningful Error: Broken Ideator in initial pass**  
    * When reviewing logs, we found that the ideator trial was often broken and contaminated. This occurred in a substantial portion of the runs (%10-28)  
    * However, we note that a ‘broken ideator’ simply defaults to pass@3 runs. When comparing pass@3 vs ideation, this means it could only have regressed to the mean.  
      * TODO run a quick analysis on this broken item.  
    * \[TODO check logs; we may have patched this after the fact.\]  
* **\[TODO identify other discoveries worth including\]**  
  * \[TODO check logs from agent given $30 and told to self-ideate. Maybe report these results as well? In Appendix?\]

**Limitations**

* **\[NOTE:** This can be left as a TODO for most of the first pass. Smooth it out, but feel free to skip the analysis elements\].  
* **Benchmark contamination**  
  * We aren’t *too* worried about contamination. Note that all of the frontier research problems were solved and genuinely unknown to the community until 2026*.* Note that the model training cut-offs, while unclear, and while we do train on some models that were very recently released, probably would not have had time to incorporate these new findings.  
    * Simple table indicating the day delta between each of the frontier problems and each of the models evaluated. **Note that OSS was released before every single one. GPT-OSS is absolutely protected from data contamination**. This partly extends to the release of IMO-Bench, Though some of those questions were collected from earlier \[TODO check dates/results\].  
      * \[TODO optional: test OSS on IMO questions published from before and after August 5 2025 with a short table. Only do this on a final, optional pass. Maybe save for the Appendix.\]  
  * **Release Dates**  
    * IMO benchmark first released on Nov 3, 2025, gpt-oss on August 5 2025, Gemma 4 on March 31st [blog](https://ai.google.dev/gemma/docs/releases), DeepSeek v4 on April 24th [docs](https://api-docs.deepseek.com/news/news260424), \[TODO check remainder\]  
  * **Solution Dates:**  
    * FirstProof February 13th. [Arxiv](https://arxiv.org/html/2602.05192v2#:~:text=Our%20solutions%20appear%20below.%20They,B.1%20Question%201%3A%20Martin%20Hairer.), Epoch Frontiermath public announcement March 23rd. [Article](https://epochai.substack.com/p/first-ai-solution-on-frontiermath), \[TODO check remainder\]  
  * \[NOTE TO DRAFTING AGENT: despite the bullets, please condense this into a short section\]  
* **Mathematical Content & Judging**  
  * We acknowledge that one serious limitation of this project is that we don't have the resources to evaluate these answers.   
    * Note that it is simply not possible. We have over five thousand IMO-level proof submissions; These cannot be judged on any reasonable time scale. This is why we put so much effort into calibrating our judge, and we believe that it is more than strong enough to be directionally correct.  
    * On frontier problems specifically, we acknowledge there may be more room for error due to apt distribution results. Again, complete judging is impractical.  
    * We did spot-check erdos 659 and found that the judge evaluation is showing genuine signal towards a solution.  
      * ~~\[IF PERFORMED\] have ui checks from Claude Opus 4.7, Gemini 3.1 Pro, **ChatGPT 5.5 Pro**~~  
  * We also acknowledge that the calibration scores from the judge agent are not optimal. We firmly believe, however, that the pass \>=6 metric is more than strong enough to provide meaningful signal despite imperfections. \[todo maybe cite human rates of judge disagreement\]  
* **Generalization & Model Quality**  
  * While we tested a range of models at different capability levels and across different scales, we do note that these ranges are not the same as testing on the true frontier.  
    * Note price increase analysis based on the same tokens API cost. Emphasize gpt-oss → gpt 5.5 Pro  
* **Dataset Size**  
  * We are working with a data set of n \= 70\. We believe that 70 problems is enough for results to likely generalize while still being small enough for us to run evaluations as intense as pass@9, and so, think that this is likely the weakest of the limitations, but we want to acknowledge the trade-off between dataset size and architecture complexity.  
  * A more serious limitation is that only 10 of the problems are research-grade, and models were overwhelmingly unable to solve these. They present another failure mode.

**Conclusion/Discussion**

* \[PLACEHOLDER: TODO in a later pass\]

**Future Work**

* **Compare generator-verifier to pass@k**. We strongly encourage researchers working with generator-verifier loops for math proofs to evaluate whether these performances do genuinely out-compete simple scaling of pass@k, *when compared with the correct per-token architecture.*

* **Evaluations on frontier models.** We call for researchers to evaluate these questions while scaling up model capability & question difficulty.

* **Human Expert Trials**. While we are reasonably confident in our team’s ability to work through certain individual outputs, it stretches our capability, and we have little confidence in our ability to faithfully emulate IMO judge scores or to evaluate at scale. We call for studies with more comprehensive checks from human graders; ideally those with strong IMO and research expertise.

**Appendix Findings \- Optional (SKIP, Final Pass Only)**

* **Relative Judge Comparison (6x70)**  
  * We compare Gemini vs DeepSeek as a judge on the main 6x70x3 run.  
  * We found that the weaker model tended to like the architecture refinements more than the preliminary one.

* **Inconclusive Frontier Result**  
  * We ran two Frontier models, Gemini 3.1 Pro and Claude 4.6 Opus, on 1\) Ramsey Hypergraphs and 2\) Hadamard Matrices through a generator-verifier loop.   
    * Specifically tried (x) with (y) different threads \[TODO check agent\_log.md\]  
  * We found that they degraded and circled the local basin; no architecture uplift.   
    * However, we believe these results are inconclusive and may simply reflect poor scaffolding.  
  * We abandoned this thread due to cost concerns; this highly-constrained preliminary dual run cost north of XX usd.

* **Preliminary FirstProof Submission**  
  * We copied Huang & Yang’s \[TODO check IMO gold results\] exact architecture, down to a fork of the repo, to emulate their submission for the first proof pset

* **Probing Devset Experiment**  
  * **\-**