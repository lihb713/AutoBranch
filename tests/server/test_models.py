"""M9b 数据模型测试（任务 2.1/2.2/2.3）。

覆盖：trees CRUD 持久化、name 唯一约束、时间戳、runs status 枚举约束、
删除 tree 时 run 级联（设计 D5）。
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from autobranch.server.db import session_factory
from autobranch.server.models import Run, Tree
from autobranch.server.services.reports import ReportService

# ------------------------------------------------------------- trees（2.1/2.3）

def test_tree_create_and_read(session):
    tree = Tree(name="登录", content="content-1")
    session.add(tree)
    session.commit()
    session.refresh(tree)
    assert tree.id is not None
    loaded = session.get(Tree, tree.id)
    assert loaded.name == "登录"
    assert loaded.content == "content-1"


def test_tree_update(session):
    tree = Tree(name="a", content="v1")
    session.add(tree)
    session.commit()
    session.refresh(tree)
    tree.content = "v2"
    session.commit()
    assert session.get(Tree, tree.id).content == "v2"


def test_tree_delete(session):
    tree = Tree(name="a", content="v1")
    session.add(tree)
    session.commit()
    tree_id = tree.id
    session.delete(tree)
    session.commit()
    assert session.get(Tree, tree_id) is None


def test_tree_name_unique(session):
    session.add(Tree(name="a", content="v1"))
    session.commit()
    session.add(Tree(name="a", content="v2"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_tree_timestamps(session):
    tree = Tree(name="ts", content="c")
    session.add(tree)
    session.commit()
    session.refresh(tree)
    assert tree.created_at is not None
    assert tree.updated_at is not None


def test_tree_crud_idempotent_recreate(session):
    tree = Tree(name="once", content="c")
    session.add(tree)
    session.commit()
    session.delete(tree)
    session.commit()
    second = Tree(name="once", content="c")
    session.add(second)
    session.commit()
    session.refresh(second)
    assert second.id is not None


# ------------------------------------------------------------- runs（2.2）

def _tree(session, name: str = "t") -> Tree:
    tree = Tree(name=name, content="c")
    session.add(tree)
    session.commit()
    session.refresh(tree)
    return tree


def test_run_default_status_pending(session):
    tree = _tree(session)
    run = Run(tree_id=tree.id)
    session.add(run)
    session.commit()
    session.refresh(run)
    assert run.status == "pending"
    assert run.report_path is None
    assert run.failure_reason is None


def test_run_invalid_status_rejected(session):
    tree = _tree(session)
    run = Run(tree_id=tree.id, status="invalid")
    session.add(run)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


@pytest.mark.parametrize("status", ["pending", "running", "success", "failure"])
def test_run_valid_statuses(session, status):
    tree = _tree(session)
    run = Run(tree_id=tree.id, status=status)
    session.add(run)
    session.commit()
    assert session.get(Run, run.id).status == status


def test_run_snapshot_columns(session):
    """快照化列：默认值 + 类型（Change A 任务 1.1）。"""
    tree = _tree(session)
    run = Run(tree_id=tree.id, status="success")
    session.add(run)
    session.commit()
    session.refresh(run)
    assert run.content_snapshot == ""
    assert run.tree_name_snapshot == ""
    assert run.tree_content_hash == ""
    assert run.inputs == {}
    assert run.outputs is None

    run.inputs = {"user": "admin"}
    run.outputs = {"结果": "ok"}
    run.content_snapshot = "tree: x"
    run.tree_content_hash = "abc123"
    session.commit()
    session.refresh(run)
    assert run.inputs == {"user": "admin"}
    assert run.outputs == {"结果": "ok"}
    assert run.tree_content_hash == "abc123"


def test_run_survives_tree_delete_sets_null(session, tmp_path):
    """删除行为树后执行历史保留（tree_id 置空、快照自包含）——Change A 任务 1.1。"""
    reports = ReportService(tmp_path / "reports")
    reports.ensure_root()
    tree = _tree(session)
    run = Run(
        tree_id=tree.id,
        status="success",
        report_path="1/exec_report.md",
        content_snapshot="tree: x",
        tree_name_snapshot="x",
        tree_content_hash="abc123",
        inputs={"user": "admin"},
    )
    session.add(run)
    session.commit()
    run_id = run.id
    session.delete(tree)
    session.commit()
    session.close()
    fresh = session_factory()()
    kept = fresh.get(Run, run_id)
    assert kept is not None
    assert kept.tree_id is None
    assert kept.tree_name_snapshot == "x"
    assert kept.content_snapshot == "tree: x"
    fresh.close()


def test_run_timestamps(session):
    tree = _tree(session)
    run = Run(tree_id=tree.id)
    session.add(run)
    session.commit()
    session.refresh(run)
    assert run.created_at is not None
    assert run.updated_at is not None
