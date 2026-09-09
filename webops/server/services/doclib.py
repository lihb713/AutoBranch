"""文档库：DB-backed 跨文档引用解析器（一文档一树，契约 §14）。

行为树文档存于数据库（``Tree``，name 唯一）。跨文档引用（``ref: 文档名``）
经 ``DbResolver`` 按文档名从数据库加载文档源，喂给 M2 parser 的
``RefResolver`` 抽象；替换 server 旧的空 ``MappingResolver``（此前跨文档
引用在生产环境必然 missing_doc）。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from webops.parser.models import DocumentSource
from webops.parser.refs import RefNotFoundError, RefResolver


class DbResolver(RefResolver):
    """按文档名从数据库加载行为树文档的实现（生产文档库）。

    每次 ``resolve`` 使用调用方提供的独立会话（短事务），不持有长连接。
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def resolve(self, doc_id: str, block_name: str | None = None) -> DocumentSource:
        from webops.server.models.tree import Tree

        tree = self._db.scalars(select(Tree).where(Tree.name == doc_id)).first()
        if tree is None:
            raise RefNotFoundError(doc_id, block_name)
        return DocumentSource(id=tree.name, data=tree.content)

    @staticmethod
    def from_session() -> DbResolver:
        """用当前会话工厂新建独立会话构造解析器（后台任务用）。"""
        from webops.server.db import session_factory

        return DbResolver(session_factory()())