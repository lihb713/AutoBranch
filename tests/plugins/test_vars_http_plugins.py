"""vars / http 插件单元测试。"""

from __future__ import annotations

from autobranch.plugin_system import PluginRegistry
from autobranch.plugins.http import HttpPlugin
from autobranch.plugins.vars import VarsPlugin


def test_vars_set_is_producing_and_returns_fixed_positions():
    reg = PluginRegistry()
    reg.register(VarsPlugin())
    spec = reg.function("vars.set")
    assert spec.output_param == "save_to"
    assert spec.returns == {"value1": "str", "value2": "str", "value3": "str"}
    result = reg.call("vars.set", {"value1": "A", "value2": "B"})
    assert result.ok
    assert result.values == ("A", "B", "")


def test_vars_set_requires_a_value():
    reg = PluginRegistry()
    reg.register(VarsPlugin())
    assert not reg.call("vars.set", {}).ok


def test_http_request_is_user_visible():
    reg = PluginRegistry()
    reg.register(HttpPlugin())
    spec = reg.function("http.request")
    assert spec is not None
    assert spec.user_visible is True
    assert spec.returns == {"status": "int", "body": "str", "headers": "object"}
