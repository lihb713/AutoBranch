"""M8 报告机制测试共享 fixture（mock M1 截图，不启动真实浏览器/LLM）。"""

from __future__ import annotations

import os

import pytest
from autobranch.browser.models import OpResult, PageRef
from reporting.factories import (
    make_action_report,
    make_composite_report,
    make_condition_report,
)

from autobranch.reporting.models import NodeInfo, NodeReport


@pytest.fixture
def action_report() -> NodeReport:
    return make_action_report()


@pytest.fixture
def condition_report() -> NodeReport:
    return make_condition_report()


@pytest.fixture
def composite_report() -> NodeReport:
    return make_composite_report()


@pytest.fixture
def node_info() -> NodeInfo:
    return NodeInfo(node_type="Action", node_desc="点击登录")


@pytest.fixture
def fake_screenshotter():
    """mock M1 截图：把文件写入目标路径并返回成功 ``OpResult``。"""

    def _shot(page_ref: PageRef, path: str) -> OpResult:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(b"png-bytes")
        return OpResult(True, detail={"path": path, "page_ref": page_ref})

    return _shot


@pytest.fixture
def failing_screenshotter():
    """mock M1 截图：抛出异常（如页面已关闭）。"""

    def _shot(page_ref: PageRef, path: str) -> OpResult:
        raise RuntimeError("页面已关闭")

    return _shot


@pytest.fixture
def error_screenshotter():
    """mock M1 截图：返回 ``ok=False`` 的失败结果。"""

    def _shot(page_ref: PageRef, path: str) -> OpResult:
        return OpResult(False, "页面已关闭", {"code": "INVALID_REF"})

    return _shot
