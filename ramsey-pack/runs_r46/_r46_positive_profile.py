"""补全循环图族在 (4,6) 上的**正端**剖面：n = 20..35 的合法解个数。

用于回答"这个族从哪里开始有解、到哪里结束有解"，使 n=36..41 的 none_exist
不再是孤立的一段，而是有正端对照的完整剖面。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from marsa.symmetric import (circulant_red, circulant_size,
                             enumerate_circulant)
from marsa.verifier import to_graph6, verify

rows = []
for n in range(20, 36):
    res = enumerate_circulant(n, 4, 6)
    bits = res["found"]
    verified = []
    for b in bits:
        ok, _w = verify(n, circulant_red(n, b), 4, 6)
        verified.append(bool(ok))
    rows.append({
        "n": n,
        "free_parameters": circulant_size(n),
        "space": 1 << circulant_size(n),
        "checked": res["checked"],
        "solutions": res["n_found"],
        "seconds": res["seconds"],
        "all_solutions_verified": all(verified) if verified else None,
        "example_graph6": to_graph6(n, circulant_red(n, bits[0])) if bits else None,
    })
    print(json.dumps(rows[-1], ensure_ascii=False), flush=True)

(HERE / "_r46_positive_profile.json").write_text(
    json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
print("WROTE", flush=True)
