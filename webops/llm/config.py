"""LLM 配置管理（契约 §6.1）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LLMConfig:
    """OpenAI 兼容接口配置。

    :param base_url: OpenAI 兼容接口地址（如 ``https://api.deepseek.com``）。
    :param api_key: 接口鉴权密钥。
    :param model: 模型名。
    :param session_id: 可选，稳定的会话标识（``x-opencode-session`` 请求头）。
        缺省由 ``LLMSession`` 自动生成 UUID（每个会话一次）。

    三个必填字段缺失任一构造时报参数校验错误（ValueError）。
    ``api_key`` 不应进入日志或报告。
    """

    base_url: str
    api_key: str
    model: str
    session_id: str | None = None

    def __post_init__(self) -> None:
        missing = [
            name
            for name, value in (
                ("base_url", self.base_url),
                ("api_key", self.api_key),
                ("model", self.model),
            )
            if not value or not isinstance(value, str)
        ]
        if missing:
            raise ValueError(f"LLMConfig 必填字段缺失或非法: {', '.join(missing)}")

    def auth_header_value(self) -> str:
        """生成 Authorization 请求头值。"""
        return f"Bearer {self.api_key}"
