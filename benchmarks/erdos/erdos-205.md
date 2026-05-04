# Problem

Is it true that all sufficiently large $n$ can be written as $2^k+m$ for some $k\geq 0$, where $\Omega(m)<\log\log m$? (Here $\Omega(m)$ is the number of prime divisors of $m$ counted with multiplicity.) What about $<\epsilon \log\log m$? Or some more slowly growing function?

# Short Solution

It is easy to see by probabilistic methods that this holds for almost all integers. Romanoff \cite{Ro34} showed that a positive density set of integers are representable as the sum of $2^k+p$ for prime $p$, and Erd\H{o}s used covering systems to show that there is a positive density set of odd integers which cannot be so represented.

Barreto and Leeham, using ChatGPT and Aristotle, have proved a negative answer, which was quantified by Tao and Alexeev (see the comments): in fact there are infinitely many $n$ such that, for all $k$ with $2^k<n$, $n-2^k$ has at least\[\gg \left(\frac{\log n}{\log\log n}\right)^{1/2}\]many prime factors.

The $n$ constructed in this way are divisible by a large power of $2$. It remains open whether there exist arbitrarily large odd counterexamples.
