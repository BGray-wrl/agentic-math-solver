# Frontier klt Del Pezzo Verifier

Date: 2026-05-12

The project PDF asks for an explicit normal projective surface over an
algebraically closed field of characteristic `3` such that:

- `X` is klt del Pezzo;
- `rho(X) = 1`;
- `X` has more than `7` singular points.

It explicitly permits several presentation styles: Method A global quotients,
Method B weighted hypersurfaces/complete intersections, and Method C blow-ups
from `P1 x P1` with HJ-chain data.  The new verifier is therefore multi-method
and conservative.

## Files

- `frontier_verifier.py`: verifies one candidate text from stdin or a file.
- `frontier_score_runs.py`: re-scores saved experiment JSON files and ranks
  partial progress.

## Usage

Verify a candidate:

```bash
python3 frontier_verifier.py candidate.txt --target-sing 8
```

Verify pasted text:

```bash
python3 frontier_verifier.py --target-sing 8 <<'EOF'
## Answer
Weights: [2, 2, 7, 7]
Equation: x0^7 + x1^7 + x2^2 + x3^2
EOF
```

Score saved model runs:

```bash
python3 frontier_score_runs.py /path/to/experiment.json --top 20
```

## Verdicts

- `PASS`: proof-level success in a supported class.
- `FAIL`: hard failure of a necessary condition.
- `ONE_SHORT`: otherwise meaningful candidate, but only `target - 1`
  singularities.
- `ESCALATE`: useful partial signal, but a human or stronger verifier must
  prove a remaining global/local condition.
- `UNSUPPORTED`: recognized as outside the current verifier.

The verifier never treats `rho=1 by Lefschetz` as proof in surface dimension.

## What It Checks

### Method B

For weighted hypersurfaces/CIs:

- parses weights and equations;
- checks surface codimension;
- checks char-3 tameness and well-formedness;
- checks weighted homogeneity and Fano index;
- calls local Macaulay2 for codimension and quasi-smoothness;
- detects unit linear-elimination collapse;
- counts exact points on one-dimensional weighted strata over `F_3bar`,
  including endpoint separation;
- computes local cyclic quotient types in supported hypersurface cases;
- computes HJ-chain corrections and `rho_if_rational`.

`rho_if_rational != 1` is reported as `ESCALATE`, not as a proof-level `FAIL`,
unless an independent rationality/Picard proof is supplied.  This is deliberate:
it reduces over-rejection while still warning models that the candidate is
probably not rank one.

### Method C

For HJ baskets such as

```text
{{3},{3},{3},{3},{2,2},{2,2},{2,2}}
```

the verifier computes:

- singular point count;
- total exceptional curve count `R`;
- discrepancy corrections;
- klt inequalities for the chains;
- if a `P1 x P1` base and blow-up count are supplied, numerical `rho` and
  `K_X^2`.

Basket-only Method C text is not accepted as a full proof.  It can still be
classified as `ONE_SHORT` or `ESCALATE`.

### Method A

Method A quotient verification is not implemented.  These answers return
`UNSUPPORTED` unless the model also gives a Method B presentation or enough
explicit fixed-point data for a future Method A checker.

## Regression Results

Known checks after implementation:

- `P(2,2,7,7)`, degree `14`: `ESCALATE`, count `9`,
  `rho_if_rational = 7`.
- linear-elimination `P(2,1,1,14)`: hard `FAIL`, collapses to `P(2,1,1)`
  with only `1` singular point.
- Method C Lacini/Bernasconi basket
  `{{3},{3},{3},{3},{2,2},{2,2},{2,2}}`: `ONE_SHORT` for the full problem,
  since it has `7` singularities.
- `P(2,4,5,25)`: `ESCALATE`, count `10`, `rho_if_rational = 8`.
- original V2 `P(2,2,5,5,5,7)` CI: `ESCALATE` due positive-dimensional
  higher-isotropy stratum/pseudoreflection-risk; it is not credited as a pass.

`frontier_score_runs.py` on the Round 3 JSON files ranked the meaningful
partial signals as:

- `ONE_SHORT` runs with `7` counted singularities;
- `P(2,2,7,7)`-type runs with count OK but bad conditional Picard rank;
- no `PASS` candidates.

## Tradeoffs

### Accuracy

`PASS` is intentionally hard to get.  It requires all supported local checks
and no unresolved Picard/ampleness issue.  This keeps false positives low.

The verifier gives conditional Picard arithmetic for Method B hypersurfaces,
but does not silently convert that into a theorem.  This directly addresses the
previous over-rejection concern.

### False Positives

Low for `PASS`, because unresolved cases become `ESCALATE`.

Moderate for raw partial scores: a model can still get a high `ESCALATE` score
from a numerically interesting but geometrically doomed construction.  The
reason field should be used, not just the score.

### False Negatives

Moderate for unsupported methods.  Method A is currently unsupported, and
Method C needs explicit blow-up/incidence/ampleness data for proof-level
verification.  These are classified as `UNSUPPORTED` or `ESCALATE`, not
mathematical failure.

### Speed

Method C basket checks are effectively instant.  Method B calls Macaulay2 for
quasi-smoothness and usually takes well under a second on the candidates in
this directory.  Heavier CIs or Pfaffian-like presentations may need a timeout
or a specialized verifier.

### Cost

No network calls and no paid APIs are used.  Cost is negligible; the only cost
is local CPU time for Python and Macaulay2.
