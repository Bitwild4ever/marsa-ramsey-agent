"""Sharded, resumable driver for the Cayley-family enumerator.

The sandbox kills a script at ~110 s and returns no partial output, so a full
2^k sweep must be split into shards that each finish well inside that window.
This driver runs ONE shard per invocation and prints a single machine-readable
line, so the caller can accumulate results across invocations.

Usage:
    cayley_shard.py <n> <group-spec> <start> <count> [s] [t]

  group-spec is "cyclic" for Z_n, or a comma list of factors, e.g. "2,22".

A shard covers mask indices [start, start+count) of the Gray-code walk.  The
Gray-code state at index `start` is reconstructed directly (gray(start) and
S_mask(start) are computed in closed form), so shards are independent and can
be run in any order.

Output line:
    SHARD n=.. group=.. start=.. count=.. checked=.. solutions=.. witness=.. time=..
`solutions` counts valid colourings found inside this shard only.
"""

import sys
import time

sys.path.insert(0, "workspace")
from cayley_exhaust import (free_bits, elements, add, has_clique, group_tag)


def gray(g):
    return g ^ (g >> 1)


def smask_at(step, bit_sets):
    """Connection-set bitmask at Gray-code index `step`, in closed form."""
    m = 0
    g = gray(step)
    b = 0
    while g:
        if g & 1:
            m ^= bit_sets[b]
        g >>= 1
        b += 1
    return m


def run_shard(n, factors, start, count, s=5, t=5):
    invol, pairs = free_bits(factors)
    k = len(invol) + len(pairs)
    space = 1 << k
    end = min(start + count, space)

    els = elements(factors)
    idx = {e: i for i, e in enumerate(els)}
    full = (1 << n) - 1

    bit_sets = [1 << idx[e] for e in invol]
    for (e, ne) in pairs:
        bit_sets.append((1 << idx[e]) | (1 << idx[ne]))

    trans = [[idx[add(els[i], els[j], factors)] for j in range(n)]
             for i in range(n)]

    def adj_from_row0(row0):
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

    S_mask = smask_at(start, bit_sets)
    prev_gray = gray(start)
    found = 0
    witness = None
    checked = 0
    t0 = time.time()

    for step in range(start, end):
        if step > start:
            g = gray(step)
            b = (g ^ prev_gray).bit_length() - 1
            S_mask ^= bit_sets[b]
            prev_gray = g
        adj = adj_from_row0(S_mask)
        checked += 1
        if has_clique(adj, s):
            continue
        comp = [full & ~adj[i] & ~(1 << i) for i in range(n)]
        if has_clique(comp, t):
            continue
        found += 1
        if witness is None:
            witness = sorted(i for i in range(n) if S_mask >> i & 1)

    return {"n": n, "group": factors, "k": k, "space": space,
            "start": start, "end": end, "checked": checked,
            "solutions": found, "witness": witness,
            "elapsed": round(time.time() - t0, 2)}


def main():
    n = int(sys.argv[1])
    spec = sys.argv[2]
    start = int(sys.argv[3])
    count = int(sys.argv[4])
    s = int(sys.argv[5]) if len(sys.argv) > 5 else 5
    t = int(sys.argv[6]) if len(sys.argv) > 6 else 5

    factors = (n,) if spec == "cyclic" else tuple(int(x) for x in spec.split(","))
    r = run_shard(n, factors, start, count, s, t)
    print("SHARD n=%d group=%s k=%d space=%d start=%d end=%d checked=%d "
          "solutions=%d witness=%s time=%ss"
          % (r["n"], group_tag(r["group"], n), r["k"], r["space"],
             r["start"], r["end"], r["checked"], r["solutions"],
             r["witness"], r["elapsed"]), flush=True)


if __name__ == "__main__":
    main()
