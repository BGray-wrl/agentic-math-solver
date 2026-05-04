"""
Prompts for the Hadamard agentic coding attack (v2).

Epoch-inspired: allow thinking out loud, concrete pseudocode scaffolding,
turn budget awareness, reflection at end.
"""

SYSTEM_PROMPT = """\
You are an expert mathematician and Python programmer working on an open problem.

**Problem**: Construct a Hadamard matrix of order 668.

A Hadamard matrix H of order n is an n×n matrix with entries in {+1, −1} satisfying H·H^T = n·I.

You have access to a Python execution environment. Each code block you write will be executed and you'll see the output. The environment is **stateless** — each execution starts fresh, so you must include all imports and definitions every time.

**Available libraries**: numpy, scipy, sympy, mpmath, itertools, collections.

Feel free to think out loud about your mathematical reasoning. Mix prose analysis with code freely — just put executable code in ```python blocks and make sure to `print()` results.

**Output format for candidate matrices:**
Large matrices (like 668×668) are too big to print to stdout. Instead, write them to a CSV file:
```python
import os
output_dir = os.environ.get("HADAMARD_OUTPUT_DIR", ".")
path = os.path.join(output_dir, "candidate.csv")
import numpy as np
np.savetxt(path, H, fmt="%d", delimiter=",")
print(f"Candidate matrix written to {path}, shape {H.shape}")
```
I will automatically detect the file and programmatically verify H·H^T = 668·I. You'll get detailed feedback: orthogonality percentage, perfect row count, worst row pairs, and a quality score.

For small test matrices (order ≤ 20), printing CSV to stdout is fine.

**Key mathematical facts:**
- 668 = 4 × 167, where 167 is prime and 167 ≡ 3 (mod 4)
- Hadamard matrices of order 4p (p odd prime) can be constructed via:
  - **Williamson construction** (most promising for this problem)
  - Goethals-Seidel arrays
  - Turyn-type sequences
"""

# Two initial prompts — same construction family (Williamson) but different search strategies
INITIAL_PROMPT_WILLIAMSON_QR = """\
Let's construct a Hadamard matrix of order 668 = 4 × 167.

**Construction: Williamson method with quadratic residue seeding.**

The Williamson construction builds a 4p × 4p Hadamard matrix from four p × p symmetric circulant {±1} matrices A, B, C, D satisfying:

    A² + B² + C² + D² = 4p · I

where the matrices commute (all circulant). Equivalently, for the first rows a, b, c, d of length p:

    PAF_a(k) + PAF_b(k) + PAF_c(k) + PAF_d(k) = 0  for all k = 1, ..., (p-1)/2

where PAF_x(k) = Σᵢ x[i] · x[(i+k) mod p] is the periodic autocorrelation function.

The 4p × 4p matrix is then:
    H = [[A, B, C, D],
         [-B, A, -D, C],
         [-C, D, A, -B],
         [-D, -C, B, A]]

**Pseudocode for your implementation:**

```
Step 1 — Build and test the Williamson array framework:
  def circulant(first_row):
      # Build p×p circulant matrix from first row
  def williamson_matrix(a, b, c, d):
      # Build 4p×4p matrix using the array above
  def check_paf(seq):
      # Compute PAF for all shifts k=1...(p-1)/2
      # Return list of PAF values
  def check_williamson(a, b, c, d):
      # Return True if sum of PAFs is 0 for all shifts
  # TEST on p=3 (order 12): known Williamson sequences exist

Step 2 — Seed from quadratic residues mod 167:
  QR = {quadratic residues mod 167}
  base_seq = [+1 if i in QR else -1 for i in range(167)]
  # The Legendre symbol gives a sequence with good autocorrelation
  # Use it as starting point for a, set b=c=d to all-ones initially
  # Compute PAF defect and iteratively improve

Step 3 — Search by local perturbation:
  # Start from QR-seeded sequences
  # Flip bits to reduce total PAF defect
  # Use hill-climbing or simulated annealing
  # The search space for symmetric sequences is 2^84 (half of 167)

Step 4 — Build and verify full 668×668 matrix:
  H = williamson_matrix(a, b, c, d)
  product = H @ H.T
  assert product == 668 * I
  # Write to file (too big for stdout):
  import os
  np.savetxt(os.path.join(os.environ["HADAMARD_OUTPUT_DIR"], "candidate.csv"), H, fmt="%d", delimiter=",")
```

Start with Step 1 — implement and test on p=3 (order 12). Here is a known Williamson solution for p=3:
  a = [1, 1, 1], b = [1, 1, -1], c = [1, -1, 1], d = [1, -1, -1]

Verify your framework produces a valid Hadamard matrix of order 12, then move to Steps 2-4.

Write Python code now.
"""

INITIAL_PROMPT_WILLIAMSON_SEARCH = """\
Let's construct a Hadamard matrix of order 668 = 4 × 167.

**Construction: Williamson method with structured search.**

The Williamson construction builds a 4p × 4p Hadamard matrix from four p × p symmetric circulant {±1} matrices A, B, C, D satisfying:

    A² + B² + C² + D² = 4p · I

For p=167 (prime, ≡ 3 mod 4), we need four symmetric {±1} sequences of length 167 whose periodic autocorrelation functions sum to zero at every non-zero shift.

**Key insight**: Williamson sequences are **symmetric** (palindromic): a[k] = a[p-k]. This halves the search space to 2^84 per sequence instead of 2^167.

**Pseudocode for your implementation:**

```
Step 1 — Framework (same as standard Williamson):
  def circulant(first_row): ...
  def williamson_matrix(a, b, c, d): ...
  def paf(seq, k):
      return sum(seq[i] * seq[(i+k) % p] for i in range(p))
  def total_paf_defect(a, b, c, d):
      return sum(abs(paf(a,k)+paf(b,k)+paf(c,k)+paf(d,k)) for k in range(1, (p+1)//2))
  # TEST on p=3, p=5, p=7

Step 2 — Construct good starting sequences using number theory:
  # Legendre symbol mod 167
  leg = [kronecker(i, 167) for i in range(167)]  # from sympy
  # Try: a = leg, b = leg, c = all-ones, d = all-ones
  # Or: a = leg, b = c = d = modified leg
  # Evaluate PAF defect for various starting configs

Step 3 — Optimize via stochastic local search:
  # Given 4 sequences, try flipping one bit at a time
  # Accept if total_paf_defect decreases (greedy)
  # Or use simulated annealing with temperature schedule
  # Exploit symmetry: only flip positions 0..83 (rest mirrors)
  # Target: total_paf_defect == 0

Step 4 — Assemble and verify the 668×668 matrix:
  # Write candidate to file (too big for stdout):
  import os
  np.savetxt(os.path.join(os.environ["HADAMARD_OUTPUT_DIR"], "candidate.csv"), H, fmt="%d", delimiter=",")
```

**Important constraints:**
- Each sequence must be length 167 with entries ±1
- Each sequence must be symmetric: a[k] = a[167-k] for k=1,...,166
- The PAF condition: Σ PAF_x(k) = 0 for all k ≠ 0

Start with Step 1 — implement and test on p=3 (order 12). Known solution:
  a = [1, 1, 1], b = [1, 1, -1], c = [1, -1, 1], d = [1, -1, -1]

Then move quickly to Step 2 — construct Legendre-symbol-based starting sequences for p=167 and evaluate the PAF defect. Don't spend more than 2-3 turns on small test cases.

Write Python code now.
"""

FEEDBACK_TEMPLATE = """\
**Turn {turn}/{max_turns} complete.** ({turns_remaining} turns remaining)

I ran your code. Here is the output:

```
{stdout}
```

{error_section}

{checker_section}

{phase_nudge}

Continue working. You may think out loud about your approach, but include executable Python code in ```python blocks.
"""

PHASE_NUDGE_EARLY = """\
**Phase check**: You should have a working Williamson framework tested on p=3 by now. \
If you do, move on to building starting sequences for p=167. Don't over-test small cases."""

PHASE_NUDGE_MID = """\
**Phase check**: By now you should be searching for Williamson sequences of length 167. \
If your current approach isn't reducing the PAF defect, try a different seeding strategy \
or switch to Goethals-Seidel construction."""

PHASE_NUDGE_LATE = """\
**Phase check**: Time is running short. If you haven't produced a 668×668 candidate yet, \
simplify your approach. Even a near-miss (low PAF defect) is valuable data for a future run."""

CHECKER_PASS = "**VERIFICATION PASSED** — The matrix is a valid Hadamard matrix of order {order}!"

CHECKER_FAIL = """\
**Programmatic verification result:**
- Order: {order}×{order} (target: {target})
- Valid: {valid}
- Violations: {violations}
{detail_section}

Use this specific feedback to fix your construction.
"""

CHECKER_DETAIL_ORTHOGONALITY = """\
**Orthogonality details:**
- {nonzero_count} non-zero off-diagonal entries in H·H^T (should all be 0)
- Max absolute off-diagonal value: {max_off}
- Worst row pairs (row_i, row_j, dot_product):
{worst_pairs}
"""

STALL_NUDGE = """\
You seem stuck. Concrete suggestions:

1. If Williamson search isn't converging, try **different starting sequences**:
   - All four = Legendre symbol mod 167
   - a = Legendre, b = negated Legendre, c = d = all-ones
   - Random symmetric sequences with the right row sums
2. If your search is too slow, **use FFT for PAF computation** (O(p log p) instead of O(p²)):
   ```python
   from numpy.fft import fft, ifft
   def paf_fft(seq):
       F = fft(seq)
       return np.real(ifft(F * np.conj(F)))  # autocorrelation via FFT
   ```
3. If Williamson seems hopeless, try **Goethals-Seidel** construction instead:
   - Needs supplementary difference sets in Z_167
   - Or try the **doubling construction**: build H_334 first, then H_2 ⊗ H_334...
     but 334 = 2×167 isn't divisible by 4, so this doesn't directly work.
4. **Paley conference matrix** C of order 167 (Legendre symbol):
   H = [[1, j^T], [-j, C+I]] gives order 168. Can't reach 668 by Kronecker from 168.

The most promising path remains Williamson with smart search. Focus there.
"""

REFLECTION_PROMPT = """\
This is the final turn. Let's reflect on what happened.

Please provide:
1. **What approaches did you try?** List each construction method and search strategy.
2. **What worked?** Any partial successes (low PAF defects, valid sub-matrices, etc.)
3. **What didn't work and why?** Specific failure modes.
4. **Best result**: What was the closest you got? (e.g., "PAF defect of X with sequences Y")
5. **What would you try next** if you had 50 more turns?
6. **Any code or sequences worth saving** for a future attempt? Print them.

This information will be saved and fed into future runs to avoid repeating dead ends.
"""
