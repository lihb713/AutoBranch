"""M7 任务 4.1/4.2：schema 帧建帧/释放与配置参数继承（配合 M3，经 ref 动态建帧）。"""

from __future__ import annotations

from orchestrator_helpers import (
    action,
    leaf_failure,
    leaf_success,
    make_run_context,
    seq,
)

from webops.orchestrator import FAILURE, SUCCESS
from webops.orchestrator.traverser import Traverser
from webops.parser.models import RefNode


class TestFrameLifecycle:
    """任务 4.1：块引用（ref）建帧/释放时机与帧隔离。"""

    def test_frames_entered_and_released(self, config) -> None:
        """ref 子块执行期间激活帧为子块帧，退出后恢复父块帧（释放）。"""
        blocks_tree = {
            "主流程": seq(action("根1"), RefNode(ref_target="this/登录"), action("根2")),
            "登录": seq(action("块1")),
        }
        ctx = make_run_context(config, blocks_tree=blocks_tree)
        paths = []

        def probe(node, timeout):
            paths.append(ctx.space._current.path)
            return leaf_success(node.description)

        ctx.leaf_executor = probe
        assert Traverser(ctx).tick(blocks_tree["主流程"]) == SUCCESS
        assert paths == ["主流程/", "主流程/登录/", "主流程/"]
        assert ctx.space._current.path == "主流程/"  # 释放回根块帧

    def test_frames_released_on_failure(self, config) -> None:
        """无论成败都释放帧：ref 块内失败退出后激活帧恢复父帧。"""
        ctx = make_run_context(config)
        ctx.leaf_executor.results["块内失败"] = leaf_failure("块内失败")
        blocks_tree = {
            "主流程": seq(RefNode(ref_target="this/登录")),
            "登录": seq(action("块内失败")),
        }
        ctx = make_run_context(config, blocks_tree=blocks_tree)
        ctx.leaf_executor.results["块内失败"] = leaf_failure("块内失败")
        assert Traverser(ctx).tick(blocks_tree["主流程"]) == FAILURE
        assert ctx.space._current.path == "主流程/"

    def test_nested_frames_depth(self, config) -> None:
        """嵌套块引用逐层建帧，逐层释放。"""
        blocks_tree = {
            "主流程": seq(seq(RefNode(ref_target="this/导出")), action("根")),
            "导出": seq(RefNode(ref_target="this/登录")),
            "登录": seq(action("深层")),
        }
        ctx = make_run_context(config, blocks_tree=blocks_tree)
        paths = []

        def probe(node, timeout):
            paths.append(ctx.space._current.path)
            return leaf_success(node.description)

        ctx.leaf_executor = probe
        assert Traverser(ctx).tick(blocks_tree["主流程"]) == SUCCESS
        assert paths == ["主流程/导出/登录/", "主流程/"]
        assert ctx.space._current.path == "主流程/"

    def test_same_name_variables_isolated(self, config) -> None:
        """同名变量在不同块帧中互不冲突（§5.7.4）。"""
        blocks_tree = {
            "主流程": seq(RefNode(ref_target="this/登录"), RefNode(ref_target="this/导出")),
            "登录": seq(action("u1")),
            "导出": seq(action("u2")),
        }
        ctx = make_run_context(config, blocks_tree=blocks_tree)

        def writer(node, timeout):
            ctx.space.write(ctx.space._current, "this/username", node.description, "str")
            return leaf_success(node.description)

        ctx.leaf_executor = writer
        assert Traverser(ctx).tick(blocks_tree["主流程"]) == SUCCESS
        root_frame = ctx.space._current
        assert root_frame.children["登录"].storage["username"] == "u1"
        assert root_frame.children["导出"].storage["username"] == "u2"
        assert root_frame.children["登录"] is not root_frame.children["导出"]


class TestConfigInheritance:
    """任务 4.2：配置参数按「自身 → 祖先 → 全局默认」三级继承（经 ref 建帧）。"""

    def test_three_level_inheritance(self, config) -> None:
        from webops.parser.models import BlockDecl, ConfigOverride

        blocks = {
            "登录": BlockDecl(
                name="登录",
                doc_id="主流程",
                config_overrides=(ConfigOverride(name="timeout", value=5),),
            ),
            "子块": BlockDecl(name="子块", doc_id="主流程"),
        }
        ctx = make_run_context(config, blocks=blocks)
        blocks_tree = {
            "主流程": seq(action("全局叶子"), RefNode(ref_target="this/登录")),
            "登录": seq(action("登录叶子"), RefNode(ref_target="this/子块")),
            "子块": seq(action("孙块叶子")),
        }
        ctx = make_run_context(config, blocks=blocks, blocks_tree=blocks_tree)
        Traverser(ctx).tick(blocks_tree["主流程"])
        # 全局默认兜底（根级 schema 注入 config.timeout=120）
        assert ctx.leaf_executor.timeouts["全局叶子"] == 120.0
        # 块自身覆盖
        assert ctx.leaf_executor.timeouts["登录叶子"] == 5.0
        # 祖先继承：孙块未覆盖 → 继承最近祖先登录块的 5
        assert ctx.leaf_executor.timeouts["孙块叶子"] == 5.0

    def test_global_default_via_config(self, config) -> None:
        """未注入全局 timeout 时 resolve_config 返回 None（无超时检测）。"""
        from orchestrator_helpers import make_run_context

        from webops.orchestrator import RunConfig

        ctx = make_run_context(RunConfig(report_dir=config.report_dir, timeout=None))
        node = seq(action("叶子"))
        Traverser(ctx).tick(node)
        assert ctx.leaf_executor.timeouts["叶子"] is None
