"""
Canned mock responses for smoke testing the agentic loop without API calls.
"""

MOCK_TURN_1 = """\
Let me start by implementing the basic building blocks and testing on small cases.

```python
import numpy as np

def hadamard_2():
    return np.array([[1, 1], [1, -1]], dtype=np.int8)

def kronecker_hadamard(*matrices):
    result = matrices[0]
    for m in matrices[1:]:
        result = np.kron(result, m)
    return result.astype(np.int8)

# Test: H_2 x H_2 = H_4
H2 = hadamard_2()
H4 = kronecker_hadamard(H2, H2)
print("H_4:")
print(H4)
product = H4.astype(np.int32) @ H4.T.astype(np.int32)
print("H4 @ H4^T:")
print(product)
print(f"Valid: {np.array_equal(product, 4 * np.eye(4, dtype=np.int32))}")
```
"""

MOCK_TURN_2 = """\
Good, the Kronecker product works. Now let me try the Paley construction for order 168.

```python
import numpy as np

# Legendre symbol for p=167
p = 167

def legendre(a, p):
    if a % p == 0:
        return 0
    return 1 if pow(a, (p-1)//2, p) == 1 else -1

# Build Jacobsthal matrix J (p x p)
J = np.zeros((p, p), dtype=np.int8)
for i in range(p):
    for j in range(p):
        J[i, j] = legendre((j - i) % p, p)

# Paley Type I: H = I + Q where Q is built from J
# For p ≡ 3 mod 4: H = [[1, j^T], [-j, J + I]]  where j = all-ones
n = p + 1  # 168
H = np.ones((n, n), dtype=np.int8)
H[0, 0] = 1
H[0, 1:] = 1
H[1:, 0] = -1
H[1:, 1:] = J + np.eye(p, dtype=np.int8)
# Fix: set diagonal of J+I block
for i in range(1, n):
    for j in range(1, n):
        if J[i-1, j-1] == 0:
            H[i, j] = 1  # diagonal

# Verify
product = H.astype(np.int32) @ H.T.astype(np.int32)
diag_ok = np.all(np.diag(product) == n)
off_diag = product - np.diag(np.diag(product))
print(f"Order {n}: diag_ok={diag_ok}, max_off_diag={np.max(np.abs(off_diag))}")
print(f"Shape: {H.shape}, entries in {{-1,1}}: {set(np.unique(H).tolist()) == {-1, 1}}")
```
"""

MOCK_TURN_3 = """\
Now let me build the full 668 matrix using a mock approach for testing.

```python
import numpy as np

# For mock testing: just output a small verification message
n = 668
print(f"Target order: {n}")
print(f"668 = 4 x 167")
print(f"Building mock matrix for pipeline test...")

# Create a fake "matrix" (won't be valid, just for pipeline testing)
H = np.ones((4, 4), dtype=np.int8)
H[1, 0] = -1
H[2, 0] = -1
H[2, 1] = -1
H[3, 0] = -1
H[3, 2] = -1

product = H.astype(np.int32) @ H.T.astype(np.int32)
print(f"Small test - order 4, valid: {np.array_equal(product, 4 * np.eye(4, dtype=np.int32))}")
print("Mock turn 3 complete - would continue construction here")
```
"""

MOCK_RESPONSES = [MOCK_TURN_1, MOCK_TURN_2, MOCK_TURN_3]
