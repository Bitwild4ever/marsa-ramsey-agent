"""Fast, exact Cayley-family enumerator for (s,t)=(5,5) on abelian groups.

Design (performance-critical):
  * The red graph is Cay(G,S).  Its adjacency row for group element g is the
    translate of row 0 by g, so we build ONE row (a bitmask over element
    indices) and derive every other row by index translation.
  * Gray-code enumeration of the connection set: consecutive masks differ in
    exactly one inverse-closed pair, so the red row is updated with one XOR.
  * Clique test is exact and uses the standard "extend by larger vertices"
    DP over bitmasks, with a degree prefilter: a k-clique needs every member
    to have degree >= k-1, so vertices below that are dropped first.  This
    is a sound filter (it can only remove vertices that cannot be in a
    k-clique), so it never changes the verdict.
  * Pruning: if the red graph already contains a K_s, or the blue graph
    already contains a K_t, the mask is invalid and we skip the full count.
    Pruning only ever skips masks that are genuinely invalid.

Family: G abelian of order n, S inverse-closed, 0 not in S.  For G = Z_n this
is exactly the circulant family.
"""

import itertools
import sys
import time


# ---------------------------------------------------------------- groups

def divisors(n):
    return [d for d in range(1, n + 1) if n % d == 0]


def smallest_prime(m):
    d = 2
    while d * d <= m:
        if m % d == 0:
            return d
        d += 1
    return m


def is_prime_power(m):
    p = smallest_prime(m)
    x = m
    while x % p == 0:
        x //= p
    return x == 1


def abelian_groups(n):
    """All abelian groups of order n as tuples of prime-power cyclic factors."""
    out = []

    def rec(rem, maxfac, acc):
        if rem == 1:
            out.append(tuple(acc))
            return
        for d in divisors(rem):
            if d == 1 or d > maxfac:
                continue
            if is_prime_power(d):
                rec(rem // d, d, acc + [d])

    rec(n, n, [])
    return sorted(out, reverse=True)


def elements(factors):
    return list(itertools.product(*[range(f) for f in factors]))


def add(a, b, factors):
    return tuple((x + y) % f for x, y, f in zip(a, b, factors))


def neg(a, factors):
    return tuple((-x) % f for x, f in zip(a, factors))


def gcd(a, b):
    while b:
        a, b = b, a % b
    return a


def lcm(a, b):
    return a // gcd(a, b) * b


def order(a, factors):
    o = 1
    for x, f in zip(a, factors):
        if x == 0:
            continue
        o = lcm(o, f // gcd(x, f))
    return o


def free_bits(factors):
    """Return (involutions, inverse_pairs) of G minus {0}."""
    els = [e for e in elements(factors) if any(e)]
    invol = [e for e in els if order(e, factors) == 2]
    pairs = []
    seen = set()
    for e in els:
        if order(e, factors) == 2:
            continue
        ne = neg(e, factors)
        key = frozenset([e, ne])
        if key in seen:
            continue
        seen.add(key)
        pairs.append((e, ne))
    return invol, pairs


# ---------------------------------------------------------------- clique test

def has_clique(adj, k):
    """True iff the graph with adjacency bitmasks `adj` contains a k-clique.

    Exact.  Vertices of degree < k-1 are dropped first (sound: such a vertex
    cannot lie in a k-clique), which is the main speedup on dense-ish graphs.
    """
    n = len(adj)
    if k <= 1:
        return n >= k
    if k == 2:
        return any(adj)
    # degree prefilter
    keep = 0
    for v in range(n):
        if bin(adj[v]).count("1") >= k - 1:
            keep |= 1 << v
    if bin(keep).count("1") < k:
        return False
    adj = [adj[v] & keep for v in range(n)]
    for start in range(n):
        if not (keep >> start) & 1:
            continue
        stack = [(start, adj[start] & ~((1 << (start + 1)) - 1), 1)]
        while stack:
            v, cand, size = stack.pop()
            if size == k:
                return True
            c = cand
            while c:
                low = c & -c
                u = low.bit_length() - 1
                c ^= low
                stack.append((u, c & adj[u], size + 1))
    return False


def count_cliques(adj, k):
    n = len(adj)
    if k <= 1:
        return n
    total = 0
    for start in range(n):
        stack = [(start, adj[start] & ~((1 << (start + 1)) - 1), 1)]
        while stack:
            v, cand, size = stack.pop()
            if size == k:
                total += 1
                continue
            c = cand
            while c:
                low = c & -c
                u = low.bit_length() - 1
                c ^= low
                stack.append((u, c & adj[u], size + 1))
    return total


# ---------------------------------------------------------------- enumeration

def enumerate_group(n, factors, s=5, t=5, limit=None, stop_at_first=True,
                     verbose=False):
    """Exhaustively decide whether some inverse-closed S gives a valid
    (s,t)-colouring of Cay(G,S).  Returns a verdict dict."""
    invol, pairs = free_bits(factors)
    k = len(invol) + len(pairs)
    space = 1 << k
    if limit is not None and space > limit:
        return {"group": factors, "free_parameters": k, "space_size": space,
                "skipped": True, "solutions_found": None,
                "witness_connection_set": None, "elapsed_seconds": 0.0,
                "checked": 0}

    els = elements(factors)
    idx = {e: i for i, e in enumerate(els)}
    full = (1 << n) - 1

    # Each free bit contributes a set of element-indices to the connection set.
    bit_sets = []
    for e in invol:
        bit_sets.append(1 << idx[e])
    for (e, ne) in pairs:
        bit_sets.append((1 << idx[e]) | (1 << idx[ne]))

    # Translation table: index of els[i] + els[j].
    trans = [[idx[add(els[i], els[j], factors)] for j in range(n)]
             for i in range(n)]

    def adj_from_row0(row0):
        """All adjacency rows by translation of row 0."""
        adj = [0] * n
        for i in range(n):
            m = 0
            c = row0
            while c:
                low = c & -c
                j = low.bit_length() - 1
                c ^= low
                m |= 1 << trans[i][j]
            adj[i] = m
        return adj

    found = 0
    witness = None
    checked = 0
    t0 = time.time()

    # Gray-code walk over the 2^k masks so each step flips one bit_set.
    S_mask = 0
    prev_gray = 0
    for step in range(space):
        gray = step ^ (step >> 1)
        if step > 0:
            diff = gray ^ prev_gray
            b = diff.bit_length() - 1
            S_mask ^= bit_sets[b]
        prev_gray = gray

        adj = adj_from_row0(S_mask)
        checked += 1

        # Exact pruning: reject as soon as either colour has a forbidden clique.
        if has_clique(adj, s):
            continue
        comp = [full & ~adj[i] & ~(1 << i) for i in range(n)]
        if has_clique(comp, t):
            continue

        found += 1
        if witness is None:
            witness = sorted(i for i in range(n) if S_mask >> i & 1)
        if stop_at_first:
            break

    return {"group": factors, "free_parameters": k, "space_size": space,
            "solutions_found": found, "witness_connection_set": witness,
            "elapsed_seconds": round(time.time() - t0, 2), "skipped": False,
            "checked": checked}


def group_tag(g, n):
    return "Z_%d" % n if g == (n,) else " x ".join("Z_%d" % f for f in g)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 44
    s = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    t = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    limit = int(sys.argv[4]) if len(sys.argv) > 4 else (1 << 22)
    print("n=%d s=%d t=%d limit=%d" % (n, s, t, limit), flush=True)
    for g in abelian_groups(n):
        invol, pairs = free_bits(g)
        k = len(invol) + len(pairs)
        tag = group_tag(g, n)
        if (1 << k) > limit:
            print("  %-22s free=%3d space=2^%d SKIPPED (over limit)"
                  % (tag, k, k), flush=True)
            continue
        r = enumerate_group(n, g, s, t, limit=limit)
        print("  %-22s free=%3d space=%10d checked=%10d solutions=%s time=%ss witness=%s"
              % (tag, k, r["space_size"], r["checked"], r["solutions_found"],
                 r["elapsed_seconds"], r["witness_connection_set"]), flush=True)


if __name__ == "__main__":
    main()
