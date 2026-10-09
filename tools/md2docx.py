"""把 选题说明.md 转成排版好的 DOCX（供 LibreOffice 转 PDF）。

只处理本文件用到的 Markdown 子集：标题、段落、表格、无序列表、
引用块、代码块、水平线，以及 **粗体** / `行内代码` / $行内公式$。
"""
import re
import sys
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

SRC = sys.argv[1] if len(sys.argv) > 1 else r"D:\myagent\选题说明.md"
OUT = sys.argv[2] if len(sys.argv) > 2 else r"D:\myagent\选题说明.docx"

CJK_BODY = "宋体"
CJK_HEAD = "微软雅黑"
LATIN_BODY = "Times New Roman"
LATIN_HEAD = "Arial"

# LaTeX 片段 -> 可读纯文本
MATH_SUBS = [
    (r"\\binom\{(\d+)\}\{(\d+)\}", r"C(\1,\2)"),
    (r"\\le\b", "≤"), (r"\\geq?\b", "≥"),
    (r"\\Rightarrow", "⇒"), (r"\\rightarrow", "→"),
    (r"\\times", "×"), (r"\\cdot", "·"), (r"\\approx", "≈"),
    (r"\\in\b", "∈"), (r"\\ldots", "…"), (r"\\dots", "…"),
    (r"\\to\b", "→"), (r"\\quad", " "), (r"\\;", " "), (r"\\,", " "),
    (r"\\left", ""), (r"\\right", ""),
    (r"\\[a-zA-Z]+", ""),      # 丢弃其余未知命令
    (r"[{}]", ""),
    (r"\s{2,}", " "),
]


def clean_math(text: str) -> str:
    for pat, rep in MATH_SUBS:
        text = re.sub(pat, rep, text)
    return text.strip()


def set_style_font(style, cjk, latin, size=None, bold=None, color=None):
    style.font.name = latin
    if size is not None:
        style.font.size = Pt(size)
    if bold is not None:
        style.font.bold = bold
    if color is not None:
        style.font.color.rgb = color
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    rfonts.set(qn("w:ascii"), latin)
    rfonts.set(qn("w:hAnsi"), latin)
    rfonts.set(qn("w:eastAsia"), cjk)


TOKEN = re.compile(
    r"(\*\*.+?\*\*|`[^`]+`|\$[^$]+\$|\*[^*\n]+\*|\[[^\]]+\]\([^)]+\))")


def _fmt(run, bold=False, italic=False):
    """只显式设置 True 的属性，避免把标题样式自带的加粗覆盖掉。"""
    if bold:
        run.bold = True
    if italic:
        run.italic = True
    return run


def add_runs(par, text, bold=False, italic=False):
    """把 **粗体** / *斜体* / `代码` / $公式$ / [链接](url) 写成多个 run。

    粗体内部的内容会递归处理，因此粗体里嵌的公式与行内代码也能正确转换。
    """
    text = re.sub(r"\$\$(.+?)\$\$", r"$\1$", text, flags=re.S)   # $$..$$ -> $..$

    for piece in TOKEN.split(text):
        if not piece:
            continue
        if piece.startswith("**") and piece.endswith("**") and len(piece) > 4:
            add_runs(par, piece[2:-2], bold=True, italic=italic)
        elif piece.startswith("`") and piece.endswith("`") and len(piece) > 2:
            r = par.add_run(piece[1:-1])
            r.font.name = "Consolas"
            r.font.color.rgb = RGBColor(0xB0, 0x30, 0x60)
            _fmt(r, bold, italic)
        elif piece.startswith("$") and piece.endswith("$") and len(piece) > 2:
            r = par.add_run(clean_math(piece[1:-1]))
            r.italic = True
            _fmt(r, bold)
        elif piece.startswith("*") and piece.endswith("*") and len(piece) > 2:
            add_runs(par, piece[1:-1], bold=bold, italic=True)
        elif piece.startswith("[") and "](" in piece and piece.endswith(")"):
            label, url = piece[1:-1].split("](", 1)
            r = par.add_run(f"{label}（{url}）")
            r.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)
            _fmt(r, bold, italic)
        else:
            _fmt(par.add_run(piece), bold, italic)


def split_row(line):
    cells = line.strip().strip("|").split("|")
    return [c.strip() for c in cells]


BLOCK_START = re.compile(r"^(#{1,4}\s|[-*]\s|\d+\.\s|>|\||```|!\[)")


def is_block_start(s: str) -> bool:
    return bool(BLOCK_START.match(s)) or bool(re.fullmatch(r"-{3,}", s))


def take_continuation(lines, i, n) -> tuple[list[str], int]:
    """吃掉一个块（段落/列表项）的后续折行。

    这一步是必需的：Markdown 里一个 **粗体** 或 $公式$ 很可能跨行书写，
    若只处理首行，跨行的标记就会原样漏进文档。
    """
    buf = []
    while i < n and lines[i].strip() and not is_block_start(lines[i].strip()):
        buf.append(lines[i].strip())
        i += 1
    return buf, i


def build():
    doc = Document()

    # A4 + 边距
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.2)
    sec.top_margin = sec.bottom_margin = Cm(2.2)

    set_style_font(doc.styles["Normal"], CJK_BODY, LATIN_BODY, 10.5)
    doc.styles["Normal"].paragraph_format.space_after = Pt(4)
    doc.styles["Normal"].paragraph_format.line_spacing = 1.25

    set_style_font(doc.styles["Title"], CJK_HEAD, LATIN_HEAD, 20, True,
                   RGBColor(0x1F, 0x38, 0x64))
    for lvl, size in ((1, 15), (2, 12.5), (3, 11)):
        set_style_font(doc.styles[f"Heading {lvl}"], CJK_HEAD, LATIN_HEAD,
                       size, True, RGBColor(0x1F, 0x38, 0x64))

    lines = open(SRC, encoding="utf-8").read().splitlines()
    i, n = 0, len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # 代码块
        if stripped.startswith("```"):
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i]); i += 1
            i += 1
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.6)
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(8)
            r = p.add_run("\n".join(buf))
            r.font.name = "Consolas"
            r.font.size = Pt(8.5)
            continue

        # 图片：![标题](路径)
        m_img = re.match(r"^!\[(.*?)\]\((.+?)\)\s*$", stripped)
        if m_img:
            cap, src = m_img.group(1), m_img.group(2)
            par = doc.add_paragraph()
            par.alignment = WD_ALIGN_PARAGRAPH.CENTER
            par.paragraph_format.space_before = Pt(6)
            par.paragraph_format.space_after = Pt(2)
            try:
                par.add_run().add_picture(src, width=Cm(16.0))
            except Exception as exc:                      # noqa: BLE001
                par.add_run(f"[图片缺失: {src} ({exc})]")
            if cap:
                cp = doc.add_paragraph()
                cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
                cp.paragraph_format.space_after = Pt(10)
                r = cp.add_run(cap)
                r.font.size = Pt(9)
                r.italic = True
                r.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
            i += 1
            continue

        # 表格
        if stripped.startswith("|") and i + 1 < n and re.match(
                r"^\|[\s:\-|]+\|$", lines[i + 1].strip()):
            header = split_row(stripped)
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(split_row(lines[i].strip())); i += 1
            table = doc.add_table(rows=1, cols=len(header))
            table.style = "Table Grid"
            table.autofit = True
            for c, txt in enumerate(header):
                cell = table.rows[0].cells[c]
                cell.text = ""
                add_runs(cell.paragraphs[0], txt)
                for r in cell.paragraphs[0].runs:
                    r.bold = True
            for row in rows:
                cells = table.add_row().cells
                for c in range(len(header)):
                    txt = row[c] if c < len(row) else ""
                    cells[c].text = ""
                    add_runs(cells[c].paragraphs[0], txt)
            doc.add_paragraph()
            continue

        # 水平线
        if re.fullmatch(r"-{3,}", stripped):
            i += 1
            continue

        # 标题
        m = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if m:
            lvl, txt = len(m.group(1)), m.group(2)
            target = 0 if lvl == 1 else min(lvl - 1, 3)
            add_runs(doc.add_heading("", level=target), txt)
            i += 1
            continue

        # 引用块
        if stripped.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip()); i += 1
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.7)
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(6)
            add_runs(p, " ".join(x for x in buf if x))
            for r in p.runs:
                r.italic = True
                r.font.color.rgb = RGBColor(0x40, 0x40, 0x40)
            continue

        # 无序列表（含跨行折行）
        m_ul = re.match(r"^[-*]\s+(.*)$", stripped)
        if m_ul:
            buf = [m_ul.group(1)]
            extra, i = take_continuation(lines, i + 1, n)
            p = doc.add_paragraph(style="List Bullet")
            add_runs(p, " ".join(buf + extra))
            continue

        # 有序列表（含跨行折行）
        m_ol = re.match(r"^\d+\.\s+(.*)$", stripped)
        if m_ol:
            buf = [m_ol.group(1)]
            extra, i = take_continuation(lines, i + 1, n)
            p = doc.add_paragraph(style="List Number")
            add_runs(p, " ".join(buf + extra))
            continue

        # 空行
        if not stripped:
            i += 1
            continue

        # 普通段落（连续非空行合并）
        buf, i = take_continuation(lines, i, n)
        if not buf:                      # 兜底，避免任何情况下的死循环
            buf.append(stripped); i += 1
        add_runs(doc.add_paragraph(), " ".join(buf))

    doc.save(OUT)
    print("saved:", OUT)


if __name__ == "__main__":
    build()
