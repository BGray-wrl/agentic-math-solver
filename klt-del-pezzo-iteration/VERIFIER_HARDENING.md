# Verifier hardening — round 2 (post-V2 retraction)

After the adversarial review retracted the V2 "verified solution", I strengthened `klt_verifier.py` with two new checks that catch the failure mode the adversary exposed.

## Bug recap

The retracted V2 candidate was in P(2,2,5,5,5,7) with three weight-5 variables. The adversary showed:
1. The mu_5 isotropy stratum is the 2-dim plane {x_0=x_1=0}, not three separate lines.
2. X meets this plane in a 1-dim conic (not isolated points).
3. The mu_5 action on the local tangent of X at a generic conic point has codim-1 fixed locus → **pseudoreflection** → smooth quotient by Chevalley–Shephard–Todd.
4. The conic contributes NO singular points to the coarse projective surface; the count drops to 5 (just the mu_2 line points), short of 8.

The old verifier counted three pairwise lines L_{23}, L_{24}, L_{34} contributing 2+2+2 = 6 points and credited all of them.

## New checks added

### Check A: maximal-isotropy strata

The M2 script now enumerates, for each prime q dividing some weight, the maximal index subset I_q with q | w_i for all i ∈ I_q. This is the actual mu_q stratum. The script computes X ∩ stratum and reports its projective dimension.

For V2 with weights (2,2,5,5,5,7):
- Prime 2: I = {0,1}, stratum dim 1.
- Prime 5: I = {2,3,4}, stratum dim 2.
- Prime 7: I = {5}, stratum dim 0.

### Check B: pseudoreflection-risk skip

For each prime q where I_q ≥ 3 (i.e., the stratum has dim ≥ 2) AND X ∩ stratum has positive dim:
- The verifier flags q as a **pseudoreflection-risk prime**.
- Pairwise singular-line contributions whose isotropy is divisible by a risk-prime are **excluded** from the count.
- Isolated coord-point contributions with weight divisible by a risk-prime are also excluded.

This is conservative: it may over-reject valid singular points. But it correctly catches V2-style false positives where the X∩stratum curve is smoothed by pseudoreflection.

A finer fix (still TODO) would explicitly compute the local mu_q-action on T_P X at each potentially-singular point and check whether the fixed locus is codim 1 (true pseudoreflection → skip) vs codim 0 (trivial action → smooth) vs codim ≥ 2 (genuine quotient sing → count). The conservative heuristic above is sufficient for the current batch.

## Validation

| Candidate | Old verifier | Hardened verifier | Correct? |
|---|---|---|---|
| Warmup `P(2,2,5,5), F = x0^5+x1^5+x2^2+x3^2` | score 7 (sing 7) | score 7 (sing 7) | ✓ |
| `P(2,4,5,25), F = x0^15+...+x2*x3` | score 7 (sing 21) | score 7 (sing 21) | ✓ (no 3-weight common factor) |
| V2 `P(2,2,5,5,5,7) CI`  | score 7 (sing 11, false) | **score 5 (sing 5)** | ✓ correct retraction |
| gpt-oss exp4 `P(2,2,5,5,11) CI` (one-short before) | score 6 (sing 7) | score 6 (sing 7) | ✓ unchanged (no 3-weight common factor) |

## Status

The running experiments (relaunched after the user said "continue as you were") still use the OLD verifier in memory (Python module caching). The hardened verifier will be applied at end-of-experiment **re-aggregation** to filter false positives.

Anyone re-verifying candidates from these or future runs should use the hardened `klt_verifier.py` from this point onward.
