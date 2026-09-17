"""M7 动态 ref 调用执行器（一文档一树）：args 注入 / returns 回收 / 帧隔离。

经 ``_tick_ref``：经 resolver 按文档名加载被引文档 → 求值实参（``Param.x``
或字面量）→ coerce 到输入类型 → 建子帧注入形参 → 递归执行被引文档主树
（从 Root 执行）→ SUCCESS 回收 returns 写父帧 → 退出子帧。
"""

from __future__ import annotations

import re

from orchestrator_helpers import (
    action,
    leaf_failure,
    leaf_success,
    make_run_context,
    seq,
)

from autobranch.orchestrator import FAILURE, SUCCESS
from autobranch.orchestrator.traverser import Traverser
from autobranch.parser.models import DocumentSource, RefNode
from autobranch.parser.parser import BehaviorTreeParser
from autobranch.parser.refs import MappingResolver
from autobranch.schema.models import PageRef

_GET_TMPL = re.compile(r"(?<![A-Za-z0-9_])Param\.([A-Za-z_][A-Za-z0-9_]*)")
_SET_TMPL = re.compile(
    r"(?<![A-Za-z0-9_])NewParam\.([A-Za-z_][A-Za-z0-9_]*)(?::(str|int|float|bool|page_ref|object))?"
)


def _doc_resolver(docs: dict[str, dict]) -> MappingResolver:
    """从 {文档名: 新 DSL dict} 构造跨文档引用解析器。"""
    resolver = MappingResolver()
    for name, raw in docs.items():
        resolver.add(DocumentSource(id=name, data=raw))
    return resolver


def _space_leaf(space, extra=None):
    """模拟 M6 叶子：对描述做 Param. 替换 + 按 NewParam. 声明写入（不经 LLM）。

    ``extra`` 为 ``{描述: callable(frame) -> str|None}`` 的自定义写入钩子；
    get 读取失败 → FAILURE（程序侧语义）。set 声明从描述文本解析
    （与 M2 ``_SET_TMPL`` 同构），写入值为占位 ``成功输出``。
    """
    extra = extra or {}

    def leaf(node, timeout):
        frame = space._current
        desc = node.description
        for m in _GET_TMPL.finditer(desc):
            value = space.read(frame, f"this/{m.group(1)}")
            if value is None:
                return leaf_failure(desc)
            desc = desc.replace(m.group(0), str(value))
        hook = extra.get(node.description)
        if hook is not None:
            problem = hook(frame)
            if problem is not None:
                return leaf_failure(f"{desc}: {problem}")
        for m in _SET_TMPL.finditer(node.description):
            path = f"this/{m.group(1)}"
            space.write(frame, path, "成功输出", m.group(2) or "str")
        return leaf_success(desc)

    return leaf


def _login_doc(inputs=None, outputs=None, body=None) -> dict:
    """构造「登录」被引文档（统一槽位 DSL，Root→Sequence→Action 叶子）。"""
    doc = {
        "tree": "登录",
        "nodes": {
            "n1": {"type": "Root", "name": "根", "body": "n2"},
            "n2": {
                "type": "Sequence",
                "name": "主流程",
                "actions": [f"n{i + 3}" for i in range(len(body or []))],
            },
        },
        "root": "n1",
    }
    if inputs:
        doc["inputs"] = inputs
    if outputs:
        doc["outputs"] = outputs
    for i, leaf in enumerate(body or []):
        doc["nodes"][f"n{i + 3}"] = {"type": "Action", "name": leaf, "description": leaf}
    return doc


class TestRefCallFromDsl:
    """新 DSL 端到端：args 列表（Param.x 变量引用/字面量）按序对应被引树 inputs，
    returns 字典（NewParam.接收名:类型）按序对应被引树 outputs。"""

    def test_dsl_ref_args_and_returns_end_to_end(self, config) -> None:
        login = _login_doc(
            inputs={"username": "str"},
            outputs=["result"],
            body=["读参数 Param.username", "输出 NewParam.result:str"],
        )
        main = {
            "tree": "主流程",
            "nodes": {
                "n1": {"type": "Root", "name": "根", "body": "n2"},
                "n2": {
                    "type": "Sequence",
                    "name": "主流程",
                    "actions": ["n3", "n4"],
                },
                "n3": {"type": "Action", "name": "填账号", "description": "填账号"},
                "n4": {
                    "type": "ref",
                    "name": "去登录",
                    "target": "登录",
                    "args": ["Param.account"],
                    "returns": {"NewParam.result": "str"},
                },
            },
            "root": "n1",
        }
        resolver = _doc_resolver({"登录": login, "主流程": main})
        result = BehaviorTreeParser().parse(DocumentSource(id="主流程", data=main), resolver)
        assert result.checks.ok
        main_tree = result.tree.root

        def fill_account(frame):
            ctx.space.write(frame, "this/account", "admin", "str")
            return None

        def check_param(frame):
            if ctx.space.read(frame, "this/username") != "admin":
                return "形参未注入"
            return None

        ctx = make_run_context(
            config, resolver=resolver, blocks_tree={"主流程": main_tree}
        )
        space = ctx.space
        ctx.leaf_executor = _space_leaf(
            space,
            extra={"填账号": fill_account, "读参数 Param.username": check_param},
        )
        assert Traverser(ctx).tick(main_tree) == SUCCESS
        root = space._current
        assert root.storage["result"] == "成功输出"
        child = root.children["登录"]
        assert child.storage["username"] == "admin"
        assert child.storage["result"] == "成功输出"

    def test_dsl_ref_literal_arg(self, config) -> None:
        """args 元素非 Param.x 引用 → 按字面量传入（校验与 inputs 类型匹配）。"""
        login = _login_doc(
            inputs={"username": "str"},
            body=["读参数 Param.username"],
        )
        main = {
            "tree": "主流程",
            "nodes": {
                "n1": {"type": "Root", "name": "根", "body": "n2"},
                "n2": {
                    "type": "Sequence",
                    "name": "主流程",
                    "actions": ["n3"],
                },
                "n3": {
                    "type": "ref",
                    "name": "去登录",
                    "target": "登录",
                    "args": ["admin"],
                },
            },
            "root": "n1",
        }
        resolver = _doc_resolver({"登录": login, "主流程": main})
        result = BehaviorTreeParser().parse(DocumentSource(id="主流程", data=main), resolver)
        assert result.checks.ok
        main_tree = result.tree.root

        def check_param(frame):
            if ctx.space.read(frame, "this/username") != "admin":
                return "字面量未注入"
            return None

        ctx = make_run_context(
            config, resolver=resolver, blocks_tree={"主流程": main_tree}
        )
        space = ctx.space
        ctx.leaf_executor = _space_leaf(
            space, extra={"读参数 Param.username": check_param}
        )
        assert Traverser(ctx).tick(main_tree) == SUCCESS
        assert space._current.children["登录"].storage["username"] == "admin"


class TestRefCall:
    """单层调用：ref args 注入 → 块内读形参 → 输出 returns 回收。"""

    def test_ref_injects_args_and_receives_returns(self, config) -> None:
        login = _login_doc(
            inputs={"username": "str"},
            outputs=["result"],
            body=["读参数 Param.username", "输出 NewParam.result:str"],
        )
        resolver = _doc_resolver({"登录": login})
        main_tree = seq(
            action("填账号"),
            RefNode(
                ref_target="登录",
                args=("Param.account",),
                returns=(("result", "str"),),
            ),
        )

        def fill_account(frame):
            ctx.space.write(frame, "this/account", "admin", "str")
            return None

        def check_param(frame):
            if ctx.space.read(frame, "this/username") != "admin":
                return "形参未注入"
            return None

        ctx = make_run_context(config, resolver=resolver, blocks_tree={"主流程": main_tree})
        space = ctx.space
        ctx.leaf_executor = _space_leaf(
            space,
            extra={"填账号": fill_account, "读参数 Param.username": check_param},
        )
        assert Traverser(ctx).tick(main_tree) == SUCCESS
        # 父帧：returns 回收写入 this/result
        root = ctx.space._current
        assert root.storage["result"] == "成功输出"
        # 子帧：args 注入的形参与块内 set 的输出
        child = root.children["登录"]
        assert child.storage["username"] == "admin"
        assert child.storage["result"] == "成功输出"
        # 执行后激活帧回到父帧
        assert ctx.space._current is root

    def test_same_block_ref_twice_independent_frames(self, config) -> None:
        login = _login_doc(
            inputs={"username": "str"},
            outputs=["result"],
            body=["读参数 Param.username", "输出 NewParam.result:str"],
        )
        resolver = _doc_resolver({"登录": login})
        seen_frames = []

        def check_param(frame):
            seen_frames.append((frame.id, ctx.space.read(frame, "this/username")))
            return None

        main_tree = seq(
            RefNode(
                ref_target="登录",
                args=("Param.account1",),
                returns=(("result1", "str"),),
            ),
            RefNode(
                ref_target="登录",
                args=("Param.account2",),
                returns=(("result2", "str"),),
            ),
        )
        ctx = make_run_context(config, resolver=resolver, blocks_tree={"主流程": main_tree})
        space = ctx.space
        space.write(space._current, "this/account1", "u1", "str")
        space.write(space._current, "this/account2", "u2", "str")
        ctx.leaf_executor = _space_leaf(
            space,
            extra={"读参数 Param.username": check_param},
        )
        assert Traverser(ctx).tick(main_tree) == SUCCESS
        # 两次调用是独立帧实例
        assert len(seen_frames) == 2
        assert seen_frames[0][0] != seen_frames[1][0]
        # 各自的实参注入到各自的子帧
        assert seen_frames[0][1] == "u1"
        assert seen_frames[1][1] == "u2"
        # 各自 returns 回收进父帧不同变量
        root = ctx.space._current
        assert root.storage["result1"] == "成功输出"
        assert root.storage["result2"] == "成功输出"

    def test_child_failure_propagates_and_skips_returns(self, config) -> None:
        login = _login_doc(
            inputs={"username": "str"},
            outputs=["result"],
            body=["块内失败"],
        )
        resolver = _doc_resolver({"登录": login})
        main_tree = seq(
            RefNode(
                ref_target="登录",
                args=("Param.account",),
                returns=(("result", "str"),),
            ),
            action("后续"),
        )
        ctx = make_run_context(config, resolver=resolver, blocks_tree={"主流程": main_tree})
        space = ctx.space
        space.write(space._current, "this/account", "admin", "str")
        ctx.leaf_executor.results["块内失败"] = leaf_failure("块内失败")
        assert Traverser(ctx).tick(main_tree) == FAILURE
        # FAILURE → 不写 returns，且后续叶子不执行
        assert "result" not in ctx.space._current.storage
        assert len(ctx.leaf_executor.calls) == 1
        # 激活帧恢复父帧
        assert ctx.space._current.name == "主流程"

    def test_config_inheritance_through_ref_frames(self, config) -> None:
        login = _login_doc(body=["块叶子"])
        login["timeout"] = 7
        resolver = _doc_resolver({"登录": login})
        main_tree = seq(RefNode(ref_target="登录"))
        ctx = make_run_context(config, resolver=resolver, blocks_tree={"主流程": main_tree})
        assert Traverser(ctx).tick(main_tree) == SUCCESS
        assert ctx.leaf_executor.timeouts["块叶子"] == 7.0

    def test_page_ref_passed_as_arg_and_activated_in_child(self, config) -> None:
        login = _login_doc(inputs={"page": "page_ref"}, body=["激活 Param.page"])
        resolver = _doc_resolver({"登录": login})

        def activate(frame):
            ctx.space.activate_page(frame, "page")
            current = ctx.space.current_page(frame)
            if current is None or current.page_id != "p1":
                return "页面变量未激活"
            return None

        main_tree = seq(RefNode(ref_target="登录", args=("Param.pageVar",)))
        ctx = make_run_context(config, resolver=resolver, blocks_tree={"主流程": main_tree})
        space = ctx.space
        space.write(
            space._current,
            "this/pageVar",
            PageRef(page_id="p1", url="https://x"),
            "page_ref",
        )
        ctx.leaf_executor = _space_leaf(space, extra={"激活 Param.page": activate})
        assert Traverser(ctx).tick(main_tree) == SUCCESS
        # 子帧注入的是 PageRef 值（页面变量走 args 传递）
        child = ctx.space._current.children["登录"]
        assert isinstance(child.storage["page"], PageRef)
        assert child.storage["page"].page_id == "p1"

    def test_ref_arg_undefined_fails(self, config) -> None:
        """父帧未定义变量作为 Param.x 实参 → ref FAILURE，不注入 "None"、不建子帧。"""
        login = _login_doc(inputs={"username": "str"}, body=["块内动作"])
        resolver = _doc_resolver({"登录": login})
        main_tree = seq(
            RefNode(ref_target="登录", args=("Param.undefinedArg",)),
        )
        ctx = make_run_context(config, resolver=resolver, blocks_tree={"主流程": main_tree})
        space = ctx.space
        ctx.leaf_executor = _space_leaf(space)
        assert Traverser(ctx).tick(main_tree) == FAILURE
        # 失败原因指明实参求值失败
        assert "实参" in (ctx.failure_reason or "")
        # 未建子帧（不进入目标块），无 "None" 注入
        assert "登录" not in space._current.children
        # 激活帧恢复父帧
        assert space._current.name == "主流程"

    def test_ref_progress_not_premature(self, config) -> None:
        """ref 树的进度：count_nodes 计入被引用块子树，进度不提前饱和 1.0。

        ref 递归 tick 记录全部子块节点；total 必须同样计入，否则
        completed/total > 1 导致 progress 提前钳到 1.0（子块仍在执行）。
        """
        from orchestrator_helpers import make_engine

        from autobranch.parser.models import BehaviorTree

        login = _login_doc(body=["登录叶"])
        export = {
            "tree": "导出",
            "nodes": {
                "n1": {"type": "Root", "name": "根", "body": "n2"},
                "n2": {"type": "Sequence", "name": "导出", "actions": ["n3", "n4"]},
                "n3": {"type": "ref", "name": "去登录", "target": "登录"},
                "n4": {"type": "Action", "name": "导出叶", "description": "导出叶"},
            },
            "root": "n1",
        }
        resolver = _doc_resolver({"登录": login, "导出": export})
        main_tree = seq(RefNode(ref_target="导出"), action("根后"))
        tree = BehaviorTree(name="主流程", root=main_tree)
        engine = make_engine()
        snapshots = []

        def probe(node, timeout):
            snapshots.append(engine.get_exec_state())
            return leaf_success(node.description)

        engine._leaf_executor = probe
        result = engine.run(
            tree,
            config,
            resolver=resolver,
            blocks_tree={"主流程": main_tree},
        )
        assert result.status == "success"
        # 进度单调不减、不提前饱和（中间 < 1.0），结束到 1.0
        progresses = [s.progress for s in snapshots]
        assert progresses == sorted(progresses)
        assert progresses[0] == 0.0
        assert all(p < 1.0 for p in progresses[:-1])
        # 结束状态进度到达 1.0，且子块节点计入已完成
        state = engine.get_exec_state()
        assert state.finished is True
        assert state.progress == 1.0
        descs = [r.node_desc for r in state.completed]
        assert "登录叶" in descs
        assert "导出叶" in descs
