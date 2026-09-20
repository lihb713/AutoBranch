"""引擎服务抽象与实现（设计 D2/D3：service 层抽象 M7，测试替换 mock）。

- ``EngineService``：抽象接口（``run`` / ``get_exec_state``），路由与执行
  后台任务只依赖它，mock M7 下可独立测试（spec §7）。
- ``EmbeddedEngineService``：真实实现，同进程内嵌 M7 ``Engine.run`` /
  ``get_exec_state``（契约 §12.3，共享内存无序列化）。报告器注入服务端
  run_id，使 M8 产物落盘于 ``<report_root>/<run_id>/``。
- ``MockEngineService``：可编程 mock（按脚本推进状态/返回结果），供
  API 与轮询流程测试。
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autobranch.config import AutoBranchConfig
from autobranch.orchestrator import Engine, RunConfig
from autobranch.orchestrator.models import RunResult
from autobranch.parser.models import DocumentSource
from autobranch.parser.parser import BehaviorTreeParser
from autobranch.parser.refs import MappingResolver
from autobranch.reporting import ExecState, Reporter
from autobranch.reporting.models import NodeReport
from autobranch.schema import SchemaSpace
from autobranch.semantic_graph.llm_fill import MockFiller

#: 引擎构造工厂：``(run_id, report_root) -> Engine``（测试注入自定义装配）。
EngineFactory = Callable[[int, Path], Engine]


class EngineService(ABC):
    """引擎服务抽象：触发执行与查询执行状态（设计 D2）。"""

    @abstractmethod
    def run(
        self,
        tree_id: int,
        content: str,
        run_id: int,
        *,
        doc_id: str | None = None,
        run_inputs: dict[str, object] | None = None,
        experience_lookup: Callable[[str], str | None] | None = None,
    ) -> RunResult:
        """内嵌执行一次行为树，返回 M7 ``RunResult``（阻塞，后台任务调用）。

        :param doc_id: 文档标识（M2 帧路径以它命名，须与根块名一致；
          缺省用 ``tree-<tree_id>`` 兜底）。
        :param run_inputs: 根级入参值（按文档 ``inputs`` 声明类型注入）。
        :param experience_lookup: 经验回灌查询回调（命中返回参考段文本，未命中
          None；None 表示不注入经验）。
        """

    @abstractmethod
    def get_exec_state(self, run_id: int) -> ExecState | None:
        """查询执行状态快照；该 run 无引擎状态（未启动/未知）返回 None。"""


def build_reporter_factory(
    run_id: int, report_root: Path, screenshotter: Callable | None = None
) -> Callable[[str, int], Reporter]:
    """构造报告器工厂：强制报告目录与 run_id 对齐服务端（``<report_root>/<run_id>/``）。

    M7 ``Engine.run`` 内部按其自生成 run_id 调用该工厂，这里改用服务端 run_id
    保证 ``runs.report_path`` 与磁盘目录一致。
    """

    def _factory(_engine_run_id: str, total_nodes: int) -> Reporter:
        return Reporter(
            run_id=str(run_id),
            report_dir=str(report_root),
            total_nodes=total_nodes,
            screenshotter=screenshotter,
        )

    return _factory


def default_screenshotter(browser) -> Callable:
    """包装 M1 截图：按页面引用取回句柄后截图（与 M7 默认截图器同逻辑）。"""

    def _shot(page_ref, path):
        result = browser.page(page_ref)
        if not result.ok:
            return result
        return result.detail["page"].screenshot(path)

    return _shot


class EmbeddedEngineService(EngineService):
    """真实引擎服务：同进程内嵌 M7（契约 §12.3）。

    :param config: 引擎统一配置（``AutoBranchConfig``，M0/M5/M7 接线）。
    :param report_root: 报告/截图持久化根目录（绝对路径）。
    :param engine_factory: 引擎构造工厂；默认装配真实 M1 浏览器 + M5 引擎函数
      （MockFiller 语义图，参照 e2e 装配方式）。测试可注入 mock 叶子/浏览器。
    """

    def __init__(
        self,
        config: AutoBranchConfig,
        report_root: Path,
        *,
        engine_factory: EngineFactory | None = None,
        registry: Any = None,
        plugins_dir: str | None = None,
    ) -> None:
        self._config = config
        self._report_root = report_root
        self._custom_factory = engine_factory is not None
        self._engine_factory = engine_factory or self._default_engine
        self._registry = registry
        self._plugins_dir = plugins_dir
        self._runs: dict[int, tuple[Engine, ExecState | None]] = {}
        self._lock = threading.Lock()

    @property
    def registry(self) -> Any:
        """共享插件注册表（插件 API 校验/重载用）。"""
        return self._registry

    # ------------------------------------------------------------- 抽象接口

    def _make_resolver(self) -> MappingResolver:
        """跨文档引用解析器：DB-backed 文档库；无 DB 时回落空 MappingResolver。"""
        try:
            from autobranch.server.services.doclib import DbResolver

            return DbResolver.from_session()
        except RuntimeError:
            return MappingResolver({})

    def run(
        self,
        tree_id: int,
        content: str,
        run_id: int,
        *,
        doc_id: str | None = None,
        run_inputs: dict[str, object] | None = None,
        experience_lookup: Callable[[str], str | None] | None = None,
    ) -> RunResult:
        """解析执行：doc_id 须与内容实际根块名一致（帧路径以它命名）。

        ``doc_id`` 缺省或与根块名不一致时按解析出的 ``tree.name`` 校正重解析
        （行为树可另命名保存，根块名由内容决定）。
        """
        desired = doc_id or f"tree-{tree_id}"
        resolver = self._make_resolver()
        probe = BehaviorTreeParser().parse(
            DocumentSource(id=desired, data=content), resolver, self._registry
        )
        actual = probe.tree.name or desired
        if actual != desired:
            result = BehaviorTreeParser().parse(
                DocumentSource(id=actual, data=content), resolver, self._registry
            )
        else:
            result = probe
        # 缺 LLM 配置时提前返回清晰可读错误（仅默认真实引擎；注入自定义
        # engine_factory 的调用方自行管理叶子执行，不拦截）。
        # 同时生成最小失败报告，使 /report、/trace 可正常读取（避免 404）。
        if not self._config.llm.api_key and not self._custom_factory:
            return self._config_error_result(run_id)
        engine = self._engine_factory(run_id, self._report_root)
        with self._lock:
            self._runs[run_id] = (engine, None)
        try:
            run_config = replace(
                self._build_run_config(), experience_lookup=experience_lookup
            )
            run_result = engine.run(
                result.tree,
                run_config,
                resolver=resolver,
                blocks_tree=result.blocks_tree,
                decl_inputs=result.decl_inputs,
                decl_outputs=result.decl_outputs,
                config_overrides=result.config,
                run_inputs=run_inputs,
            )
        finally:
            with self._lock:
                self._runs[run_id] = (engine, engine.get_exec_state())
        return run_result

    def get_exec_state(self, run_id: int) -> ExecState | None:
        with self._lock:
            entry = self._runs.get(run_id)
        if entry is None:
            return None
        engine, final_state = entry
        if final_state is not None:
            return final_state
        return engine.get_exec_state()

    # ------------------------------------------------------------- 内部装配

    def _config_error_result(self, run_id: int) -> RunResult:
        """缺 LLM 配置时的失败结果：生成最小报告，使 /report、/trace 可读。"""
        reason = (
            "未配置 LLM API 密钥：请在 autobranch.config.json 填入 api_key，"
            "或设置环境变量 AUTOBRANCH_LLM_API_KEY 后重启后端"
        )
        reporter = Reporter(run_id=str(run_id), report_dir=str(self._report_root))
        reporter.record_node(
            NodeReport(
                node_type="Action",
                node_desc="行为树执行",
                result="failure",
                timestamp=datetime.now(UTC).isoformat(),
                action_call=None,
                condition_result=None,
                page_url=None,
                screenshot_path=None,
            )
        )
        bundle = reporter.finalize()
        return RunResult(
            status="failure",
            failure_reason=reason,
            exec_report=bundle.exec_report,
            trace_report=bundle.trace_report,
        )

    def _build_run_config(self) -> RunConfig:
        cfg = self._config
        llm_config = cfg.to_llm_config() if cfg.llm.api_key else None
        return cfg.to_run_config(
            report_dir=str(self._report_root),
            llm_config=llm_config,
        )

    def _default_engine(self, run_id: int, report_root: Path) -> Engine:
        """默认装配（插件模式）：真实浏览器 + 插件框架（浏览器/计算等预置插件）。"""
        from autobranch.browser import BrowserDriver

        browser = BrowserDriver()
        schema_space = SchemaSpace()
        return Engine(
            browser=browser,
            space_factory=lambda: schema_space,
            reporter_factory=build_reporter_factory(run_id, report_root),
            registry=self._registry,
            plugins_dir=self._plugins_dir,
            llm_filler=MockFiller(),
        )


class MockEngineService(EngineService):
    """可编程 mock 引擎服务（spec §7 独立测试用）。

    - ``set_script(run_id, result, states)``：为一次 run 设定返回结果与状态
      推进序列；``get_exec_state`` 依次弹出脚本状态（轮询测试确定性推进）。
    - ``default_result``：未按键设定时的兜底返回（避免预测自增 run_id）。
    - ``call_log`` 记录 ``run`` 调用（断言后台任务触发）。
    """

    def __init__(self) -> None:
        self.call_log: list[tuple[int, str, int]] = []
        self.run_inputs_log: list[dict[str, object] | None] = []
        self.experience_lookup_log: list[Callable[[str], str | None] | None] = []
        self._results: dict[int, list[RunResult]] = {}
        self._states: dict[int, list[ExecState]] = {}
        self._final: dict[int, ExecState] = {}
        self._final_states: dict[int, ExecState] = {}
        self.default_result: RunResult = RunResult(status="success")
        self.default_final_state: ExecState | None = None

    def set_script(
        self,
        run_id: int,
        result: RunResult | None = None,
        states: list[ExecState] | None = None,
    ) -> None:
        if result is not None:
            self._results[run_id] = [result]
        if states:
            self._states[run_id] = list(states)

    def set_final_state(self, run_id: int, state: ExecState) -> None:
        """设定 run 的终态（含 completed NodeReport，供经验采集测试注入）。"""
        self._final_states[run_id] = state

    def run(
        self,
        tree_id: int,
        content: str,
        run_id: int,
        *,
        doc_id: str | None = None,
        run_inputs: dict[str, object] | None = None,
        experience_lookup: Callable[[str], str | None] | None = None,
    ) -> RunResult:
        self.call_log.append((tree_id, content, run_id))
        self.run_inputs_log.append(run_inputs)
        self.experience_lookup_log.append(experience_lookup)
        queue = self._results.get(run_id)
        outcome = queue.pop(0) if queue else self.default_result
        self._final[run_id] = (
            self._final_states.get(run_id)
            or self.default_final_state
            or ExecState(run_id=str(run_id), finished=True)
        )
        return outcome

    def get_exec_state(self, run_id: int) -> ExecState | None:
        queue = self._states.get(run_id)
        if queue:
            state = queue.pop(0)
            if not queue:
                self._states.pop(run_id, None)
            return state
        state = self._final.get(run_id)
        if state is not None:
            return state
        return self._final_states.get(run_id)


__all__ = [
    "EngineService",
    "EmbeddedEngineService",
    "MockEngineService",
    "EngineFactory",
    "build_reporter_factory",
    "default_screenshotter",
]
