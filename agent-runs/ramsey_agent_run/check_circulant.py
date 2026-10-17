"""Cross-check the local Cayley enumerator against the engine's circulant verdicts.

Known anchors (engine, family=circulant, (s,t)=(5,5)):
  n=38 : exists   (a valid circulant colouring is known)
  n=43 : none     (engine exhaustive; the known 43-vertex colouring is NOT circulant)
  n=44 : none     (engine exhaustive, 2^22 members)
  n=45 : none     (engine exhaustive, 2^22 members)
  n=46 : none     (engine exhaustive; also impossible by R(5,5) <= 46)

If the local code reproduces these, it is trustworthy for non-cyclic groups.

Usage:  check_circulant.py [n1 n2 ...]
With no arguments it runs the full anchor list (slow: several minutes).
"""
import sys
sys.path.insert(0, "workspace")
from cayley_exhaust import enumerate_group

ANCHORS = [(38, "exists"), (43, "none"), (44, "none"), (45, "none"), (46, "none")]

want = [int(a) for a in sys.argv[1:]]
todo = [a for a in ANCHORS if not want or a[0] in want]

bad = 0
for n, expect in todo:
    r = enumerate_group(n, (n,), 5, 5, stop_at_first=True)
    got = "exists" if r["solutions_found"] else "none"
    ok = "OK      " if got == expect else "MISMATCH"
    if got != expect:
        bad += 1
    print("%s n=%3d circulant free=%2d space=%9d checked=%9d solutions=%s expect=%s time=%ss witness=%s"
          % (ok, n, r["free_parameters"], r["space_size"], r["checked"],
             r["solutions_found"], expect, r["elapsed_seconds"],
             r["witness_connection_set"]), flush=True)

print("MISMATCHES:", bad, flush=True)
