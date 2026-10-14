"""交叉校验：枚举器判定 vs 独立判定器 D vs 独立验证器 C。

路径 A: marsa.symmetric.FastChecker.is_valid
        枚举器 & sweep 实际使用的判定
路径 D: _r46_direct.DirectChecker.is_valid
        第二路全空间判定（全部 C(n,k) 子集，不去重、不降维、不用平移对称性）
路径 C: marsa.verifier.verify
        独立验证器（显式布尔矩阵 + combinations），即 CLI `verify`

步骤：
  (1) 样本上 A / C / D 逐条对比；
  (2) 全空间用 A 与 D 各扫一遍，比对合法解个数（防漏判）；
  (3) n=36,37 额外用 C 做全空间扫描。
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from _r46_direct import DirectChecker                                    # noqa: E402
from marsa.symmetric import FastChecker, circulant_red, circulant_size    # noqa: E402
from marsa.verifier import verify                                         # noqa: E402

random.seed(20240606)
OUT = HERE / "_r46_crosscheck.json"
VERIFIER_FULL_SCAN = {36, 37}

report = []
for n in range(36, 42):
    k = circulant_size(n)
    space = 1 << k
    fast = FastChecker(n, 4, 6)
    direct = DirectChecker(n, 4, 6)

    samples = {0, space - 1, 1}
    for b in range(k):
        samples.add(1 << b)
    for _ in range(200):
        samples.add(random.randrange(space))
    for _ in range(60):
        samples.add(random.randrange(space) & random.randrange(space))
    for _ in range(60):
        samples.add(random.randrange(space) | random.randrange(space))
    samples = sorted(samples)

    disagree = []
    t0 = time.perf_counter()
    for bits in samples:
        a = bool(fast.is_valid(bits))
        d = bool(direct.is_valid(bits))
        c, wit = verify(n, circulant_red(n, bits), 4, 6)
        if not (a == d == bool(c)):
            disagree.append({"bits": bits, "A_fastchecker": a, "C_verifier": bool(c),
                             "D_direct": d, "witness": list(wit) if wit else None})
    sample_seconds = round(time.perf_counter() - t0, 2)

    row = {"n": n, "free_parameters": k, "space": space,
           "samples_crosschecked": len(samples), "sample_seconds": sample_seconds,
           "sample_disagreements": disagree}
    print(json.dumps(row, ensure_ascii=False), flush=True)

    t0 = time.perf_counter()
    cnt_A = sum(1 for bits in range(space) if fast.is_valid(bits))
    sec_A = time.perf_counter() - t0
    t0 = time.perf_counter()
    cnt_D = sum(1 for bits in range(space) if direct.is_valid(bits))
    sec_D = time.perf_counter() - t0
    row.update(full_scan_A_count=cnt_A, full_scan_A_seconds=round(sec_A, 2),
               full_scan_D_count=cnt_D, full_scan_D_seconds=round(sec_D, 2),
               full_scan_A_vs_D_agree=(cnt_A == cnt_D))
    print(json.dumps({kk: row[kk] for kk in
                      ("n", "full_scan_A_count", "full_scan_D_count",
                       "full_scan_A_vs_D_agree", "full_scan_A_seconds",
                       "full_scan_D_seconds")}, ensure_ascii=False), flush=True)

    if n in VERIFIER_FULL_SCAN:
        t0 = time.perf_counter()
        cnt_C = sum(1 for bits in range(space)
                    if verify(n, circulant_red(n, bits), 4, 6)[0])
        row.update(full_scan_C_count=cnt_C,
                   full_scan_C_seconds=round(time.perf_counter() - t0, 2),
                   full_scan_A_vs_C_agree=(cnt_A == cnt_C))
        print(json.dumps({"n": n, "full_scan_C_count": cnt_C,
                          "full_scan_A_vs_C_agree": cnt_A == cnt_C},
                         ensure_ascii=False), flush=True)
    else:
        row.update(full_scan_C_count=None, full_scan_A_vs_C_agree=None,
                   full_scan_C_note="空间过大，独立验证器只在样本上对比")

    report.append(row)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

print("WROTE", OUT, flush=True)
