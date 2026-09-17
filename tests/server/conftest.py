"""M9b 后端测试共享 fixture：临时数据库 + TestClient + mock 引擎。

- 每个用例独立 ``tmp_path`` 数据库与报告根（互不干扰）。
- 默认注入 ``MockEngineService``（spec §7 独立测试），集成测试另行注入
  内嵌真实引擎。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from autobranch.server.config import ServerConfig
from autobranch.server.db import configure_database, session_factory
from autobranch.server.main import create_app
from autobranch.server.services.engine import MockEngineService

#: 通过 M2 清晰度校验的合法行为树文档（统一槽位 DSL）。
VALID_YAML = """
tree: 冒烟流程
nodes:
  n1:
    type: Root
    name: 根
    body: n2
  n2:
    type: Sequence
    name: 流程
    actions: [n3, n4]
  n3:
    type: Step
    name: 登录
    action: n5
    expect: 出现"工作台"
  n5:
    type: Action
    name: 点登录
    description: 点"登录"
  n4:
    type: Step
    name: 退出
    action: n6
    expect: 回到登录页
  n6:
    type: Action
    name: 点退出
    description: 点"退出"
root: n1
""".strip()

#: 引用缺失（契约 §4.4 引用存在）。
INVALID_REF_YAML = """
tree: 坏文档
nodes:
  n1:
    type: Root
    name: 根
    body: n2
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
    body: n2
  n2:
    type: LoopUntil
    name: l
    action: n3
    until: 出现"最后一页"
  n3:
    type: Action
    name: 下一页
    description: 点击"下一页"
root: n1
""".strip()


@pytest.fixture
def settings(tmp_path) -> ServerConfig:
    return ServerConfig(db_path=tmp_path / "autobranch.db", report_root=tmp_path / "reports")


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
    """生成一文档一树统一槽位合法文档（契约 §12：tree/nodes/root）。"""
    return (
        f"tree: {name}\n"
        "nodes:\n"
        "  n1:\n"
        "    type: Root\n"
        "    name: 根\n"
        "    body: n2\n"
        "  n2:\n"
        "    type: Step\n"
        "    name: 登录\n"
        "    action: n3\n"
        '    expect: 出现"工作台"\n'
        "  n3:\n"
        "    type: Action\n"
        "    name: 点登录\n"
        '    description: 点击"登录"按钮\n'
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
