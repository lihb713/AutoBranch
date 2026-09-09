"""M7 引擎入口（design D7/D8）：会话初始化、遍历编排、报告输出与状态查询。

``Engine.run`` 保持同步阻塞语义（返回 ``RunResult``）；M9b 在后台线程中调用它，
主线程经 ``get_exec_state()`` 轮询执行状态（§12.3/§12.4）。引擎自身不管理线程。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from webops.browser import BrowserDriver
from webops.browser.errors import FatalBrowserError
from webops.browser.models import PageRef as BrowserPageRef
from webops.orchestrator.context import RunContext, make_default_leaf_executor
from webops.orchestrator.models import FAILURE, RunConfig, RunResult
from webops.orchestrator.traverser import Traverser, count_nodes
from webops.reporting import ExecState, Reporter
from webops.schema import SchemaSpace
from webops.schema.errors import SchemaError

if TYPE_CHECKING:
    from webops.parser.models import BehaviorTree, BlockDecl, Node

logger = logging.getLogger(__name__)


def _make_run_id(name: str) -> str:
    """生成运行标识（根块名 + 时间戳，经 M8 清洗为安全目录名）。"""
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    return f"{name or 'run'}_{ts}"


class Engine:
    """确定性编排引擎（M7 spec §5.1）。

    :param browser: M1 浏览器驱动（默认新建实例；每次 run 经 ``start`` 冷启动
      全新 context、结束统一释放，契约 §5.9）。
    :param leaf_executor: 叶子执行器 ``(node, timeout) -> LeafResult``（默认包装
      M6 ``execute_leaf``；测试注入 mock）。
    :param space_factory: 每次 run 新建 ``SchemaSpace`` 的工厂（默认每次新建）。
    :param reporter_factory: 报告器工厂 ``(run_id, total_nodes) -> Reporter``
      （默认 M8 ``Reporter``，截图经 M1 ``page().screenshot`` 注入）。
    """

    def __init__(
        self,
        *,
        browser: BrowserDriver | None = None,
        leaf_executor: Callable[..., Any] | None = None,
        space_factory: Callable[[], SchemaSpace] | None = None,
        reporter_factory: Callable[[str, int], Reporter] | None = None,
    ) -> None:
        self._browser = browser if browser is not None else BrowserDriver()
        self._leaf_executor = leaf_executor
        self._space_factory = space_factory or (lambda: SchemaSpace())
        self._reporter_factory = reporter_factory
        self._run_context: RunContext | None = None

    # ------------------------------------------------------------ 入口

    def run(
        self,
        tree: BehaviorTree,
        blocks: dict[str, BlockDecl],
        config: RunConfig,
        blocks_tree: dict[str, Node] | None = None,
    ) -> RunResult:
        """执行入口（§9.8 ⓪/①/②）：会话初始化 → 遍历 → 返回运行结果。

        校验失败（行为树/块声明/配置缺失或非法）直接返回修正信息，不启动任何
        会话、遍历与报告；成功路径每次运行创建全新浏览器 context、注入全局
        默认配置到根级 schema、遍历结束后统一释放 context。

        :param blocks_tree: 每块预展开的可执行基础树（ref 节点运行期动态调用的
          目标查找表；None/空 dict 表示无 ref 场景）。
        """
        self._run_context = None
        problem = self._validate_input(tree, blocks, config)
        if problem is not None:
            return RunResult(status="failure", failure_reason=problem)

        run_id = _make_run_id(tree.name)
        total = count_nodes(tree.root, blocks_tree or {})
        space = self._space_factory()
        reporter = self._make_reporter(run_id, total, config)
        self._inject_global_config(space, config)
        ctx = RunContext(
            config=config,
            space=space,
            reporter=reporter,
            browser=self._browser,
            blocks=blocks,
            leaf_executor=self._leaf_executor or make_default_leaf_executor(config, space),
            blocks_tree=blocks_tree or {},
        )
        self._run_context = ctx
        traverser = Traverser(ctx)
        started = False
        status = FAILURE
        try:
            self._browser.start(config.browser_config)
            started = True
            space.enter_block(tree.name, ctx.schema_decl(tree.name))
            status = traverser.tick(tree.root)
        except FatalBrowserError as exc:
            ctx.failure_reason = ctx.failure_reason or f"程序侧致命错误: {exc}"
            status = FAILURE
        except SchemaError as exc:
            ctx.failure_reason = ctx.failure_reason or f"运行期 schema 错误: {exc}"
            status = FAILURE
        except Exception as exc:
            logger.exception("行为树执行未预期异常")
            ctx.failure_reason = ctx.failure_reason or f"执行异常: {exc}"
            status = FAILURE
        finally:
            if started:
                try:
                    self._browser.stop()
                except Exception:
                    logger.warning("浏览器会话释放异常", exc_info=True)
        bundle = reporter.finalize()
        return RunResult(
            status=status,
            failure_reason=ctx.failure_reason if status == FAILURE else None,
            exec_report=bundle.exec_report,
            trace_report=bundle.trace_report,
        )

    def get_exec_state(self) -> ExecState:
        """可查询执行状态快照（§12.4，供 M9b 轮询）；未运行返回空状态。

        附带当前 blackboard 变量快照（§5.3 扩展，供前端变量黑板展示）。
        """
        if self._run_context is None:
            return ExecState(run_id="")
        state = self._run_context.reporter.exec_state()
        try:
            variables = self._run_context.space.snapshot_variables(
                self._run_context.space.root
            )
        except Exception:
            variables = []
        return replace(state, variables=variables)

    # ------------------------------------------------------------ 内部

    def _validate_input(
        self, tree: Any, blocks: Any, config: Any
    ) -> str | None:
        """入口校验：失败返回可修正错误信息（不启动遍历）。"""
        if tree is None or getattr(tree, "root", None) is None:
            return "行为树为空（解析产物缺失，无法执行）"
        if blocks is None:
            return "块声明表缺失（解析产物缺失）"
        if config is None:
            return "运行配置缺失"
        if not isinstance(config, RunConfig):
            return f"运行配置类型非法: {type(config).__name__}（应为 RunConfig）"
        return None

    def _make_reporter(self, run_id: str, total_nodes: int, config: RunConfig) -> Reporter:
        if self._reporter_factory is not None:
            return self._reporter_factory(run_id, total_nodes)
        return Reporter(
            run_id=run_id,
            report_dir=config.report_dir,
            total_nodes=total_nodes,
            screenshotter=self._make_screenshotter(),
        )

    def _make_screenshotter(self) -> Callable[[BrowserPageRef, str], Any]:
        """包装 M1 截图：按页面引用取回句柄后截图（schema PageRef → M1 PageRef）。"""

        def _shot(page_ref: BrowserPageRef, path: str) -> Any:
            result = self._browser.page(page_ref)
            if not result.ok:
                return result
            return result.detail["page"].screenshot(path)

        return _shot

    def _inject_global_config(self, space: SchemaSpace, config: RunConfig) -> None:
        """全局默认配置注入根级 schema（契约 §5.7.5 继承链最终兜底）。"""
        if config.timeout is not None:
            space.set_config(space.root, "timeout", float(config.timeout))
        for name, value in (config.global_config or {}).items():
            space.set_config(space.root, name, value)


__all__ = ["Engine"]
