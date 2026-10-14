"""对循环图族在 n = 36..41 上做**完整**枚举，统计全部合法 (4,6)-染色。

CLI 的 enumerate 只返回第一个解，这里用 marsa.symmetric.enumerate_circulant
把整个空间查完并保留每一个合法比特串。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marsa.symmetric import (circulant_red, circulant_size, enumerate_circulant)
from marsa.verifier import to_graph6, verify

OUT = Path(__file__).resolve().parent / "_r46_full_count.json"
rows = []
for n in range(36, 42):
    res = enumerate_circulant(n, 4, 6)
    bits = res["found"]
    row = {
        "n": n,
        "s": 4,
        "t": 6,
        "free_parameters": circulant_size(n),
        "space": 1 << circulant_size(n),
        "checked": res["checked"],
        "solutions": res["n_found"],
        "seconds": res["seconds"],
        "rate": res["rate"],
        "bits_all": bits,
        "bitstrings": [format(b, "0%db" % circulant_size(n)) for b in bits],
        "connection_sets": [
            sorted(d for d in range(1, n // 2 + 1) if b >> (d - 1) & 1)
            for b in bits
        ],
        "graph6_examples": [],
        "verify_all": [],
    }
    # 对**每一个**解都过独立验证器（不是只验第一个）
    for b in bits:
        red = circulant_red(n, b)
        ok, wit = verify(n, red, 4, 6)
        row["verify_all"].append(bool(ok))
        if len(row["graph6_examples"]) < 3:
            row["graph6_examples"].append(to_graph6(n, red))
    row["all_solutions_verified"] = all(row["verify_all"]) if row["verify_all"] else None
    print(json.dumps({k: v for k, v in row.items() if k != "bitstrings"},
                     ensure_ascii=False), flush=True)
    rows.append(row)

OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
print("WROTE", OUT, flush=True)
