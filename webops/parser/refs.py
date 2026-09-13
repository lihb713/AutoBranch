"""引用解析抽象接口与内存实现（设计决策 D2，任务 4.1）。

``parse`` 接受 ``RefResolver`` 抽象，M2 模块不感知存储后端；M7 执行时可
注入真实解析器，测试时可注入 fixture 解析器，从而支撑跨文档 fixture 测试。
``MappingResolver`` 为基于文档源映射的内存实现。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from webops.parser.errors import RefNotFoundError
from webops.parser.models import DocumentSource


@runtime_checkable
class RefResolver(Protocol):
    """文档引用解析抽象：给定文档标识返回该文档源。

    实现须在文档不存在时抛出 :class:`RefNotFoundError`。
    """

    def resolve(self, doc_id: str) -> DocumentSource: ...


class MappingResolver:
    """内存映射引用解析器（测试 / 简单场景）。

    以 ``dict[doc_id, DocumentSource]`` 为源映射，跨文档引用时按文档标识
    返回对应文档源；文档缺失抛出 :class:`RefNotFoundError`。
    """

    def __init__(self, sources: Mapping[str, DocumentSource] | None = None) -> None:
        self._sources: dict[str, DocumentSource] = dict(sources or {})

    def add(self, source: DocumentSource) -> None:
        """注册一份文档源。"""
        self._sources[source.id] = source

    def resolve(self, doc_id: str) -> DocumentSource:
        src = self._sources.get(doc_id)
        if src is None:
            raise RefNotFoundError(doc_id)
        return src
