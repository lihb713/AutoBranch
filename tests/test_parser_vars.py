"""Param./NewParam. 新语法解析与校验单元测试（参数语法重构）。"""

from autobranch.parser.expand import (
    ExpandContext,
    _check_param_syntax,
    _iter_get_paths,
    _iter_set_decls,
    _iter_schema_paths,
)


def test_get_reference():
    assert _iter_get_paths("访问 Param.base_url 网站") == ["base_url"]


def test_get_boundary_at_chinese():
    assert _iter_get_paths("保存www.google.com参数到Param.base_url中") == ["base_url"]


def test_get_identifier_ascii_only():
    assert _iter_get_paths("读 Param.site now") == ["site"]
    assert _iter_get_paths("读 Param.x_y2 和 Param.z") == ["x_y2", "z"]


def test_set_decl_with_type():
    assert _iter_set_decls("保存为 NewParam.appleAmount:int") == [("appleAmount", "int")]


def test_set_decl_no_type():
    assert _iter_set_decls("保存为 NewParam.base_url") == [("base_url", "")]


def test_set_all_types():
    for t in ("str", "int", "float", "bool", "page_ref", "object"):
        assert _iter_set_decls(f"NewParam.v:{t}") == [("v", t)]


def test_backtick_escape_not_collected():
    assert _iter_get_paths("写 `Param` 这个词") == []
    assert _iter_set_decls("写 `NewParam` 这个词") == []
    assert _iter_get_paths("`Param.x` 是纯文本") == []


def test_schema_paths_merge():
    text = "读 Param.a，保存为 NewParam.b:int"
    assert sorted(_iter_schema_paths(text)) == ["a", "b"]


def _issues(text: str):
    ctx = ExpandContext(max_depth=32)
    _check_param_syntax(ctx, text, None)
    return [i.code for i in ctx.issues]


def test_deprecated_get_rejected():
    assert "syntax.deprecated" in _issues("填 [[get:amount]]")


def test_deprecated_set_rejected():
    assert "syntax.deprecated" in _issues("存 [[set:int:amount]]")


def test_deprecated_this_path_rejected():
    assert "syntax.deprecated" in _issues("填 this/username")


def test_unclosed_backtick_rejected():
    assert "syntax.unclosed_backtick" in _issues("写 `Param")


def test_closed_backtick_ok():
    assert _issues("写 `Param` 词") == []


def test_invalid_name_rejected():
    assert "syntax.invalid_name" in _issues("读 Param.2x")


def test_clean_text_no_issues():
    assert _issues("访问 Param.base_url 并保存为 NewParam.网址:int") == []