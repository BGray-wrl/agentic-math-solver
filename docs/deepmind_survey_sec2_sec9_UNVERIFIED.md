## 2: Techniques for AI-Assisted Research

Across the various successful collaborations documented here, several common techniques emerged. These strategies represent a "playbook" for researchers looking to integrate AI into their theoretical work.

### 2.1 Iterative Prompting and Refinement

Rarely does a model solve a deep open problem in a single shot. Success often comes from an iterative dialogue.

- **Initial Broad Query:** Start by asking the model to digest a relevant paper or problem statement to gauge its understanding.
- **Specific Sub-tasks:** Break down the main problem into smaller, verifiable lemmas or calculations.
- **Error Correction:** When the model makes a mistake (e.g., a wrong constant or invalid assumption), pointing it out specifically often leads to a correct and sometimes more elegant solution in the next turn.
- **Scaffolding:** Providing the model with a high-level proof strategy or "scaffold" allows it to fill in the technical details effectively.
- **Adversarial Self-Correction for Review:** When tasked with reviewing complex proofs, standard prompts often yield superficial results. A rigorous protocol instructing the model to (1) generate an initial review, (2) critique its own findings for hallucinations, and (3) iteratively refine the logic, enables deep technical critique. This was critical in identifying the flaw in a SNARGs paper, where the model distinguished between a definition of perfect consistency and a construction of statistical consistency.

### 2.2 Cross-Pollination of Ideas

Models have ingested vast amounts of literature across all fields. They excel at:

- **Finding Analogies:** Identifying similar problems in different domains (e.g., applying techniques from computational geometry to graph theory).
- **Retrieving obscure theorems:** Bringing relevant but less-known theorems to the researcher’s attention (e.g., Stone-Weierstrass or Kirszbraun Extension Theorem) to bridge gaps in a proof.

### 2.3 Simulation and Counterexample Search

For conjectures, models can be tasked to:

- **Construct Counterexamples:** Generating specific instances (graphs, matrices, set systems) that violate a proposed conjecture.
- **Verify Small Cases:** Writing code to computationally verify a conjecture for small *n*, providing empirical evidence before attempting a general proof.

### 2.4 Formalization and Rigor Checks

While models can hallucinate, they are increasingly capable of formal reasoning when prompted correctly.

- **Proof Sketch to Formal Proof:** Asking the model to expand a high-level sketch into a rigorous LaTeX proof.
- **Sanity Checking:** Using the model to check consistent usage of notation or to verify that all conditions of a theorem are met.
- **Mathematical Derivation:** Researchers can offload the mechanical heavy lifting of complex derivations to the model, such as simplifying expressions, computing limits, or solving integrals, allowing them to focus on the high-level logic.

### 2.5 Interactive Proof Construction with External Validation

A powerful technique involves using the model to identify necessary external theorems and then validating those theorems with external sources.

- **Identifying Dependencies:** Asking the model to list all external theorems required for a proof.
- **External Verification:** The researcher finds the formal statements of these theorems (e.g., via Google Search or textbooks) and feeds them back to the model.
- **Self-Contained Proof Generation:** The model then incorporates these verified statements to generate a rigorous, self-contained proof.

### 2.6 Agentic Tool-Use and Automated Feedback

While most of the collaborations documented here rely on manual, iterative dialogue, frontier models can also be deployed as agents within automated programmatic loops. For problems requiring heavy algebraic manipulation or where symbolic math must be rigorously grounded in numerical reality, researchers can construct a “neuro-symbolic" pipeline consisting of the following steps:

- **Symbolic Proposal:** The LLM generates a mathematical hypothesis or intermediate expression.
- **Code Generation:** The LLM autonomously writes an executable script (e.g., in Python) to evaluate its proposed math against a known numerical baseline.
- **Automated Feedback:** The system executes the code. If the code fails, hits a runtime error, or reveals numerical instability (such as catastrophic cancellation), the automated harness captures the exact execution traceback and injects it back into the LLM’s context window. This programmatic loop allows the AI to systematically explore a tree of mathematical solutions, autonomously pruning dead-ends and self-correcting its algebra without requiring a human-in-the-loop for every intermediate step.

### 2.7 Human-AI Collaboration Dynamics

It is important to note that AI models like Gemini function best as powerful collaborators rather than autonomous researchers. In the successful case studies presented here, the partnership between the model and the human expert was key to the results.

- **Selection and Refinement:** Models are capable of generating a high volume of diverse mathematical statements. Human expertise is valuable for filtering these outputs and identifying the most promising directions for further investigation.
- **Iterative Guidance:** While models can solve some problems in a single shot, tackling deep open problems is often most successful through an iterative process. The researcher guides the model, refining the problem statement and narrowing the focus to achieve the desired result.
- **Standard Verification:** As with any research collaboration, the AI can make mistakes, and AI-generated proofs and counterexamples benefit from rigorous verification. The model serves as an excellent accelerator for ideation and drafting, while the researcher validates the mathematical correctness.
- **Optimizing Context:** Performance is often optimized by providing clear, self-contained definitions, particularly when using highly specialized notation that may deviate from standard literature.
- **Leveraging Literature:** We found that incorporating relevant papers directly into the context significantly enhanced the model’s ability to construct correct proofs for specialized domains.
- **Context De-Identification:** The model sometimes avoids non-trivial machinery (for example, the Kirszbraun extension theorem), treating such proofs as non-elementary, or it may do so because the prompt steers it toward conservatism to avoid hallucinations, causing it to abandon an otherwise viable approach. Separately, on occasion, when shown the paper as context in the prompt, it recognizes the statement to prove as a conjecture in the paper and refuses to attempt it on the grounds that it is an open problem. One way to bypass both issues is via context de-identification (remove the paper and provide only the problem statement and definitions), after which the model typically engages (and may ultimately draw on deeper results to resolve a conjecture).

We view the AI as a tireless, knowledgeable, and creative bright junior collaborator. Its value lies in its ability to synthesize vast amounts of information and generate novel hypotheses that human researchers can then validate and build upon.

### 2.8 Summary: The AI-Assisted Research Playbook

Taken together, the techniques outlined above represent a fundamental shift in how theoretical research can be conducted. The LLM is no longer acting merely as a search engine or a syntax formatter; it is functioning as a combinatorial reasoning engine and a sounding board for abstract ideation.

However, the most successful collaborations documented in the following case studies all share a common denominator: strong human orchestration. Although several of our successes came from a single “zero-shot" prompt, many required scaffolded reasoning, i.e., breaking down deep open problems into verifiable parts, testing hypotheses through adversarial prompting, and actively steering the model. Informally this interactive workflow has been called “vibe-proving".

By mastering the techniques outlined above—particularly iterative refinement and adversarial self-correction—researchers can effectively elevate the AI from a passive tool into an active, high-leverage research partner.

[...]

## 9: Conclusion and Future Directions

The diverse array of case studies presented in this manuscript demonstrates unequivocally that frontier AI models—specifically Gemini Deep Think and its advanced variants—have crossed a critical threshold. They are no longer merely tools for routine automation, data processing, or syntax formatting; they are now capable of acting as genuine, expert-level collaborators in mathematical and algorithmic discovery. Across theoretical computer science, economics, physics, and optimization, we have shown that LLMs can actively resolve open conjectures, tighten long-standing mathematical bounds, and identify obscure, cross-disciplinary theorems to bypass human roadblocks. The value of the AI in these collaborations manifested in several distinct paradigms. In some instances, it acted as a cross-disciplinary bridge, retrieving theorems from distant mathematical domains (such as the Kirszbraun Extension Theorem) to resolve computational geometry roadblocks. In others, it served as a relentless adversarial reviewer, successfully identifying a fatal, deeply buried flaw regarding perfect versus statistical consistency in a state-of-the-art cryptography preprint. Crucially, however, these successes were not achieved autonomously. They required a tightly coupled human-AI workflow characterized by iterative refinement, strategic scaffolding, and rigorous verification—a process some authors have colloquially termed “vibe-proving.”

### 9.1 Common Themes and Problem Suitability

Across these diverse case studies, clear themes emerge regarding the types of problems where this human-AI collaborative approach excels, and where it currently struggles.

**Highly Suited Problem Classes:** The model is exceptionally effective on problems that can be decomposed into verifiable steps, require cross-disciplinary knowledge retrieval (e.g., bridging graph theory with continuous measure theory), or involve generating counterexamples to bounded conjectures. It also thrives in settings where the human can provide a strategic “scaffold” while the AI fills in tactical derivations, or where automated execution loops can rapidly test and prune algebraic hypotheses against numerical ground-truths (as in the cosmic strings derivation).

**Less Suited Problem Classes:** One goal is to improve the model on problems requiring completely unconstrained, multi-page derivations, where intermediate steps cannot be easily verified or grounded. Problems that require establishing entirely novel mathematical frameworks from scratch, or those with extremely long, sparse reward horizons without intermediate feedback, exceed the autonomous capabilities of current models and require some amount of human orchestration.

**Capabilities Needed for Expansion:** To further expand the range of scientific problems that can be tackled, future AI capabilities likely should evolve beyond natural language and standard code execution. Models will need enhanced capacities for long-horizon logical planning to maintain context over lengthy proofs. Furthermore, seamless, native integration with interactive theorem provers (discussed in Section 9.3) are important to autonomously verify the logical soundness of deep reasoning steps and mitigate hallucination bottlenecks.

### 9.2 Understanding Current Limitations and Failure Modes

Left unchecked, current models exhibit distinct failure modes that researchers must actively manage. Across our experiments, several recurring limitations emerged:

- **Confirmation Bias:** As noted in information theory case studies, models exhibit a strong tendency to support the hypothesis presented in a prompt. If tasked with proving a false conjecture, the AI will often attempt to bridge logical gaps with confident but “hand-wavy” arguments that do not withstand rigorous scrutiny. Neutral prompting (e.g., “prove or refute”) is essential.
- **Confident Technical Hallucinations:** While models excel at high-level structural insights, they can occasionally make subtle algebraic errors, drop constraints, or confidently misapply theorems (e.g., flipping inequality signs in hypercontractivity bounds).
- **Alignment Friction:** Standard safety and alignment guardrails can sometimes hinder scientific exploration. As noted in Section 2, the model may initially refuse to attempt a problem if it recognizes it as an “unsolved open problem” (requiring Context De-Identification to bypass).

Because of these limitations, the human researcher’s role is elevated rather than replaced. The scientist shifts from executing mechanical derivations to acting as an orchestrator, auditor, and strategic director of the AI’s combinatorial reasoning.

### 9.3 Future Directions: From Code Execution to Formal Verification

To overcome the limitations of LLM hallucinations, researchers must integrate pure language models with external verification environments. As outlined in Section 2.6 and demonstrated in a cosmic strings experiments, we are already seeing success by embedding AI in “neuro-symbolic” loops—where the model autonomously writes code to numerically verify its proposed mathematical steps and uses traceback errors to prune invalid branches.

However, while numerical execution is a powerful grounding mechanism for applied mathematics and physics, it is fundamentally limited when dealing with abstract proofs. For pure mathematics and theoretical computer science, the natural evolution of this workflow is **Formal Verification**. As AI systems generate increasingly complex, multi-page mathematical proofs, human verification becomes an exhausting bottleneck. Future research must focus on building autoformalization pipelines that automatically translate LLM-generated informal mathematics into formal verification languages (such as Lean, Coq, or Isabelle). By pairing the creative, associative leaps of an LLM with the absolute rigorous certainty of an interactive theorem prover, the research community can systematically eliminate the hallucination problem in mathematical discovery.

### 9.4 Final Thoughts

Just as the advent of calculators and computational algebra systems revolutionized applied mathematics in previous decades, the ability to rapidly iterate on abstract reasoning with a tireless, knowledgeable AI collaborator promises to dramatically reduce the friction of theoretical execution. Ultimately, the premise of this work is not just that AI can help solve specific, isolated research problems, but that it transforms how we do research. The implications for scientists are important: the day-to-day workflow of theoretical research will likely shift away from mechanical derivations and exhaustive literature hunting, moving instead toward high-level orchestration, hypothesis generation, and rigorous verification. By acting as a collaborative sounding board, AI lowers the barrier to entry for exploring complex, interdisciplinary ideas. This shift promises to empower a broader diversity of researchers, allowing them to tackle bigger, more ambitious problems than they could alone. By embracing this collaborative paradigm, understanding its failure modes, and building new automated verification pipelines, researchers can explore broader hypothesis spaces and ultimately accelerate the pace of scientific discovery.