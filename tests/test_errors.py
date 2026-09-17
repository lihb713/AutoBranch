"""任务 6.1/6.2/6.3/6.4：可分类错误语义。"""

from __future__ import annotations

import pytest

from autobranch.llm.errors import (
    LLMAuthError,
    LLMBudgetExceeded,
    LLMConnectionError,
    LLMError,
    LLMTimeoutError,
)
from autobranch.llm.session import LLMSession


def test_connection_error_classified(config, fake):
    """6.1 网络异常 → LLMConnectionError，重试语义可区分。"""
    fake.error = LLMConnectionError("connection refused")
    session = LLMSession(config=config, system_prompt="s", transport=fake)
    session.add_user_message("hi")
    with pytest.raises(LLMConnectionError):
        session.request()


def test_auth_error_on_401(config, fake):
    """6.2 HTTP 401 → LLMAuthError。"""
    fake.responses = [(401, '{"error":{"message":"invalid api key"}}')]
    session = LLMSession(config=config, system_prompt="s", transport=fake)
    session.add_user_message("hi")
    with pytest.raises(LLMAuthError):
        session.request()


def test_auth_error_on_403(config, fake):
    fake.responses = [(403, "forbidden")]
    session = LLMSession(config=config, system_prompt="s", transport=fake)
    session.add_user_message("hi")
    with pytest.raises(LLMAuthError):
        session.request()


def test_timeout_error_classified(config, fake):
    """6.3 请求超时 → LLMTimeoutError。"""
    fake.error = LLMTimeoutError("timed out")
    session = LLMSession(config=config, system_prompt="s", transport=fake, timeout=0.1)
    session.add_user_message("hi")
    with pytest.raises(LLMTimeoutError):
        session.request()


def test_four_exception_classes_distinguishable():
    """6.4 四类异常可被上层区分捕获（各自继承 LLMError，互不为子类）。"""
    auth = LLMAuthError("a")
    conn = LLMConnectionError("c")
    timeout = LLMTimeoutError("t")
    budget = LLMBudgetExceeded("b")

    assert isinstance(auth, LLMError)
    assert isinstance(conn, LLMError)
    assert isinstance(timeout, LLMError)
    assert isinstance(budget, LLMError)

    # 互不相同：捕获其一不会误捕其余
    for base, others in [
        (LLMAuthError, [conn, timeout, budget]),
        (LLMConnectionError, [auth, timeout, budget]),
        (LLMTimeoutError, [auth, conn, budget]),
        (LLMBudgetExceeded, [auth, conn, timeout]),
    ]:
        for other in others:
            assert not isinstance(other, base)


def test_caller_can_dispatch_by_error_source(config, fake):
    """上层按错误源分流：连接/超时重试有意义，鉴权重试无意义。"""
    results: list[str] = []

    fake.error = LLMConnectionError("network down")
    session = LLMSession(config=config, system_prompt="s", transport=fake)
    session.add_user_message("hi")
    try:
        session.request()
    except LLMAuthError:
        results.append("config-problem")
    except (LLMConnectionError, LLMTimeoutError):
        results.append("retryable")
    except LLMBudgetExceeded:
        results.append("terminate")

    assert results == ["retryable"]
