"""协议适配层（设计决策 D3）。

Chat Completions 与 Responses 两种协议形态各有独立的请求构造与响应解析，
二者都映射到同一内部消息序列（``Message``）与同一 ``LLMResponse`` 结果结构。
会话层（消息累积、工具回填、预算）只面对一种模型，协议切换只影响适配层。
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Literal

from autobranch.llm.errors import LLMProtocolError
from autobranch.llm.models import LLMResponse, Message, ToolCall, ToolSpec

ProtocolName = Literal["chat", "responses"]


class ProtocolAdapter(ABC):
    """协议适配器基类。"""

    endpoint_suffix: str

    @abstractmethod
    def build_request(
        self,
        model: str,
        system_prompt: str,
        messages: list[Message],
        tools: list[ToolSpec] | None,
        stream: bool,
    ) -> dict:
        """构造协议请求体（dict，传输层负责 JSON 序列化）。"""

    @abstractmethod
    def parse_response(self, body: bytes) -> tuple[LLMResponse, dict]:
        """解析协议响应体，返回 (LLMResponse, usage)。

        响应无法解析（格式错误 / 非法 JSON 参数）时抛 :class:`LLMProtocolError`。
        """


def _parse_json_body(body: bytes) -> dict:
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LLMProtocolError(f"LLM 响应不是合法 JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LLMProtocolError("LLM 响应体不是 JSON 对象")
    return parsed


class ChatCompletionsAdapter(ProtocolAdapter):
    """Chat Completions 协议（/chat/completions）。"""

    endpoint_suffix = "/chat/completions"

    def build_request(
        self,
        model: str,
        system_prompt: str,
        messages: list[Message],
        tools: list[ToolSpec] | None,
        stream: bool,
    ) -> dict:
        api_messages: list[dict] = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            entry: dict = {"role": msg.role}
            if msg.role == "tool":
                entry["tool_call_id"] = msg.tool_call_id or ""
                entry["content"] = msg.content
            elif msg.role == "assistant" and msg.tool_calls:
                entry["content"] = msg.content
                entry["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.name, "arguments": call.arguments},
                    }
                    for call in msg.tool_calls
                ]
            else:
                entry["content"] = msg.content
            api_messages.append(entry)

        payload: dict = {"model": model, "messages": api_messages, "stream": stream}
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in tools
            ]
        return payload

    def parse_response(self, body: bytes) -> tuple[LLMResponse, dict]:
        parsed = _parse_json_body(body)
        choices = parsed.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMProtocolError("Chat Completions 响应缺少 choices")
        message = choices[0].get("message") or {}
        text = message.get("content") or ""
        tool_calls: list[ToolCall] = []
        raw_calls = message.get("tool_calls") or []
        if isinstance(raw_calls, list):
            for raw in raw_calls:
                func = raw.get("function") or {}
                arguments = func.get("arguments") or ""
                _validate_json_arguments(arguments)
                tool_calls.append(
                    ToolCall(id=raw.get("id", ""), name=func.get("name", ""), arguments=arguments)
                )
        usage = parsed.get("usage")
        return LLMResponse(text=text, tool_calls=tool_calls), usage

    def parse_stream_response(self, body: bytes) -> tuple[LLMResponse, dict]:
        """解析 Chat Completions SSE 流式响应（chat.completion.chunk）。

        逐行累积 ``delta.content`` 与 ``delta.tool_calls``（按 index 归并、逐段拼接
        ``function.arguments``），usage 取任一 chunk 顶层 ``usage``（OpenAI 流式在
        最终 chunk 提供）。最终工具参数经 JSON 合法性校验。
        """
        text_parts: list[str] = []
        call_buffers: dict[int, dict[str, str]] = {}
        usage: dict | None = None
        for line in body.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                continue
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue
            if isinstance(event.get("usage"), dict):
                usage = event["usage"]
            choices = event.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            content = delta.get("content")
            if content:
                text_parts.append(content)
            raw_calls = delta.get("tool_calls")
            if isinstance(raw_calls, list):
                for raw in raw_calls:
                    idx = raw.get("index", 0)
                    buf = call_buffers.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                    if raw.get("id"):
                        buf["id"] = raw["id"]
                    fn = raw.get("function") or {}
                    if fn.get("name"):
                        buf["name"] = fn["name"]
                    if fn.get("arguments"):
                        buf["arguments"] += fn["arguments"]
        tool_calls: list[ToolCall] = []
        for idx in sorted(call_buffers):
            buf = call_buffers[idx]
            if not buf["name"]:
                continue
            _validate_json_arguments(buf["arguments"])
            tool_calls.append(ToolCall(id=buf["id"], name=buf["name"], arguments=buf["arguments"]))
        return LLMResponse(text="".join(text_parts), tool_calls=tool_calls), usage


class ResponsesAdapter(ProtocolAdapter):
    """Responses 协议（/v1/responses）。"""

    endpoint_suffix = "/responses"

    def build_request(
        self,
        model: str,
        system_prompt: str,
        messages: list[Message],
        tools: list[ToolSpec] | None,
        stream: bool,
    ) -> dict:
        payload: dict = {"model": model, "instructions": system_prompt, "stream": stream}
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                }
                for tool in tools
            ]

        input_items: list[dict] = []
        for msg in messages:
            if msg.role == "tool":
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": msg.tool_call_id or "",
                        "output": msg.content,
                    }
                )
            elif msg.role == "assistant" and msg.tool_calls:
                input_items.append({"type": "message", "role": "assistant", "content": msg.content})
                for call in msg.tool_calls:
                    input_items.append(
                        {
                            "type": "function_call",
                            "call_id": call.id,
                            "name": call.name,
                            "arguments": call.arguments,
                        }
                    )
            else:
                input_items.append({"type": "message", "role": msg.role, "content": msg.content})
        payload["input"] = input_items
        return payload

    def parse_response(self, body: bytes) -> tuple[LLMResponse, dict]:
        parsed = _parse_json_body(body)
        output = parsed.get("output")
        if not isinstance(output, list):
            raise LLMProtocolError("Responses 响应缺少 output")

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "message":
                content = item.get("content") or []
                for part in content:
                    if isinstance(part, dict) and part.get("type") in ("output_text", "text"):
                        text_parts.append(part.get("text", "") or "")
            elif item_type == "function_call":
                arguments = item.get("arguments") or ""
                _validate_json_arguments(arguments)
                tool_calls.append(
                    ToolCall(
                        id=item.get("call_id", ""),
                        name=item.get("name", ""),
                        arguments=arguments,
                    )
                )
        usage = parsed.get("usage")
        return LLMResponse(text="".join(text_parts), tool_calls=tool_calls), usage


def _validate_json_arguments(arguments: str) -> None:
    """工具调用参数必须是合法 JSON 字符串（M0 spec §5.3 场景 5）。"""
    try:
        json.loads(arguments)
    except json.JSONDecodeError as exc:
        raise LLMProtocolError(f"工具调用参数不是合法 JSON: {exc}") from exc


def parse_chat_stream(body: bytes) -> list[str]:
    """解析 Chat Completions SSE 流，返回按 chunk 分段的内容列表。

    SSE 事件格式：以 ``data: `` 前缀、换行分隔，空行表示事件结束；
    ``[DONE]`` 表示流结束。每个事件的 ``choices[0].delta.content``
    即一段文本。解析失败的分段会被跳过，保证非流式路径不受影响。
    """
    chunks: list[str] = []
    lines = body.decode("utf-8", errors="replace").splitlines()
    for line in lines:
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[len("data:"):].strip()
        if data == "[DONE]":
            continue
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            continue
        choices = event.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        text = delta.get("content")
        if text:
            chunks.append(text)
    return chunks


ADAPTERS: dict[ProtocolName, ProtocolAdapter] = {
    "chat": ChatCompletionsAdapter(),
    "responses": ResponsesAdapter(),
}
