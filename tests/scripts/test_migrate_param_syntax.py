"""参数语法迁移脚本单元测试：中文变量名 → 语义英文 + 旧语法 → Param./NewParam.。"""

from __future__ import annotations

from scripts.migrate_param_syntax import migrate_content


def test_get_set_rewrite():
    content = "访问[[get:param1]]页面并写入[[set:str:param2]]"
    assert migrate_content(content) == "访问Param.param1页面并写入NewParam.param2:str"


def test_set_no_type():
    assert migrate_content("存[[set:amount]]") == "存NewParam.amount"


def test_chinese_rename_and_args_and_returns():
    content = """tree: t
nodes:
  n2:
    type: Action
    description: 提取苹果 苹果金额 [[set:int:苹果金额]]
  n3:
    type: Action
    description: 提取香蕉 香蕉金额 [[set:int:香蕉金额]]
  n4:
    type: FunctionCall
    function: compute.add
    args: [苹果金额, 香蕉金额]
    returns:
      水果合计: int
root: n1
"""
    new = migrate_content(content)
    assert "NewParam.appleAmount:int" in new
    assert "args: [Param.appleAmount, Param.bananaAmount]" in new
    assert "NewParam.fruitTotal: int" in new


def test_inline_returns_prefixed():
    content = "    returns: {结果: int}"
    assert migrate_content(content) == "    returns: {NewParam.result: int}"


def test_bare_ascii_returns_prefixed():
    content = "returns:\n  param2: str\n"
    assert migrate_content(content) == "returns:\n  NewParam.param2: str\n"


def test_literal_args_kept():
    content = '    args: ["2", "3"]\n'
    assert migrate_content(content) == content


def test_url_literal_arg_kept():
    content = "    args:\n      - http://127.0.0.1:8123/index.html\n"
    assert migrate_content(content) == content


def test_idempotent():
    content = """tree: t
inputs: {入参1: str}
nodes:
  n2:
    type: Action
    description: 访问[[get:param1]]并保存[[set:int:苹果金额]]
  n3:
    type: FunctionCall
    function: compute.add
    args: [苹果金额]
    returns:
      结果: int
root: n1
"""
    once = migrate_content(content)
    twice = migrate_content(once)
    assert once == twice
    assert "苹果金额" not in once
    assert "[[get:" not in once
    assert "[[set:" not in once
    assert "NewParam." in once
    assert "Param." in once
