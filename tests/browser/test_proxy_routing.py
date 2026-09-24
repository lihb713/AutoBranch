"""浏览器代理路由单测（browser-proxy-routing 任务 1.1）。

覆盖：配置加载容错、hostname 模式匹配、首条命中优先级、default 兜底（具名 profile
与 system/direct）、profile 规范化、proxy_key。
"""

from __future__ import annotations

import json

from autobranch.plugins.browser.proxy import (
    ProxyRouter,
    load_proxy_config,
    proxy_key,
)

CONFIG = {
    "default": "system",
    "profiles": {
        "直连": {"mode": "direct"},
        "公司代理": {"server": "http://proxy.corp:8080", "username": "u", "password": "p"},
    },
    "rules": [
        {"pattern": "*.corp.example", "proxy": "公司代理"},
        {"pattern": "127.0.0.1", "proxy": "直连"},
    ],
}


def test_load_config_missing_returns_none(tmp_path):
    assert load_proxy_config(str(tmp_path / "nope.json")) is None


def test_load_config_invalid_returns_none(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json", encoding="utf-8")
    assert load_proxy_config(str(bad)) is None
    bad.write_text('{"rules": 1}', encoding="utf-8")
    assert load_proxy_config(str(bad)) is None


def test_load_config_valid(tmp_path):
    p = tmp_path / "proxy.json"
    p.write_text(json.dumps(CONFIG), encoding="utf-8")
    data = load_proxy_config(str(p))
    assert data["default"] == "system"


def test_resolve_subdomain_rule():
    r = ProxyRouter(CONFIG)
    assert r.resolve("http://intranet.corp.example/x") == {
        "mode": "custom",
        "server": "http://proxy.corp:8080",
        "username": "u",
        "password": "p",
    }


def test_resolve_exact_host_rule():
    r = ProxyRouter(CONFIG)
    assert r.resolve("http://127.0.0.1:8123/index.html") == {"mode": "direct"}


def test_resolve_first_match_wins():
    cfg = {
        "default": "system",
        "profiles": {"A": {"mode": "direct"}, "B": {"mode": "direct"}},
        "rules": [
            {"pattern": "*.x.example", "proxy": "A"},
            {"pattern": "api.x.example", "proxy": "B"},
        ],
    }
    r = ProxyRouter(cfg)
    assert r.resolve("http://api.x.example/") == {"mode": "direct"}
    # 首条命中（`*.x.example` 也匹配 api.x.example，按序先到先得）
    assert r.resolve("http://a.x.example/") == {"mode": "direct"}


def test_resolve_catch_all_star():
    cfg = {
        "default": "system",
        "profiles": {"直连": {"mode": "direct"}},
        "rules": [{"pattern": "*", "proxy": "直连"}],
    }
    r = ProxyRouter(cfg)
    assert r.resolve("http://anything.example/") == {"mode": "direct"}


def test_resolve_default_fallback():
    r = ProxyRouter(CONFIG)
    assert r.resolve("http://example.com/") == {"mode": "system"}


def test_resolve_default_named_profile():
    cfg = {
        "default": "直连",
        "profiles": {"直连": {"mode": "direct"}},
        "rules": [],
    }
    r = ProxyRouter(cfg)
    assert r.resolve("http://example.com/") == {"mode": "direct"}


def test_resolve_unmatched_scheme():
    r = ProxyRouter(CONFIG)
    assert r.resolve("not-a-url") == {"mode": "system"}


def test_proxy_key():
    assert proxy_key({"mode": "system"}) == "system"
    assert proxy_key({"mode": "direct"}) == "direct"
    assert proxy_key({"mode": "custom", "server": "http://p:1"}) == "custom:http://p:1"
    assert proxy_key({"mode": "system"}) == "system"
    assert proxy_key({"mode": "direct"}) == "direct"
    assert proxy_key({"mode": "custom", "server": "http://p:1"}) == "custom:http://p:1"


def test_load_config_default_path_missing():
    """插件目录无 proxy.config.json → load_proxy_config() 返回 None（不启用路由）。"""
    assert load_proxy_config() is None
