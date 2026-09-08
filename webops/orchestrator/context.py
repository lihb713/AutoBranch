"""M7 运行上下文（design D2）：一次 run 的共享依赖与块声明转换。

``RunContext`` 通过构造函数注入依赖（schema 命名空间 M3 / 报告器 M8 /
浏览器 M1 / 块声明 M2 / 叶子执行器 M6），遍历器只与它交互；mock 替换成本为零。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from webops.orchestrator.models import OrchestratorError, RunConfig
from webops.schema import BlockDecl as SchemaBlockDecl

if TYPE_CHECKING:
    from webops.browser import BrowserDriver
    from webops.leaf_agent.models import LeafResult
    from webops.parser.models import BlockDecl as ParserBlockDecl
    from webops.parser.models import Node
    from webops.reporting import Reporter
    from webops.schema import SchemaSpace

#: 叶子执行器签名：``(node, effective_timeout) -> LeafResult``。
#: M7 在叶子 tick 时把生效超时（``resolve_config('timeout')``）折算后传入。
LeafExecutor = Callable[["Node", float | None], "LeafResult"]


@dataclass
class RunContext:
    """一次 run 的共享可变状态（design D2：依赖注入构造，mock 友好）。

    :param config: 运行配置（M7 自身 + 叶子参数）。
    :param space: M3 schema 命名空间（帧管理 / 配置继承）。
    :param reporter: M8 报告记录器（节点报告 / 截图 / 执行状态）。
    :param browser: M1 浏览器驱动（会话生命周期）。
    :param blocks: M2 块声明表（块名 -> ``BlockDecl``，建帧注入配置覆盖）。
    :param leaf_executor: 叶子执行器（默认包装 M6 ``execute_leaf``；测试注入 mock）。
    :param failure_reason: 首个失败节点描述（沿树传播到根时作为失败原因）。
    """

    config: RunConfig
    space: SchemaSpace
    reporter: Reporter
    browser: BrowserDriver
    blocks: dict[str, ParserBlockDecl]
    leaf_executor: LeafExecutor
    failure_reason: str | None = None

    @property
    def current_frame(self) -> Any:
        """当前激活的 schema 帧（M3 无公开读取器，访问其内部当前帧指针）。"""
        return self.space._current

    def schema_decl(self, block_name: str) -> SchemaBlockDecl | None:
        """把 M2 块声明转换为 M3 ``BlockDecl``（建帧注入配置覆盖用）。

        声明表查无（如跨文档块不在根文档声明表中）返回 None：仅失去该块的
        配置覆盖注入，不影响建帧与执行。
        """
        decl = self.blocks.get(block_name)
        if decl is None:
            return None
        return SchemaBlockDecl(
            block_name=block_name,
            inputs={name: typ for name, typ in decl.inputs},
            outputs={name: "" for name in decl.outputs},
            config={override.name: override.value for override in decl.config_overrides},
        )


def make_default_leaf_executor(
    config: RunConfig, space: Any | None = None
) -> LeafExecutor:
    """默认叶子执行器：按 ``config`` 构建 ``LeafContext`` 并调用 M6 ``execute_leaf``。

    需要 ``config.llm_config`` 与 ``config.engine``（M0 + M5 注入）；缺失时抛出
    :class:`OrchestratorError`。测试请注入 mock 叶子执行器。

    :param space: M3 ``SchemaSpace``（叶子 get 变量替换用；M7 传入 RunContext.space）。
    """
    from webops.leaf_agent import execute_leaf
    from webops.leaf_agent.models import LeafContext

    def _execute(node: Any, timeout: float | None) -> Any:
        if config.llm_config is None or config.engine is None:
            raise OrchestratorError(
                "真实叶子执行需要 RunConfig.llm_config 与 RunConfig.engine"
                "（M0 + M5）注入；测试请注入 mock leaf_executor"
            )
        leaf_ctx = LeafContext(
            config=config.llm_config,
            engine=config.engine,
            space=space,
            session_factory=config.session_factory,
            tools=config.tools,
            max_rounds=config.max_rounds,
            no_progress_rounds=config.no_progress_rounds,
            timeout=timeout,
            session_timeout=config.session_timeout,
            initial_graph_scope=config.initial_graph_scope,
            initial_graph_lod=config.initial_graph_lod,
        )
        return execute_leaf(node, leaf_ctx)

    return _execute


__all__ = ["RunContext", "LeafExecutor", "make_default_leaf_executor"]
