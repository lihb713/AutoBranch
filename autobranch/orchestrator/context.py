"""M7 运行上下文（design D2）：一次 run 的共享依赖与块声明转换。

``RunContext`` 通过构造函数注入依赖（schema 命名空间 M3 / 报告器 M8 /
浏览器 M1 / 块声明 M2 / 叶子执行器 M6），遍历器只与它交互；mock 替换成本为零。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from autobranch.orchestrator.models import OrchestratorError, RunConfig
from autobranch.schema import FrameDecl

if TYPE_CHECKING:
    from autobranch.browser import BrowserDriver
    from autobranch.leaf_agent.models import LeafResult
    from autobranch.parser.models import Node
    from autobranch.reporting import Reporter
    from autobranch.schema import SchemaSpace

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
    :param blocks_tree: 文档名 -> 主树（一文档一树；ref 运行期经 resolver
      加载被引文档，本表仅承载根文档主树）。
    :param resolver: 跨文档引用解析器（ref 按文档名加载被引文档用）。
    :param decl_inputs: 文档级入参声明（名 -> 类型）。
    :param decl_outputs: 文档级出参名列表。
    :param config_overrides: 全局配置覆盖（timeout/retry/browser）。
    :param leaf_executor: 叶子执行器（默认包装 M6 ``execute_leaf``；测试注入 mock）。
    :param failure_reason: 首个失败节点描述（沿树传播到根时作为失败原因）。
    """

    config: RunConfig
    space: SchemaSpace
    reporter: Reporter
    browser: BrowserDriver
    leaf_executor: LeafExecutor
    blocks_tree: dict[str, Node] = field(default_factory=dict)
    resolver: Any = None
    decl_inputs: dict[str, str] = field(default_factory=dict)
    decl_outputs: list[str] = field(default_factory=list)
    config_overrides: dict[str, object] = field(default_factory=dict)
    registry: Any = None
    runtime: Any = None
    failure_reason: str | None = None

    @property
    def current_frame(self) -> Any:
        """当前激活的 schema 帧（M3 无公开读取器，访问其内部当前帧指针）。"""
        return self.space._current

    def schema_decl(self, doc_name: str) -> FrameDecl | None:
        """把文档级声明转换为 M3 ``FrameDecl``（根帧注入接口与配置覆盖用）。"""
        return FrameDecl(
            name=doc_name,
            inputs=dict(self.decl_inputs),
            outputs={name: "" for name in self.decl_outputs},
            config=dict(self.config_overrides),
        )


def make_default_leaf_executor(
    config: RunConfig,
    space: Any | None = None,
    *,
    registry: Any,
    runtime: Any = None,
) -> LeafExecutor:
    """默认叶子执行器：按 ``config`` 构建 ``LeafContext`` 并调用 M6 ``execute_leaf``。

    需要 ``config.llm_config``（M0）；缺失时抛出 :class:`OrchestratorError`。
    测试请注入 mock 叶子执行器。

    :param space: M3 ``SchemaSpace``（叶子 get 变量替换用；M7 传入 RunContext.space）。
    :param registry: 插件框架注册表（叶子走两级能力选择）。
    :param runtime: 插件运行上下文（懒装配传插件）。
    """
    from autobranch.leaf_agent import execute_leaf
    from autobranch.leaf_agent.models import LeafContext

    def _execute(node: Any, timeout: float | None) -> Any:
        if config.llm_config is None:
            raise OrchestratorError(
                "真实叶子执行需要 RunConfig.llm_config（M0）注入；测试请注入 mock leaf_executor"
            )
        leaf_ctx = LeafContext(
            config=config.llm_config,
            registry=registry,
            space=space,
            session_factory=config.session_factory,
            runtime=runtime,
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
