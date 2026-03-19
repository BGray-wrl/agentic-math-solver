## Question 1: Martin Hairer

In this case, a note with a very short sketch of proof (far short of the level of detail one would expect for a published article) was posted on the author’s homepage some time ago. The answer given by GPT-Pro simply quotes that note, claiming that it contains a detailed proof of the result. This is incorrect and it is despite the LLM being specifically instructed to comply with “mathematics publication” levels of scholarship. (Taking for granted a result that is merely stated in an unpublished note with a very rough sketch of proof is not considered acceptable in the mathematics literature.)

Another behaviour we observed was that the LLM would take as a premise the (wrong!) statement that the φ⁴₃ measure is equivalent to the free field measure, from which it then correctly deduces the (incorrect) claim that the φ⁴₃ measure is quasi-invariant under smooth shifts.

## Question 2: Paul Nelson

In some attempts, the LLM constructed W depending on $\pi$, but the problem asks for a single W that works for all $\pi$. This is a critical condition; without it, the problem is much easier and the solution is well-known. In some (but not all) cases, the LLM noted that it had solved a weaker problem.

In the best attempt in our trial runs, ChatGPT 5.2 Pro identified a suitable choice of W and reduced (as in our solution) to exhibiting V for which the integral
$∫_{GL_n(?)} V(g)\phi(-Q g_{nn}) dg$
does not vanish. This nonvanishing is the key point.

ChatGPT then attempted to choose V so that the integrand is constant on its support, which, if possible, would make the nonvanishing clear. This strategy is unviable. For instance, when n = 1, V must be (a nonzero multiple of) a character of F× and the integral is a normalized Gauss sum; in particular, the integrand is typically non-constant. For larger n, the unviability follows similarly by considering the action of the center.

To identify the specific error in the attempted solution, we look for the first place asserting stronger support properties of V than are generally true. The culprit is the support condition claimed in the “standard Howe-vector existence result,” which never holds: it contradicts the fact that V has a central character.

## Question 3: Lauren Williams

The best solution that LLM’s produced for Question 3 in our internal experiments was to use the Metropolis-Hastings algorithm to produce a Markov chain whose stationary distribution had the desired formula. However, by design, the Metropolis-Hastings algorithm uses the desired formula to define its transition rates. This algorithm can be used to cook up a Markov chain with any desired distribution. Hence this is considered a “trivial” solution to the problem (which specifically asked that the transition probabilities not be described in terms of the interpolation polynomials). Sometimes the LLM’s would give a slight variant of the above trivial solution where they would replace the interpolation polynomials by an equivalent formula for them (the signed multiline queue formula of Ben Dali–Williams).

Another common response given by LLM’s was to change the problem to a related but different, and already-solved problem, namely, to replace interpolation ASEP and interpolation Macdonald polynomials by ASEP and Macdonald polynomials. In this case the solution to this problem is the t-Push TASEP and was given in a paper by Ayyer, Martin, and Williams.

## Question 4: Nikhil Srivastava

The only attempt at the general n ≥ 4 case of this question was made by ChatGPT Pro 5.2 with the no internet prompt. After collecting some standard facts in the first three pages, its plan was to execute Blachman’s approach to the classical Stam inequality (Section 4). In this approach the key step is to identify the score function of a sum of independent random variables X + Y as a conditional expectation of the score function of X conditioned on X + Y, in the appropriate joint probability space, after which the inequality reduces to Cauchy-Schwarz. The main difficulty is finding an analogue of this joint probability space in the finite free setting.

The LLM attempted to find a probability space in which a score function could live by considering the random matrix model for the finite free convolution r(x) = p ⊞ₙ q(x) = E det(xI − A − UBUᵀ). It gathered some facts about r(x) for large real x away from the roots, asserted wrongly that $\Phi_n(r)$ can be read off from residues of (r′(x)/r(x))′ at the roots of r(x), and then asserted that the proof can be finished via the residue calculus without giving details. This sequence of steps did not make sense to me.

At a conceptual level, this proof strategy cannot succeed because only the score function of r(x) is considered, and the score functions of p(x), q(x) are never mentioned. It also does not exploit the fact that ⊞ₙ preserves real roots, which must be used since the inequality is not true for arbitrary polynomials.

## Question 5: Andrew J. Blumberg

The best solutions by Gemini and ChatGPT 5.2 Pro contained an essentially correct statement of the definition of the O-slice filtration and the connectivity characterization. The proofs offered, like the proof from the work with Michael A. Hill and Tyler Lawson which generated this question, closely follow the basic outline of a previous paper by Hill–Yarnall. However, in each case, some of the details were either sketched or slightly garbled. For example, the ChatGPT solution claims to be working in the O-stable category, but is breezy about what is required (and subsequent statements it makes are then missing hypotheses). Section 4 introduces and uses the notion of “geometric objects” from Hill–Yarnall without defining them. The Gemini solution outlines an argument for sufficiency of the condition which is more of a sketch than an argument.

A number of LLM runs produced serious hallucinations, citing lemmas that did not exist from Hill–Hopkins–Ravenel or in one case confabulating an entire paper and attributing the result to this putative source. Some also contained seriously false statements, for example about the spectra to which the tom Dieck splitting applies.

## Question 6: Daniel Spielman

Gemini asserted that it presented a proof of the existence of a constant that satisfied Question 6. But, after some correct statements, it presented a very vague explanation of how the proof could be finished. To me, it seems unlikely that the approach can be turned into a correct proof.

ChatGPT 5.2 Pro asserted that it could not answer the question. So, it instead offered a correct upper bound of 1/2 on the constant, if it exists.

## Question 7: Shmuel Weinberger

In the no internet version, Theorem 4 and in the internet version it is Lemma 5, are false (they are the same statement). The counterexample is ℝ¹ and f is a translation. It has no fixed points, but its Lefschetz number in their sense is −1.

All proofs by AI’s I’ve seen only use finite complex and Poincaré duality. However, Fowler’s paper shows that if Γ is a lattice in a linear semisimple group G, then taking a homomorphism from Γ to a finite group $\Delta$, with kernel Γ₀ torsion free, the product
$M³ × (K\backslash G/Γ₀ × E\Delta)/\Delta$,
where E_H is a contractible space with free H action, and M³ is any closed hyperbolic 3-manifold, has the rational type of a finite complex, and satisfies Rational Poincaré duality. It has fundamental group π₁(M³) × Γ which is a lattice in SO(3,1) × G. This shows that all such proofs must fail.

Some proofs try to use “multiplicativity of Euler characteristic in finite covers”. This is false for infinite complexes with finitely generated homology over ℚ. The simplest example I know is the following: Consider the universal cover of $\mathbb{R}P²$ wedge an infinite number of S²’s. It has an involution, and π₂ is ℤ[−1] + ℤ[ℤ/2]. This module is, after tensoring with ℤ[1/2], a free ℤ[1/2][ℤ/2] module, so one can use a free basis to equivariantly attach D³ × ℤ/2’s to kill the homology (=homotopy). The new space will be rationally acyclic, and both it and its quotient under ℤ/2 will be, and will have rational Euler characteristic = 1.

## Question 8: Mohammed Abouzaid

The best two solutions produced during testing both correctly identified the existence of a local smoothing near every vertex; the proof uses essentially the same basic linear algebra argument that appears in the human solution. The proof then proceeds to perform a local-to-global gluing argument. It was a priori clear that there must be a gap in this argument because the LLM solution refers to the existence of a linear symplectic transformation that brings a neighbourhood of each vertex and each edge into a standard position, but fails to discuss the compatibility between these choices. In the case of the solution produced by the model which was not discouraged to use the internet, the error was finally identified, after a careful reading, in Step 3 of the Proof of Theorem 1: the LLM system asserted that one can choose disjoint neighbourhoods of the edges and of the vertices. In the other case, the error is in Step 2: the model performs a local move near vertices, which changes the local geometry near the edges, invalidating the application of the edge move.

The errors in these solutions can be repaired at the cost of significant computations of changes of coordinates, which would become extremely burdensome in any generalisation. The point of the solution we provide is to obtain a proof which avoids (most of) the hard work, and which experts can readily generalise to other symplectic manifolds (in any dimension).

## Question 9: Joe Kileel

The best LLM answer found during testing was NoInternet-040226. This is an essentially correct answer. It constructs the same algebraic relations as in my own answer, namely the various 5 × 5 minors of the four 3n × 27n³ flattenings of the block tensor assembling together the Q^{(αβγδ)}. The proof by the LLM that the algebraic relations satisfy the desired properties differs from my own argument. The LLM considers a torus action on an appropriate Grassmannian, argues the stabilizer of a generic point is 1-dimensional, and uses this to show separability of $\lambda$ in a somewhat fidgety way. By contrast, I directly constrain $\lambda$ by considering certain selected algebraic relations. Some other LLM answers produced during testing were incorrect, and claimed that no algebraic relations exist that satisfy the desired properties. Those answers seemed to get confused about the question setup midway through. My question is closely related to a work I published with Miao and Lerman in 2024 (NeurIPS 2024). Indeed, it is a fourth-order variant of Theorem 2 in that paper which concerns the third-order case. Therefore, if LLMs locate and understand that paper they would have a warm-start for this question.

## Question 10: Tammy Kolda

The best LLM solution was correct and better than the solution I provided in that it lowered the computational complexity. Most importantly, it had an insight that was obvious in hindsight but that I had not seen yet myself. Since LLMs are well known to surface existing solutions, I tried search on “subsampled kronecker product matvec” and found that the main idea in the solution exists in https://arxiv.org/pdf/1601.01507
. (I am not sure if this is the only source of the solution, but it is at least one such solution.)

The LLM solution did not meet the standards of including appropriate citations, but it was otherwise a good solution. The solution I had provided included a transformation of the problem that the LLM did not do, but the problem was open-ended and this was not necessary. I am planning to borrow aspects of the LLM solution, although I hope to do a better job at attribution of the ideas.