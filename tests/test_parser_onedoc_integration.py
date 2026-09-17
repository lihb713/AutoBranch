"""一文档一树统一槽位解析 → BehaviorTreeParser 全链路集成测试。"""

from __future__ import annotations

from autobranch.parser.models import ActionNode, DocumentSource
from autobranch.parser.parser import BehaviorTreeParser
from autobranch.parser.refs import MappingResolver


def _parse(raw: dict, doc_id: str = "主流程", resolver=None):
    parser = BehaviorTreeParser()
    if resolver is None:
        resolver = MappingResolver()
    return parser.parse(DocumentSource(id=doc_id, data=raw), resolver)


def test_parse_full_chain():
    """统一槽位 DSL → 基础树（Root→Sequence→Step(Action 子树)/ref）+ 校验通过。"""
    raw = {
        "tree": "主流程",
        "inputs": {"起始订单": "str"},
        "outputs": ["处理结果"],
        "nodes": {
            "n1": {"type": "Root", "name": "根", "body": "n2"},
            "n2": {"type": "Sequence", "name": "主流程", "actions": ["n3", "n4"]},
            "n3": {
                "type": "Step",
                "name": "登录",
                "action": "n5",
                "expect": "出现工作台",
            },
            "n5": {"type": "Action", "name": "点登录", "description": "点击登录"},
            "n4": {
                "type": "ref",
                "name": "处理B",
                "target": "文档B",
                "args": ["起始订单"],
                "returns": {"结果": "str"},
            },
        },
        "root": "n1",
    }
    b_doc = {
        "tree": "文档B",
        "inputs": {"起始订单": "str"},
        "outputs": ["处理结果"],
        "nodes": {
            "n1": {"type": "Root", "name": "根", "body": "n2"},
            "n2": {
                "type": "Step",
                "name": "s",
                "action": "n3",
                "expect": "b",
            },
            "n3": {"type": "Action", "name": "a", "description": "操作"},
        },
        "root": "n1",
    }
    resolver = MappingResolver()
    resolver.add(DocumentSource(id="文档B", data=b_doc))
    result = _parse(raw, resolver=resolver)
    assert result.checks.ok, result.checks.issues
    assert result.decl_inputs == {"起始订单": "str"}
    assert result.decl_outputs == ["处理结果"]
    assert result.tree.name == "主流程"
    # Step 展开为 Sequence(ActionNode, ConditionNode)；action 槽位子树含 Action
    seq = result.tree.root
    assert seq.children[0].children[0].children[0].__class__ is ActionNode


def test_parse_with_undeclared_get_fails():
    """[[get:this/x]] 读取未定义变量 → 校验失败（scope.get_undeclared）。"""
    raw = {
        "tree": "主流程",
        "nodes": {
            "n1": {"type": "Root", "name": "根", "body": "n2"},
            "n2": {"type": "Step", "name": "x", "action": "n3", "expect": "ok"},
            "n3": {
                "type": "Action",
                "name": "a",
                "description": "填 [[get:this/未定义]]",
            },
        },
        "root": "n1",
    }
    result = _parse(raw)
    assert not result.checks.ok
    assert any(i.code == "scope.get_undeclared" for i in result.checks.issues)
