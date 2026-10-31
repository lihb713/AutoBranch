"""M7：Define 节点确定性变量声明（不调用 LLM、无截图）。"""

from __future__ import annotations

from orchestrator_helpers import make_run_context

from autobranch.orchestrator import FAILURE, SUCCESS
from autobranch.orchestrator.traverser import Traverser
from autobranch.parser.models import DefineNode


def define(*rows: tuple[str, str, str]) -> DefineNode:
    return DefineNode(vars=tuple(rows))


class TestTickDefine:
    def test_creates_literal_vars(self, config) -> None:
        ctx = make_run_context(config)
        node = define(("baseUrl", "str", "https://e.com"), ("retries", "int", "3"))
        assert Traverser(ctx).tick(node) == SUCCESS
        assert ctx.space.read(ctx.current_frame, "baseUrl") == "https://e.com"
        assert ctx.space.read(ctx.current_frame, "retries") == 3

    def test_coerces_literal_to_declared_type(self, config) -> None:
        ctx = make_run_context(config)
        assert Traverser(ctx).tick(define(("s", "str", "42"))) == SUCCESS
        assert ctx.space.read(ctx.current_frame, "s") == "42"

    def test_copy_rename_from_param(self, config) -> None:
        ctx = make_run_context(config)
        traverser = Traverser(ctx)
        assert traverser.tick(define(("orig", "str", "hello"))) == SUCCESS
        assert traverser.tick(define(("alias", "str", "Param.orig"))) == SUCCESS
        assert ctx.space.read(ctx.current_frame, "alias") == "hello"

    def test_undefined_param_fails(self, config) -> None:
        ctx = make_run_context(config)
        assert Traverser(ctx).tick(define(("x", "str", "Param.nope"))) == FAILURE
        assert ctx.failure_reason is not None
        assert "nope" in ctx.failure_reason

    def test_coerce_failure_fails(self, config) -> None:
        ctx = make_run_context(config)
        assert Traverser(ctx).tick(define(("n", "int", "abc"))) == FAILURE
        assert ctx.failure_reason is not None
        assert "n" in ctx.failure_reason
