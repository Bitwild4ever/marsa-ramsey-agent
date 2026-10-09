"""用 Pillow 画图（不依赖 matplotlib，保证在任何环境可复现）。

项目原本想用 matplotlib，但运行环境不允许安装第三方包。Pillow 是本环境
自带的，且系统里有中文字体，因此自己写一个小型折线/柱状图渲染器，
既无依赖又能精确控制输出样式。

全部输出为 PNG，随后嵌入 DOCX -> PDF 生成实验报告。
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PALETTE = ["#1f4e79", "#c00000", "#2e7d32", "#e07b00",
           "#6a1b9a", "#00838f", "#8d6e63", "#ad1457"]

FONT_REG = "C:/Windows/Fonts/msyh.ttc"
FONT_BOLD = "C:/Windows/Fonts/msyhbd.ttc"
_font_cache: dict[tuple[int, bool], ImageFont.FreeTypeFont] = {}


def font(size: int, bold: bool = False):
    key = (size, bold)
    if key not in _font_cache:
        try:
            _font_cache[key] = ImageFont.truetype(
                FONT_BOLD if bold else FONT_REG, size)
        except OSError:
            _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]


def _nice_ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    if hi <= lo:
        hi = lo + 1.0
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1.0
    for m in (1, 2, 2.5, 5, 10):
        step = m * mag
        if raw <= step:
            break
    start = math.floor(lo / step) * step
    out = []
    v = start
    while v <= hi + step * 0.5:
        if v >= lo - step * 0.5:
            out.append(v)
        v += step
    return out


def _fmt(v: float) -> str:
    if abs(v) >= 1e6:
        return f"{v/1e6:.1f}M"
    if abs(v) >= 1e4:
        return f"{v/1e3:.0f}k"
    if abs(v) >= 100:
        return f"{v:.0f}"
    if abs(v - round(v)) < 1e-9:
        return f"{int(round(v))}"
    return f"{v:.2f}"


def line_chart(out: str | Path, series: list[dict], title: str,
               xlabel: str = "", ylabel: str = "",
               width: int = 1680, height: int = 1020,
               logy: bool = False, y_min_zero: bool = False) -> str:
    """series: [{"label": str, "xs": [...], "ys": [...], "color": "#..."}]"""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)

    ml, mr, mt, mb = 170, 70, 120, 130
    px0, py0, px1, py1 = ml, mt, width - mr, height - mb

    f_title, f_lab, f_tick, f_leg = (font(44, True), font(30),
                                     font(26), font(27))

    d.text(((px0 + px1) / 2, 56), title, fill="#111111", font=f_title,
           anchor="mm")

    all_x = [x for s in series for x in s["xs"]]
    all_y = [y for s in series for y in s["ys"]]
    if not all_x or not all_y:
        d.text(((px0 + px1) / 2, (py0 + py1) / 2), "（无数据）",
               fill="#888888", font=f_lab, anchor="mm")
        img.save(out)
        return str(out)

    x_lo, x_hi = min(all_x), max(all_x)
    if x_hi <= x_lo:
        x_hi = x_lo + 1
    y_lo = 0.0 if y_min_zero else min(all_y)
    y_hi = max(all_y)
    if y_hi <= y_lo:
        y_hi = y_lo + 1.0

    def TX(x):
        return px0 + (x - x_lo) / (x_hi - x_lo) * (px1 - px0)

    if logy:
        y_lo_l = math.log10(max(1e-9, y_lo if y_lo > 0 else 1e-9))
        y_hi_l = math.log10(max(1e-9, y_hi))
        if y_hi_l <= y_lo_l:
            y_hi_l = y_lo_l + 1

        def TY(y):
            return py1 - (math.log10(max(1e-9, y)) - y_lo_l) / \
                (y_hi_l - y_lo_l) * (py1 - py0)
    else:
        def TY(y):
            return py1 - (y - y_lo) / (y_hi - y_lo) * (py1 - py0)

    # 网格与刻度
    for v in _nice_ticks(y_lo, y_hi, 6):
        yy = TY(v)
        if py0 - 1 <= yy <= py1 + 1:
            d.line([(px0, yy), (px1, yy)], fill="#e6e6e6", width=2)
            d.text((px0 - 18, yy), _fmt(v), fill="#444444", font=f_tick,
                   anchor="rm")
    for v in _nice_ticks(x_lo, x_hi, 6):
        xx = TX(v)
        if px0 - 1 <= xx <= px1 + 1:
            d.line([(xx, py0), (xx, py1)], fill="#f2f2f2", width=1)
            d.text((xx, py1 + 22), _fmt(v), fill="#444444", font=f_tick,
                   anchor="mm")

    d.rectangle([px0, py0, px1, py1], outline="#333333", width=3)

    for i, s in enumerate(series):
        color = s.get("color") or PALETTE[i % len(PALETTE)]
        pts = [(TX(x), TY(y)) for x, y in zip(s["xs"], s["ys"])]
        if len(pts) == 1:
            x, y = pts[0]
            d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=color)
        else:
            if len(pts) > 4000:                     # 抽稀，避免文件过大
                stepn = max(1, len(pts) // 4000)
                pts = pts[::stepn] + [pts[-1]]
            d.line(pts, fill=color, width=5, joint="curve")

    # 图例
    ly = py0 + 8
    for i, s in enumerate(series):
        color = s.get("color") or PALETTE[i % len(PALETTE)]
        lx = px0 + 24
        d.line([(lx, ly), (lx + 56, ly)], fill=color, width=6)
        d.text((lx + 70, ly), str(s["label"]), fill="#222222", font=f_leg,
               anchor="lm")
        ly += 40

    if xlabel:
        d.text(((px0 + px1) / 2, height - 34), xlabel, fill="#222222",
               font=f_lab, anchor="mm")
    if ylabel:
        tmp = Image.new("RGBA", (height, 60), (255, 255, 255, 0))
        td = ImageDraw.Draw(tmp)
        td.text((height // 2, 30), ylabel, fill="#222222", font=f_lab,
                anchor="mm")
        img.paste(tmp.rotate(90, expand=True), (8, py0 - 30), tmp.rotate(
            90, expand=True))
    img.save(out)
    return str(out)


def bar_chart(out: str | Path, categories: list[str],
              series: list[dict], title: str, ylabel: str = "",
              width: int = 1680, height: int = 1020,
              annotate: bool = True) -> str:
    """series: [{"label": str, "ys": [...], "color": "#..."}]"""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)

    ml, mr, mt, mb = 170, 70, 120, 150
    px0, py0, px1, py1 = ml, mt, width - mr, height - mb
    f_title, f_lab, f_tick, f_leg = (font(44, True), font(30),
                                     font(26), font(27))

    d.text(((px0 + px1) / 2, 56), title, fill="#111111", font=f_title,
           anchor="mm")

    vals = [v for s in series for v in s["ys"]]
    y_lo, y_hi = 0.0, max(vals) if vals else 1.0
    if y_hi <= 0:
        y_hi = 1.0

    def TY(y):
        return py1 - (y - y_lo) / (y_hi - y_lo) * (py1 - py0)

    for v in _nice_ticks(y_lo, y_hi, 6):
        yy = TY(v)
        if py0 - 1 <= yy <= py1 + 1:
            d.line([(px0, yy), (px1, yy)], fill="#e6e6e6", width=2)
            d.text((px0 - 18, yy), _fmt(v), fill="#444444", font=f_tick,
                   anchor="rm")

    nc = len(categories)
    ns = len(series)
    slot = (px1 - px0) / max(1, nc)
    bw = slot * 0.72 / max(1, ns)

    for ci, cat in enumerate(categories):
        base_x = px0 + slot * ci + slot * 0.14
        for si, s in enumerate(series):
            color = s.get("color") or PALETTE[si % len(PALETTE)]
            v = s["ys"][ci]
            x0 = base_x + bw * si
            y = TY(v)
            d.rectangle([x0, y, x0 + bw * 0.92, py1], fill=color)
            if annotate:
                d.text((x0 + bw * 0.46, y - 16), _fmt(v), fill="#222222",
                       font=f_tick, anchor="mb")
        d.text((px0 + slot * ci + slot / 2, py1 + 26), cat, fill="#222222",
               font=f_tick, anchor="mm")

    d.rectangle([px0, py0, px1, py1], outline="#333333", width=3)

    lx = px0 + 24
    ly = py0 + 8
    for si, s in enumerate(series):
        color = s.get("color") or PALETTE[si % len(PALETTE)]
        d.rectangle([lx, ly - 13, lx + 46, ly + 13], fill=color)
        d.text((lx + 60, ly), str(s["label"]), fill="#222222", font=f_leg,
               anchor="lm")
        ly += 40

    if ylabel:
        tmp = Image.new("RGBA", (height, 60), (255, 255, 255, 0))
        td = ImageDraw.Draw(tmp)
        td.text((height // 2, 30), ylabel, fill="#222222", font=f_lab,
                anchor="mm")
        rot = tmp.rotate(90, expand=True)
        img.paste(rot, (8, py0 - 30), rot)

    img.save(out)
    return str(out)
