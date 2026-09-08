"""WebOps 引擎函数层（M5）。

把 M1 浏览器能力、M4 语义图与 M3 变量机制封装为暴露给 LLM 的引擎函数集
（契约 §5.8.1/§5.8.2/§5.10，模块 spec docs/specs/M5-engine-functions.md）：
- ``ENGINE_TOOLS``：工具 schema 注册表（15 个函数，供 M0 会话声明工具）
- ``EngineFunctions``：执行实现（每个函数一个方法，统一返回 ``OpResult``）
- ``EngineRefMap``：ref 确定性解析（``[N]`` ↔ 元素 id ↔ DOM 节点 ↔ CSS 选择器，
  策略 B 即用即弃，拒绝无效/过期 ref）
- ``EngineProbe``：记录最近爬取快照的 M1 探针（ref 映射刷新用）
- 复用类型：``OpResult`` / ``FatalBrowserError``（M1）、``ToolSpec``（M0）

被依赖方：M6 叶子 agent 把 ``ENGINE_TOOLS`` 作为工具定义传给 LLM、经
``EngineFunctions.call`` 执行工具调用。
"""

from webops.engine.engine import EngineFunctions
from webops.engine.models import ErrorCode, FatalBrowserError, OpResult, ToolSpec, failure, success
from webops.engine.probe import EngineProbe
from webops.engine.refmap import EngineRefMap, RefResolution
from webops.engine.tools import ENGINE_TOOLS, tool_names

__all__ = [
    "ENGINE_TOOLS",
    "tool_names",
    "EngineFunctions",
    "EngineRefMap",
    "RefResolution",
    "EngineProbe",
    "OpResult",
    "FatalBrowserError",
    "ToolSpec",
    "ErrorCode",
    "success",
    "failure",
]
