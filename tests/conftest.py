"""pytest 共享 fixture：默认 LLMConfig 与 FakeTransport。"""

from __future__ import annotations

import pytest
from fake_transport import FakeTransport

from autobranch.llm.config import LLMConfig
from autobranch.llm.session import _STREAM_MODE_CACHE


@pytest.fixture(autouse=True)
def _clear_stream_mode_cache():
    """清空进程级请求形态缓存（流式/非流式自动兼容），避免跨测试污染。"""
    _STREAM_MODE_CACHE.clear()
    yield
    _STREAM_MODE_CACHE.clear()


@pytest.fixture
def config() -> LLMConfig:
    return LLMConfig(
        base_url="https://api.test.example/v1",
        api_key="test-secret-key",
        model="test-model",
    )


@pytest.fixture
def fake() -> FakeTransport:
    return FakeTransport()
