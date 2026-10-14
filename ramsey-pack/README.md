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

另外附带 **4 份技能**，把本项目三周里真正硬的方法论固化给 agent。技能遵循
Moonshine 的三层渐进式披露：`description`（路由条件）常驻模型上下文，
完整正文按需经 `load_skill_definition` 加载。

| 技能 | 什么时候用（路由条件） | 固化的是哪条经验 |
|---|---|---|
| `ramsey-construction-search` | 目标是**下界** `R(s,t) > n`，需要产出或判定一份构造 | 核心工作流；并严格区分「已证明／部分进展／无定论」 |
| `symmetric-family-exhaustion` | 构造落在**参数很少的结构族**里，可以整族查完 | 循环图族完整刻画那一战：能穷举就绝不去搜 |
| `search-operator-iteration` | 交付物是**更好的方法**，不是某个实例上更好的答案 | 阶段 1 的教训：固定墙钟预算、多种子取均值、训练/held-out 分离、警惕退化的选择 |
| `ramsey-frontier-bookkeeping` | 每个研究回合的**开头**，用来重建"已知边界" | 防止重复劳动与过度声称；并给出 `R(5,5)` 唯一开放的靶子 |

其中 `search-operator-iteration` 里特别写进了三条**已经踩过的坑**（都是本项目实测）：
按步数比较会替便宜的算子作弊；单种子在同配置下能差近一倍；`C(n,2)` 全量评估是
大 `n` 的性能瓶颈，而"候选多大"和"候选怎么选"同样重要。

`ramsey-frontier-bookkeeping` 里写清了一件极易搞错的事：
因为 `R(5,5) >= 43` 意味着**存在** 43 顶点的合法染色，而删点保持合法性，
所以 `n <= 43` 全都存在 —— **真正开放的靶子只有 `n = 44` 和 `n = 45`**。
在 `n <= 43` 上做出构造是标定，不是新结果。

另附 **1 份 agent 人格** `computational-construction-search`。它把 agent 的默认身份
从"通用数学研究者"调成"**构造性组合搜索者**"，核心是一句行为准则：

> **在问"我能不能找到"之前，先问"这个问题能不能被判死"。**

人格里固化了四条本项目特有的判断：
1. **证据是精确计算，不是评审。** 具体构造是否合法由 `ramsey_*` 判定；
   严禁把构造断言送去 LLM 评审（那会得到一个自信但无意义的答案）。
2. **下界与上界是两个问题。** 下界找构造（可搜索）；上界要证明**所有**染色都失败
   （不可搜索）—— 搜索失败**不是**上界的证据。
3. **先判断靶子是否开放。** 在 `n <= 43` 上做出构造是标定，不是进展。
4. **报结果必须带类型与作用域。** 已证明 / 已测量 / 无定论三者不得混用；
   小违反度（1~5）不得描述成"快好了"。

## 本地控制台（推荐先跑这个）

命令行能用，但演示和日常使用都不方便：要记一串参数、结果是裸 JSON、
想看当前边界还得翻日志。所以附带一个**零依赖的本地 Web 控制台**：

```bash
python console/server.py            # 然后浏览器打开 http://127.0.0.1:8777
```

只用 Python 标准库（`http.server`），无第三方依赖，只绑定 127.0.0.1。页面上有三块：

| 面板 | 内容 |
|---|---|
| **当前边界** | `R(5,5)` / `R(4,6)` 的上下界、**开放靶子**，以及可点击的靶子按钮 |
| **跑一次实验** | 三选一：穷举对称族 / 搜索 / 验证一份 graph6；结果含判定徽章与完整字段 |
| **已装载的能力** | 列出装进 Moonshine 的 4 个工具 / 4 份技能 / 1 个人格 |

**关键点：它完全不经过大模型，所以不需要任何 API key。** 这恰好体现了本项目的分工——
需要计算的事交给计算，不需要模型。

实测（真实 HTTP 请求，非模拟）：

```
GET  /                      -> HTTP 200, 10425 字符
GET  /api/state             -> 边界 2 项；工具 4 / 技能 4 / agent 1；算子 5 个
POST /api/run enumerate n=40 -> exists  solutions=24  space=1,048,576  1.62s
POST /api/run search    n=34 -> solved  violations=0  verified=True
POST /api/run verify    n=34 -> verified
```

> **验证边界说明**：我验证了页面可正常返回、三个 API 端到端可用、
> 页面引用的 DOM id 与接口路径都一致。但这个环境里**没有浏览器**，
> 所以页面的**视觉渲染未经我目视检查**——样式是否合意需要你自己打开看一眼。

## 从零到跑起来（可安装性）

```bash
# 1. 安装计算内核（让 Moonshine 能 import 它）
python -m pip install -e <本项目根目录> --no-deps

# 2. 安装 Moonshine 本体（重依赖都是惰性导入，--no-deps 即可跑）
cd <Moonshine 源码目录>
python -m pip install -e . --no-deps

# 3. 初始化 Moonshine 运行时目录
python -m moonshine --home <运行时 home> init

# 4. 装本 pack（工具 / 技能 / 人格）
python ramsey-pack/install.py --moonshine <Moonshine 源码目录> --home <运行时 home>

# 5. 自检
python -m moonshine --home <运行时 home> tools      # 应列出 4 个 ramsey_* 工具
python ramsey-pack/test_ramsey_tools.py             # 端到端工具自检
python ramsey-pack/test_skills.py                   # 技能发现与加载自检

# 6. 起控制台
python console/server.py
```

**关于安装难度，两条实测结论：**

- **Moonshine 的重依赖（lancedb / chromadb / langgraph / tiktoken）全部是惰性导入**，
  所以 `--no-deps` 就能跑起来核心功能。要向量检索才需要装 `.[all]`。
- **`install.py` 是幂等的**，重复运行不会重复打补丁（已验证）。

**唯一一处必须改 Moonshine 源码**：`tools/registry.py` 的 `_handler_map` 是硬编码的，
运行时工具定义无法引入新的 Python 实现。改动为纯新增约 40 行、带 `try/except` 保护，
原文件备份为 `registry.py.orig`。


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
