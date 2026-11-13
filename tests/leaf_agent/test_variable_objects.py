"""对象变量传递：Param.x 保留、函数参数解析、多返回值 save_to、变量表注入。"""

from __future__ import annotations

import pytest
from fake_transport import FakeTransport, chat_response
from leaf_agent_helpers import MockRegistry

from autobranch.leaf_agent import execute_leaf
from autobranch.leaf_agent.models import LeafContext
from autobranch.llm import LLMConfig, LLMSession
from autobranch.parser.models import ActionNode
from autobranch.plugin_system import FunctionResult
from autobranch.schema import SchemaSpace


class Conn:
    def __repr__(self) -> str:
        return "SSHConnection(id=abc)"


@pytest.fixture
def llm_config() -> LLMConfig:
    return LLMConfig(base_url="https://api.test.example/v1", api_key="sk-test", model="m")


@pytest.fixture
def space() -> SchemaSpace:
    sp = SchemaSpace()
    sp.enter_frame("主流程")
    return sp


def _ctx(llm_config, space, transport, engine):
    def factory(cfg, system_prompt):
        return LLMSession(config=cfg, system_prompt=system_prompt, transport=transport)

    return LeafContext(
        config=llm_config,
        registry=engine,
        space=space,
        session_factory=factory,
        tools=[],
    )


def test_object_param_preserved_and_variable_table_injected(llm_config, space):
    conn = Conn()
    space.write(space._current, "this/conn", conn, "object")
    transport = FakeTransport(responses=[chat_response(text="结果: 成功")])
    ctx = _ctx(llm_config, space, transport, MockRegistry())
    node = ActionNode(description="在SSH会话 Param.conn 上执行命令")
    result = execute_leaf(node, ctx)
    assert result.status == "success"
    user_text = " ".join(
        m["content"] for m in transport.last_request.json()["messages"] if m["role"] == "user"
    )
    assert "Param.conn" in user_text
    assert "conn (object): SSHConnection(id=abc)" in user_text


def test_param_arg_resolved_to_object(llm_config, space):
    conn = Conn()
    space.write(space._current, "this/conn", conn, "object")
    engine = MockRegistry()
    engine.register("ssh.ssh_exec")
    engine.results["ssh.ssh_exec"] = FunctionResult.success("file1", "", 0)
    transport = FakeTransport(
        responses=[
            chat_response(
                tool_calls=[
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {
                            "name": "ssh.ssh_exec",
                            "arguments": '{"session":"Param.conn","command":"ls /home"}',
                        },
                    }
                ]
            ),
            chat_response(text="结果: 成功"),
        ]
    )
    ctx = _ctx(llm_config, space, transport, engine)
    result = execute_leaf(ActionNode(description="执行命令"), ctx)
    assert result.status == "success"
    assert engine.calls[0][1]["session"] is conn


def test_multi_return_save_to_dict(llm_config, space):
    engine = MockRegistry()
    engine.register(
        "ssh.ssh_exec",
        output_param="save_to",
        returns={"stdout": "str", "stderr": "str", "exit_code": "int"},
    )
    engine.results["ssh.ssh_exec"] = FunctionResult.success("file1", "", 0)
    transport = FakeTransport(
        responses=[
            chat_response(
                tool_calls=[
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {
                            "name": "ssh.ssh_exec",
                            "arguments": (
                                '{"session":"Param.conn","command":"ls /home",'
                                '"save_to":{"stdout":"home_list","exit_code":"code"}}'
                            ),
                        },
                    }
                ]
            ),
            chat_response(text="结果: 成功"),
        ]
    )
    space.write(space._current, "this/conn", Conn(), "object")
    ctx = _ctx(llm_config, space, transport, engine)
    node = ActionNode(
        description="执行命令 NewParam.home_list:str NewParam.code:int",
        set_targets=("home_list", "code"),
        set_decls=(("home_list", "str"), ("code", "int")),
    )
    result = execute_leaf(node, ctx)
    assert result.status == "success"
    assert space.read(space._current, "this/home_list") == "file1"
    assert space.read(space._current, "this/code") == 0
    assert "save_to" not in engine.calls[0][1]


def test_single_return_save_to_string_for_multi_return_function(llm_config, space):
    engine = MockRegistry()
    engine.register(
        "ssh.ssh_exec",
        output_param="save_to",
        returns={"stdout": "str", "stderr": "str", "exit_code": "int"},
    )
    engine.results["ssh.ssh_exec"] = FunctionResult.success("out", "err", 0)
    transport = FakeTransport(
        responses=[
            chat_response(
                tool_calls=[
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {
                            "name": "ssh.ssh_exec",
                            "arguments": (
                                '{"session":"Param.conn","command":"ls",'
                                '"save_to":"home_list"}'
                            ),
                        },
                    }
                ]
            ),
            chat_response(text="结果: 成功"),
        ]
    )
    space.write(space._current, "this/conn", Conn(), "object")
    ctx = _ctx(llm_config, space, transport, engine)
    node = ActionNode(
        description="执行命令 NewParam.home_list:str",
        set_targets=("home_list",),
        set_decls=(("home_list", "str"),),
    )
    result = execute_leaf(node, ctx)
    assert result.status == "success"
    assert space.read(space._current, "this/home_list") == "out"


def test_save_to_json_string_is_parsed(llm_config, space):
    engine = MockRegistry()
    engine.register(
        "ssh.ssh_exec",
        output_param="save_to",
        returns={"stdout": "str", "stderr": "str", "exit_code": "int"},
    )
    engine.results["ssh.ssh_exec"] = FunctionResult.success("out", "err", 0)
    transport = FakeTransport(
        responses=[
            chat_response(
                tool_calls=[
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {
                            "name": "ssh.ssh_exec",
                            "arguments": (
                                '{"session":"Param.conn","command":"ls",'
                                '"save_to":"{\\"stdout\\":\\"home_list\\"}"}'
                            ),
                        },
                    }
                ]
            ),
            chat_response(text="结果: 成功"),
        ]
    )
    space.write(space._current, "this/conn", Conn(), "object")
    ctx = _ctx(llm_config, space, transport, engine)
    node = ActionNode(
        description="执行命令 NewParam.home_list:str",
        set_targets=("home_list",),
        set_decls=(("home_list", "str"),),
    )
    result = execute_leaf(node, ctx)
    assert result.status == "success"
    assert space.read(space._current, "this/home_list") == "out"
