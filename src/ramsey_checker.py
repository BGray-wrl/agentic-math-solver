"""
Programmatic verifier for ramsey-hypergraphs solutions.

Checks whether a hypergraph (V, H) satisfies:
  1. |V| >= 64
  2. |H| <= 20
  3. No isolated vertices (every vertex in V is in at least one edge)
  4. No partition of size > 20

A "partition of size n" means there exist D ⊆ V and P ⊆ H with |D| = n
such that every member of D is in exactly one member of P.

Equivalently, for check (4): for every subset P ⊆ H, the number of vertices
that appear in exactly one edge of P must be <= 20.
"""

from __future__ import annotations

import re


def parse_hypergraph(text: str) -> tuple[set[int], list[frozenset[int]]]:
    """Parse a hypergraph from model output text.

    Tries several formats:
      - {1,2,3},{4,5},{6,7,8}  (comma-separated edge sets)
      - {1, 2, 3}, {4, 5}     (with spaces)
      - One edge per line

    Returns (V, H) where V is the vertex set and H is the list of edges.
    """
    # Find all {a,b,...} patterns
    edge_pattern = r'\{([0-9,\s]+)\}'
    matches = re.findall(edge_pattern, text)

    edges: list[frozenset[int]] = []
    vertices: set[int] = set()

    for match in matches:
        nums = [x.strip() for x in match.split(',') if x.strip()]
        edge = frozenset(int(x) for x in nums if x.isdigit())
        if edge:
            edges.append(edge)
            vertices.update(edge)

    # Deduplicate edges (keep order)
    seen: set[frozenset[int]] = set()
    unique_edges = []
    for e in edges:
        if e not in seen:
            seen.add(e)
            unique_edges.append(e)

    return vertices, unique_edges


def check_no_large_partition(H: list[frozenset[int]], max_allowed: int = 20) -> tuple[bool, int, int | None]:
    """Check that no subset P ⊆ H yields a partition of size > max_allowed.

    Uses bitmask approach: for each vertex, precompute which edges contain it.
    For each subset P (bitmask over edges), count vertices with popcount(v_mask & P) == 1.

    Returns (passes, max_partition_found, worst_subset_mask).
    """
    m = len(H)
    if m > 25:
        # Safety: 2^25 = 33M subsets; anything larger is infeasible
        raise ValueError(f"|H| = {m} too large for exhaustive check (max 25)")

    # Collect all vertices across all edges
    all_verts: set[int] = set()
    for edge in H:
        all_verts.update(edge)

    # For each vertex, compute bitmask of which edges contain it
    v_masks: list[int] = []
    for v in sorted(all_verts):
        mask = 0
        for j, edge in enumerate(H):
            if v in edge:
                mask |= (1 << j)
        v_masks.append(mask)

    max_partition = 0
    worst_mask = None

    for P in range(1, 1 << m):
        count = 0
        for vm in v_masks:
            intersection = vm & P
            # popcount == 1: vertex is in exactly one edge of P
            if intersection and (intersection & (intersection - 1)) == 0:
                count += 1
        if count > max_partition:
            max_partition = count
            worst_mask = P
            # Early exit if we already exceed the limit
            if count > max_allowed:
                return False, max_partition, worst_mask

    return max_partition <= max_allowed, max_partition, worst_mask


def verify_hypergraph(V: set[int], H: list[frozenset[int]], min_V: int = 64, max_H: int = 20, max_partition: int = 20) -> dict:
    """Full verification of a ramsey-hypergraph construction.

    Returns dict with:
      valid: bool
      checks: dict of individual results
      violations: list of descriptions
    """
    violations = []
    checks = {}

    # Check 1: |V| >= min_V
    checks["V_size"] = len(V)
    checks["V_size_pass"] = len(V) >= min_V
    if not checks["V_size_pass"]:
        violations.append(f"|V| = {len(V)} < {min_V}")

    # Check 2: |H| <= max_H
    checks["H_size"] = len(H)
    checks["H_size_pass"] = len(H) <= max_H
    if not checks["H_size_pass"]:
        violations.append(f"|H| = {len(H)} > {max_H}")

    # Check 3: No isolated vertices
    covered = set()
    for edge in H:
        covered.update(edge)
    isolated = V - covered
    checks["no_isolated"] = len(isolated) == 0
    checks["isolated_count"] = len(isolated)
    if not checks["no_isolated"]:
        violations.append(f"{len(isolated)} isolated vertices")

    # Check 4: All edge vertices are in V
    edge_verts = set()
    for edge in H:
        edge_verts.update(edge)
    extra = edge_verts - V
    checks["edges_subset_V"] = len(extra) == 0
    if not checks["edges_subset_V"]:
        violations.append(f"{len(extra)} vertices in edges but not in V")

    # Check 5: No partition of size > max_partition
    # Only run if |H| is small enough for exhaustive check
    if len(H) <= 25:
        passes, max_part, worst = check_no_large_partition(H, max_partition)
        checks["max_partition_found"] = max_part
        checks["no_large_partition"] = passes
        checks["worst_subset_mask"] = worst
        if not passes:
            violations.append(f"Found partition of size {max_part} > {max_partition} (subset mask: {worst})")
    else:
        checks["max_partition_found"] = None
        checks["no_large_partition"] = None
        violations.append(f"|H| = {len(H)} too large for exhaustive partition check")

    return {
        "valid": len(violations) == 0,
        "checks": checks,
        "violations": violations,
    }


def verify_solution_text(solution_text: str) -> dict:
    """End-to-end: parse and verify a hypergraph from solution text.

    The model output should contain the hypergraph in {a,b,...} format.
    The vertex set V is inferred as all vertices appearing in edges.
    """
    V, H = parse_hypergraph(solution_text)

    if not H:
        return {
            "valid": False,
            "parse_error": True,
            "V_size": 0,
            "H_size": 0,
            "checks": {},
            "violations": ["Could not parse any hypergraph edges from solution text"],
        }

    result = verify_hypergraph(V, H)
    result["parse_error"] = False
    result["V_size"] = len(V)
    result["H_size"] = len(H)
    return result
