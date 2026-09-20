"""一次性迁移脚本：`runs` 表升级为"执行实例"快照模型（Change A 任务 1.2）。

背景：`Run` 从"指向 trees 的指针"升级为"自包含执行实例"——新增
``content_snapshot`` / ``tree_name_snapshot`` / ``tree_content_hash`` /
``inputs`` / ``outputs`` 列，``tree_id`` 由 ``NOT NULL + ON DELETE CASCADE``
改为``可空 + ON DELETE SET NULL``（删除行为树后保留执行历史）。

SQLite 不支持改列约束，故：

1. 新列（均为可空/带默认）用 ``ALTER TABLE ADD COLUMN``（幂等：按
   ``PRAGMA table_info`` 检测列是否存在）。
2. ``tree_id`` 约束改动走**表重建**：``PRAGMA foreign_keys=OFF`` → 建
   ``runs_new``（新结构）→ 拷数据 → drop 旧表 → rename → 重建索引与约束。

用法（autobranch conda 环境，项目根下）：
    python -m scripts.migrate_runs_snapshot [--db <path>]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from autobranch.server.config import DEFAULT_DB_PATH  # noqa: E402

#: 新增列（SQLite ALTER TABLE ADD COLUMN；JSON 列按 TEXT 存储，兼容 SQLAlchemy JSON）。
_NEW_COLUMNS: list[tuple[str, str]] = [
    ("content_snapshot", "TEXT NOT NULL DEFAULT ''"),
    ("tree_name_snapshot", "VARCHAR(200) NOT NULL DEFAULT ''"),
    ("tree_content_hash", "VARCHAR(64) NOT NULL DEFAULT ''"),
    ("inputs", "TEXT NOT NULL DEFAULT '{}'"),
    ("outputs", "TEXT"),
]

#: 重建后的 runs 表结构（与模型对齐：tree_id 可空 + SET NULL，新列带默认）。
_RUNS_DDL = """
CREATE TABLE runs_new (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    tree_id INTEGER,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    failure_reason TEXT,
    report_path VARCHAR(500),
    content_snapshot TEXT NOT NULL DEFAULT '',
    tree_name_snapshot VARCHAR(200) NOT NULL DEFAULT '',
    tree_content_hash VARCHAR(64) NOT NULL DEFAULT '',
    inputs TEXT NOT NULL DEFAULT '{}',
    outputs TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_runs_status CHECK (status IN ('pending','running','success','failure')),
    FOREIGN KEY(tree_id) REFERENCES trees (id) ON DELETE SET NULL
)
"""


def _columns(conn: sqlite3.Connection, table: str) -> dict[str, dict]:
    """``PRAGMA table_info`` → {列名: 行信息}。"""
    return {row[1]: {"type": row[2], "notnull": row[3]} for row in conn.execute(
        f"PRAGMA table_info({table})"
    ).fetchall()}


def _foreign_key_actions(conn: sqlite3.Connection, table: str) -> list[tuple]:
    return conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()


def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def migrate(conn: sqlite3.Connection) -> list[str]:
    """对单连接执行迁移；返回执行的步骤描述（幂等）。"""
    steps: list[str] = []
    if not _has_table(conn, "runs"):
        steps.append("runs 表不存在，跳过")
        return steps

    cols = _columns(conn, "runs")

    # 1) 新增列（幂等）
    for name, ddl in _NEW_COLUMNS:
        if name not in cols:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {name} {ddl}")
            steps.append(f"新增列 {name}")

    # 2) tree_id 约束：NOT NULL + CASCADE → 可空 + SET NULL（表重建）
    tree_id = _columns(conn, "runs").get("tree_id")
    fk = _foreign_key_actions(conn, "runs")
    already = tree_id is not None and tree_id["notnull"] == 0 and any(
        row[6] == "SET NULL" for row in fk  # PRAGMA foreign_key_list on_delete 列
    )
    if not already:
        conn.execute("PRAGMA foreign_keys=OFF")
        old_cols = _columns(conn, "runs")
        _copy_columns = ", ".join(col for col in old_cols if col != "id") or "id"
        conn.execute("DROP TABLE IF EXISTS runs_new")
        conn.execute(_RUNS_DDL)
        conn.execute(
            f"INSERT INTO runs_new (id, {_copy_columns}) SELECT id, {_copy_columns} FROM runs"
        )
        conn.execute("DROP TABLE runs")
        conn.execute("ALTER TABLE runs_new RENAME TO runs")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_runs_tree_id ON runs (tree_id)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_runs_tree_content_hash ON runs (tree_content_hash)"
        )
        conn.execute("PRAGMA foreign_keys=ON")
        steps.append("表重建：tree_id 可空 + ON DELETE SET NULL，新列带默认值")
    else:
        steps.append("tree_id 约束已是 SET NULL，跳过表重建")

    return steps


def main() -> int:
    parser = argparse.ArgumentParser(description="迁移 runs 表为执行实例快照模型")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite 数据库文件路径")
    args = parser.parse_args()

    path = Path(args.db).resolve()
    if not path.is_file():
        print(f"数据库不存在，跳过: {path}")
        return 0
    conn = sqlite3.connect(str(path))
    try:
        steps = migrate(conn)
        conn.commit()
    finally:
        conn.close()

    print(f"数据库: {path}")
    if steps:
        for step in steps:
            print(f"  - {step}")
    else:
        print("  无变更")
    print("完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
