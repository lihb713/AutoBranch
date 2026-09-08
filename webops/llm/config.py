"""LLM 配置管理（契约 §6.1）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LLMConfig:
    """OpenAI 兼容接口配置。

    :param base_url: OpenAI 兼容接口地址（如 ``https://api.deepseek.com``）。
    :param api_key: 接口鉴权密钥。
    :param model: 模型名。

    三个字段均为必填，缺失任一字段构造时报参数校验错误（ValueError）。
    ``api_key`` 不应进入日志或报告。
    """

    base_url: str
    api_key: str
    model: str

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
