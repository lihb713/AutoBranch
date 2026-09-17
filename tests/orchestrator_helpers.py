"""M7 编排器测试共享辅助（mock M6 叶子 / mock M1 浏览器 / 节点工厂 / RunContext 构造）。

与 ``tests/engine_helpers.py`` / ``tests/leaf_agent_helpers.py`` 同模式：位于
tests 根目录，经 ``pythonpath=["tests"]`` 以顶层模块导入，供 ``tests/orchestrator/``
用例复用。不启动真实浏览器与 LLM。
"""

from __future__ import annotations

import time

from autobranch.leaf_agent.models import LeafResult
from autobranch.parser.models import (
    ActionNode,
    BranchSpec,
    ConditionNode,
    FinishNode,
    RepeatNode,
    SelectorNode,
    SequenceNode,
)
from autobranch.reporting.models import LeafTrace

ROOT_FRAME = "主流程/"


# ---------------------------------------------------------------- 节点工厂

def action(desc: str = "动作") -> ActionNode:
    return ActionNode(description=desc)


def cond(desc: str = "条件") -> ConditionNode:
    return ConditionNode(description=desc)


def seq(*children) -> SequenceNode:
    return SequenceNode(children=tuple(children))


def branch(condition: ConditionNode | None, child) -> BranchSpec:
    return BranchSpec(condition=condition, child=child)


def sel(*branches) -> SelectorNode:
    return SelectorNode(branches=tuple(branches))


def repeat(body, mode: str = "retry", until=None, max: int = 3) -> RepeatNode:
    return RepeatNode(body=body, mode=mode, until=until, max=max)


def finish() -> FinishNode:
    return FinishNode()


# ---------------------------------------------------------------- 叶子结果

def leaf_success(
    desc: str = "成功", bool_value: bool | None = None, trace: LeafTrace | None = None
) -> LeafResult:
    return LeafResult(
        status="success",
        bool_value=bool_value,
        trace=trace or LeafTrace(llm_input={"desc": desc}),
    )


def leaf_failure(
    desc: str = "失败", terminator: str = "llm_error", source: str = "llm"
) -> LeafResult:
    return LeafResult(
        status="failure",
        error_source=source,
        trace=LeafTrace(llm_input={"desc": desc}, terminator=terminator),
    )


def leaf_condition(bool_value: bool, desc: str = "条件") -> LeafResult:
    return LeafResult(
        status="success" if bool_value else "failure",
        bool_value=bool_value,
        trace=LeafTrace(llm_input={"desc": desc}),
    )


# ---------------------------------------------------------------- mock 依赖

class StubLeaf:
    """mock M6 叶子执行器：按节点描述返回固定 ``LeafResult``（可脚本化）。

    - ``results``：描述 -> ``LeafResult`` / ``LeafResult`` 列表（按序弹出）/
      可调用对象 ``(node, timeout) -> LeafResult``。
    - 未配置的描述默认返回成功；``calls`` 记录全部调用、``timeouts`` 记录
      每个叶子收到的生效超时。
    """

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.results: dict[str, object] = {}
        self.timeouts: dict[str, float | None] = {}

    def __call__(self, node, timeout: float | None) -> LeafResult:
        self.calls.append((node, timeout))
        self.timeouts[node.description] = timeout
        handler = self.results.get(node.description, leaf_success(node.description))
        if callable(handler):
            return handler(node, timeout)
        if isinstance(handler, list):
            if not handler:
                return leaf_success(node.description)
            return handler.pop(0)
        return handler


class BlockingLeaf:
    """阻塞叶子：先 sleep 指定时长再返回（叶子超时测试用，mock M6 慢执行）。"""

    def __init__(self, delay: float, result: LeafResult | None = None) -> None:
        self.delay = delay
        self.result = result or leaf_success()
        self.calls: list[tuple] = []

    def __call__(self, node, timeout: float | None) -> LeafResult:
        self.calls.append((node, timeout))
        time.sleep(self.delay)
        return self.result


class MockBrowser:
    """mock M1 浏览器驱动：记录 start/stop 调用（不启动真实浏览器）。"""

    def __init__(self) -> None:
        self.starts: list = []
        self.stops: list = []
        self.started: bool = False

    def start(self, config=None) -> None:
        self.started = True
        self.starts.append(config)

    def stop(self) -> None:
        self.started = False
        self.stops.append(True)

    def current_page(self):
        return None

    def activate_page(self, page_ref):
        from autobranch.engine.models import OpResult

        return OpResult(True, detail={"page_ref": page_ref})


# ---------------------------------------------------------------- 上下文构造

def make_run_context(
    config,
    leaf_executor=None,
    browser=None,
    resolver=None,
    reporter=None,
    tree_name: str = ROOT_FRAME.strip("/"),
    blocks_tree=None,
    decl_inputs=None,
    decl_outputs=None,
    config_overrides=None,
):
    """构造 ``RunContext``：注入 mock 依赖、注入全局配置并进入根级块帧。

    供直接 tick（``Traverser``）测试使用；``Engine.run`` 测试请用
    ``make_engine``。
    """
    from autobranch.orchestrator import RunContext as RC
    from autobranch.reporting import Reporter
    from autobranch.schema import SchemaSpace

    space = SchemaSpace()
    if config.timeout is not None:
        space.set_config(space.root, "timeout", float(config.timeout))
    for name, value in (config.global_config or {}).items():
        space.set_config(space.root, name, value)
    if reporter is None:
        reporter = Reporter(run_id="run-test", report_dir=config.report_dir)
    if leaf_executor is None:
        leaf_executor = StubLeaf()
    ctx = RC(
        config=config,
        space=space,
        reporter=reporter,
        browser=browser or MockBrowser(),
        leaf_executor=leaf_executor,
        blocks_tree=blocks_tree or {},
        resolver=resolver,
        decl_inputs=decl_inputs or {},
        decl_outputs=decl_outputs or [],
        config_overrides=config_overrides or {},
    )
    space.enter_frame(tree_name, ctx.schema_decl(tree_name))
    return ctx


def make_engine(*, browser=None, leaf_executor=None, space_factory=None, reporter_factory=None):
    """构造 ``Engine``（默认注入 mock 浏览器与 StubLeaf）。"""
    from autobranch.orchestrator import Engine

    return Engine(
        browser=browser if browser is not None else MockBrowser(),
        leaf_executor=leaf_executor if leaf_executor is not None else StubLeaf(),
        space_factory=space_factory,
        reporter_factory=reporter_factory,
    )


def make_doc_resolver(docs: dict):
    """从 {文档名: 新 DSL dict} 构造跨文档引用解析器（测试用）。"""
    from autobranch.parser.models import DocumentSource
    from autobranch.parser.refs import MappingResolver

    resolver = MappingResolver()
    for name, raw in docs.items():
        resolver.add(DocumentSource(id=name, data=raw))
    return resolver


def make_leaf_doc(doc_name: str, leaf_name: str, action_text: str | None = None) -> dict:
    """构造单 Action 叶子被引文档（统一槽位 DSL，Root.body → Action）。"""
    return {
        "tree": doc_name,
        "nodes": {
            "n1": {"type": "Root", "name": "根", "body": "n2"},
            "n2": {
                "type": "Action",
                "name": leaf_name,
                "description": action_text or leaf_name,
            },
        },
        "root": "n1",
    }
