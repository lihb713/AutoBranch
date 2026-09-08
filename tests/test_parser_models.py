"""任务 1.1/1.2：基础节点模型、输出契约、校验报告、引用解析接口。"""

from __future__ import annotations

import pytest
from parser_fixtures import LOGIN_DOC

from webops.parser import (
    ActionNode,
    BehaviorTree,
    BlockDecl,
    BranchSpec,
    CheckReport,
    ConditionNode,
    ConfigOverride,
    DocumentSource,
    FinishNode,
    InvalidDocumentError,
    Loc,
    MappingResolver,
    ParamBinding,
    ParserError,
    ParseResult,
    RefNotFoundError,
    RepeatNode,
    SelectorNode,
    SequenceNode,
    make_issue,
)
from webops.parser.models import FrameInfo


def test_action_node_fields():
    """1.1 ActionNode：自然语言描述 + 可选 CSS 提示。"""
    node = ActionNode(description="点击登录", css_hint="button[type=submit]")
    assert node.description == "点击登录"
    assert node.css_hint == "button[type=submit]"
    plain = ActionNode(description="点击登录")
    assert plain.css_hint is None


def test_condition_node_fields():
    node = ConditionNode(description="出现工作台", target="工作台", predicate="出现")
    assert node.description == "出现工作台"
    assert node.target == "工作台"
    assert node.predicate == "出现"


def test_sequence_and_selector_nodes():
    seq = SequenceNode(children=(ActionNode("a"), ConditionNode("c")))
    assert len(seq.children) == 2
    b = BranchSpec(condition=ConditionNode("满足"), child=FinishNode())
    sel = SelectorNode(branches=(b,))
    assert sel.branches[0].condition is not None
    assert isinstance(sel.branches[0].child, FinishNode)


def test_repeat_node_mode_until_max():
    """1.1 Repeat 的 mode/until/max 符合契约。"""
    until = ConditionNode("页面就绪")
    loop = RepeatNode(body=ActionNode("点击"), mode="loop_until", until=until, max=50)
    assert loop.mode == "loop_until"
    assert loop.until is not None
    assert loop.max == 50
    retry = RepeatNode(body=ActionNode("下载"), mode="retry", until=None, max=3)
    assert retry.mode == "retry"
    assert retry.until is None


def test_behavior_tree_shape():
    tree = BehaviorTree(name="主流程", root=SequenceNode(children=(FinishNode(),)))
    assert tree.name == "主流程"
    assert isinstance(tree.root, SequenceNode)


def test_block_decl_fields():
    """1.1/2.2 BlockDecl：输入（名,类型）/输出/配置参数覆盖。"""
    decl = BlockDecl(
        name="登录",
        doc_id="登录",
        inputs=(("username", "str"), ("password", "str")),
        outputs=("login_success",),
        config_overrides=(ConfigOverride(name="timeout", value=30),),
    )
    assert decl.inputs == (("username", "str"), ("password", "str"))
    assert decl.outputs == ("login_success",)
    assert decl.config_overrides[0].name == "timeout"


def test_parse_result_fields():
    """1.2 ParseResult：tree / blocks / checks（+ bindings/frames 扩展）。"""
    result = ParseResult(
        tree=BehaviorTree(name="x", root=FinishNode()),
        blocks={},
        checks=CheckReport(ok=True),
        bindings=(
            ParamBinding(frame_path="x/", block_name="b", target_path="$this/b/i", value_expr="v"),
        ),
        frames=(FrameInfo(path="x/", block="x", parent=None, children=()),),
    )
    assert result.tree.name == "x"
    assert result.blocks == {}
    assert result.checks.ok is True
    assert result.bindings[0].block_name == "b"
    assert result.frames[0].path == "x/"


def test_check_report_and_issue():
    """1.2 CheckReport/CheckIssue：结论 + 可读错误项（code/message/rule/loc）。"""
    loc = Loc(doc_id="登录", path="登录/Sequence/0/Step")
    issue = make_issue("scope", "out_of_scope", "变量越作用域", loc)
    assert issue.code == "scope.out_of_scope"
    assert issue.rule == "变量契约"
    assert issue.message == "变量越作用域"
    assert issue.loc == loc
    report = CheckReport(ok=False, issues=(issue,))
    assert report.ok is False
    assert report.issues[0].rule == "变量契约"


def test_rule_name_mapping():
    assert make_issue("structure", "unknown_node", "x").rule == "结构合法性"
    assert make_issue("expand", "residual_composite", "x").rule == "展开后合法性"
    assert make_issue("ref", "missing_doc", "x").rule == "块引用存在"
    assert make_issue("repeat", "max_missing", "x").rule == "循环上界"
    assert make_issue("locatable", "not_locatable", "x").rule == "可定位性"
    assert make_issue("verify", "missing_condition", "x").rule == "验证条件"
    assert make_issue("predicate", "empty_condition", "x").rule == "谓词可校验"


def test_document_source_fields():
    src = DocumentSource(id="登录", data=LOGIN_DOC, path="登录.md")
    assert src.id == "登录"
    assert src.data == LOGIN_DOC
    assert src.path == "登录.md"


def test_ref_resolver_protocol_with_mapping_resolver():
    """1.2 RefResolver 抽象接口：MappingResolver 实现可被协议识别。"""
    resolver = MappingResolver()
    assert isinstance(resolver, MappingResolver)
    # 缺失文档抛 RefNotFoundError（可识别异常类型）
    with pytest.raises(RefNotFoundError):
        resolver.resolve("不存在")
    assert issubclass(RefNotFoundError, ParserError)


def test_error_hierarchy():
    assert issubclass(InvalidDocumentError, ParserError)
    assert issubclass(RefNotFoundError, ParserError)
    assert ParserError.__bases__ == (Exception,)
