"""M9b 后端测试共享 fixture：临时数据库 + TestClient + mock 引擎。

- 每个用例独立 ``tmp_path`` 数据库与报告根（互不干扰）。
- 默认注入 ``MockEngineService``（spec §7 独立测试），集成测试另行注入
  内嵌真实引擎。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from webops.server.config import ServerConfig
from webops.server.db import configure_database, session_factory
from webops.server.main import create_app
from webops.server.services.engine import MockEngineService

#: 通过 M2 清晰度校验的合法行为树文档。
VALID_YAML = """
tree: 冒烟流程
nodes:
  n1:
    type: Root
    name: 根
    slots: {1: n2}
  n2:
    type: Sequence
    name: 流程
    slots: {1: n3, 2: n4}
  n3:
    type: Step
    name: 登录
    action: 点"登录"
    expect: 出现"工作台"
  n4:
    type: Step
    name: 退出
    action: 点"退出"
    expect: 回到登录页
root: n1
""".strip()

#: 引用缺失（契约 §4.4 引用存在）。
INVALID_REF_YAML = """
tree: 坏文档
nodes:
  n1:
    type: Root
    name: 根
    slots: {1: n2}
  n2:
    type: ref
    name: x
    target: 不存在的文档
root: n1
""".strip()

#: 循环无上界（契约 §4.4 循环有上界）。
INVALID_LOOP_YAML = """
tree: 死循环
nodes:
  n1:
    type: Root
    name: 根
    slots: {1: n2}
  n2:
    type: LoopUntil
    name: l
    action: 点"下一页"
    until: 出现"最后一页"
root: n1
""".strip()


@pytest.fixture
def settings(tmp_path) -> ServerConfig:
    return ServerConfig(db_path=tmp_path / "webops.db", report_root=tmp_path / "reports")


@pytest.fixture
def mock_engine() -> MockEngineService:
    return MockEngineService()


@pytest.fixture
def client(settings, mock_engine) -> TestClient:
    app = create_app(settings, engine_service=mock_engine)
    return TestClient(app)


@pytest.fixture
def session(settings):
    """独立数据库会话（模型/服务层单测用）。"""
    configure_database(settings.db_path)
    db = session_factory()()
    yield db
    db.close()


def make_tree_yaml(name: str) -> str:
    """生成一文档一树合法文档（契约 §12：tree/nodes/root）。"""
    return (
        f"tree: {name}\n"
        "nodes:\n"
        "  n1:\n"
        "    type: Root\n"
        "    name: 根\n"
        "    slots: {1: n2}\n"
        "  n2:\n"
        "    type: Step\n"
        "    name: 登录\n"
        '    action: 点"登录"\n'
        '    expect: 出现"工作台"\n'
        "root: n1\n"
    )


def create_tree(client: TestClient, name: str = "冒烟流程", content: str | None = None) -> dict:
    resp = client.post(
        "/api/trees",
        json={"name": name, "content": content or make_tree_yaml(name)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


__all__ = [
    "VALID_YAML",
    "INVALID_REF_YAML",
    "INVALID_LOOP_YAML",
    "create_tree",
]
