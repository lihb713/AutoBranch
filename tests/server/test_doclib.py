"""文档库（DbResolver）测试：按文档名加载行为树文档供跨文档引用解析。"""

from __future__ import annotations

import pytest

from webops.parser.models import DocumentSource
from webops.parser.refs import RefNotFoundError
from webops.server.models.tree import Tree
from webops.server.services.doclib import DbResolver


def test_resolve_by_name_found(session):
    """按文档名查到 → 返回 DocumentSource(id=name, data=content)。"""
    session.add(Tree(name="文档B", content="content-B"))
    session.commit()
    resolver = DbResolver(session)
    src = resolver.resolve("文档B")
    assert isinstance(src, DocumentSource)
    assert src.id == "文档B"
    assert src.data == "content-B"


def test_resolve_missing_raises(session):
    """按文档名查不到 → RefNotFoundError。"""
    resolver = DbResolver(session)
    with pytest.raises(RefNotFoundError):
        resolver.resolve("不存在的文档")


def test_resolve_uses_tree_name_not_id(session):
    """按 name 而非 id 查询（文档名唯一）。"""
    session.add(Tree(name="唯一名", content="x"))
    session.commit()
    resolver = DbResolver(session)
    assert resolver.resolve("唯一名").data == "x"
