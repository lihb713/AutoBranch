"""WebOps 编排器（M7）。

确定性编排与遍历中枢（整合 M2 + M3 + M6 + M8）：阻塞式遍历、SUCCESS/FAILURE
聚合与短路、组合节点纯程序执行、叶子触发（M6）、schema 帧生命周期（M3）、
会话初始化（M1）与报告记录（M8）。对外提供 ``Engine.run`` 入口与可查询执行
状态（``get_exec_state``，§12.4）。模块 spec 见 ``docs/specs/M7-orchestrator.md``。

对外公开：
- ``Engine``：引擎入口（``run`` / ``get_exec_state``）
- ``RunConfig`` / ``RunResult`` / ``NodeStatus``（``SUCCESS`` / ``FAILURE``）
- ``RunContext``：一次运行的共享依赖上下文
- ``Traverser`` / ``count_nodes``：遍历器与节点统计
- ``OrchestratorError``：编排器运行期错误
"""

from webops.orchestrator.context import RunContext
from webops.orchestrator.engine import Engine
from webops.orchestrator.models import (
    FAILURE,
    SUCCESS,
    NodeStatus,
    OrchestratorError,
    RunConfig,
    RunResult,
)
from webops.orchestrator.traverser import Traverser, count_nodes

__all__ = [
    "Engine",
    "RunContext",
    "RunConfig",
    "RunResult",
    "NodeStatus",
    "SUCCESS",
    "FAILURE",
    "Traverser",
    "count_nodes",
    "OrchestratorError",
]
