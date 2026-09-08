"""M2 变量新语法测试：{{get:this/...}} 与 {{set:this/...}}。

覆盖：读取/写入路径识别、set_targets 提取、作用域校验、越权读取拒绝。
"""

from __future__ import annotations

from parser_fixtures import parse_doc


def test_action_set_targets_extracted():
    """Action 描述中的 {{set:this/xxx}} 被记录为 set_targets。"""
    result = parse_doc("主", {"操作块 主": {"Action": "提取金额 {{set:this/amount}}"}}, None)
    assert result.checks.ok, result.checks.issues
    action = result.tree.root
    assert action.set_targets == ("this/amount",)


def test_action_multiple_set_targets():
    result = parse_doc(
        "主",
        {
            "操作块 主": {
                "Action": "提取金额 {{set:this/amount}} 和名称 {{set:this/name}}"
            }
        },
        None,
    )
    assert result.checks.ok, result.checks.issues
    assert result.tree.root.set_targets == ("this/amount", "this/name")


def test_get_and_set_scope_valid():
    """读自身 + 写自身（this/）通过校验。"""
    doc = {
        "操作块 主": {
            "Action": "填 {{get:this/用户名}} 并提取 {{set:this/结果}}"
        }
    }
    result = parse_doc("主", doc, None)
    assert not any(i.code == "scope.out_of_scope" for i in result.checks.issues)


def test_get_out_of_scope_fails():
    """读取兄弟/孙子帧变量 → scope.out_of_scope。"""
    doc = {
        "操作块 主": {"Sequence": [{"ref": "this/甲"}]},
        "操作块 甲": {"Sequence": [{"Action": "读 {{get:this/兄弟/值}}"}]},
        "操作块 兄弟": {"Sequence": [{"Action": "动作"}]},
    }
    result = parse_doc("主", doc, None)
    issues = [i for i in result.checks.issues if i.code == "scope.out_of_scope"]
    assert issues
    assert "兄弟" in issues[0].message


def test_set_out_of_scope_fails():
    """写入兄弟/孙子帧变量 → scope.out_of_scope。"""
    doc = {
        "操作块 主": {"Sequence": [{"ref": "this/甲"}]},
        "操作块 甲": {"Sequence": [{"Action": "存 {{set:this/兄弟/值}}"}]},
        "操作块 兄弟": {"Sequence": [{"Action": "动作"}]},
    }
    result = parse_doc("主", doc, None)
    issues = [i for i in result.checks.issues if i.code == "scope.out_of_scope"]
    assert issues


def test_old_syntax_no_longer_parsed():
    """旧语法 {{$this/...}} 与 => $this/... 不再被识别（无 scope 校验也无 set_targets）。"""
    doc = {
        "操作块 主": {
            "Action": "提取 {{$this/旧值}} => $this/旧结果"
        }
    }
    result = parse_doc("主", doc, None)
    action = result.tree.root
    assert action.set_targets == ()  # 旧 => 不再产生 set_targets
    assert not any(i.code.startswith("scope") for i in result.checks.issues)


def test_set_type_annotation_page():
    """{{set:page_ref:页面A}} 记录 set_decls=(this/页面A, page_ref)。"""
    result = parse_doc(
        "主",
        {"操作块 主": {"Action": "打开登录页 {{set:page_ref:页面A}}"}},
        None,
    )
    assert result.checks.ok, result.checks.issues
    action = result.tree.root
    assert action.set_targets == ("this/页面A",)
    assert action.set_decls == (("this/页面A", "page_ref"),)


def test_set_type_annotation_string():
    """{{set:str:url}} 记录 set_decls=(this/url, str)。"""
    result = parse_doc(
        "主",
        {"操作块 主": {"Action": "记下地址 {{set:str:url}}"}},
        None,
    )
    assert result.checks.ok, result.checks.issues
    assert result.tree.root.set_decls == (("this/url", "str"),)


def test_set_type_annotation_with_this_prefix():
    """{{set:page_ref:this/页面B}} 与省略 this 等价。"""
    result = parse_doc(
        "主",
        {"操作块 主": {"Action": "开 {{set:page_ref:this/页面B}}"}},
        None,
    )
    assert result.checks.ok, result.checks.issues
    assert result.tree.root.set_decls == (("this/页面B", "page_ref"),)


def test_set_type_annotation_numeric_tokens():
    """{{set:int/float/bool:...}} 泛化 token 也被接受（TYPE_REGISTRY 全量）。"""
    doc = {
        "操作块 主": {
            "Action": (
                "取数 {{set:int:this/数量}} 比率 {{set:float:this/比率}}"
                " 开关 {{set:bool:this/开关}}"
            )
        }
    }
    result = parse_doc("主", doc, None)
    assert result.checks.ok, result.checks.issues
    assert result.tree.root.set_decls == (
        ("this/数量", "int"),
        ("this/比率", "float"),
        ("this/开关", "bool"),
    )


def test_set_no_type_default_empty():
    """{{set:this/amount}}（无类型标注）→ type=""。"""
    result = parse_doc(
        "主",
        {"操作块 主": {"Action": "提取 {{set:this/amount}}"}},
        None,
    )
    assert result.checks.ok, result.checks.issues
    assert result.tree.root.set_decls == (("this/amount", ""),)
