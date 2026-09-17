"""清晰度校验服务测试（任务 4.1，对照契约 §4.4 用例矩阵）。

覆盖：合法文档通过、结构错误/引用缺失/循环无上界/缺验证条件返回可读
错误清单；非 yaml/dict 输入返回 422。
"""

from __future__ import annotations

import pytest

from autobranch.parser.models import DocumentSource
from autobranch.parser.parser import BehaviorTreeParser
from autobranch.parser.refs import MappingResolver
from autobranch.server.errors import CheckValidationError
from autobranch.server.services.validation import CheckReportBuilder, validate_document

from .conftest import INVALID_LOOP_YAML, INVALID_REF_YAML, VALID_YAML

INVALID_DOC_YAML = """
tree: 缺验证
nodes:
  n1:
    type: Root
    name: 根
    body: n2
  n2:
    type: Step
    name: 登录
    action: n3
  n3:
    type: Action
    name: 点登录
    description: 点击"登录"按钮
root: n1
""".strip()

#: (文档, 期望错误码前缀, 期望规则名/关键词)
INVALID_CASES = [
    (INVALID_REF_YAML, "ref", "块引用存在"),
    (INVALID_LOOP_YAML, "repeat", "循环上界"),
    (INVALID_DOC_YAML, "verify", "验证条件"),
]


def test_valid_document_passes():
    result = validate_document(VALID_YAML, "冒烟流程")
    assert result.tree.name == "冒烟流程"
    assert result.checks.ok


def test_check_report_builder_ok():
    report = CheckReportBuilder.build(VALID_YAML, "冒烟流程")
    assert report.ok is True
    assert report.issues == []


@pytest.mark.parametrize("doc, code_prefix, rule_name", INVALID_CASES)
def test_invalid_document_rejected(doc, code_prefix, rule_name):
    with pytest.raises(CheckValidationError) as exc_info:
        validate_document(doc, "文档")
    issues = exc_info.value.detail
    assert issues, "错误清单不应为空"
    assert any(i["code"].startswith(code_prefix) for i in issues)
    assert any(i["rule"] == rule_name for i in issues)
    assert all(isinstance(i["message"], str) and i["message"] for i in issues)


def test_invalid_document_detail_readable():
    with pytest.raises(CheckValidationError) as exc_info:
        validate_document(INVALID_REF_YAML, "坏文档")
    issues = exc_info.value.detail
    assert issues[0]["code"] == "ref.missing_doc"
    assert "不存在的文档" in issues[0]["message"]
    assert issues[0]["loc"]


def test_check_report_builder_invalid():
    report = CheckReportBuilder.build(INVALID_LOOP_YAML, "死循环")
    assert report.ok is False
    assert any(issue.code == "repeat.max_missing" for issue in report.issues)


def test_not_a_document_returns_422():
    with pytest.raises(CheckValidationError) as exc_info:
        validate_document("[1, 2, 3]", "x")
    issues = exc_info.value.detail
    assert issues[0]["code"] == "structure.invalid_document"
    assert "yaml" in issues[0]["message"].lower() or "行为树" in issues[0]["message"]


def test_validation_consistent_with_parser():
    """复用 M2：服务层校验结果与直接调用 M2 解析器一致（设计 D6 防漂移）。"""
    result = BehaviorTreeParser().parse(
        DocumentSource(id="坏文档", data=INVALID_REF_YAML), MappingResolver({})
    )
    assert not result.checks.ok
    with pytest.raises(CheckValidationError) as exc_info:
        validate_document(INVALID_REF_YAML, "坏文档")
    codes = {i["code"] for i in exc_info.value.detail}
    assert codes == {i.code for i in result.checks.issues}
