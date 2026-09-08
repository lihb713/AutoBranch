"""M7 编排器测试共享 fixture（mock M6 叶子 / M1 浏览器，不启动真实浏览器/LLM）。"""

from __future__ import annotations

import pytest
from orchestrator_helpers import MockBrowser, StubLeaf

from webops.orchestrator import Engine, RunConfig


@pytest.fixture
def config(tmp_path) -> RunConfig:
    return RunConfig(report_dir=str(tmp_path))


@pytest.fixture
def stub_leaf() -> StubLeaf:
    return StubLeaf()


@pytest.fixture
def mock_browser() -> MockBrowser:
    return MockBrowser()


@pytest.fixture
def engine(stub_leaf, mock_browser) -> Engine:
    return Engine(browser=mock_browser, leaf_executor=stub_leaf)
