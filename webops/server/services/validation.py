"""清晰度校验服务（设计 D6：单一校验函数，保存时与执行前两处复用）。

封装 M2 ``BehaviorTreeParser.parse``（契约 §4.4/§12.5）：校验失败抛
``CheckValidationError``（422 + 错误清单），成功返回 ``ParseResult``
（执行路径可直接取 ``tree`` / ``blocks``）。
"""

from __future__ import annotations

from webops.parser.errors import InvalidDocumentError
from webops.parser.models import CheckIssue, DocumentSource, ParseResult
from webops.parser.parser import BehaviorTreeParser
from webops.parser.refs import MappingResolver
from webops.server.errors import CheckValidationError
from webops.server.schemas.check import CheckIssueOut, CheckReportOut

_DEFAULT_DOC_ID = "文档"


def _parse(content: str, doc_id: str) -> ParseResult:
    parser = BehaviorTreeParser()
    try:
        return parser.parse(DocumentSource(id=doc_id, data=content), MappingResolver({}))
    except InvalidDocumentError as exc:
        raise CheckValidationError(
            [
                {
                    "code": "structure.invalid_document",
                    "message": f"文档不是合法 yaml/dict 行为树: {exc}",
                    "rule": "结构合法性",
                    "loc": None,
                }
            ]
        ) from exc


def validate_document(content: str, doc_id: str = _DEFAULT_DOC_ID) -> ParseResult:
    """校验行为树文档，失败抛 ``CheckValidationError``（422 + 错误清单）。"""
    result = _parse(content, doc_id)
    if not result.checks.ok:
        raise CheckValidationError([_issue_dict(issue) for issue in result.checks.issues])
    return result


def _issue_dict(issue: CheckIssue) -> dict:
    return {
        "code": issue.code,
        "message": issue.message,
        "rule": issue.rule,
        "loc": str(issue.loc) if issue.loc else None,
    }


class CheckReportBuilder:
    """构建可读校验报告（``POST /check`` 用，不抛错）。

    与 ``validate_document`` 共用同一 M2 校验入口（设计 D6 防语义漂移）。
    """

    @staticmethod
    def build(content: str, doc_id: str = _DEFAULT_DOC_ID) -> CheckReportOut:
        result = _parse(content, doc_id)
        issues = [
            CheckIssueOut.model_validate(_issue_dict(issue)) for issue in result.checks.issues
        ]
        return CheckReportOut(ok=result.checks.ok, issues=issues)


__all__ = ["validate_document", "CheckReportBuilder"]
