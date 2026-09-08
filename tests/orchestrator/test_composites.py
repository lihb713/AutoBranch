"""M7 任务 2.1~2.6：组合节点（Sequence/Selector/Repeat 两模式）表驱动测试。

组合节点为纯程序确定性遍历（§5.7.7）：聚合、短路、上界，全部经 mock 叶子
验证（零 LLM / 零真实浏览器）。
"""

from __future__ import annotations

import pytest
from orchestrator_helpers import (
    action,
    branch,
    cond,
    leaf_condition,
    leaf_failure,
    leaf_success,
    make_run_context,
    repeat,
    sel,
    seq,
)

from webops.orchestrator import FAILURE, SUCCESS
from webops.orchestrator.traverser import Traverser


class TestSequence:
    """任务 2.1：Sequence 依次执行、首个 FAILURE 短路、全 SUCCESS 才 SUCCESS。"""

    @pytest.mark.parametrize(
        ("leaf_results", "expected", "executed"),
        [
            # 全 SUCCESS → SUCCESS，全部执行
            (
                {"a": leaf_success("a"), "b": leaf_success("b"), "c": leaf_success("c")},
                SUCCESS,
                3,
            ),
            # 首个 FAILURE → 短路，后续不执行
            (
                {"a": leaf_failure("a"), "b": leaf_success("b"), "c": leaf_success("c")},
                FAILURE,
                1,
            ),
            # 中途 FAILURE → 短路，后续不执行
            (
                {"a": leaf_success("a"), "b": leaf_failure("b"), "c": leaf_success("c")},
                FAILURE,
                2,
            ),
        ],
    )
    def test_sequence_branches(self, config, leaf_results, expected, executed) -> None:
        ctx = make_run_context(config)
        ctx.leaf_executor.results.update(leaf_results)
        node = seq(action("a"), action("b"), action("c"))
        status = Traverser(ctx).tick(node)
        assert status == expected
        # 短路后后续子节点不执行：调用数精确等于期望执行数
        assert len(ctx.leaf_executor.calls) == executed


class TestSelector:
    """任务 2.2：Selector 按条件分流、首个命中分支生效（短路）、全 FAILURE 才 FAILURE。"""

    @pytest.mark.parametrize(
        ("leaf_results", "expected", "executed_descs"),
        [
            # 首个分支条件命中 → 走该分支，后续分支不执行
            (
                {
                    "cond1": leaf_condition(True),
                    "child1": leaf_success("child1"),
                    "cond2": leaf_condition(True),
                    "child2": leaf_success("child2"),
                },
                SUCCESS,
                ["cond1", "child1"],
            ),
            # 条件1 未命中 → 检查条件2 命中 → 走分支2
            (
                {
                    "cond1": leaf_condition(False),
                    "child1": leaf_success("child1"),
                    "cond2": leaf_condition(True),
                    "child2": leaf_success("child2"),
                },
                SUCCESS,
                ["cond1", "cond2", "child2"],
            ),
            # 全部分支条件失败 → 整体 FAILURE，不落入任何分支
            (
                {
                    "cond1": leaf_condition(False),
                    "child1": leaf_success("child1"),
                    "cond2": leaf_condition(False),
                    "child2": leaf_success("child2"),
                },
                FAILURE,
                ["cond1", "cond2"],
            ),
        ],
    )
    def test_selector_branches(self, config, leaf_results, expected, executed_descs) -> None:
        ctx = make_run_context(config)
        ctx.leaf_executor.results.update(leaf_results)
        node = sel(
            branch(cond("cond1"), action("child1")),
            branch(cond("cond2"), action("child2")),
        )
        status = Traverser(ctx).tick(node)
        assert status == expected
        descs = [n.description for n, _ in ctx.leaf_executor.calls]
        assert descs == executed_descs

    def test_selector_otherwise_branch(self, config) -> None:
        """otherwise 分支（condition=None）：条件未命中时直接走该分支。"""
        ctx = make_run_context(config)
        ctx.leaf_executor.results.update(
            {"cond1": leaf_condition(False), "child1": leaf_success("child1"),
             "child2": leaf_success("child2")}
        )
        node = sel(
            branch(cond("cond1"), action("child1")),
            branch(None, action("child2")),
        )
        assert Traverser(ctx).tick(node) == SUCCESS
        assert [n.description for n, _ in ctx.leaf_executor.calls] == ["cond1", "child2"]

    def test_selector_no_fallback_on_child_failure(self, config) -> None:
        """分支条件命中但子节点失败 → 整体 FAILURE（不承载兜底，不试下一分支）。"""
        ctx = make_run_context(config)
        ctx.leaf_executor.results.update(
            {"cond1": leaf_condition(True), "child1": leaf_failure("child1"),
             "cond2": leaf_condition(True), "child2": leaf_success("child2")}
        )
        node = sel(
            branch(cond("cond1"), action("child1")),
            branch(cond("cond2"), action("child2")),
        )
        assert Traverser(ctx).tick(node) == FAILURE
        assert [n.description for n, _ in ctx.leaf_executor.calls] == ["cond1", "child1"]


class TestRepeatRetry:
    """任务 2.3/2.5：Retry 每轮直接执行 body，成功即退、失败重试至上限。"""

    def test_retry_success_first_try(self, config) -> None:
        ctx = make_run_context(config)
        ctx.leaf_executor.results["body"] = leaf_success("body")
        status = Traverser(ctx).tick(repeat(action("body"), mode="retry", max=5))
        assert status == SUCCESS
        assert len(ctx.leaf_executor.calls) == 1

    def test_retry_fails_then_succeeds(self, config) -> None:
        ctx = make_run_context(config)
        ctx.leaf_executor.results["body"] = [
            leaf_failure("body"),
            leaf_failure("body"),
            leaf_success("body"),
        ]
        status = Traverser(ctx).tick(repeat(action("body"), mode="retry", max=5))
        assert status == SUCCESS
        assert len(ctx.leaf_executor.calls) == 3

    def test_retry_exhausts_max_returns_failure(self, config) -> None:
        ctx = make_run_context(config)
        ctx.leaf_executor.results["body"] = leaf_failure("body")
        status = Traverser(ctx).tick(repeat(action("body"), mode="retry", max=3))
        assert status == FAILURE
        assert len(ctx.leaf_executor.calls) == 3

    def test_repeat_max_zero_returns_failure(self, config) -> None:
        """上界为 0：循环不可执行 → 整体 FAILURE（安全闸）。"""
        ctx = make_run_context(config)
        assert Traverser(ctx).tick(repeat(action("body"), mode="retry", max=0)) == FAILURE


class TestRepeatLoopUntil:
    """任务 2.4：LoopUntil 每轮先判 until，满足即退、不满足才执行 body。"""

    def test_until_satisfied_initially(self, config) -> None:
        """初始即满足 → SUCCESS，body 一次也不执行。"""
        ctx = make_run_context(config)
        ctx.leaf_executor.results["until"] = leaf_condition(True)
        ctx.leaf_executor.results["body"] = leaf_success("body")
        status = Traverser(ctx).tick(
            repeat(action("body"), mode="loop_until", until=cond("until"), max=5)
        )
        assert status == SUCCESS
        assert [n.description for n, _ in ctx.leaf_executor.calls] == ["until"]

    def test_until_not_satisfied_then_body(self, config) -> None:
        """初始不满足 → 执行 body；下一轮重判 until 满足 → 退出。"""
        ctx = make_run_context(config)
        ctx.leaf_executor.results["until"] = [leaf_condition(False), leaf_condition(True)]
        ctx.leaf_executor.results["body"] = leaf_success("body")
        status = Traverser(ctx).tick(
            repeat(action("body"), mode="loop_until", until=cond("until"), max=5)
        )
        assert status == SUCCESS
        assert [n.description for n, _ in ctx.leaf_executor.calls] == [
            "until",
            "body",
            "until",
        ]

    def test_until_never_satisfied_reaches_max(self, config) -> None:
        """until 始终不满足 → 循环至上限 → 整体 FAILURE。"""
        ctx = make_run_context(config)
        ctx.leaf_executor.results["until"] = leaf_condition(False)
        ctx.leaf_executor.results["body"] = leaf_success("body")
        status = Traverser(ctx).tick(
            repeat(action("body"), mode="loop_until", until=cond("until"), max=3)
        )
        assert status == FAILURE
        assert [n.description for n, _ in ctx.leaf_executor.calls] == [
            "until",
            "body",
            "until",
            "body",
            "until",
            "body",
        ]

    def test_loop_until_body_failure_propagates(self, config) -> None:
        """循环体失败 → 沿树传播为整体 FAILURE（不吞掉失败继续循环）。"""
        ctx = make_run_context(config)
        ctx.leaf_executor.results["until"] = leaf_condition(False)
        ctx.leaf_executor.results["body"] = leaf_failure("body")
        status = Traverser(ctx).tick(
            repeat(action("body"), mode="loop_until", until=cond("until"), max=5)
        )
        assert status == FAILURE
        assert len(ctx.leaf_executor.calls) == 2


class TestCompositeNodeReport:
    """组合节点退出前也记录报告（§5.8.3：所有节点）。"""

    def test_sequence_records_report(self, config) -> None:
        ctx = make_run_context(config)
        ctx.leaf_executor.results["a"] = leaf_success("a")
        status = Traverser(ctx).tick(seq(action("a")))
        assert status == SUCCESS
        reports = ctx.reporter.exec_state().completed
        node_types = [r.node_type for r in reports]
        assert node_types == ["Action", "Sequence"]
        assert reports[-1].result == "success"

    def test_failed_composite_records_failure(self, config) -> None:
        ctx = make_run_context(config)
        ctx.leaf_executor.results["a"] = leaf_failure("a")
        status = Traverser(ctx).tick(seq(action("a")))
        assert status == FAILURE
        reports = ctx.reporter.exec_state().completed
        assert reports[-1].node_type == "Sequence"
        assert reports[-1].result == "failure"
