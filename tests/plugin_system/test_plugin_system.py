"""插件框架（M3）单元测试：注册 / 双路径加载 / 懒装配分发 / 能力选择 / 报告接口。"""

from __future__ import annotations

import sys

import pytest

from autobranch.plugin_system import (
    FunctionResult,
    PluginBase,
    PluginError,
    PluginRegistry,
    check_plugin_source,
    collect_report_entries,
    engine_function,
    load_builtin_plugins,
    load_plugin_from_source,
)
from autobranch.plugin_system.capability import (
    USE_CAPABILITY_TOOL,
    capability_overview,
    handle_use_capability,
)


class DemoPlugin(PluginBase):
    name = "demo"
    description = "演示插件（乘法 / 问候）"

    def __init__(self) -> None:
        self.inits = 0
        self.released = 0

    @engine_function(
        name="multiply",
        description="乘法",
        parameters={
            "type": "object",
            "properties": {
                "a": {"type": "number"},
                "b": {"type": "number"},
            },
            "required": ["a", "b"],
        },
        returns=("result",),
    )
    def multiply(self, a, b):
        return a * b

    @engine_function(
        name="greet",
        description="问候（产出型，目标变量参数 target）",
        output_param="target",
    )
    def greet(self, target, who):
        return f"hi {who}"

    def _helper(self):
        return 42

    def init(self, runtime=None):
        self.inits += 1

    def release(self):
        self.released += 1


def test_registration_only_marked_functions():
    reg = PluginRegistry()
    reg.register(DemoPlugin())
    assert set(reg.functions()) == {"demo.multiply", "demo.greet"}
    assert reg.function("demo.multiply").returns == ("result",)
    assert reg.function("demo.greet").is_producing


def test_cross_plugin_same_name_allowed():
    class Other(PluginBase):
        name = "other"

        @engine_function(name="multiply", description="另一个 multiply")
        def multiply(self, a, b):
            return a + b

    reg = PluginRegistry()
    reg.register(DemoPlugin())
    reg.register(Other())  # 跨插件同名：不冲突
    assert reg.function("demo.multiply") is not None
    assert reg.function("other.multiply") is not None
    assert reg.call("demo.multiply", {"a": 2, "b": 3}).value == 6
    assert reg.call("other.multiply", {"a": 2, "b": 3}).value == 5


def test_same_plugin_duplicate_function_deduped():
    class Dup(PluginBase):
        name = "dup"

        @engine_function(name="same", description="第一个")
        def same(self):
            return 1

        @engine_function(name="same", description="第二个")
        def same2(self):
            return 2

    reg = PluginRegistry()
    reg.register(Dup())
    assert set(reg.functions()) == {"dup.same"}  # 同插件内同名只保留一个


def test_lazy_load_and_dispatch():
    reg = PluginRegistry()
    plugin = DemoPlugin()
    reg.register(plugin)
    assert not reg.is_loaded("demo")
    result = reg.call("demo.multiply", {"a": 2, "b": 3})
    assert result.ok and result.value == 6
    assert plugin.inits == 1
    reg.call("demo.multiply", {"a": 4, "b": 5})
    assert plugin.inits == 1  # 只装配一次


def test_unknown_function_returns_error():
    reg = PluginRegistry()
    reg.register(DemoPlugin())
    result = reg.call("nope")
    assert not result.ok and "未知函数" in result.error


def test_release_on_finish():
    reg = PluginRegistry()
    plugin = DemoPlugin()
    reg.register(plugin)
    reg.call("demo.multiply", {"a": 1, "b": 2})
    reg.release()
    assert plugin.released == 1
    assert not reg.is_loaded("demo")


def test_load_plugin_from_source():
    reg = PluginRegistry()
    source = '''
from autobranch.plugin_system import PluginBase, engine_function

class MyPlugin(PluginBase):
    name = "mycalc"
    description = "我的计算插件"

    @engine_function(name="double", description="翻倍")
    def double(self, x):
        return x * 2

plugin = MyPlugin()
'''
    load_plugin_from_source(reg, "mycalc", source)
    assert "mycalc" in reg.known_plugins()
    result = reg.call("mycalc.double", {"x": 21})
    assert result.ok and result.value == 42


def test_load_plugin_name_mismatch():
    reg = PluginRegistry()
    source = '''
from autobranch.plugin_system import PluginBase

class MyPlugin(PluginBase):
    name = "other"

plugin = MyPlugin()
'''
    with pytest.raises(PluginError):
        load_plugin_from_source(reg, "mycalc", source)


@pytest.mark.parametrize(
    ("source", "error_type"),
    [
        ("def broken(:\n", "syntax"),
        ("import requests\nplugin = None\n", "constraint"),
        ("from autobranch.plugins.browser import plugin\n", "constraint"),
    ],
)
def test_check_plugin_source_rejects(source, error_type):
    ok, errors = check_plugin_source(source)
    assert not ok
    assert any(e["type"] == error_type for e in errors)
    assert all("line" in e and "message" in e and "constraint" in e for e in errors)


def test_check_plugin_source_stdlib_ok():
    ok, errors = check_plugin_source("import json\nimport os\nplugin = None\n")
    assert ok and not errors


def test_load_builtin_plugins_scans_packages(tmp_path):
    reg = PluginRegistry()
    pkg = tmp_path / "demo_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        "from autobranch.plugin_system import PluginBase, engine_function\n"
        "class Demo(PluginBase):\n"
        "    name = 'scanned'\n"
        "    @engine_function(name='ping', description='ping')\n"
        "    def ping(self):\n"
        "        return 'pong'\n"
        "plugin = Demo()\n",
        encoding="utf-8",
    )
    (tmp_path / "_helper").mkdir()  # 下划线目录应跳过
    sys.path.insert(0, str(tmp_path))
    try:
        loaded = load_builtin_plugins(reg, tmp_path, package_root=tmp_path.name)
    finally:
        sys.path.remove(str(tmp_path))
    assert loaded == ["scanned"]
    assert reg.call("scanned.ping") == FunctionResult.success("pong")


def test_capability_overview_and_use():
    reg = PluginRegistry()
    reg.register(DemoPlugin())
    overview = capability_overview(reg)
    assert "demo" in overview and "demo.multiply" in overview
    result = handle_use_capability(reg, {"capability": "demo"})
    assert result.ok
    names = [s.name for s in result.detail["functions"]]
    assert "demo__multiply" in names  # LLM 工具名为转义全名（. → __）
    assert reg.is_loaded("demo")
    bad = handle_use_capability(reg, {"capability": "nope"})
    assert not bad.ok


def test_tool_spec_uses_escaped_full_name():
    reg = PluginRegistry()
    reg.register(DemoPlugin())
    spec = reg.function("demo.multiply")
    assert spec.tool_name == "demo__multiply"
    assert spec.to_tool_spec().name == "demo__multiply"


def test_use_capability_tool_is_framework_level():
    assert USE_CAPABILITY_TOOL.name == "use_capability"


def test_report_entries_by_source():
    result = FunctionResult.success(report={"sections": [{"title": "t", "body": "b"}]})
    entries = collect_report_entries(result, "demo")
    assert entries == [{"source": "demo", "sections": [{"title": "t", "body": "b"}]}]
    assert collect_report_entries(FunctionResult.success(), "demo") == []
