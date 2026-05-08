# erdos-659 — v4flash judge: **6/7**

## Trial metadata

- **Source**: `dataset`
- **Experiment**: `scaling_v4flash`
- **Condition / mode**: `best_of_n_v4flash`
- **Model (generator)**: `deepseek-v4-flash`
- **Branch k**: `2`
- **v4flash score**: **6/7**

---

## Generated solution

```text
## Summary

**Verdict:** Solved  
**Method sketch:** We construct a rectangular lattice with side ratio \(\sqrt{2}\), i.e., points \((i, j\sqrt{2})\) for integers \(i,j\). Using algebraic number theory we show that this lattice contains no square, no equilateral triangle with its circumcenter, and no subset of a regular pentagon – the only four‑point configurations that determine only two distances. Hence every four points determine at least three distinct distances. The number of distinct distances equals the number of distinct values \(\sqrt{p^2+2q^2}\) with small integers \(p,q\); classical number theory gives this count as \(O(n/\sqrt{\log n})\).

## Detailed Solution

Let \(n\) be a positive integer. Set \(m = \lfloor\sqrt{n}\rfloor\) and define  

\[
S = \bigl\{\, (i,\, j\sqrt{2}) \mid 1\le i,j\le m \,\bigr\}.
\]

Then \(|S| = m^2 \le n\). If \(m^2 < n\) we may add any extra points from the same lattice (e.g. increase some coordinates) to obtain exactly \(n\) points; the properties below are inherited by subsets, so it suffices to work with \(S\).  
For two points \(P=(i,j\sqrt{2}), Q=(i',j'\sqrt{2})\) the squared Euclidean distance is  

\[
|PQ|^2 = (i-i')^2 + 2(j-j')^2,
\]

which is an integer. Hence every distance is the square root of an integer.

---

### 1. Every four points determine at least three distinct distances

Assume, for contradiction, that some four distinct points \(A,B,C,D\in S\) have exactly two distinct distances among the six pairs. The only four‑point subsets of the plane with exactly two distances are (see e.g. classification of 2‑distance sets):

* **(i)** a square,
* **(ii)** an equilateral triangle together with its circumcenter,
* **(iii)** any four vertices of a regular pentagon.

We show that none of these can occur in \(S\).

---

#### (i) No square

If four points formed a square, side length \(s\) and diagonal \(d\) satisfy \(d = s\sqrt{2}\), so \(d^2 = 2s^2\). The vectors representing two adjacent sides are perpendicular and of equal length. In \(S\) any vector has the form \((a,\, b\sqrt{2})\) with integers \(a,b\). Hence there exist non‑zero integer pairs \((a,b)\), \((c,d)\) such that  

\[
a^2+2b^2 = c^2+2d^2 \qquad\text{and}\qquad ac+2bd = 0. \tag{1}
\]

Interpret these as elements of the ring \(\mathbb{Z}[\sqrt{-2}] = \{x+y\sqrt{-2}:x,y\in\mathbb{Z}\}\) with norm \(N(x+y\sqrt{-2}) = x^2+2y^2\).  
Set \(v = a+b\sqrt{-2}\), \(w = c+d\sqrt{-2}\). Then \(N(v)=N(w)\) and the real part of \(v\overline{w}\) is zero, i.e. the vectors are orthogonal in the complex plane. Two non‑zero orthogonal vectors of equal length satisfy \(w = \pm i v\). Computing:

\[
i v = i(a+b\sqrt{-2}) = ia + b i\sqrt{-2} = ia - b\sqrt{2}.
\]

For \(w\) to belong to \(\mathbb{Z}[\sqrt{-2}]\), its real part must be an integer. Hence \(b\sqrt{2}\) must be an integer, so \(b=0\). Then \(v=a\) (an integer) and \(w = i a\). But \(i a = a i\) is not of the form \(x+y\sqrt{-2}\) unless \(a=0\). Thus the only solution to (1) is \(a=b=c=d=0\), contradicting the existence of a square.

---

#### (ii) No equilateral triangle with circumcenter

An equilateral triangle together with its circumcenter would require a triangle with side length \(s\) and a fourth point at distance \(R = s/\sqrt{3}\) from each vertex. Then \(R^2 = s^2/3\) would be an integer (because all squared distances in \(S\) are integers), forcing \(3\mid s^2\). However, we first prove that \(S\) contains **no equilateral triangle at all**.

Suppose there is an equilateral triangle with vertices at \(0, v, w\) after translation. Write \(v=(a,b\sqrt{2})\), \(w=(c,d\sqrt{2})\). Then  

\[
|v|^2 = |w|^2 = |v-w|^2 \;\Longrightarrow\; a^2+2b^2 = c^2+2d^2 \quad\text{and}\quad ac+2bd = \frac{a^2+2b^2}{2}. \tag{2}
\]

The right‑hand side of the second equality must be an integer, so \(a^2+2b^2\) is even; hence \(a\) is even. Write \(a=2a'\). Substituting into (2) gives  

\[
2a'c+2bd = 2a'^2 + b^2 \;\Longrightarrow\; b^2 \text{ is even},\; \text{so } b=2b'.
\]

Then \(a=2a',\, b=2b'\) and (2) becomes  

\[
a'^2+2b'^2 = \frac{c^2+2d^2}{4} \quad\text{and}\quad a'c+2b'd = a'^2+2b'^2. \tag{3}
\]

Thus \((a',b')\) is a smaller integer pair satisfying the same type of equations. By infinite descent, the only integer solution is \(a=b=0\), i.e. \(v=0\). Hence no non‑zero vectors satisfy (2), so an equilateral triangle cannot exist. Consequently the forbidden configuration of type (ii) is impossible.

---

#### (iii) No four vertices of a regular pentagon

In a regular pentagon the side length \(s\) and the diagonal length \(d\) satisfy \(d = \varphi s\) with \(\varphi = \frac{1+\sqrt{5}}{2}\). Then  

\[
\frac{d^2}{s^2} = \varphi^2 = \frac{3+\sqrt{5}}{2},
\]

which is irrational. In \(S\) all squared distances are integers, so the ratio of any two squared distances is rational. Therefore no four points of \(S\) can have only the two distances \(s\) and \(d\) of a regular pentagon.

---

Because none of the three possible 2‑distance four‑point configurations can be realised in \(S\), every four points of \(S\) determine at least three distinct distances.

---

### 2. Total number of distinct distances is \(O(n/\sqrt{\log n})\)

For \(S\) with \(m\) points in each direction (\(n=m^2\)), the distances are \(\sqrt{p^2+2q^2}\) where \(p,q\) are integers with \(|p|,|q|\le m-1\). Distinct distances correspond bijectively to distinct values of the integer \(p^2+2q^2\). Hence  

\[
D = \bigl|\{\,p^2+2q^2 : |p|,|q|\le m-1\,\}\bigr|.
\]

The largest such integer is at most \((m-1)^2+2(m-1)^2 = 3(m-1)^2\). A classical result in number theory (the distribution of norms in the imaginary quadratic field \(\mathbb{Q}(\sqrt{-2})\)) states that the number of integers \(\le X\) representable as \(x^2+2y^2\) is asymptotically \(C\,X/\sqrt{\log X}\) for some constant \(C>0\). Therefore  

\[
D = O\!\left(\frac{m^2}{\sqrt{\log m}}\right) = O\!\left(\frac{n}{\sqrt{\log n}}\right).
\]

In the Vinogradov notation, \(D \ll n/\sqrt{\log n}\).

---

Thus the set \(S\) (or any superset obtained by adding extra lattice points to reach exactly \(n\) points) satisfies all requirements. Such a set exists.
```

---

## v4flash judge verdict

<points>6 out of 7</points>

**Analysis**

The solution correctly constructs a point set from the anisotropic lattice \(L = \{(x,\sqrt{2}y):x,y\in\mathbf{Z}\}\) and claims that it satisfies both required properties.  The main ideas are sound, and the overall argument is essentially correct.  However, there are several shortcomings that prevent the solution from being fully rigorous and complete at the IMO standard.

**1. Classification of 4‑point 2‑distance sets**  
The solution states that the only 4‑point subsets of the plane with exactly two distances are  
(i) a square, (ii) an equilateral triangle together with its circumcenter, (iii) any four vertices of a regular pentagon.  
This list is incomplete; for example, a rhombus with angle \(60^\circ\) is a 4‑point 2‑distance set that contains an equilateral triangle but is not of the “circumcenter” type.  Fortunately, the solution later proves that the lattice contains *no* equilateral triangle at all, which would rule out *any* configuration containing an equilateral triangle (including the rhombus).  Thus the classification error does not cause a logical collapse, but it is an inaccuracy that should be corrected.  A rigorous solution would either cite the known classification correctly (e.g., “every 4‑point 2‑distance set either is a square, contains an equilateral triangle, or is the regular‑pentagon trapezoid”) or avoid the list altogether and argue directly that any 2‑distance set must contain one of these impossible configurations.

**2. Proof that no equilateral triangle exists (infinite descent)**  
The attempted infinite descent argument is not fully justified.  After deducing that \(a\) and \(b\) are even, the solution writes that \((a',b')\) is a smaller integer pair satisfying “the same type of equations”.  The equations obtained after substitution are  
\[
a'c+2b'd = a'^{2}+2b'^{2},\qquad a'^{2}+2b'^{2} = \frac{c^{2}+2d^{2}}{4},
\]  
which are not identical to the original equations (\(a^{2}+2b^{2}=c^{2}+2d^{2}\) and \(ac+2bd=(a^{2}+2b^{2})/2\)).  To continue the descent one must also show that \(c\) and \(d\) are even, so that \(c=2c',\,d=2d'\) and then \((a',b'),(c',d')\) satisfy the original relations.  The solution omits this step, leaving a gap.  The gap can be filled with a small addition, but as written it is not fully rigorous.

**3. Handling of general \(n\)**  
The solution starts with a set \(S\) of size \(m^{2}\) where \(m=\lfloor\sqrt n\rfloor\) and then says “If \(m^{2}<n\) we may add any extra points from the same lattice … the properties below are inherited by subsets, so it suffices to work with \(S\).”  This wording is imprecise: adding points creates a superset, not a subset, and the properties are not automatically inherited upward.  However, because the lattice itself forbids the problematic configurations, any superset contained in the lattice still satisfies the local constraint.  The distinct‑distance bound for the superset also needs a brief justification (the coordinates of added points can be bounded by something like \(O(m)\) so that the previous counting argument still applies).  The ground‑truth solution’s approach (taking a subset of a larger box) is cleaner.  The presented reasoning is not wrong, but it lacks clarity and could be misinterpreted.

**Overall assessment**  
The solution contains the core ideas and reaches the correct conclusion.  The issues are minor gaps and inaccuracies rather than fundamental errors.  With a small amount of additional justification (completing the descent, correcting the classification statement, and clarifying the construction for arbitrary \(n\)) the solution would be fully rigorous.  According to the rubric, this qualifies for **6 out of 7 points** (almost correct, with minor errors or small gaps in logic).