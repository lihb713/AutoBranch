"""浏览器代理路由（SwitchyOmega 式，浏览器插件内）。

按站点规则（配置文件）把打开页面的 URL 映射到代理模式（system / direct / 自定义），
供 ``BrowserDriver.open`` 选择对应会话（context）打开页面。

配置文件为插件资产 ``proxy.config.json``（与 ``proxy.py`` 同目录）；缺失/非法
则不启用路由，打开行为保持默认（跟随系统代理）。配置格式见 ``proxy.config.example.json``。
"""

from __future__ import annotations

import json
import os
from urllib.parse import urlparse

#: 插件目录内默认配置文件路径。
DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxy.config.json")


def load_proxy_config(path: str | None = None) -> dict | None:
    """加载代理配置；缺失/非法返回 None（调用方不启用路由）。

    :param path: 配置文件路径；None 用插件目录默认 ``proxy.config.json``。
    """
    target = path or DEFAULT_CONFIG_PATH
    if not os.path.isfile(target):
        return None
    try:
        with open(target, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if not isinstance(data.get("rules", []), list) or not isinstance(
        data.get("profiles", {}), dict
    ):
        return None
    return data


def _host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def _match_pattern(pattern: str, host: str) -> bool:
    """hostname 模式匹配：``*`` 全部；``*.x`` 匹配 x 及任意子域；``x`` 精确匹配。"""
    p = (pattern or "").strip().lower()
    if not p or p == "*":
        return True
    if p.startswith("*."):
        base = p[2:]
        return host == base or host.endswith("." + base)
    return host == p


class ProxyRouter:
    """代理路由：URL → 代理 profile（首条规则命中，否则 default）。

    返回规范化 profile：``{"mode":"system"}`` / ``{"mode":"direct"}`` /
    ``{"mode":"custom","server",...}``。
    """

    def __init__(self, config: dict) -> None:
        self._default: object = config.get("default") or "system"
        self._profiles: dict = config.get("profiles") or {}
        self._rules: list = config.get("rules") or []

    def resolve(self, url: str) -> dict:
        host = _host_of(url)
        for rule in self._rules:
            if not isinstance(rule, dict):
                continue
            if _match_pattern(rule.get("pattern"), host):
                profile = self._profiles.get(rule.get("proxy"))
                if profile is not None:
                    return self._normalize(profile)
        return self._resolve_default()

    def _resolve_default(self) -> dict:
        if isinstance(self._default, str) and self._default in self._profiles:
            return self._normalize(self._profiles[self._default])
        mode = self._default if self._default in ("system", "direct") else "system"
        return {"mode": mode}

    @staticmethod
    def _normalize(profile: object) -> dict:
        if not isinstance(profile, dict):
            return {"mode": "system"}
        if profile.get("mode") in ("system", "direct"):
            return {"mode": profile["mode"]}
        server = profile.get("server")
        if isinstance(server, str) and server:
            out: dict = {"mode": "custom", "server": server}
            if isinstance(profile.get("username"), str):
                out["username"] = profile["username"]
            if isinstance(profile.get("password"), str):
                out["password"] = profile["password"]
            return out
        return {"mode": "system"}


def proxy_key(profile: dict) -> str:
    """profile → 会话（context）键：system / direct / custom:<server>。"""
    if profile.get("mode") == "direct":
        return "direct"
    if profile.get("mode") == "custom":
        return f"custom:{profile.get('server', '')}"
    return "system"


__all__ = ["ProxyRouter", "load_proxy_config", "proxy_key", "DEFAULT_CONFIG_PATH"]
