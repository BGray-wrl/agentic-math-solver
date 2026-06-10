#!/usr/bin/env python3
"""
Arithmetic probe for the natural Method C generalization of the known
characteristic-3 Frobenius-tangent construction.

Model:
  Start from P1xP1.
  Let C be a smooth rational curve triple-tangent to n chosen fibers.
  Blow up three times over each chosen tangency, as in the known 7-point
  construction.  Contract:
    - each fiber F_i, now a [-3] curve;
    - each canonical chain H_i-G_i = [2,2];
    - the final strict transform of C, a single [-m] curve.

Then b=3n, R=3n+1, so rho(X)=2+b-R=1 automatically.
This script checks the remaining numerical constraints.
"""

from fractions import Fraction


def correction_single(m: int) -> Fraction:
    """K^2 correction for a single [-m] HJ chain."""
    return Fraction((m - 2) ** 2, m)


def row(n: int, m: int) -> dict:
    # K_Y^2 = K_{P1xP1}^2 - number of blowups.
    KY2 = Fraction(8 - 3 * n, 1)
    # n isolated [-3] singularities, n [2,2] canonical A2 chains, and C=[m].
    KX2 = KY2 + n * correction_single(3) + correction_single(m)
    # Pullback of -K_X intersects each uncontracted connector E_i by:
    # 1 - alpha(F_i) - alpha(C), where alpha([-q])=(q-2)/q.
    connector = Fraction(1, 1) - Fraction(1, 3) - Fraction(m - 2, m)
    sing_count = 2 * n + 1
    return {
        "n": n,
        "m": m,
        "sing_count": sing_count,
        "KX2": KX2,
        "connector_intersection": connector,
        "passes_numeric": KX2 > 0 and connector > 0 and sing_count >= 8,
    }


def main():
    print("n = chosen triple-tangent fibers")
    print("m = -C^2 after the 3n blowups")
    print("singularities = n*[3] + n*[2,2] + [m], count = 2n+1")
    print()
    print(f"{'n':>2} {'m':>2} {'#sing':>5} {'KX^2':>8} {'(-K).E':>8} verdict")
    for n in range(1, 9):
        for m in range(2, 13):
            r = row(n, m)
            if n >= 4 or r["passes_numeric"]:
                verdict = "numeric pass" if r["passes_numeric"] else ""
                print(
                    f"{n:2d} {m:2d} {r['sing_count']:5d} "
                    f"{str(r['KX2']):>8} {str(r['connector_intersection']):>8} {verdict}"
                )

    print()
    print("Conclusion:")
    print("  For ampleness on the connector curves E_i, need (-K_X).E_i > 0,")
    print("  i.e. m < 6.  With m=2,3,4,5 and K_X^2>0, one gets n <= 3.")
    print("  Hence this one-central-Frobenius-curve Method C family cannot exceed")
    print("  2*3+1 = 7 singularities.")


if __name__ == "__main__":
    main()
