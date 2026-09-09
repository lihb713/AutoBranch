"""一文档一树 DSL 解析测试（tree/nodes/root + slots 引用）。"""

from __future__ import annotations

import pytest

from webops.parser.models import DocumentSource
from webops.parser.onedoc import parse_document


def _doc(raw: str | dict) -> DocumentSource:
    return DocumentSource(id="主流程", data=raw)


def test_parse_simple_tree():
    """tree/nodes/root：Root→Sequence→{Step,Step} 主树。"""
    raw = {
        "tree": "主流程",
        "nodes": {
            "n1": {"type": "Root", "name": "根", "slots": {"1": "n2"}},
            "n2": {"type": "Sequence", "name": "主流程", "slots": {"1": "n3", "2": "n4"}},
            "n3": {"type": "Step", "name": "登录", "action": "点登录", "expect": "出现工作台"},
            "n4": {"type": "Step", "name": "导出", "action": "点导出", "expect": "出现下载"},
        },
        "root": "n1",
    }
    result = parse_document(_doc(raw))
    assert result.checks_ok()
    assert result.main_tree is not None
    # 主树根为 Root，沿 slots 到 Sequence
    assert result.main_tree.kind == "Root"


def test_parse_free_tree_detected():
    """游离节点（未被任何 slots 引用）保留为游离树。"""
    raw = {
        "tree": "主流程",
        "nodes": {
            "n1": {"type": "Root", "name": "根", "slots": {"1": "n2"}},
            "n2": {"type": "Sequence", "name": "主流程", "slots": {}},
            "n3": {"type": "Step", "name": "重置密码", "action": "点重置", "expect": "ok"},
        },
        "root": "n1",
    }
    result = parse_document(_doc(raw))
    assert result.checks_ok()
    assert len(result.free_trees) == 1
    assert result.free_trees[0].kind == "Step"


def test_parse_ref_node():
    """ref 节点：target/args/returns 映射为 IR ref。"""
    raw = {
        "tree": "主流程",
        "nodes": {
            "n1": {"type": "Root", "name": "根", "slots": {"1": "n2"}},
            "n2": {
                "type": "ref",
                "name": "处理B",
                "target": "文档B",
                "args": ["起始订单"],
                "returns": {"结果": "str"},
            },
        },
        "root": "n1",
    }
    result = parse_document(_doc(raw))
    assert result.checks_ok()
    assert result.main_tree is not None
    ref_node = result.main_tree.children[0]  # Root 唯一子即 ref
    assert ref_node.kind == "ref"
    assert ref_node.ref_target == "文档B"
    assert ref_node.args == (("起始订单", "起始订单"),)  # 变量名
    assert ref_node.returns == (("结果", "str"),)


def test_parse_invalid_no_root_node():
    """无 type:Root 节点 → 校验失败。"""
    raw = {
        "tree": "主流程",
        "nodes": {
            "n1": {"type": "Sequence", "name": "主流程", "slots": {}},
        },
        "root": "n1",
    }
    result = parse_document(_doc(raw))
    assert not result.checks_ok()


def test_parse_slots_reference_missing():
    """slots 引用不存在的 id → 校验失败。"""
    raw = {
        "tree": "主流程",
        "nodes": {
            "n1": {"type": "Root", "name": "根", "slots": {"1": "n9"}},
        },
        "root": "n1",
    }
    result = parse_document(_doc(raw))
    assert not result.checks_ok()


def test_parse_duplicate_reference_rejected():
    """同一节点被多个槽位引用 → 校验失败。"""
    raw = {
        "tree": "主流程",
        "nodes": {
            "n1": {"type": "Root", "name": "根", "slots": {"1": "n2", "2": "n3"}},
            "n2": {"type": "Sequence", "name": "s", "slots": {"1": "n4"}},
            "n3": {"type": "Sequence", "name": "s2", "slots": {"1": "n4"}},
            "n4": {"type": "Step", "name": "x", "action": "a", "expect": "b"},
        },
        "root": "n1",
    }
    result = parse_document(_doc(raw))
    assert not result.checks_ok()


def test_parse_cycle_detected():
    """slots 引用成环（n2↔n3）→ 校验失败。"""
    raw = {
        "tree": "主流程",
        "nodes": {
            "n1": {"type": "Root", "name": "根", "slots": {"1": "n2"}},
            "n2": {"type": "Sequence", "name": "s", "slots": {"1": "n3"}},
            "n3": {"type": "Sequence", "name": "s2", "slots": {"1": "n2"}},
        },
        "root": "n1",
    }
    result = parse_document(_doc(raw))
    assert not result.checks_ok()


def test_parse_step_missing_expect():
    """Step 缺 expect → 校验失败（必填字段）。"""
    raw = {
        "tree": "主流程",
        "nodes": {
            "n1": {"type": "Root", "name": "根", "slots": {"1": "n2"}},
            "n2": {"type": "Step", "name": "x", "action": "点登录"},
        },
        "root": "n1",
    }
    result = parse_document(_doc(raw))
    assert not result.checks_ok()


def test_parse_invalid_inputs_type():
    """inputs 类型非法 → 校验失败。"""
    raw = {
        "tree": "主流程",
        "inputs": {"url": "不存在的类型"},
        "nodes": {
            "n1": {"type": "Root", "name": "根", "slots": {"1": "n2"}},
            "n2": {"type": "Step", "name": "x", "action": "a", "expect": "b"},
        },
        "root": "n1",
    }
    result = parse_document(_doc(raw))
    assert not result.checks_ok()
