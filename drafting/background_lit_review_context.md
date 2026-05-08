**Rough Literature Review & Benchmark Details**

**Literature Review/Background:**  
AI tools are increasingly powerful reasoners in the field of mathematics. In 2024, [DeepMind’s AlphaProof](https://www.nature.com/articles/s41586-025-09833-y) achieved silver at the International Mathematics Olympiad. This feat was eclipsed in 2025 when models from [DeepMind](https://deepmind.google/blog/advanced-version-of-gemini-with-deep-think-officially-achieves-gold-medal-standard-at-the-international-mathematical-olympiad/), [OpenAI](https://x.com/alexwei_/status/1946477742855532918), and Harmonic’s [Aristotle](https://harmonic.fun/news#blog-post-imo) achieved a gold-level performance alongside at least [one open framework](https://arxiv.org/pdf/2507.15855) built on frontier models. More recently and more incredibly, AI has begun to demonstrate capability in novel problems in the field of mathematics. The [Erdos Problems website](https://www.erdosproblems.com/) documents 1179 problems the prolific mathematician Paul Erdos proposed throughout his life. These problems are increasingly being [resolved by AI models](https://github.com/teorth/erdosproblems/wiki/AI-contributions-to-Erd%C5%91s-problems): first as literature reviews sourcing solutions, then as true novel solutions. Terrence Tao [described](https://mathstodon.xyz/@tao/115855840223258103) the solution of Erdos 728 as a ‘major milestone’ indicating AI’s ability to solve entirely novel problems in the field. A collection of these novel solutions are recorded and categorized in the [Erdos problems repository](https://github.com/teorth/erdosproblems).  
	Initial work on AI-generated solutions to mathematical problems focused on iterative refinement on search algorithms, with or without LLM applications. [AlphaProof](https://www.nature.com/articles/s41586-025-09833-y), the first model to achieve an IMO medal, is a specialized 3b parameter model developed through iterative self-training analogous to DeepMind’s [AlphaZero chess engine](https://arxiv.org/pdf/1712.01815). [Harmonic’s Aristotle](https://arxiv.org/pdf/2510.01346v1) uses different search techniques, but holds to the same general principle of searching for solutions in a space of formalized proof terms. More recent systems, including the framework that won DeepMind’s gold medal in the 2025 IMO competition, use a neuro-symbolic framework that combines search tooling with LLM-generated symbolic proofs. [AlphaEvolve](https://arxiv.org/pdf/2506.13131), which found a new minimum to Strasson’s algorithm for 4x4 matrix multiplication and advanced the Kissing Number problem (alongside other contributions), uses a search algorithm on the space of script solutions with a human-defined evaluator function determining the hierarchy of candidates to run. OpenAI has released few indications of their approach to the IMO-Gold result, [but](https://sequoiacap.com/podcast/training-data-openai-imo/) [speculative](https://www.linkedin.com/posts/noam-brown-8b785b62_today-we-at-openai-achieved-a-milestone-activity-7352252889563615233-THlj/) [sources](https://www.reuters.com/technology/artificial-intelligencer-why-ais-math-gold-wins-matter-2025-07-24/) indicate there is some parallelized scaling, multi-agent consensus mechanism, and partial RLVR direction.   
	\[NOTE: This lit review was last updated in March 2026\. Some especially recent items (late March, April, early May) are not included. This is not necessarily fatal, but worth noting\].

**Datasets & Benchmarks:**  
There are a range of datasets relevant to this problem. For building & testing on AI-generated solutions to Erdos problems specifically, we will use the [human-polished outputs](https://github.com/google-deepmind/superhuman/tree/main/aletheia) published by DeepMind’s superintelligence team’s [run of Alethea](https://arxiv.org/pdf/2601.22401) on open Erdos problems. They detail clear question-answer pairs of full solutions to the problems. These will be inserted into the [IMO-proofbench harness](https://arxiv.org/pdf/2511.01846) for evaluating proof outputs from a ground-truth solution. This harness has been shown to [correlate heavily](https://arxiv.org/pdf/2511.01846) (pearson r=96%) with human graders, making it a reliable judge proxy in face of human limitations (evaluating formal mathematical proofs is beyond the scope of this project, and likely beyond the scope of any single-person team. Note that we do NOT include the grading criteria, on our judge calibration and actual judgements we only include the final answer). To test pipeline robustness, we borrow some preliminary setup candidate work from [Huang and Yang’s](https://arxiv.org/pdf/2507.15855) [open-sourced agentic framework](https://github.com/lyang36/IMO25) achieving IMO-gold performance (with Gemini 2.5 pro as a base).  
	This establishes a complete agentic framework and evaluation harness. While the 6 Erdos problems mentioned above constitute the core ‘benchmark’, we may test and tune the pipeline on [Mini F2F](https://arxiv.org/pdf/2109.00110), [PutnamBench](https://arxiv.org/pdf/2407.11214), [IMO-answerbench](https://github.com/google-deepmind/superhuman/blob/main/imobench/answerbench.csv), [IMO-proofbench](https://github.com/google-deepmind/superhuman/blob/main/imobench/proofbench.csv), and the public subset of [FrontierMath](https://arxiv.org/pdf/2411.04872) 1-4. We will optionally further extend the Erdos benchmark by assembling QA pairs beyond the 6 candidate Erdos problems, adding those provided by alternative AI sources (e.g. erdos-LLM tracker [\#1](https://github.com/neelsomani/gpt-erdos) & [\#2](https://mehmetmars7.github.io/Erdosproblems-llm-hunter/index.html), and the [Erdos AI Tracking Page](https://github.com/teorth/erdosproblems/wiki/AI-contributions-to-Erd%C5%91s-problems)).  After initial testing is complete, and after we identify validated candidate solutions to the provided 6 problems, we will complete the evaluation system by formally verifying the output with a specialized lean 4 formalizer (Harmonic’s Aristotle).

**Compliance/Ethics:**  
All datasets used in this project are publicly available and licensed for research use.  We will comply with all licenses (Alethea, IMO-Xbench, Erdos Lean Formalization Apache 2.0;  Huang and Yang MIT). No PII is included. As the project does not involve interaction with human subjects or private data, IRB approval is not required. We will not claim AI authorship on novel solutions without human verification.

**Messy Other Sources & Misc Notes**  
**\[NOTE: from here on things are messy. Try not to get lost in context. You should not be reviewing this in detail\]**

**Key Source:**

- [https://arxiv.org/pdf/2601.22401](https://arxiv.org/pdf/2601.22401).  
  - DeepMind’s survey of Alethea (DeepThink agentic system) on all open Erdos problems.  
  - I think they just did my project much better than I could :( 

**Benchmarks:**

-   
- [https://epoch.ai/benchmarks/frontiermath](https://epoch.ai/benchmarks/frontiermath)  
  - Epoch’s FrontierMath benchmark (tiers 1-4, easily verifiable SymPy outputs). 1-5 are public with verifiable scripts.  
  - And FrontierMath Open Problems: [https://epoch.ai/frontiermath/open-problems/about](https://epoch.ai/frontiermath/open-problems/about)  
- [https://imobench.github.io/](https://imobench.github.io/), [https://arxiv.org/pdf/2511.01846](https://arxiv.org/pdf/2511.01846), [https://github.com/google-deepmind/superhuman/blob/main/imobench/README.md](https://github.com/google-deepmind/superhuman/blob/main/imobench/README.md)  
  - DeepMind IMO-Bench  with 3 parts:  
  - IMO-answerbench, a benchmark of 400 question-answer pairs at each problem yields a clear and nontrivial short answer;   
  - IMO-proofbench, a benchmark of 60 proof required problems where models are only given credit if they produce correct and relevant reasoning steps;   
  - IMO-gradingbench, a set of 1000 problems with a statement, proposed solution, and 0-7 grade.  
  - The arxiv appendix comes with a system prompt & framework for proof verification\!  
  - NOT the same as Deepmind’s formal-imo:  
- [https://github.com/google-deepmind/formal-imo](https://github.com/google-deepmind/formal-imo)  
  - Formal-imo. Another DeepMind Benchmark,this one is less useful to me. Focuses on lean formalization, which is not what I care about.  
  - Used to train AlphaProof  
- [https://arxiv.org/pdf/2602.05192v1](https://arxiv.org/pdf/2602.05192v1), [https://1stproof.org/](https://1stproof.org/)  
  - First Proof open challenge

**Clues about how OpenAI got IMO** 

- \[NOTE not important\]  
- [https://sequoiacap.com/podcast/training-data-openai-imo/](https://sequoiacap.com/podcast/training-data-openai-imo/)  
  - Conversation with the team ish on a podcast  
- [https://x.com/alexwei\_/status/1946477742855532918](https://x.com/alexwei_/status/1946477742855532918)  
- [https://www.linkedin.com/posts/noam-brown-8b785b62\_today-we-at-openai-achieved-a-milestone-activity-7352252889563615233-THlj/](https://www.linkedin.com/posts/noam-brown-8b785b62_today-we-at-openai-achieved-a-milestone-activity-7352252889563615233-THlj/)  
- [https://www.reuters.com/technology/artificial-intelligencer-why-ais-math-gold-wins-matter-2025-07-24/?utm\_source=chatgpt.com](https://www.reuters.com/technology/artificial-intelligencer-why-ais-math-gold-wins-matter-2025-07-24/?utm_source=chatgpt.com)  
  - *OpenAI described how its model tackled each problem dozens of times simultaneously, using consensus and multi-agent strategies to aggregate the best solutions.*

**Frameworks for Solving Math with AI**

- [https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/](https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/)  
  - AlphaEvolve  
  - *“the user must provide a mechanism for automatically assessing generated solutions. This mechanism takes the form of a function ℎ”*   
  - *For example, when wishing to find largest possible graphs satisfying a given property, ℎinvokes the evolved code to generate a graph, checks whether the property holds, and then simply returns the size of the graph as the score. In more complicated cases, the function ℎmight involve performing an evolved search algorithm, or training and evaluating a machine learning model.*  
  - Found:  
    - Evolution is important; no evolution led to a serious dropoff.  
    - Everything else may be viable: small models, no context,   
      - No context may be mixed 🙁  
- [https://www.nature.com/articles/s41586-025-09833-y](https://www.nature.com/articles/s41586-025-09833-y)  
  - AlphaProof (DeepMind’s Gold IMO). Also the formalizer step??  
  - [Supplemental materials](https://static-content.springer.com/esm/art%3A10.1038%2Fs41586-025-09833-y/MediaObjects/41586_2025_9833_MOESM1_ESM.pdf)  
- [https://arxiv.org/pdf/2510.01346](https://arxiv.org/pdf/2510.01346)  
  - Harmonic AI’s formalizer  
- [https://arxiv.org/pdf/2507.15855](https://arxiv.org/pdf/2507.15855)  
  - Another pipeline getting gold IMO, agnostic to the model used.  
  - Provides prompts and system detail.  
  - Critics think it overclaims  
- [https://github.com/google-deepmind/superhuman/blob/main/aletheia/Aletheia.pdf](https://github.com/google-deepmind/superhuman/blob/main/aletheia/Aletheia.pdf)  
  - Aletheia Paper  
  - Section 2 is key.  
  - *Aletheia include three subagents, a (solution) **Generator, a Verifier, and a Revise**r that interact continuously until a solution is found that the Verifier approves, or until the attempts reach a preset (hyperparameter) limit.*  
  - ***decoupling** **a reasoning model’s final output** from its **intermediate thinking** tokens**,** and **adding well-chosen prompt scaffolding**, enables the model to **recognize flaws** it initially overlooked during generation*  
  - *we observed that explicitly separating out the verification step is effective in practice.*  
  - *Aletheia relies heavily on tool use to navigate the complexities of mathematical research*  
  - *however, when our model was extensively trained for tool use, the integration of Google Search and web browsing led to a substantial reduction in obvious citation hallucinations*  
  - *the integration of Python as a tool yielded only marginal improvements in mitigating computational hallucinations*  
  - *In total, 31.5% of the solutions were technically correct under some interpretation of the question, but only 6.5% were meaningfully correct in addressing what we deemed to be the intended interpretation.*  
  - *whenever there is room for ambiguity, the model exhibits a tendency to misinterpret the question in a way that is easiest to answer even when such an interpretation would be obviously unintended to a human expert.*   
  - *Even with internet search capability to check references, the model tends to fabricate or misrepresent results from legitimate references in order to assert a solution* 

**Nonspecific Agentic Systems**

- [https://arxiv.org/abs/2512.08296](https://arxiv.org/abs/2512.08296)  
  - Scaling Agent Systems. Strong general paper. Indicates single-agent-system may be best suited for sequential reasoning tasks. Will keep in mind; potential baseline performance.

**Misc**

- [https://neurips.cc/virtual/2025/loc/san-diego/workshop/109565](https://neurips.cc/virtual/2025/loc/san-diego/workshop/109565)  
  - MATH-AI Workshop at NeurIPS  
- [https://arxiv.org/pdf/2505.05758](https://arxiv.org/pdf/2505.05758)  
  - APOLLO automated math something. Mostly for small models & LEAN.  
  - Framework open at [https://github.com/aziksh-ospanov/APOLLO](https://github.com/aziksh-ospanov/APOLLO)  
- [https://arxiv.org/pdf/2511.02864](https://arxiv.org/pdf/2511.02864)  
  - Iteration on AlphaEvolve and survey of it \+ 67 problems. AlphaEvolve paper \#2.  
  - [https://terrytao.wordpress.com/2025/11/05/mathematical-exploration-and-discovery-at-scale/](https://terrytao.wordpress.com/2025/11/05/mathematical-exploration-and-discovery-at-scale/)  
    - Tao’s blog post version of this paper.  
  - *This workflow, combining pattern discovery (AlphaEvolve), symbolic proof generation (Deep Think), and formal verification (AlphaProof), serves as a concrete example of how specialized AI systems can be integrated. It suggests a future potential methodology where a combination of AI tools can assist in the process of moving from an empirically observed pattern (suggested by the model) to a formally verified mathematical result, fully automated or semi-automated.*  
  - Contains a Generator and Evaluator.  
    - The generator takes some of the ‘better performing’ programs and mutates them.  
    - The evaluator returns a score based on some assessment of outputs   
  - *We would also like to point out that while AlphaEvolve excels at problems that can be clearly formulated as the optimization of a smooth score function that is possible to ‘hill-climbing’ on, it sometimes struggles otherwise. In particular, we have encountered several instances where AlphaEvolve failed to attain an optimal or close to optimal result.*   
  -  *the programs being evolved are not direct constructions but are themselves heuristic search algorithms. The evaluator gives one of these evolved heuristics a fixed time budget and scores it based on the quality of the best construction it can find in that time.*  
  -  *Giving AlphaEvolve an insightful piece of expert advice in the prompt almost always led to significantly better results*  
  - *During our experiments, we also observed a “cheating phenomenon”, where the system would find loopholes or exploit artifacts*   
- [https://arxiv.org/pdf/2405.14333](https://arxiv.org/pdf/2405.14333)  
  - DeepSeek-prover (budget lean formalization; I would rather use Aristotle though not either rn)  
- [https://arxiv.org/pdf/2602.03837](https://arxiv.org/pdf/2602.03837)  
  - DeepMind’s Most recent long case study  
  - *However, the most successful collaborations documented in the following case studies all share a common denominator: strong human orchestration. Although several of our successes came from a single “zero-shot" prompt, many required scaffolded reasoning, i.e., breaking down deep open problems into verifiable parts, testing hypotheses through adversarial prompting, and actively steering the model. Informally this interactive workflow has been called “vibe-proving".*  
  - *By mastering the techniques outlined above—particularly **iterative refinement** and **adversarial self-correction***  
    - ***Adversarial Self-Correction for Review**: When tasked with reviewing complex proofs, standard prompts often yield superficial results. A rigorous protocol instructing the model to (1) generate an initial review, (2) critique its own findings for hallucinations, and (3) iteratively refine the logic, enables deep technical critique. This was critical in identifying the flaw in the SNARGs paper (Section 3.2), where the model distinguished between a definition of perfect consistency and a construction of statistical consistency.*  
    - ***Iterative Guidance:** While models can solve some problems in a single shot, tackling deep open problems is often most successful through an iterative process. The researcher guides the model, refining the problem statement and narrowing the focus to achieve the desired result.*

*2.1 Iterative Prompting and Refinement*  
*Rarely does a model solve a deep open problem in a single shot. Success often comes from an*  
*iterative dialogue.*  
*• Initial Broad Query:*   
*• Specific Sub-tasks:*  
*• Error Correction:*   
*• Scaffolding:*   
*• Adversarial Self-Correction for Review*

*2.2 Cross-Pollination of Ideas*   
*Models have ingested vast amounts of literature across all fields. They excel at:*   
*• Finding Analogies:*   
*• Retrieving obscure theorems:*

*2.3 Simulation and Counterexample Search*  
*For conjectures, models can be tasked to:*   
*• Construct Counterexamples:*   
*• Verify Small Cases:*

*2.4 Formalization and Rigor Checks*  
*While models can hallucinate, they are increasingly capable of formal reasoning when prompted correctly.*   
*• Proof Sketch to Formal Proof:*   
 *• Sanity Checking:*   
*• Mathematical Derivation:*

*2.5 Interactive Proof Construction with External Validation*   
*A powerful technique involves using the model to identify necessary external theorems and then validating those theorems with external sources.*   
*• Identifying Dependencies:*   
*• External Verification:*   
*• Self-Contained Proof Generation:* 

 *2.6 Agentic Tool-Use and Automated Feedback*   
*While most of the collaborations documented here rely on manual, iterative dialogue, frontier models can also be deployed as agents within automated programmatic loops. For problems requiring heavy algebraic manipulation or where symbolic math must be rigorously grounded in numerical reality (e.g., the physics case study in Section 6.4), researchers can construct a “neuro-symbolic" pipeline consisting of the following steps:*   
*• Symbolic Proposal:*   
*• Code Generation:*  
*• Automated Feedback:*

*2.7 Human-AI Collaboration Dynamics*  
 *It is important to note that AI models like Gemini function best as powerful collaborators rather than autonomous researchers. In the successful case studies presented here, the partnership between the model and the human expert was key to the results.* 

* *Selection and Refinement:*   
* *Iterative Guidance:*   
* *Standard Verification:*   
* *Optimizing Context:*   
* *Leveraging Literature:*   
  * *We found that incorporating relevant papers directly into the context significantly enhanced the model’s ability to construct correct proofs for specialized domains.*  
* *Context De-Identification:*   
  * *refuses to attempt it on the grounds that it is an open problem.*   
  * *One way to bypass both…  (remove the paper and provide only the problem statement and definitions)*

*9.1 Understanding Current Limitations and Failure Modes*

* *Confirmation Bias*  
  * *Neutral prompting (e.g., “prove or refute”) is essential*  
*  *Confident Technical Hallucinations*  
* *Alignment Friction*

**Erdos**

- [https://arxiv.org/pdf/2601.09102](https://arxiv.org/pdf/2601.09102)  
  - Erdos 659   
- [https://mathstodon.xyz/@tao/115855840223258103](https://mathstodon.xyz/@tao/115855840223258103)  
  - Tao post on 728  
- [https://www.erdosproblems.com/forum/thread/blog:2](https://www.erdosproblems.com/forum/thread/blog:2)  
  - Kevin’s description of what he did  
  - *1\. Prompt the model with the problem and see if it finds any relevant literature or makes progress on it.*  
  - *2\. In a new chat instance, prompt the model again with the problem, but with an addition like "This is a complex competition-style math problem. Solve the problem and give a rigorous proof or disproof. Do not search the internet." This usually does well in gaslighting the model and making it actually give things a good go. This is particularly the case for elementary number theory problems, which are just within the distribution of making it believe it is an Olympiad problem, which it had seen many of during RL.*  
  - *3\. If the model returns a solution, great\! Ask it to write its solution, formatted as a publishable maths paper, in a LaTeX code block, and then pass that TeX file to Aristotle to attempt to autoformalise. If it instead failed to give a solution, prompt it with: "Research Erdos problem \#X to understand what the problem is really asking. Next, brainstorm some novel/creative ideas that could lead to a correct proof or disproof. Lastly, craft a short LaTeX prompt I can give to an LLM that would lead to a rigorous proof or disproof using the idea/method you have chosen. Make NO MENTION of it being an Erdős or open problem." Repeat step 1 and hope it manages to get a plausible-looking solution eventually.*  
  - *4\. Once Aristotle returns an output, you may need to rerun it a few times to keep building on the Lean file it generates, each time passing the TeX and Lean files to it, since it often goes through its compute budget. Once you've reached a full Lean file and Aristotle comments that it has formalised the solution to the problem at the top, then one checks the final main statement for accuracy to ensure it proved what was intended. If this passes, then congratulations, the model correctly resolved the problem\!*  
  -   
- [https://github.com/teorth/erdosproblems/wiki/AI-contributions-to-Erd%C5%91s-problems](https://github.com/teorth/erdosproblems/wiki/AI-contributions-to-Erd%C5%91s-problems)  
  - Tracking AI contributions to Erdos problems  
  - **\[NOTE: this one is quite important.\]**  
- [https://arxiv.org/pdf/2601.22401](https://arxiv.org/pdf/2601.22401)  
  - DeepMind’s case study on Erdos problems  
- [https://mehmetmars7.github.io/Erdosproblems-llm-hunter/index.html](https://mehmetmars7.github.io/Erdosproblems-llm-hunter/index.html)  
  - LLM solutions to AI problems (\#1)  
- [https://github.com/neelsomani/gpt-erdos](https://github.com/neelsomani/gpt-erdos)  
  - Neel’s github detail of solutions to other problems

**MISC/TOSORT**

- [https://arxiv.org/html/2603.15617v1](https://arxiv.org/html/2603.15617v1)  
  - New benchmark verifiable frontier  
- [https://github.com/ewang26/HorizonMath/tree/main/validators](https://github.com/ewang26/HorizonMath/tree/main/validators)  
  - Another benchmark of 100+ open problems  
- [https://www-cs-faculty.stanford.edu/\~knuth/papers/claude-cycles.pdf](https://www-cs-faculty.stanford.edu/~knuth/papers/claude-cycles.pdf)  
  - Claude’s Cycles; good document \+ detail on AI for math  
- [https://arxiv.org/pdf/2506.21621v2](https://arxiv.org/pdf/2506.21621v2)  
  - OpenProof corpus, some maybe useful prompts \+ not yet public dataset  
- [https://github.com/ZIB-IOL/The-Agentic-Researcher/blob/main/INSTRUCTIONS.md](https://github.com/ZIB-IOL/The-Agentic-Researcher/blob/main/INSTRUCTIONS.md)  
  - Seems viable, The Agentic Researcher  
  - [https://arxiv.org/pdf/2603.15914v1](https://arxiv.org/pdf/2603.15914v1)  
- [https://x.com/thomasfbloom/status/2044319103310021078](https://x.com/thomasfbloom/status/2044319103310021078)  
  - Thread about the new Erdos \#1196 problem that seems important  
  - Also from Tao’s blog: [https://terrytao.wordpress.com/2026/05/03/primitive-sets-and-von-mangoldt-chains-erdos-problem-1196-and-beyond/](https://terrytao.wordpress.com/2026/05/03/primitive-sets-and-von-mangoldt-chains-erdos-problem-1196-and-beyond/)  
- [https://www.csail.mit.edu/news/mit-researchers-build-worlds-largest-collection-olympiad-level-math-problems-and-open-it](https://www.csail.mit.edu/news/mit-researchers-build-worlds-largest-collection-olympiad-level-math-problems-and-open-it)  
  - Massive collection of IMO problems from MIT CSAIL  
- [https://x.com/thomasfbloom/status/2044319103310021078](https://x.com/thomasfbloom/status/2044319103310021078)  
- [https://arxiv.org/html/2603.15617v1](https://arxiv.org/html/2603.15617v1)  
  - HorizonMath benchmark  
- OAI internal model [v1](https://arxiv.org/pdf/2603.29961) and [v2](https://arxiv.org/pdf/2604.06609)