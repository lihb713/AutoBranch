"""M7 任务 4.1/4.2：schema 帧建帧/释放与配置参数继承（一文档一树，经 ref 动态建帧）。"""

from __future__ import annotations

from orchestrator_helpers import (
    action,
    leaf_failure,
    leaf_success,
    make_doc_resolver,
    make_leaf_doc,
    make_run_context,
    seq,
)

from webops.orchestrator import FAILURE, SUCCESS
from webops.orchestrator.traverser import Traverser
from webops.parser.models import ActionNode, RefNode


class TestFrameLifecycle:
    """任务 4.1：ref 建帧/释放时机与帧隔离。"""

    def test_frames_entered_and_released(self, config) -> None:
        """ref 子帧执行期间激活帧为子帧，退出后恢复父帧（释放）。"""
        resolver = make_doc_resolver({"登录": make_leaf_doc("登录", "块1")})
        main_tree = seq(action("根1"), RefNode(ref_target="登录"), action("根2"))
        ctx = make_run_context(config, resolver=resolver, blocks_tree={"主流程": main_tree})
        paths = []

        def probe(node, timeout):
            if isinstance(node, ActionNode):
                paths.append(ctx.space._current.path)
            return leaf_success(node.description)

        ctx.leaf_executor = probe
        assert Traverser(ctx).tick(main_tree) == SUCCESS
        assert paths == ["主流程/", "主流程/登录/", "主流程/"]
        assert ctx.space._current.path == "主流程/"  # 释放回根帧

    def test_frames_released_on_failure(self, config) -> None:
        """无论成败都释放帧：ref 内失败退出后激活帧恢复父帧。"""
        resolver = make_doc_resolver({"登录": make_leaf_doc("登录", "块内失败")})
        main_tree = seq(RefNode(ref_target="登录"))
        ctx = make_run_context(config, resolver=resolver, blocks_tree={"主流程": main_tree})
        ctx.leaf_executor.results["块内失败"] = leaf_failure("块内失败")
        assert Traverser(ctx).tick(main_tree) == FAILURE
        assert ctx.space._current.path == "主流程/"

    def test_nested_frames_depth(self, config) -> None:
        """嵌套 ref 逐层建帧，逐层释放。"""
        resolver = make_doc_resolver(
            {
                "导出": {
                    "tree": "导出",
                    "nodes": {
                        "n1": {"type": "Root", "name": "根", "body": "n2"},
                        "n2": {"type": "ref", "name": "去登录", "target": "登录"},
                    },
                    "root": "n1",
                },
                "登录": make_leaf_doc("登录", "深层"),
            }
        )
        main_tree = seq(seq(RefNode(ref_target="导出")), action("根"))
        ctx = make_run_context(config, resolver=resolver, blocks_tree={"主流程": main_tree})
        paths = []

        def probe(node, timeout):
            if isinstance(node, ActionNode):
                paths.append(ctx.space._current.path)
            return leaf_success(node.description)

        ctx.leaf_executor = probe
        assert Traverser(ctx).tick(main_tree) == SUCCESS
        assert paths == ["主流程/导出/登录/", "主流程/"]
        assert ctx.space._current.path == "主流程/"

    def test_same_name_variables_isolated(self, config) -> None:
        """同名变量在不同子帧中互不冲突（§5.7.4）。"""
        resolver = make_doc_resolver(
            {
                "登录": make_leaf_doc("登录", "u1"),
                "导出": make_leaf_doc("导出", "u2"),
            }
        )
        main_tree = seq(RefNode(ref_target="登录"), RefNode(ref_target="导出"))
        ctx = make_run_context(config, resolver=resolver, blocks_tree={"主流程": main_tree})

        def writer(node, timeout):
            if isinstance(node, ActionNode):
                ctx.space.write(ctx.space._current, "this/username", node.description, "str")
            return leaf_success(node.description)

        ctx.leaf_executor = writer
        assert Traverser(ctx).tick(main_tree) == SUCCESS
        root_frame = ctx.space._current
        assert root_frame.children["登录"].storage["username"] == "u1"
        assert root_frame.children["导出"].storage["username"] == "u2"
        assert root_frame.children["登录"] is not root_frame.children["导出"]


class TestConfigInheritance:
    """任务 4.2：配置参数按「自身 → 祖先 → 全局默认」三级继承（经 ref 建帧）。"""

    def test_three_level_inheritance(self, config) -> None:
        login_doc = {
            "tree": "登录",
            "timeout": 5,
            "nodes": {
                "n1": {"type": "Root", "name": "根", "body": "n2"},
                "n2": {
                    "type": "Sequence",
                    "name": "登录",
                    "actions": ["n3", "n4"],
                },
                "n3": {"type": "Action", "name": "登录叶子", "description": "登录叶子"},
                "n4": {"type": "ref", "name": "去子块", "target": "子块"},
            },
            "root": "n1",
        }
        resolver = make_doc_resolver(
            {"登录": login_doc, "子块": make_leaf_doc("子块", "孙块叶子")}
        )
        main_tree = seq(action("全局叶子"), RefNode(ref_target="登录"))
        ctx = make_run_context(config, resolver=resolver, blocks_tree={"主流程": main_tree})
        Traverser(ctx).tick(main_tree)
        # 全局默认兜底（根级 schema 注入 config.timeout=120）
        assert ctx.leaf_executor.timeouts["全局叶子"] == 120.0
        # 被引文档自身覆盖
        assert ctx.leaf_executor.timeouts["登录叶子"] == 5.0
        # 祖先继承：子块未覆盖 → 继承最近祖先登录文档的 5
        assert ctx.leaf_executor.timeouts["孙块叶子"] == 5.0

    def test_global_default_via_config(self, config) -> None:
        """未注入全局 timeout 时 resolve_config 返回 None（无超时检测）。"""
        from orchestrator_helpers import make_run_context

        from webops.orchestrator import RunConfig

        ctx = make_run_context(RunConfig(report_dir=config.report_dir, timeout=None))
        node = seq(action("叶子"))
        Traverser(ctx).tick(node)
        assert ctx.leaf_executor.timeouts["叶子"] is None
