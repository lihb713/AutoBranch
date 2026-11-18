"""M8/M10 时区统一测试：时间戳写本地 + 旧库 UTC 审计列迁移。"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from autobranch.server.db import configure_database, session_factory
from autobranch.server.models import Tree
from autobranch.timeutil import DEFAULT_TIMEZONE, configure_timezone, now_local_naive


def test_timestamp_mixin_writes_configured_local_time(tmp_path):
    try:
        configure_timezone("Asia/Shanghai")
        configure_database(tmp_path / "fresh.db")
        db = session_factory()()
        tree = Tree(name="时区树", content="tree: 时区树\nnodes: {}\nroot: null")
        db.add(tree)
        db.commit()
        db.refresh(tree)
        assert tree.created_at.tzinfo is None
        assert abs((tree.created_at - now_local_naive()).total_seconds()) < 5
        db.close()
    finally:
        configure_timezone(DEFAULT_TIMEZONE)


def test_old_utc_timestamps_migrated_to_local(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE trees ("
        "id INTEGER PRIMARY KEY, name VARCHAR(200), content TEXT, "
        "status VARCHAR(20), created_at DATETIME, updated_at DATETIME)"
    )
    conn.execute(
        "INSERT INTO trees (name, content, status, created_at, updated_at) "
        "VALUES ('旧树', 'tree: 旧树\\nnodes: {}\\nroot: null', 'published', "
        "'2026-01-01 00:00:00', '2026-01-01 00:00:00')"
    )
    conn.commit()
    conn.close()

    try:
        configure_timezone("Asia/Shanghai")
        configure_database(path)
        db = session_factory()()
        tree = db.query(Tree).filter(Tree.name == "旧树").one()
        assert tree.created_at == datetime(2026, 1, 1, 8, 0)
        assert tree.updated_at == datetime(2026, 1, 1, 8, 0)
        db.close()
        # 再次启动不应重复 +8 小时。
        configure_database(path)
        db = session_factory()()
        tree = db.query(Tree).filter(Tree.name == "旧树").one()
        assert tree.created_at == datetime(2026, 1, 1, 8, 0)
        db.close()
    finally:
        configure_timezone(DEFAULT_TIMEZONE)
