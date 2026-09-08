"""任务 1.3（统一规范化入口）/ 2.1（结构解析）/ 2.2（声明提取）/ 2.3（配置覆盖）。"""

from __future__ import annotations

import pytest
from parser_fixtures import LOGIN_DOC, LOGIN_YAML

from webops.parser.document import parse_structure
from webops.parser.errors import InvalidDocumentError
from webops.parser.models import DocumentSource
from webops.parser.yamlio import normalize_document


def test_normalize_dict_passthrough():
    """1.3 dict 输入直接走同一解析路径。"""
    assert normalize_document(LOGIN_DOC) is LOGIN_DOC


def test_normalize_yaml_equals_dict():
    """1.3 yaml 文本与 dict 解析结果完全一致（子集解析器）。"""
    assert normalize_document(LOGIN_YAML) == LOGIN_DOC


def test_normalize_invalid_inputs_raise():
    """1.3 非法输入抛出可识别的解析错误（不产生部分结果）。"""
    with pytest.raises(InvalidDocumentError):
        normalize_document(123)
    with pytest.raises(InvalidDocumentError):
        normalize_document(None)
    with pytest.raises(InvalidDocumentError):
        normalize_document("- a\n- b")  # yaml 顶层为列表而非映射
    with pytest.raises(InvalidDocumentError):
        normalize_document("")  # 空文档
    with pytest.raises(InvalidDocumentError):
        normalize_document(["非法列表"])


def test_normalize_yaml_with_flow_bindings():
    """1.3 流式映射 ``写入: { ... }`` 可解析（主流程 yaml 文本）。"""
    from parser_fixtures import MAIN_YAML

    loaded = normalize_document(MAIN_YAML)
    assert loaded["操作块 主流程"]["Sequence"][0]["ref"] == "导出/导出"
    bindings = loaded["操作块 主流程"]["Sequence"][0]["写入"]
    assert bindings["$this/导出/username"] == "{{$this/账号}}"
    assert bindings["$this/导出/password"] == "{{$this/密}}"


def test_yaml_quoted_string_and_comment():
    loaded = normalize_document('操作块 登录:\n  Sequence:\n    - Action: 点击"登录"按钮  # 注释\n')
    body = loaded["操作块 登录"]["Sequence"]
    assert body[0]["Action"] == '点击"登录"按钮'


def test_structure_form_a_root_block():
    """2.1 写法 A：顶层「操作块 <块名>:」→ 根块 = 文档名匹配者。"""
    result = parse_structure(DocumentSource(id="登录", data=LOGIN_DOC), LOGIN_DOC)
    ir = result.ir
    assert ir.doc_id == "登录"
    assert ir.root_block == "登录"
    assert set(ir.blocks) == {"登录"}
    assert ir.root.kind == "Sequence"
    assert len(ir.root.children) == 4
    assert result.issues == ()


def test_structure_form_b_named_blocks():
    """2.1 写法 B：附加命名块，根块 = 名字匹配文档名的块。"""
    doc = {
        "操作块 主流程": {"Sequence": [{"ref": "this/登录"}]},
        "操作块 登录": {"Sequence": [{"Action": "填账号"}]},
    }
    result = parse_structure(DocumentSource(id="主流程", data=doc), doc)
    ir = result.ir
    assert ir.root_block == "主流程"
    assert set(ir.blocks) == {"主流程", "登录"}
    assert ir.ir_by_block["登录"].kind == "Sequence"
    assert ir.blocks["登录"].inputs == ()


def test_structure_form_c_bare_tree():
    """2.1 写法 C：整个 dict 即根块行为树（根块名 = 文档名）。"""
    doc = {"Sequence": [{"Step": {"action": "点", "expect": "出现"}}]}
    result = parse_structure(DocumentSource(id="裸树", data=doc), doc)
    assert result.ir.root_block == "裸树"
    assert result.ir.root.kind == "Sequence"
    assert result.ir.root.children[0].kind == "Step"


def test_structure_ir_all_node_kinds():
    """2.1 中间表示保留全部节点类型（复合节点与 ref 不提前展开）。"""
    doc = {
        "操作块 全节点": {
            "Sequence": [
                {"Step": {"action": "点甲", "expect": "出现乙"}},
                {
                    "Branch": {
                        "action": "点丙",
                        "branches": [{"when": "出现丁", "then": "戊"}],
                    }
                },
                {"LoopUntil": {"action": "点己", "until": "庚消失", "max": 50}},
                {
                    "Retry": {"max": 3, "body": {"Step": {"action": "点辛", "expect": "出现壬"}}}
                },
                {"IfThenElse": {"if": "癸存在", "then": "子", "else": "丑"}},
                {"ref": "this/辅助"},
            ]
        },
        "操作块 辅助": {"Sequence": [{"Action": "寅"}]},
    }
    result = parse_structure(DocumentSource(id="全节点", data=doc), doc)
    children = result.ir.root.children
    assert [c.kind for c in children] == [
        "Step",
        "Branch",
        "LoopUntil",
        "Retry",
        "IfThenElse",
        "ref",
    ]
    step = children[0]
    assert step.action.kind == "Action"
    assert step.condition.kind == "Condition"
    branch = children[1]
    assert branch.action.kind == "Action"
    assert branch.branches[0].when.kind == "Condition"
    assert branch.branches[0].target.kind == "ref"  # 裸字符串分支目标 → this/块名
    assert branch.branches[0].target.ref_target == "this/戊"
    loop = children[2]
    assert loop.max == 50
    assert loop.until.kind == "Condition"
    retry = children[3]
    assert retry.body.kind == "Step"
    ifte = children[4]
    assert ifte.condition.kind == "Condition"
    assert len(ifte.children) == 2
    ref = children[5]
    assert ref.ref_target == "this/辅助"


def test_structure_decl_extraction():
    """2.2 块声明提取：输入/输出与文档声明一致（含根块）。"""
    result = parse_structure(DocumentSource(id="登录", data=LOGIN_DOC), LOGIN_DOC)
    decl = result.ir.blocks["登录"]
    assert decl.inputs == ("username", "password")
    assert decl.outputs == ("login_success",)


def test_structure_decl_list_and_single():
    """2.2 声明支持字符串（逗号分隔）与列表两种写法。"""
    doc = {
        "操作块 甲": {"输入": "$a, $b", "输出": ["$x"], "Sequence": [{"Action": "动作"}]}
    }
    result = parse_structure(DocumentSource(id="甲", data=doc), doc)
    decl = result.ir.blocks["甲"]
    assert decl.inputs == ("a", "b")
    assert decl.outputs == ("x",)


def test_config_override_detection():
    """2.3 识别块内配置参数覆盖（timeout/retry/browser），标注块级生效。"""
    doc = {
        "操作块 甲": {
            "timeout": 30,
            "retry": 2,
            "browser": "chromium",
            "Sequence": [{"Action": "动作"}],
        }
    }
    result = parse_structure(DocumentSource(id="甲", data=doc), doc)
    decl = result.ir.blocks["甲"]
    by_name = {o.name: o.value for o in decl.config_overrides}
    assert by_name == {"timeout": 30, "retry": 2, "browser": "chromium"}
    assert result.issues == ()


def test_no_config_override_when_undeclared():
    """2.3 未声明配置参数时，输出不含该覆盖。"""
    doc = {"操作块 甲": {"Sequence": [{"Action": "动作"}]}}
    result = parse_structure(DocumentSource(id="甲", data=doc), doc)
    decl = result.ir.blocks["甲"]
    assert decl.config_overrides == ()
    assert "timeout" not in {o.name for o in decl.config_overrides}


def test_config_override_invalid_value():
    """2.3 覆盖值非标量 → 结构校验失败。"""
    doc = {"操作块 甲": {"timeout": {"怪": "值"}, "Sequence": [{"Action": "动作"}]}}
    result = parse_structure(DocumentSource(id="甲", data=doc), doc)
    codes = {i.code for i in result.issues}
    assert "structure.invalid_config" in codes


def test_structure_invalid_flow_reported():
    """2.1 非法结构：块必须且只能含一个行为树节点键。"""
    doc = {"操作块 甲": {"Sequence": [{"Action": "a"}], "Step": {"action": "b", "expect": "c"}}}
    result = parse_structure(DocumentSource(id="甲", data=doc), doc)
    assert any(i.code == "structure.invalid_flow" for i in result.issues)


def test_structure_unknown_node_reported():
    doc = {"操作块 甲": {"Flog": "未知节点"}}
    result = parse_structure(DocumentSource(id="甲", data=doc), doc)
    assert any(i.code == "structure.unknown_node" for i in result.issues)
    assert any("Flog" in i.message for i in result.issues)
