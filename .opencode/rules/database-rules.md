# 数据库设计与 SQL 约束

> 适用范围：M9b 后端数据持久化（SQLite，开发期）。契约依据 `docs/specs/M9b-management-backend.md`（文档库 + 报告/截图存储）。

## 1. 选型与 ORM

- **SQLite**（开发期单文件库），通过 **SQLAlchemy 2.0 ORM** 访问（配合 FastAPI 的依赖注入）。
- 不手写裸 SQL 拼字符串；复杂查询用 SQLAlchemy 表达式或参数化语句。
- 数据库连接统一在 `webops/server/db.py` 管理（engine + session 依赖）。

```python
# webops/server/db.py
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

engine = create_engine(
    "sqlite:///./webops.db",
    connect_args={"check_same_thread": False},  # FastAPI 多线程共享
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

## 2. 表设计规范

### 2.1 命名

- 表名：**复数 snake_case**（`trees`、`runs`、`node_reports`）。
- 列名：snake_case（`created_at`、`run_id`）。
- 主键统一 `id`（自增 INTEGER），外键列 `*_id` 命名，索引名 `ix_<表>_<列>`。

### 2.2 时间戳与审计列

- 所有业务表必带 `created_at` / `updated_at`（`DATETIME DEFAULT CURRENT_TIMESTAMP`），在 ORM 层用 `onupdate` 维护。

```python
from datetime import datetime
from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
```

### 2.3 核心表（M9b）

```python
# webops/server/models/tree.py
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from webops.server.db import Base
from webops.server.models.mixins import TimestampMixin


class Tree(Base, TimestampMixin):
    """行为树文档库。"""

    __tablename__ = "trees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)  # 行为树 yaml 文本
```

```python
# webops/server/models/run.py
class Run(Base, TimestampMixin):
    """一次执行记录。"""

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tree_id: Mapped[int] = mapped_column(ForeignKey("trees.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_path: Mapped[str | None] = mapped_column(String(500), nullable=True)  # 报告相对路径
```

## 3. 约束与校验

### 3.1 约束写在数据库层，不只靠应用层

```
✅  unique=True (name)          → 唯一约束
✅  nullable=False              → 非空约束
✅  ForeignKey("trees.id")      → 引用完整性
✅  CheckConstraint            → 枚举/范围约束
```

```python
from sqlalchemy import CheckConstraint, ForeignKey

STATUS_VALUES = ("pending", "running", "success", "failure")


class Run(Base, TimestampMixin):
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','success','failure')", name="ck_runs_status"
        ),
    )
    ...
```

### 3.2 外键与级联

- 删除父资源时明确级联策略：报告/节点记录随 run 删除用 `ondelete="CASCADE"`；业务文档被引用时禁止误删用 `RESTRICT`。

```python
class NodeReport(Base):
    run_id: Mapped[int] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
```

## 4. 查询规范

### 4.1 参数化，杜绝 SQL 注入

```
✅  session.execute(text("SELECT * FROM runs WHERE tree_id = :tid"), {"tid": tree_id})
❌  session.execute(text(f"SELECT * FROM runs WHERE tree_id = {tree_id}"))  # 注入风险
```

### 4.2 会话与事务

- 读取用独立 `Session`（FastAPI `Depends(get_db)` 注入），**长事务内不做网络/LLM 调用**（浏览器执行在后台任务，不占 HTTP 会话事务）。
- 写操作统一 `commit()`；失败 `rollback()`。

```python
def create_tree(db: Session, payload: TreeCreate) -> Tree:
    tree = Tree(name=payload.name, content=payload.content)
    db.add(tree)
    db.commit()
    db.refresh(tree)
    return tree
```

## 5. 迁移

- 开发期用 SQLAlchemy `create_all()` 建库；进入稳定期后引入 **Alembic** 管理版本化迁移。
- 迁移脚本只做增量变更，**不修改历史迁移文件**。

```bash
alembic init alembic
alembic revision --autogenerate -m "add runs table"
alembic upgrade head
```

## 6. 报告 / 截图文件存储

- 元数据入库，**文件本体落盘**（`data/reports/`），库中只存相对路径。
- 路径一律相对存储根，由 API 层做白名单解析（见 api-conventions.md §7）。

## 7. Do's & Don'ts 速查

| Do ✅ | Don't ❌ |
|---|---|
| 表名复数 snake_case、主键统一 id | 单数表名、混合命名、无主键表 |
| 约束写在数据库层（unique/check/非空） | 只靠应用层 if 校验 |
| 显式外键 + 明确级联策略 | 隐式关联、字段无外键 |
| 参数化查询 | 字符串拼接 SQL |
| 每请求独立短事务，写后 commit | 长事务内做 LLM/浏览器调用 |
| 大字段（报告正文）落盘存路径 | 把 yaml/报告全文塞进 DB 列 |
| 变更走 Alembic 增量迁移 | 手动改库 / 改写历史迁移 |