"""MARSA —— 记忆增强的 Ramsey 反例搜索智能体。

模块划分：
    bitset     位掩码团计数与增量违反度（执行器的"引擎"）
    verifier   独立暴力验证器（唯一有权宣布成功的模块）
    search     模拟退火 / 禁忌搜索执行器
    memory     长期记忆：障碍签名 + 次模检索
    planner    规划器：LLM 接口 + 离线脚本化回退
    agent      智能体主循环
    log        JSONL 迭代日志
"""

__version__ = "0.1.0"
