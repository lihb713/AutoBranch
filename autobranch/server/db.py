"""数据库连接管理（database-rules.md §1/§3）。

- SQLite（开发期单文件库）+ SQLAlchemy 2.0 ORM，``check_same_thread=False``
  供 FastAPI 多线程共享。
- 连接统一经 ``configure_database`` 初始化；SQLite 开启外键约束（PRAGMA）
  使 ``ondelete`` 级联生效。
- 请求内独立短事务（``Depends(get_db)`` 注入），后台任务用独立新会话。
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from autobranch.timeutil import now_local_naive, utc_naive_to_local_naive

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


class Base(DeclarativeBase):
    """ORM 声明基类（所有模型继承）。"""


def configure_database(db_path: str | Path) -> None:
    """创建 engine + 会话工厂并建表（开发期 ``create_all``，database-rules §5）。"""
    global _engine, _session_factory
    resolved = Path(db_path).resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{resolved.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", _enable_foreign_keys)
    _engine = engine
    _session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    # 确保 TreeGroup 模型已注册到 metadata，再建表。
    from autobranch.server.models.tree_group import TreeGroup  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_tree_groups(engine)
    _ensure_tree_status_column(engine)
    _ensure_tree_description_column(engine)
    _ensure_plugin_config_column(engine)
    _ensure_run_source_columns(engine)
    _migrate_timestamps_to_local(engine)


def create_all_tables() -> None:
    """再次建表（供插件注册模型后调用；create_all 幂等）。"""
    if _engine is not None:
        Base.metadata.create_all(bind=_engine)


def _ensure_tree_groups(engine: Engine) -> None:
    """轻量迁移：保证默认分组存在，并给旧 trees 补 group_id。"""
    insp = inspect(engine)
    if "tree_groups" not in insp.get_table_names():
        return
    now = now_local_naive()
    with engine.begin() as conn:
        default_id = conn.execute(
            text("SELECT id FROM tree_groups WHERE is_default = 1 ORDER BY id LIMIT 1")
        ).scalar()
        if default_id is None:
            conn.execute(
                text(
                    "INSERT INTO tree_groups (name, is_default, created_at, updated_at) "
                    "VALUES (:name, 1, :now, :now)"
                ),
                {"name": "默认分组", "now": now},
            )
            default_id = conn.execute(
                text("SELECT id FROM tree_groups WHERE is_default = 1 ORDER BY id LIMIT 1")
            ).scalar()
        if "trees" not in insp.get_table_names():
            return
        columns = {col["name"] for col in insp.get_columns("trees")}
        if "group_id" not in columns:
            conn.execute(text("ALTER TABLE trees ADD COLUMN group_id INTEGER"))
        conn.execute(
            text("UPDATE trees SET group_id = :group_id WHERE group_id IS NULL"),
            {"group_id": default_id},
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_trees_group_id ON trees (group_id)")
        )


def _ensure_run_source_columns(engine: Engine) -> None:
    """轻量迁移：旧库 ``runs`` 无 M10 来源列时补列。"""
    insp = inspect(engine)
    if "runs" not in insp.get_table_names():
        return
    columns = {col["name"] for col in insp.get_columns("runs")}
    with engine.begin() as conn:
        if "source" not in columns:
            conn.execute(
                text(
                    "ALTER TABLE runs ADD COLUMN source VARCHAR(16) "
                    "NOT NULL DEFAULT 'manual'"
                )
            )
        if "schedule_id" not in columns:
            conn.execute(text("ALTER TABLE runs ADD COLUMN schedule_id INTEGER"))
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_runs_schedule_id "
                "ON runs (schedule_id)"
            )
        )


def _migrate_timestamps_to_local(engine: Engine) -> None:
    """一次性把旧库 UTC 时间戳转换为配置时区本地时间（PRAGMA user_version=1）。

    旧版 ``created_at``/``updated_at`` 由 SQLite ``CURRENT_TIMESTAMP`` 写入（UTC），
    而 ``schedule_rules.last_run_at`` 由 Python 本地时间写入，导致列表时间相差 8 小时。
    此迁移只转换审计列 ``created_at``/``updated_at``；``last_run_at`` 已经是本地时间，
    保持不变。新库无数据时仅写入版本标记。
    """
    insp = inspect(engine)
    with engine.begin() as conn:
        version = int(conn.exec_driver_sql("PRAGMA user_version").scalar() or 0)
        if version >= 1:
            return
        for table in insp.get_table_names():
            columns = {col["name"] for col in insp.get_columns(table)}
            targets = [name for name in ("created_at", "updated_at") if name in columns]
            if not targets:
                continue
            rows = conn.exec_driver_sql(
                f"SELECT id, {', '.join(targets)} FROM {table}"
            ).fetchall()
            for row in rows:
                row_id = row[0]
                updates: dict[str, datetime] = {}
                for index, column in enumerate(targets, start=1):
                    raw = row[index]
                    if raw is None:
                        continue
                    value = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))
                    updates[column] = utc_naive_to_local_naive(value)
                if not updates:
                    continue
                assignments = ", ".join(f"{name} = :{name}" for name in updates)
                conn.exec_driver_sql(
                    f"UPDATE {table} SET {assignments} WHERE id = :row_id",
                    {**updates, "row_id": row_id},
                )
        # 标记迁移完成；切换时区不会自动回改历史数据。
        conn.exec_driver_sql("PRAGMA user_version = 1")


def _ensure_plugin_config_column(engine: Engine) -> None:
    """轻量迁移：旧库 ``plugins`` 无 config 列时补列（JSON 文本）。"""
    insp = inspect(engine)
    if "plugins" not in insp.get_table_names():
        return
    columns = {col["name"] for col in insp.get_columns("plugins")}
    if "config" in columns:
        return
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE plugins ADD COLUMN config TEXT NOT NULL DEFAULT '{}'")
        )


def _ensure_tree_status_column(engine: Engine) -> None:
    """轻量迁移：旧库 ``trees`` 无 status 列时补列（默认 published）。"""
    insp = inspect(engine)
    if "trees" not in insp.get_table_names():
        return
    columns = {col["name"] for col in insp.get_columns("trees")}
    if "status" in columns:
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE trees ADD COLUMN status VARCHAR(20) "
                "NOT NULL DEFAULT 'published'"
            )
        )


def _ensure_tree_description_column(engine: Engine) -> None:
    """轻量迁移：旧库 ``trees`` 无 description 列时补列（默认空串）。"""
    insp = inspect(engine)
    if "trees" not in insp.get_table_names():
        return
    columns = {col["name"] for col in insp.get_columns("trees")}
    if "description" in columns:
        return
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE trees ADD COLUMN description TEXT NOT NULL DEFAULT ''")
        )


def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def session_factory() -> sessionmaker[Session]:
    """获取当前会话工厂（后台任务/独立事务用新会话）。"""
    if _session_factory is None:
        raise RuntimeError("数据库未初始化：请先调用 configure_database()")
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：请求级独立短事务会话。"""
    db = session_factory()()
    try:
        yield db
    finally:
        db.close()


__all__ = ["Base", "configure_database", "session_factory", "get_db"]
