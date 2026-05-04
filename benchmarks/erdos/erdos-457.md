# Problem

Is there some $\epsilon>0$ such that there are infinitely many $n$ where all primes $p\leq (2+\epsilon)\log n$ divide\[\prod_{1\leq i\leq \log n}(n+i)?\]

# Short Solution
A problem of Erd\H{o}s and Pomerance.

More generally, let $q(n,k)$ denote the least prime which does not divide $\prod_{1\leq i\leq k}(n+i)$. This problem asks whether\[q(n,\log n)\geq (2+\epsilon)\log n\]infinitely often. Taking $n$ to be the product of primes between $\log n$ and $(2+o(1))\log n$ gives an example where\[q(n,\log n)\geq (2+o(1))\log n.\]GPT-5.2 Pro (prompted by Barreto) has given a construction that gives an affirmative answer to the original question, with the constant $2$ replaced by $\frac{3}{\log 4}\approx 2.16$, and GPT later proved this with $2$ replaced by an arbitrarily large constant.

An elaboration sketched by Tao proves that there are infinitely many $n$ such that\[q(n,\log n) > \frac{1-o(1)}{2}\frac{\log\log n}{\log\log\log n}\log n.\]Tao suggests that standard heuristics suggest that this lower bound is also (up to constants) an upper bound for all $n$.
