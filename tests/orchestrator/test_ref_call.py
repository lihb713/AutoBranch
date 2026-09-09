"""M7 动态 ref 调用执行器（Plan ③ Task 3）：args 注入 / returns 回收 / 帧隔离。

经 ``_tick_ref``：求值实参（父帧裸路径或字面量）→ coerce 到输入类型 →
建子帧注入形参 → 递归执行目标块树 → SUCCESS 回收 returns 写父帧 → 退出子帧。
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

from webops.orchestrator import FAILURE, SUCCESS
from webops.orchestrator.traverser import Traverser
from webops.parser.models import BlockDecl, RefNode
from webops.schema.models import PageRef

_GET_TMPL = re.compile(r"\[\[\s*get:\s*this/([^\[\]]+?)\s*\]\]")
_SET_TMPL = re.compile(
    r"\[\[\s*set:(?:(str|int|float|bool|page_ref):)?\s*this/([^\[\]:]+?)\s*\]\]"
)


def _space_leaf(space, extra=None):
    """模拟 M6 叶子：对描述做 get 替换 + 按 set 声明写入（不经 LLM）。

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
            path = f"this/{m.group(2)}"
            space.write(frame, path, "成功输出", m.group(1) or "str")
        return leaf_success(desc)

    return leaf


class TestRefCall:
    """单层调用：ref args 注入 → 块内读形参 → 输出 returns 回收。"""

    def test_ref_injects_args_and_receives_returns(self, config) -> None:
        blocks = {
            "登录": BlockDecl(
                name="登录",
                doc_id="主流程",
                inputs=(("username", "str"),),
                outputs=("result",),
            )
        }

        def fill_account(frame):
            space.write(frame, "this/账号", "admin", "str")
            return None

        def check_param(frame):
            if space.read(frame, "this/username") != "admin":
                return "形参未注入"
            return None

        blocks_tree = {
            "主流程": seq(
                action("填账号"),
                RefNode(
                    ref_target="this/登录",
                    args=(("username", "this/账号"),),
                    returns=(("result", "this/结果"),),
                ),
            ),
            "登录": seq(
                action("读参数 [[get:this/username]]"), action("输出 [[set:str:this/result]]")
            ),
        }
        ctx = make_run_context(config, blocks=blocks, blocks_tree=blocks_tree)
        space = ctx.space
        ctx.leaf_executor = _space_leaf(
            space,
            extra={"填账号": fill_account, "读参数 [[get:this/username]]": check_param},
        )
        assert Traverser(ctx).tick(blocks_tree["主流程"]) == SUCCESS
        # 父帧：returns 回收写入 this/结果
        root = ctx.space._current
        assert root.storage["结果"] == "成功输出"
        # 子帧：args 注入的形参与块内 set 的输出
        child = root.children["登录"]
        assert child.storage["username"] == "admin"
        assert child.storage["result"] == "成功输出"
        # 执行后激活帧回到父帧
        assert ctx.space._current is root

    def test_same_block_ref_twice_independent_frames(self, config) -> None:
        blocks = {
            "登录": BlockDecl(
                name="登录",
                doc_id="主流程",
                inputs=(("username", "str"),),
                outputs=("result",),
            )
        }
        seen_frames = []

        def check_param(frame):
            seen_frames.append((frame.id, space.read(frame, "this/username")))
            return None

        blocks_tree = {
            "主流程": seq(
                RefNode(
                    ref_target="this/登录",
                    args=(("username", "this/账号1"),),
                    returns=(("result", "this/结果1"),),
                ),
                RefNode(
                    ref_target="this/登录",
                    args=(("username", "this/账号2"),),
                    returns=(("result", "this/结果2"),),
                ),
            ),
            "登录": seq(
                action("读参数 [[get:this/username]]"), action("输出 [[set:str:this/result]]")
            ),
        }
        ctx = make_run_context(config, blocks=blocks, blocks_tree=blocks_tree)
        space = ctx.space
        space.write(space._current, "this/账号1", "u1", "str")
        space.write(space._current, "this/账号2", "u2", "str")
        ctx.leaf_executor = _space_leaf(
            space,
            extra={"读参数 [[get:this/username]]": check_param},
        )
        assert Traverser(ctx).tick(blocks_tree["主流程"]) == SUCCESS
        # 两次调用是独立帧实例
        assert len(seen_frames) == 2
        assert seen_frames[0][0] != seen_frames[1][0]
        # 各自的实参注入到各自的子帧
        assert seen_frames[0][1] == "u1"
        assert seen_frames[1][1] == "u2"
        # 各自 returns 回收进父帧不同变量
        root = ctx.space._current
        assert root.storage["结果1"] == "成功输出"
        assert root.storage["结果2"] == "成功输出"

    def test_child_failure_propagates_and_skips_returns(self, config) -> None:
        blocks = {
            "登录": BlockDecl(
                name="登录",
                doc_id="主流程",
                inputs=(("username", "str"),),
                outputs=("result",),
            )
        }
        blocks_tree = {
            "主流程": seq(
                RefNode(
                    ref_target="this/登录",
                    args=(("username", "this/账号"),),
                    returns=(("result", "this/结果"),),
                ),
                action("后续"),
            ),
            "登录": seq(action("块内失败")),
        }
        ctx = make_run_context(config, blocks=blocks, blocks_tree=blocks_tree)
        space = ctx.space
        space.write(space._current, "this/账号", "admin", "str")
        ctx.leaf_executor.results["块内失败"] = leaf_failure("块内失败")
        assert Traverser(ctx).tick(blocks_tree["主流程"]) == FAILURE
        # FAILURE → 不写 returns，且后续叶子不执行
        assert "结果" not in ctx.space._current.storage
        assert len(ctx.leaf_executor.calls) == 1
        # 激活帧恢复父帧
        assert ctx.space._current.block_name == "主流程"

    def test_config_inheritance_through_ref_frames(self, config) -> None:
        from webops.parser.models import ConfigOverride

        blocks = {
            "登录": BlockDecl(
                name="登录",
                doc_id="主流程",
                config_overrides=(ConfigOverride(name="timeout", value=7),),
            )
        }
        blocks_tree = {
            "主流程": seq(RefNode(ref_target="this/登录")),
            "登录": seq(action("块叶子")),
        }
        ctx = make_run_context(config, blocks=blocks, blocks_tree=blocks_tree)
        assert Traverser(ctx).tick(blocks_tree["主流程"]) == SUCCESS
        assert ctx.leaf_executor.timeouts["块叶子"] == 7.0

    def test_page_ref_passed_as_arg_and_activated_in_child(self, config) -> None:
        blocks = {
            "登录": BlockDecl(
                name="登录",
                doc_id="主流程",
                inputs=(("page", "page_ref"),),
            )
        }

        def activate(frame):
            space.activate_page(frame, "page")
            current = space.current_page(frame)
            if current is None or current.page_id != "p1":
                return "页面变量未激活"
            return None

        blocks_tree = {
            "主流程": seq(RefNode(ref_target="this/登录", args=(("page", "this/页"),))),
            "登录": seq(action("激活 [[get:this/page]]")),
        }
        ctx = make_run_context(config, blocks=blocks, blocks_tree=blocks_tree)
        space = ctx.space
        space.write(space._current, "this/页", PageRef(page_id="p1", url="https://x"), "page_ref")
        ctx.leaf_executor = _space_leaf(space, extra={"激活 [[get:this/page]]": activate})
        assert Traverser(ctx).tick(blocks_tree["主流程"]) == SUCCESS
        # 子帧注入的是 PageRef 值（页面变量走 args 传递）
        child = ctx.space._current.children["登录"]
        assert isinstance(child.storage["page"], PageRef)
        assert child.storage["page"].page_id == "p1"

    def test_ref_arg_undefined_fails(self, config) -> None:
        """父帧未定义变量作为裸路径实参 → ref FAILURE，不注入 "None"、不建子帧。"""
        blocks = {
            "登录": BlockDecl(
                name="登录",
                doc_id="主流程",
                inputs=(("username", "str"),),
            )
        }
        blocks_tree = {
            "主流程": seq(
                RefNode(
                    ref_target="this/登录",
                    args=(("username", "this/未定义账号"),),
                ),
            ),
            "登录": seq(action("块内动作")),
        }
        ctx = make_run_context(config, blocks=blocks, blocks_tree=blocks_tree)
        space = ctx.space
        ctx.leaf_executor = _space_leaf(space)
        assert Traverser(ctx).tick(blocks_tree["主流程"]) == FAILURE
        # 失败原因指明实参求值失败
        assert "实参" in (ctx.failure_reason or "")
        # 未建子帧（不进入目标块），无 "None" 注入
        assert "登录" not in space._current.children
        # 激活帧恢复父帧
        assert space._current.block_name == "主流程"

    def test_ref_progress_not_premature(self, config) -> None:
        """ref 树的进度：count_nodes 计入被引用块子树，进度不提前饱和 1.0。

        ref 递归 tick 记录全部子块节点；total 必须同样计入，否则
        completed/total > 1 导致 progress 提前钳到 1.0（子块仍在执行）。
        """
        from orchestrator_helpers import make_engine

        from webops.parser.models import BehaviorTree

        blocks_tree = {
            "主流程": seq(RefNode(ref_target="this/导出"), action("根后")),
            "导出": seq(RefNode(ref_target="this/登录"), action("导出叶")),
            "登录": seq(action("登录叶")),
        }
        tree = BehaviorTree(name="主流程", root=blocks_tree["主流程"])
        engine = make_engine()
        snapshots = []

        def probe(node, timeout):
            snapshots.append(engine.get_exec_state())
            return leaf_success(node.description)

        engine._leaf_executor = probe
        result = engine.run(tree, {}, config, blocks_tree=blocks_tree)
        assert result.status == "success"
        # 8 节点 = 主流程seq/RefNode主/根后/导出seq/RefNode导/导出叶/登录seq/登录叶
        progresses = [s.progress for s in snapshots]
        assert progresses == [0.0, 3 / 8, 6 / 8]
        # 结束状态进度到达 1.0，且子块节点计入已完成
        state = engine.get_exec_state()
        assert state.finished is True
        assert state.progress == 1.0
        descs = [r.node_desc for r in state.completed]
        assert "登录叶" in descs
        assert "导出叶" in descs

    def test_cross_doc_same_name_block_resolves_to_owner(self, config) -> None:
        """跨文档同名块碰撞：导出块内部 this/登录 运行期解析到所属文档。

        根文档（主流程）与跨文档（导出）各有同名块「登录」；静态解析已把
        导出块的 this/登录 指到所属文档，运行期必须同样命中「导出/登录」，
        而非误取根文档同名块。
        """
        from parser_fixtures import build_resolver

        from webops.parser.models import DocumentSource
        from webops.parser.parser import BehaviorTreeParser

        resolver = build_resolver(
            DocumentSource(
                id="主流程",
                data={"block 主流程": {"Sequence": [{"ref": "导出/导出"}]}},
            ),
            DocumentSource(
                id="导出",
                data={
                    "block 导出": {"Sequence": [{"ref": "this/登录"}]},
                    "block 登录": {
                        "Sequence": [{"Step": {"action": "导出文档登录块", "expect": "非空"}}]
                    },
                },
            ),
        )
        result = BehaviorTreeParser().parse(
            DocumentSource(
                id="主流程",
                data={
                    "block 主流程": {"Sequence": [{"ref": "导出/导出"}]},
                    "block 登录": {
                        "Sequence": [{"Step": {"action": "根文档登录块", "expect": "非空"}}]
                    },
                },
            ),
            resolver,
        )
        assert result.checks.ok, result.checks.issues
        ctx = make_run_context(
            config, blocks=result.blocks, blocks_tree=result.blocks_tree, tree_name="主流程"
        )
        calls: list[str] = []
        base = _space_leaf(ctx.space)

        def rec(node, timeout):
            calls.append(node.description)
            return base(node, timeout)

        ctx.leaf_executor = rec
        assert Traverser(ctx).tick(result.blocks_tree["主流程"]) == SUCCESS
        # 命中导出文档的同名块，而非根文档同名块
        assert "导出文档登录块" in calls
        assert "根文档登录块" not in calls

    def test_returns_respects_declared_type(self, config) -> None:
        """returns 回收输出时优先父帧已声明类型，不覆盖为推断类型。

        父帧预声明 this/结果 为 str；被引用块输出 int。returns 回写必须尊重
        声明类型（类型契约），而不静默以 infer_type(int)=int 覆盖。
        """
        blocks = {
            "导出": BlockDecl(name="导出", doc_id="主流程", outputs=("num",)),
        }

        def write_int(frame):
            space.write(frame, "this/num", 5, "int")
            return None

        blocks_tree = {
            "主流程": seq(RefNode(ref_target="this/导出", returns=(("num", "this/结果"),))),
            "导出": seq(action("产整数")),
        }
        ctx = make_run_context(config, blocks=blocks, blocks_tree=blocks_tree)
        space = ctx.space
        space.write(space._current, "this/结果", "initial", "str")
        ctx.leaf_executor = _space_leaf(space, extra={"产整数": write_int})
        assert Traverser(ctx).tick(blocks_tree["主流程"]) == FAILURE
        assert "类型" in (ctx.failure_reason or "")

    def test_cross_doc_chain_owner_this_at_runtime(self, config) -> None:
        """跨文档链 主流程→导出→(this/登录)：导出块内部 this/ 解析到所属文档。

        静态校验无 missing_block（handoff 2 修复），运行期三层动态调用：
        主流程帧 → 导出帧 → 登录帧，args 逐层注入、returns 逐层回收。
        """
        from parser_fixtures import build_resolver

        from webops.parser.models import DocumentSource
        from webops.parser.parser import BehaviorTreeParser

        resolver = build_resolver(
            DocumentSource(
                id="主流程",
                data={
                    "block 主流程": {
                        "Sequence": [
                            {
                                "ref": "导出/导出",
                                "args": {"username": "this/账号", "password": "this/密"},
                                "returns": {"report": "this/报告"},
                            }
                        ]
                    }
                },
            ),
            DocumentSource(
                id="导出",
                data={
                    "block 导出": {
                        "inputs": {"username": "str", "password": "str"},
                        "outputs": "report",
                        "Sequence": [
                            {
                                "ref": "this/登录",
                                "args": {"username": "this/username", "password": "this/password"},
                                "returns": {"login_success": "this/成功"},
                            },
                            {"Step": {"action": "输出 [[set:str:this/report]]", "expect": "非空"}},
                        ],
                    },
                    "block 登录": {
                        "inputs": {"username": "str", "password": "str"},
                        "outputs": "login_success",
                        "Sequence": [
                            {"Step": {"action": "读参数 [[get:this/username]]", "expect": "正确"}},
                            {
                                "Step": {
                                    "action": "输出 [[set:str:this/login_success]]",
                                    "expect": "非空",
                                }
                            },
                        ],
                    },
                },
            ),
        )
        result = BehaviorTreeParser().parse(
            DocumentSource(
                id="主流程",
                data={
                    "block 主流程": {
                        "Sequence": [
                            {
                                "ref": "导出/导出",
                                "args": {"username": "this/账号", "password": "this/密"},
                                "returns": {"report": "this/报告"},
                            }
                        ]
                    }
                },
            ),
            resolver,
        )
        assert result.checks.ok, result.checks.issues
        ctx = make_run_context(
            config, blocks=result.blocks, blocks_tree=result.blocks_tree, tree_name="主流程"
        )
        space = ctx.space
        space.write(space._current, "this/账号", "admin", "str")
        space.write(space._current, "this/密", "pw", "str")
        ctx.leaf_executor = _space_leaf(space)
        assert Traverser(ctx).tick(result.blocks_tree["主流程"]) == SUCCESS
        # returns 逐层回收：登录→导出（this/成功），导出→主流程（this/报告）
        root = ctx.space._current
        assert root.storage["报告"] == "成功输出"
        export = root.children["导出"]
        assert export.storage["成功"] == "成功输出"
        login = export.children["登录"]
        assert login.storage["username"] == "admin"
        assert login.storage["login_success"] == "成功输出"
