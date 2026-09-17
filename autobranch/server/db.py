"""数据库连接管理（database-rules.md §1/§3）。

- SQLite（开发期单文件库）+ SQLAlchemy 2.0 ORM，``check_same_thread=False``
  供 FastAPI 多线程共享。
- 连接统一经 ``configure_database`` 初始化；SQLite 开启外键约束（PRAGMA）
  使 ``ondelete`` 级联生效。
- 请求内独立短事务（``Depends(get_db)`` 注入），后台任务用独立新会话。
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

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
    Base.metadata.create_all(bind=engine)


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
