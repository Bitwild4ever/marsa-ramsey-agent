"""一次性补丁：把 ramsey_prior 接进 install.py 模板与线上 registry.py。"""
from pathlib import Path

# ---------- install.py（补丁模板，供以后重装用） ----------
p = Path(r"D:\myagent\ramsey-pack\install.py")
t = p.read_text(encoding="utf-8")

t = t.replace(
    "        ramsey_grow,\n        ramsey_search,",
    "        ramsey_grow,\n        ramsey_prior,\n        ramsey_search,")
t = t.replace(
    "    ramsey_compare = ramsey_grow = None",
    "    ramsey_compare = ramsey_grow = ramsey_prior = None")
t = t.replace(
    '''            "ramsey_grow": (
                (lambda runtime, **kwargs: ramsey_grow(runtime, **kwargs))
                if _RAMSEY_TOOLS_AVAILABLE
                else _ramsey_unavailable("ramsey_grow")
            ),''',
    '''            "ramsey_grow": (
                (lambda runtime, **kwargs: ramsey_grow(runtime, **kwargs))
                if _RAMSEY_TOOLS_AVAILABLE
                else _ramsey_unavailable("ramsey_grow")
            ),
            "ramsey_prior": (
                (lambda runtime, **kwargs: ramsey_prior(runtime, **kwargs))
                if _RAMSEY_TOOLS_AVAILABLE
                else _ramsey_unavailable("ramsey_prior")
            ),''')
t = t.replace(
    '''    shutil.copy2(PACK / "tools" / "ramsey_grow.py",
                 moon / "tools" / "ramsey_grow.py")''',
    '''    shutil.copy2(PACK / "tools" / "ramsey_grow.py",
                 moon / "tools" / "ramsey_grow.py")
    shutil.copy2(PACK / "tools" / "ramsey_prior.py",
                 moon / "tools" / "ramsey_prior.py")''')
t = t.replace(
    '        "    from .ramsey_grow import ramsey_grow\\n"',
    '        "    from .ramsey_grow import ramsey_grow\\n"\n'
    '        "    from .ramsey_prior import ramsey_prior\\n"')
t = t.replace(
    '        "    from ramsey_grow import ramsey_grow  # noqa: F401\\n"',
    '        "    from ramsey_grow import ramsey_grow  # noqa: F401\\n"\n'
    '        "    from ramsey_prior import ramsey_prior  # noqa: F401\\n"')
p.write_text(t, encoding="utf-8")
print("install.py 已更新")

# ---------- 线上 registry.py ----------
r = Path(r"D:\myagent\Moonshine-main\Moonshine-main\tools\registry.py")
s = r.read_text(encoding="utf-8")
s = s.replace(
    "        ramsey_grow,\n        ramsey_search,",
    "        ramsey_grow,\n        ramsey_prior,\n        ramsey_search,")
s = s.replace(
    "    ramsey_compare = ramsey_grow = None",
    "    ramsey_compare = ramsey_grow = ramsey_prior = None")
s = s.replace(
    '''            "ramsey_grow": (
                (lambda runtime, **kwargs: ramsey_grow(runtime, **kwargs))
                if _RAMSEY_TOOLS_AVAILABLE
                else _ramsey_unavailable("ramsey_grow")
            ),''',
    '''            "ramsey_grow": (
                (lambda runtime, **kwargs: ramsey_grow(runtime, **kwargs))
                if _RAMSEY_TOOLS_AVAILABLE
                else _ramsey_unavailable("ramsey_grow")
            ),
            "ramsey_prior": (
                (lambda runtime, **kwargs: ramsey_prior(runtime, **kwargs))
                if _RAMSEY_TOOLS_AVAILABLE
                else _ramsey_unavailable("ramsey_prior")
            ),''')
r.write_text(s, encoding="utf-8")
print("registry.py 已更新")

# 校验
for f, needle in ((p, "ramsey_prior"), (r, "ramsey_prior")):
    cnt = f.read_text(encoding="utf-8").count(needle)
    print(f"  {f.name}: 出现 {cnt} 次")
