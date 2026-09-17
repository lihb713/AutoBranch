"""行为树文档解析的异常类型（M2）。

| 异常 | 语义 |
|---|---|
| ``ParserError`` | 解析错误基类 |
| ``InvalidDocumentError`` | 文档源非法：既不是合法 yaml 也不是合法 dict |
| ``RefNotFoundError`` | 引用解析失败：目标文档不存在（由 RefResolver 实现抛出） |

清晰度校验的**结构/语义违规**不抛异常，而是以 ``CheckReport`` 的错误清单
返回（供用户修正），与「非法输入抛错」区分开。
"""

from __future__ import annotations


class ParserError(Exception):
    """行为树解析错误基类。"""


class InvalidDocumentError(ParserError):
    """文档源非法：既不是合法 yaml 也不是合法 dict。

    解析入口对此类输入直接抛出，不产生部分行为树结果（M2 spec 场景）。
    """


class RefNotFoundError(ParserError):
    """引用解析失败：目标文档不存在。

    由 ``RefResolver`` 实现抛出；解析层捕获后转为清晰度校验的
    ``ref.missing_doc`` 错误项。
    """

    def __init__(self, doc_id: str) -> None:
        self.doc_id = doc_id
        super().__init__(f"引用目标不存在: {doc_id}")
