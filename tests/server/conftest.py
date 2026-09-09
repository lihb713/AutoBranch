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
block 冒烟流程:
  Sequence:
    - Step:
        action: 点"登录"
        expect: 出现"工作台"
    - Step:
        action: 点"退出"
        expect: 回到登录页
""".strip()

#: 块引用缺失（契约 §4.4 引用存在）。
INVALID_REF_YAML = """
block 坏文档:
  Sequence:
    - ref: this/不存在的块
""".strip()

#: 循环无上界（契约 §4.4 循环有上界）。
INVALID_LOOP_YAML = """
block 死循环:
  Sequence:
    - LoopUntil:
        action: 点"下一页"
        until: 出现"最后一页"
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
    """生成主块名 = 树名的单块合法文档（方案 2：主块名 = 行为树名）。"""
    return (
        f"block {name}:\n"
        "  Sequence:\n"
        "    - Step:\n"
        '        action: 点"登录"\n'
        '        expect: 出现"工作台"\n'
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
