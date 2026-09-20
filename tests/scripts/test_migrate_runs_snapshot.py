"""scripts/migrate_runs_snapshot.py 迁移测试（Change A 任务 1.2）。

用"旧结构"的临时 SQLite 库验证：新列新增、数据保留、tree_id 改可空 + SET NULL、
幂等（重复执行无额外步骤）。
"""

from __future__ import annotations

import sqlite3

from scripts.migrate_runs_snapshot import _columns, migrate

#: 旧结构 runs 表（NOT NULL + CASCADE，无快照列）。
_OLD_RUNS_DDL = """
CREATE TABLE trees (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(200) NOT NULL UNIQUE,
    content TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE runs (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    tree_id INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    failure_reason TEXT,
    report_path VARCHAR(500),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_runs_status CHECK (status IN ('pending','running','success','failure')),
    FOREIGN KEY(tree_id) REFERENCES trees (id) ON DELETE CASCADE
);
CREATE INDEX ix_runs_tree_id ON runs (tree_id);
"""


def _make_old_db(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(str(path))
    conn.executescript(_OLD_RUNS_DDL)
    conn.execute("INSERT INTO trees (name, content) VALUES ('t', 'c')")
    conn.execute(
        "INSERT INTO runs (tree_id, status, failure_reason, report_path) "
        "VALUES (1, 'success', NULL, '1/exec_report.md')"
    )
    conn.commit()
    return path, conn


def test_migrate_adds_columns_and_preserves_data(tmp_path):
    path, conn = _make_old_db(tmp_path)
    try:
        steps = migrate(conn)
        conn.commit()
        assert any("新增列" in s for s in steps)
        assert any("表重建" in s for s in steps)

        cols = _columns(conn, "runs")
        for name in (
            "content_snapshot",
            "tree_name_snapshot",
            "tree_content_hash",
            "inputs",
            "outputs",
        ):
            assert name in cols, name

        row = conn.execute(
            "SELECT id, status, report_path, content_snapshot, inputs FROM runs"
        ).fetchone()
        assert row == (1, "success", "1/exec_report.md", "", "{}")
    finally:
        conn.close()


def test_migrate_sets_tree_id_nullable_and_set_null(tmp_path):
    path, conn = _make_old_db(tmp_path)
    try:
        migrate(conn)
        conn.commit()
        tree_id_col = _columns(conn, "runs")["tree_id"]
        assert tree_id_col["notnull"] == 0
        fk = conn.execute("PRAGMA foreign_key_list(runs)").fetchall()
        assert any(r[6] == "SET NULL" for r in fk)

        # 删除行为树 → run 保留、tree_id 置空（需显式开启外键，裸连接默认关闭）
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("DELETE FROM trees WHERE id = 1")
        conn.commit()
        row = conn.execute("SELECT tree_id FROM runs WHERE id = 1").fetchone()
        assert row[0] is None
    finally:
        conn.close()


def test_migrate_idempotent(tmp_path):
    path, conn = _make_old_db(tmp_path)
    try:
        migrate(conn)
        conn.commit()
        second = migrate(conn)
        conn.commit()
        # 二次执行无实际变更（新增列/表重建均不触发；跳过消息不以"表重建："/"新增列"开头）
        assert not any(s.startswith("表重建：") for s in second)
        assert not any(s.startswith("新增列") for s in second)
        assert second == ["tree_id 约束已是 SET NULL，跳过表重建"]
    finally:
        conn.close()


def test_migrate_missing_table_noop(tmp_path):
    path = tmp_path / "empty.db"
    conn = sqlite3.connect(str(path))
    try:
        steps = migrate(conn)
        conn.commit()
        assert any("不存在" in s for s in steps)
    finally:
        conn.close()
