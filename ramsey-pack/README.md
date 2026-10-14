# ramsey-pack —— 对 Moonshine 的二次开发

把本项目已有的**精确计算内核**接成 [Moonshine](./) 数学研究 agent 的一等工具。

## 为什么需要这一层

Moonshine 原生的 `verify_correctness_*` 系列是 **LLM 评审**：它审查"证明过程"里
有没有计算错误、假设误用、逻辑漏洞。这对待数学证明是合理的。

但对**计算性断言**——例如"这个 43 顶点的图不含 $K_5$"——LLM 无法判定。
它只能评论，不能枚举团。这类断言的正确处理方式是**精确计算**，而且需要一条
与搜索器**独立实现**的验证路径（否则搜索器算错时会一起错）。

所以我们补上一层确定性工具，使这类断言由**计算**决定，而不是由模型评价决定。
这不是"借用老师的框架"，而是补上框架在**构造性组合问题**上的一个真实缺口。

## 提供的四个工具

| 工具 | 作用 | 输出性质 |
|---|---|---|
| `ramsey_verify_construction` | 精确独立判定一份构造是否合法 | **判定**：`verified` / `refuted` |
| `ramsey_enumerate_family` | 穷举对称构造族（循环图） | **判定**：`exists` / `none_exist` |
| `ramsey_search` | 固定墙钟预算的局部搜索 | 尽力而为；成功必经独立复核 |
| `ramsey_violations` | 精确统计违反度（单色团个数） | 度量 |

另外附带一份技能 `ramsey-construction-search`，教 agent 什么时候该用哪个工具、
以及如何区分"已证明 / 部分进展 / 无定论"这三种状态。

## 安装

前置：Moonshine 源码已就位，且 `marsa` 引擎可导入。

```bash
# 1) 让 Moonshine 能 import 我们的计算内核
python -m pip install -e <本项目根目录> --no-deps

# 2) 安装 pack（幂等，可重复运行）
python ramsey-pack/install.py \
  --moonshine <Moonshine 源码目录> \
  --home <Moonshine 运行时 home>
```

安装脚本会做四件事：复制工具实现、复制工具定义、复制技能、给
`tools/registry.py` 打注册补丁（原文件备份为 `registry.py.orig`）。

## 为什么必须改 Moonshine 源码

Moonshine 的 `tools/registry.py` 里 `_handler_map` 是**硬编码**的：
运行时目录中的工具定义 `.md` 只能引用已注册的 handler，
无法自行引入新的 Python 实现。因此新增工具必然要动这一处。

我们的改动是**纯新增**、约 40 行，且带 `try/except` 保护——
即使 `marsa` 没装，Moonshine 的其余功能照常工作。
这是整个二次开发中唯一需要碰 Moonshine 源码的地方。

## 自检

```bash
python -m moonshine --home <home> tools        # 应列出 4 个 ramsey_* 工具
python ramsey-pack/test_ramsey_tools.py        # 端到端：走 ToolRegistry 真实派发
```

`test_ramsey_tools.py` 会做一件额外的事：在 `n = 46` 上穷举循环图族，
预期得到"无解"——这与已证明的定理 $R(5,5) \le 46$ 一致，
等于用**已知定理反向校验**我们的内核。这是这套工具可信度的重要一环。

## 与 Moonshine 原生验证的分工

| 断言类型 | 该用谁 |
|---|---|
| 证明过程、引理链、假设使用 | `verify_correctness_*`（LLM 评审，擅长） |
| 具体构造是否合法、某个族是否存在解 | `ramsey_*`（精确计算，LLM 做不了） |

两者互补，不互相替代。技能文件里明确写了这条边界，避免 agent 把构造断言
送去 LLM 评审。
