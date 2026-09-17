"""任务 5.1/5.2/5.3：token 统计与预算管理。"""

from __future__ import annotations

import pytest
from fake_transport import chat_response

from autobranch.llm.errors import LLMBudgetExceeded
from autobranch.llm.session import LLMSession


def make_session(config, fake, budget=None):
    return LLMSession(config=config, system_prompt="你是助手", transport=fake, budget_limit=budget)


def test_token_usage_accumulates(config, fake):
    """5.1 token_used() 随请求只增不减，等于各轮累加和。"""
    fake.responses = [
        chat_response(text="a", usage={"prompt_tokens": 10, "completion_tokens": 5}),
        chat_response(text="b", usage={"prompt_tokens": 7, "completion_tokens": 3}),
    ]
    session = make_session(config, fake)
    session.add_user_message("hi")
    session.request()
    assert session.token_used() == 15
    session.request()
    assert session.token_used() == 25


def test_token_estimated_when_no_usage(config, fake):
    """usage 缺失时保守估算，token 仍累积（非零）。"""
    fake.responses = [chat_response(text="hello")]  # 无 usage
    session = make_session(config, fake)
    session.add_user_message("你好，请介绍一下自己。")
    session.request()
    assert session.token_used() > 0


def test_under_budget_returns_normally(config, fake):
    """5.2 未超预算时请求正常返回。"""
    fake.responses = [chat_response(text="ok", usage={"total_tokens": 30})]
    session = make_session(config, fake, budget=100)
    session.add_user_message("hi")
    resp = session.request()
    assert resp.text == "ok"
    assert not session.exceeds_budget(100)
    assert session.exceeds_budget(10) is True


def test_budget_exceeded_raises(config, fake):
    """5.3 请求后累计超过上限 → LLMBudgetExceeded。"""
    fake.responses = [
        chat_response(text="a", usage={"total_tokens": 60}),
        chat_response(text="b", usage={"total_tokens": 60}),
    ]
    session = make_session(config, fake, budget=100)
    session.add_user_message("q1")
    session.request()  # 60 <= 100，正常
    session.add_user_message("q2")
    with pytest.raises(LLMBudgetExceeded):
        session.request()  # 120 > 100，抛错


def test_budget_exceeded_can_be_caught_by_caller(config, fake):
    """调用方可捕获预算异常并终止叶子（对应 spec 预算场景）。"""
    fake.responses = [chat_response(text="x", usage={"total_tokens": 999})]
    session = make_session(config, fake, budget=10)
    session.add_user_message("q")
    with pytest.raises(LLMBudgetExceeded) as exc_info:
        session.request()
    assert "预算超限" in str(exc_info.value)
