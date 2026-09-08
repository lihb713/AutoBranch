"""任务 3.1/3.2/3.3：复合节点展开（§4.3 精确语义，表驱动）。"""

from __future__ import annotations

from parser_fixtures import build_resolver, parse_doc, walk_nodes

from webops.parser import (
    ActionNode,
    ConditionNode,
    FinishNode,
    RepeatNode,
    SelectorNode,
    SequenceNode,
)
from webops.parser.document import parse_structure
from webops.parser.expand import ExpandContext, expand_document
from webops.parser.models import DocumentSource

EXPAND_RESOLVER = build_resolver()


def _expand_tree(doc_id: str, data: dict):
    st = parse_structure(DocumentSource(id=doc_id, data=data), data)
    ctx = ExpandContext(ir=st.ir, resolver=EXPAND_RESOLVER, max_depth=64)
    return expand_document(ctx)


def test_step_expands_to_sequence():
    """3.1 Step = Sequence(Action + Condition)。"""
    doc = {"操作块 用例": {"Step": {"action": "点击登录", "expect": "出现工作台"}}}
    exp = _expand_tree("用例", doc)
    assert exp.issues == ()
    tree = exp.tree
    assert isinstance(tree, SequenceNode)
    assert len(tree.children) == 2
    action, cond = tree.children
    assert isinstance(action, ActionNode)
    assert action.description == "点击登录"
    assert isinstance(cond, ConditionNode)
    assert cond.description == "出现工作台"


def test_step_with_css_hint():
    """3.1 Step 的 action 含 CSS 提示。"""
    doc = {
        "操作块 用例": {
            "Step": {
                "action": {"描述": "点击登录", "CSS": "button[type=submit]"},
                "expect": "出现工作台",
            }
        }
    }
    exp = _expand_tree("用例", doc)
    action = exp.tree.children[0]
    assert action.css_hint == "button[type=submit]"


def test_branch_expands_to_action_plus_selector():
    """3.1 Branch = Action + Selector（顺序 when，第一个命中生效，无匹配走 otherwise）。"""
    doc = {
        "操作块 用例": {
            "Branch": {
                "action": "点击登录",
                "branches": [
                    {"when": "出现工作台", "then": {"Finish": "完成"}},
                    {"when": "出现密码错误", "then": {"Finish": "重试"}},
                    {"otherwise": {"Finish": "终止"}},
                ],
            }
        }
    }
    exp = _expand_tree("用例", doc)
    assert exp.issues == ()
    tree = exp.tree
    assert isinstance(tree, SequenceNode)
    action, selector = tree.children
    assert isinstance(action, ActionNode)
    assert isinstance(selector, SelectorNode)
    assert len(selector.branches) == 3
    whens = [b.condition for b in selector.branches]
    assert [w.description if w else None for w in whens] == ["出现工作台", "出现密码错误", None]
    targets = [b.child for b in selector.branches]
    assert all(isinstance(t, FinishNode) for t in targets)


def test_loop_until_expands_to_repeat():
    """3.1 LoopUntil = Repeat(mode=loop_until, until=条件, max=上限)，每轮先判 until。"""
    doc = {"操作块 用例": {"LoopUntil": {"action": "点击批准", "until": "批准按钮消失", "max": 50}}}
    exp = _expand_tree("用例", doc)
    assert exp.issues == ()
    repeat = exp.tree
    assert isinstance(repeat, RepeatNode)
    assert repeat.mode == "loop_until"
    assert repeat.max == 50
    assert isinstance(repeat.body, ActionNode)
    assert repeat.until is not None
    assert repeat.until.description == "批准按钮消失"


def test_retry_expands_to_repeat():
    """3.1 Retry = Repeat(mode=retry, max=上限)，每轮后判 body 结果。"""
    doc = {
        "操作块 用例": {
            "Retry": {"max": 3, "body": {"Step": {"action": "点击下载", "expect": "出现下载成功"}}}
        }
    }
    exp = _expand_tree("用例", doc)
    assert exp.issues == ()
    repeat = exp.tree
    assert isinstance(repeat, RepeatNode)
    assert repeat.mode == "retry"
    assert repeat.until is None
    assert repeat.max == 3
    body = repeat.body
    assert isinstance(body, SequenceNode)
    assert isinstance(body.children[0], ActionNode)
    assert isinstance(body.children[1], ConditionNode)


def test_if_then_else_expands_to_selector():
    """3.1 IfThenElse = Selector(if→then, else→else)，先判 if 条件。"""
    doc = {
        "操作块 用例": {
            "IfThenElse": {
                "if": "存在下载成功提示",
                "then": {"Finish": "完成流程"},
                "else": {"Finish": "重试下载"},
            }
        }
    }
    exp = _expand_tree("用例", doc)
    assert exp.issues == ()
    selector = exp.tree
    assert isinstance(selector, SelectorNode)
    assert len(selector.branches) == 2
    if_branch, else_branch = selector.branches
    assert if_branch.condition is not None
    assert if_branch.condition.description == "存在下载成功提示"
    assert isinstance(if_branch.child, FinishNode)
    assert else_branch.condition is None
    assert isinstance(else_branch.child, FinishNode)


def test_expansion_table_driven_all_composites():
    """3.1 表驱动：五类复合节点展开结构与 §4.3 精确语义一致。"""
    cases = [
        (
            "Step",
            {"action": "点", "expect": "出现"},
            lambda n: (isinstance(n, SequenceNode), n.children[0], n.children[1]),
        ),
        (
            "Branch",
            {
                "action": "点",
                "branches": [
                    {"when": "出现", "then": {"Finish": "a"}},
                    {"otherwise": {"Finish": "b"}},
                ],
            },
            lambda n: (isinstance(n, SequenceNode), n.children[0], n.children[1]),
        ),
        (
            "LoopUntil",
            {"action": "点", "until": "消失", "max": 10},
            lambda n: (isinstance(n, RepeatNode), n.mode, n.max),
        ),
        (
            "Retry",
            {"max": 2, "body": {"Action": "点"}},
            lambda n: (isinstance(n, RepeatNode), n.mode, n.max),
        ),
        (
            "IfThenElse",
            {"if": "存在", "then": {"Finish": "a"}, "else": {"Finish": "b"}},
            lambda n: (isinstance(n, SelectorNode), len(n.branches)),
        ),
    ]
    for kind, payload, assert_fn in cases:
        doc = {"操作块 用例": {kind: payload}}
        exp = _expand_tree("用例", doc)
        assert exp.issues == (), f"{kind} 展开不应有校验问题"
        ok, *rest = assert_fn(exp.tree)
        assert ok, f"{kind} 展开为错误节点类型"
        if kind == "Branch":
            assert isinstance(rest[1], SelectorNode)
            assert rest[1].branches[1].condition is None  # otherwise
        elif kind in ("LoopUntil", "Retry"):
            assert rest[0] == ("loop_until" if kind == "LoopUntil" else "retry")
            assert rest[1] == (10 if kind == "LoopUntil" else 2)


def test_expanded_tree_only_basic_nodes():
    """3.2 展开后的行为树仅含基础节点（含嵌套复合节点场景）。"""
    doc = {
        "操作块 用例": {
            "Retry": {
                "max": 3,
                "body": {
                    "IfThenElse": {
                        "if": "存在",
                        "then": {
                            "Branch": {
                                "action": "点",
                                "branches": [{"otherwise": {"Finish": "x"}}],
                            }
                        },
                        "else": {"LoopUntil": {"action": "点", "until": "消失", "max": 5}},
                    }
                },
            }
        }
    }
    exp = _expand_tree("用例", doc)
    assert exp.issues == ()
    from webops.parser import models

    basic = (
        models.ActionNode,
        models.ConditionNode,
        models.SequenceNode,
        models.SelectorNode,
        models.RepeatNode,
        models.FinishNode,
    )
    for node in walk_nodes(exp.tree):
        assert isinstance(node, basic), f"残留非基础节点: {type(node).__name__}"
    # 结构细节：Retry body = IfThenElse → Selector
    repeat = exp.tree
    assert isinstance(repeat, RepeatNode)
    assert isinstance(repeat.body, SelectorNode)
    then_selector = repeat.body.branches[0].child
    assert isinstance(then_selector, SequenceNode)  # Branch → Action + Selector
    else_repeat = repeat.body.branches[1].child
    assert isinstance(else_repeat, RepeatNode)
    assert else_repeat.mode == "loop_until"


def test_deep_nesting_expands_correctly():
    """3.3 深嵌套（Retry 内嵌 Step、IfThenElse 内嵌 Branch）展开正确。"""
    doc = {
        "操作块 用例": {
            "Retry": {
                "max": 3,
                "body": {
                    "IfThenElse": {
                        "if": "存在",
                        "then": {
                            "Branch": {
                                "action": "点",
                                "branches": [{"otherwise": {"Finish": "x"}}],
                            }
                        },
                        "else": {"Step": {"action": "点", "expect": "出现"}},
                    }
                },
            }
        }
    }
    exp = _expand_tree("用例", doc)
    assert exp.issues == ()
    repeat = exp.tree
    ifte = repeat.body
    assert isinstance(ifte, SelectorNode)
    assert isinstance(ifte.branches[0].child, SequenceNode)  # Branch 展开
    step_seq = ifte.branches[1].child
    assert isinstance(step_seq, SequenceNode)  # Step 展开
    assert len(step_seq.children) == 2


def _nested_retry(n: int) -> dict:
    inner: dict = {"Step": {"action": "点", "expect": "出现"}}
    for _ in range(n):
        inner = {"Retry": {"max": 3, "body": inner}}
    return inner


def test_expand_recursion_limit_exceeded():
    """3.3 超过展开深度上限 → 校验失败（expand.depth_exceeded）。"""
    doc = {"操作块 用例": _nested_retry(100)}
    exp = _expand_tree("用例", doc)
    assert any(i.code == "expand.depth_exceeded" for i in exp.issues)


def test_expand_within_depth_limit_ok():
    """3.3 未超上限的深嵌套展开成功。"""
    doc = {"操作块 用例": _nested_retry(10)}
    exp = _expand_tree("用例", doc)
    assert exp.issues == ()


def test_ref_recursion_limit_exceeded():
    """3.3 引用链超过上限 → ref.recursion_depth。"""
    resolver = build_resolver()
    n = 80
    for i in range(n):
        doc_id = f"d{i}"
        if i == n - 1:
            body = {"Sequence": [{"Finish": "末"}]}
        else:
            body = {"Sequence": [{"ref": f"d{i + 1}/d{i + 1}"}]}
        resolver.add(DocumentSource(id=doc_id, data={"操作块 " + doc_id: body}))
    result = parse_doc("d0", {"操作块 d0": {"Sequence": [{"ref": "d1/d1"}]}}, resolver)
    assert any(i.code == "ref.recursion_depth" for i in result.checks.issues)
    assert result.checks.ok is False
