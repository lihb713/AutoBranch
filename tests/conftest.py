"""pytest 共享 fixture：默认 LLMConfig 与 FakeTransport。"""

from __future__ import annotations

import pytest
from fake_transport import FakeTransport

from autobranch.llm.config import LLMConfig


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
