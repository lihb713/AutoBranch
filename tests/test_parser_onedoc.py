"""一文档一树统一槽位模型解析测试（tree/nodes/root + 语义槽位字段）。"""

from __future__ import annotations

from webops.parser.models import DocumentSource
from webops.parser.onedoc import parse_document
from webops.parser.refs import MappingResolver


def _doc(raw: str | dict) -> DocumentSource:
    return DocumentSource(id="主流程", data=raw)


def _resolver(sources: dict[str, dict]) -> MappingResolver:
    resolver = MappingResolver()
    for name, data in sources.items():
        resolver.add(DocumentSource(id=name, data=data))
    return resolver


def test_parse_simple_tree():
    """Root.body → Sequence.actions → {Step,Step}；Step.action 挂 Action 子树。"""
    raw = {
        "tree": "主流程",
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
                "type": "Step",
                "name": "导出",
                "action": "n6",
                "expect": "出现下载",
            },
            "n6": {"type": "Action", "name": "点导出", "description": "点击导出"},
        },
        "root": "n1",
    }
    result = parse_document(_doc(raw))
    assert result.checks_ok()
    assert result.main_tree is not None
    assert result.main_tree.kind == "Root"
    seq = result.main_tree.children[0]
    assert seq.kind == "Sequence"
    assert len(seq.children) == 2
    step = seq.children[0]
    assert step.kind == "Step"
    assert step.action is not None and step.action.kind == "Action"
    assert step.condition is not None and step.condition.description == "出现工作台"


def test_parse_action_leaf():
    """Action 叶子：description 解析；缺 description 报错。"""
    raw = {
        "tree": "主流程",
        "nodes": {
            "n1": {"type": "Root", "name": "根", "body": "n2"},
            "n2": {"type": "Action", "name": "操作", "description": "点击登录"},
        },
        "root": "n1",
    }
    result = parse_document(_doc(raw))
    assert result.checks_ok()
    leaf = result.main_tree.children[0]
    assert leaf.kind == "Action"
    assert leaf.description == "点击登录"


def test_parse_if_then_else():
    """IfThenElse：if 条件 + then/else 槽位子树。"""
    raw = {
        "tree": "主流程",
        "nodes": {
            "n1": {"type": "Root", "name": "根", "body": "n2"},
            "n2": {
                "type": "IfThenElse",
                "name": "判状态",
                "if": "存在下载成功",
                "then": "n3",
                "else": "n4",
            },
            "n3": {"type": "Action", "name": "a", "description": "完成"},
            "n4": {"type": "Action", "name": "b", "description": "重试"},
        },
        "root": "n1",
    }
    result = parse_document(_doc(raw))
    assert result.checks_ok()
    node = result.main_tree.children[0]
    assert node.kind == "IfThenElse"
    assert node.condition is not None and node.condition.description == "存在下载成功"
    assert len(node.children) == 2  # then / else 子树
    assert node.children[0].kind == "Action"
    assert node.children[1].kind == "Action"


def test_parse_branch():
    """Branch：action 前置操作 + branches（when/otherwise）各挂 action 子树。"""
    raw = {
        "tree": "主流程",
        "nodes": {
            "n1": {"type": "Root", "name": "根", "body": "n2"},
            "n2": {
                "type": "Branch",
                "name": "处理审批",
                "action": "n3",
                "branches": [
                    {"when": "出现已批准", "action": "n4"},
                    {"otherwise": "n5"},
                ],
            },
            "n3": {"type": "Action", "name": "查状态", "description": "查询审批状态"},
            "n4": {"type": "Action", "name": "导出", "description": "导出报表"},
            "n5": {"type": "Action", "name": "重试", "description": "稍后重试"},
        },
        "root": "n1",
    }
    result = parse_document(_doc(raw))
    assert result.checks_ok()
    node = result.main_tree.children[0]
    assert node.kind == "Branch"
    assert node.action is not None and node.action.kind == "Action"
    assert len(node.branches) == 2
    assert node.branches[0].when is not None and node.branches[0].when.description == "出现已批准"
    assert node.branches[0].target.kind == "Action"
    assert node.branches[1].when is None  # otherwise
    assert node.branches[1].target.kind == "Action"


def test_parse_retry():
    """Retry：body 子树 + max。"""
    raw = {
        "tree": "主流程",
        "nodes": {
            "n1": {"type": "Root", "name": "根", "body": "n2"},
            "n2": {"type": "Retry", "name": "重试下载", "body": "n3", "max": 3},
            "n3": {"type": "Action", "name": "下载", "description": "点击下载"},
        },
        "root": "n1",
    }
    result = parse_document(_doc(raw))
    assert result.checks_ok()
    node = result.main_tree.children[0]
    assert node.kind == "Retry"
    assert node.max == 3
    assert node.body is not None and node.body.kind == "Action"


def test_parse_loop_until():
    """LoopUntil：until 条件 + action 子树 + max。"""
    raw = {
        "tree": "主流程",
        "nodes": {
            "n1": {"type": "Root", "name": "根", "body": "n2"},
            "n2": {
                "type": "LoopUntil",
                "name": "翻页",
                "until": "出现最后一页",
                "action": "n3",
                "max": 50,
            },
            "n3": {"type": "Action", "name": "下一页", "description": "点击下一页"},
        },
        "root": "n1",
    }
    result = parse_document(_doc(raw))
    assert result.checks_ok()
    node = result.main_tree.children[0]
    assert node.kind == "LoopUntil"
    assert node.until is not None and node.until.description == "出现最后一页"
    assert node.action is not None and node.action.kind == "Action"
    assert node.max == 50


def test_parse_free_tree_detected():
    """游离节点（未被任何槽位字段引用）保留为游离树。"""
    raw = {
        "tree": "主流程",
        "nodes": {
            "n1": {"type": "Root", "name": "根", "body": "n2"},
            "n2": {"type": "Sequence", "name": "主流程", "actions": []},
            "n3": {
                "type": "Step",
                "name": "重置密码",
                "action": "n4",
                "expect": "ok",
            },
            "n4": {"type": "Action", "name": "重置", "description": "点击重置"},
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
            "n1": {"type": "Root", "name": "根", "body": "n2"},
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
    ref_node = result.main_tree.children[0]  # Root.body 唯一子即 ref
    assert ref_node.kind == "ref"
    assert ref_node.ref_target == "文档B"
    assert ref_node.args == ("起始订单",)
    assert ref_node.returns == (("结果", "str"),)


def test_parse_invalid_no_root_node():
    """root 引用未指向 type:Root 节点 → 校验失败。"""
    raw = {
        "tree": "主流程",
        "nodes": {
            "n1": {"type": "Sequence", "name": "主流程", "actions": []},
        },
        "root": "n1",
    }
    result = parse_document(_doc(raw))
    assert not result.checks_ok()


def test_parse_slot_reference_missing():
    """槽位字段引用不存在的 id → 校验失败。"""
    raw = {
        "tree": "主流程",
        "nodes": {
            "n1": {"type": "Root", "name": "根", "body": "n9"},
        },
        "root": "n1",
    }
    result = parse_document(_doc(raw))
    assert not result.checks_ok()


def test_parse_duplicate_reference_rejected():
    """同一节点被多个槽位引用 → 校验失败（纯树）。"""
    raw = {
        "tree": "主流程",
        "nodes": {
            "n1": {"type": "Root", "name": "根", "body": "n2"},
            "n2": {"type": "Sequence", "name": "s", "actions": ["n4"]},
            "n3": {"type": "Sequence", "name": "s2", "actions": ["n4"]},
            "n4": {"type": "Action", "name": "x", "description": "a"},
        },
        "root": "n1",
    }
    result = parse_document(_doc(raw))
    assert not result.checks_ok()


def test_parse_cycle_detected():
    """槽位引用成环（n2↔n3）→ 校验失败。"""
    raw = {
        "tree": "主流程",
        "nodes": {
            "n1": {"type": "Root", "name": "根", "body": "n2"},
            "n2": {"type": "Sequence", "name": "s", "actions": ["n3"]},
            "n3": {"type": "Sequence", "name": "s2", "actions": ["n2"]},
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
            "n1": {"type": "Root", "name": "根", "body": "n2"},
            "n2": {"type": "Step", "name": "x", "action": "n3"},
            "n3": {"type": "Action", "name": "a", "description": "点登录"},
        },
        "root": "n1",
    }
    result = parse_document(_doc(raw))
    assert not result.checks_ok()


def test_parse_action_missing_description():
    """Action 缺 description → 校验失败。"""
    raw = {
        "tree": "主流程",
        "nodes": {
            "n1": {"type": "Root", "name": "根", "body": "n2"},
            "n2": {"type": "Action", "name": "x"},
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
            "n1": {"type": "Root", "name": "根", "body": "n2"},
            "n2": {"type": "Action", "name": "x", "description": "a"},
        },
        "root": "n1",
    }
    result = parse_document(_doc(raw))
    assert not result.checks_ok()


# ---- 任务 2.4：ref 参数校验（需 resolver 加载被引文档） ----

B_DOC = {
    "tree": "文档B",
    "inputs": {"url": "str", "page": "page_ref"},
    "outputs": ["url文本"],
    "nodes": {
        "n1": {"type": "Root", "name": "根", "body": "n2"},
        "n2": {"type": "Action", "name": "s", "description": "打开页面"},
    },
    "root": "n1",
}


def test_ref_args_mismatch_rejected():
    """args 数量与被引文档 inputs 不匹配 → 校验失败。"""
    raw = {
        "tree": "主流程",
        "inputs": {"起始订单": "str"},
        "nodes": {
            "n1": {"type": "Root", "name": "根", "body": "n2"},
            "n2": {
                "type": "ref",
                "name": "B",
                "target": "文档B",
                "args": ["起始订单"],  # 只传 1 个，B 有 2 个 inputs
                "returns": {"结果": "str"},
            },
        },
        "root": "n1",
    }
    result = parse_document(_doc(raw), _resolver({"文档B": B_DOC}))
    assert not result.checks_ok()


def test_ref_args_ok_with_literal():
    """args 含字面量（非变量名）且数量匹配 → 通过。"""
    raw = {
        "tree": "主流程",
        "nodes": {
            "n1": {"type": "Root", "name": "根", "body": "n2"},
            "n2": {
                "type": "ref",
                "name": "B",
                "target": "文档B",
                "args": ["起始订单", "http://x"],  # 变量 + 字面量
                "returns": {"结果": "str"},
            },
        },
        "root": "n1",
    }
    result = parse_document(_doc(raw), _resolver({"文档B": B_DOC}))
    assert result.checks_ok()


def test_ref_cross_doc_cycle_rejected():
    """A ref B、B ref A → 跨文档环校验失败。"""
    a_raw = {
        "tree": "主流程",
        "nodes": {
            "n1": {"type": "Root", "name": "根", "body": "n2"},
            "n2": {"type": "ref", "name": "B", "target": "文档B"},
        },
        "root": "n1",
    }
    b_raw = {
        "tree": "文档B",
        "nodes": {
            "n1": {"type": "Root", "name": "根", "body": "n2"},
            "n2": {"type": "ref", "name": "A", "target": "主流程"},
        },
        "root": "n1",
    }
    result = parse_document(_doc(a_raw), _resolver({"文档B": b_raw}))
    assert not result.checks_ok()
