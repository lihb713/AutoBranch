"""插件框架：插件定义契约（M3 spec 插件定义与显式注册）。

- ``FunctionDef``：结构化函数定义（名字 / 说明 / 参数 / 多返回值 / 变量目标
  参数 / 实现）。
- ``FunctionResult``：插件函数返回值（业务值 + 报告附加信息）。
- ``@engine_function``：显式注册装饰器——未标注的函数与类不注册。
- ``PluginBase``：插件基类（``name`` / ``description`` / ``function_defs()`` /
  ``init(runtime)`` / ``call(name, args)``）。

插件函数只返回值、不接触变量空间（变量写入由引擎落笔，见分发层）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from autobranch.llm import ToolSpec


class PluginError(Exception):
    """插件框架错误（注册 / 加载 / 分发）。"""


@dataclass
class FunctionResult:
    """插件函数返回值：业务值 + 报告附加信息（引擎落笔）。

    :param values: 业务返回值（按 ``FunctionDef.returns`` 顺序）；单值工具为
      ``(v,)``。
    :param ok: 是否成功。
    :param error: 失败原因（``ok=False`` 时）。
    :param report: 报告附加信息（结构化 ``{"sections": [...]}``）；引擎补来源后
      写入报告。
    :param detail: 其他结构化附加数据。
    """

    values: tuple[Any, ...] = ()
    ok: bool = True
    error: str | None = None
    report: dict[str, Any] | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success(
        cls,
        *values: Any,
        report: dict[str, Any] | None = None,
        **detail: Any,
    ) -> FunctionResult:
        return cls(values=tuple(values), ok=True, report=report, detail=dict(detail))

    @classmethod
    def failure(cls, error: str, **detail: Any) -> FunctionResult:
        return cls(values=(), ok=False, error=error, detail=dict(detail))

    @property
    def value(self) -> Any:
        """单值工具的首个返回值（无则 None）。"""
        return self.values[0] if self.values else None


@dataclass(frozen=True)
class FunctionDef:
    """结构化函数定义（M3 spec）。

    :param name: 注册函数名（**插件内唯一**，跨插件允许同名）。
    :param plugin: 所属插件名（注册时填充；未注册时为空）。
    :param description: 函数说明（供 LLM 工具 schema）。
    :param parameters: JSON Schema 参数定义。
    :param returns: 返回值名列表（多返回值，按序）。
    :param output_param: 产出型工具的变量目标参数名（None = 非产出型）。
    :param impl: 函数实现（装饰器自动绑定）。
    """

    name: str
    plugin: str = ""
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    returns: tuple[str, ...] = ()
    output_param: str | None = None
    impl: Callable[..., Any] | None = None

    @property
    def is_producing(self) -> bool:
        """是否产出型工具（声明了变量目标参数）。"""
        return bool(self.output_param)

    @property
    def full_name(self) -> str:
        """全名标识：``插件名.函数名``（无插件时退化为裸函数名）。"""
        return f"{self.plugin}.{self.name}" if self.plugin else self.name

    @property
    def tool_name(self) -> str:
        """LLM 工具名（API 安全）：全名中的 ``.`` 转义为 ``__``。

        多数 OpenAI 兼容 API 的工具名仅允许 ``[a-zA-Z0-9_-]``，点号会被拒绝；
        引擎在分发时按此名反查回全名（见 M6 ``_plugin_tool_call``）。
        """
        return self.full_name.replace(".", "__")

    def to_tool_spec(self, *, extra_params: dict[str, Any] | None = None) -> ToolSpec:
        """转为 M0 工具 schema（可选追加参数，如产出型工具的 target）。

        工具名 = ``tool_name``（全名的 API 安全转义），跨插件同名工具不歧义。
        """
        params = dict(self.parameters) if self.parameters else {
            "type": "object",
            "properties": {},
        }
        if extra_params:
            props = dict(params.get("properties", {}))
            props.update(extra_params)
            params = {**params, "properties": props}
        return ToolSpec(name=self.tool_name, description=self.description, parameters=params)


def engine_function(
    name: str | None = None,
    description: str = "",
    parameters: dict[str, Any] | None = None,
    returns: tuple[str, ...] | list[str] = (),
    output_param: str | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """显式注册装饰器：把函数标注为插件对外函数。

    未标注的函数与类不注册。函数名默认取函数名；``description`` 缺省取
    函数 docstring。
    """

    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        spec = FunctionDef(
            name=name or fn.__name__,
            description=description or (fn.__doc__ or "").strip(),
            parameters=parameters or {"type": "object", "properties": {}},
            returns=tuple(returns),
            output_param=output_param,
            impl=fn,
        )
        fn.__engine_function__ = spec
        return fn

    return deco


def _wrap_result(raw: Any) -> FunctionResult:
    """把插件函数的裸返回值包装为 ``FunctionResult``。"""
    if isinstance(raw, FunctionResult):
        return raw
    if raw is None:
        return FunctionResult.success()
    return FunctionResult.success(raw)


class PluginBase:
    """插件基类（M3 spec）：插件类定义能力。

    子类覆写类属性 ``name`` / ``description``，用 ``@engine_function`` 装饰
    对外函数（方法），可选覆写 ``init(runtime)`` 初始化公共资源。``call`` 由
    基类按函数名分发到方法。
    """

    name: str = ""
    description: str = ""

    def function_defs(self) -> list[FunctionDef]:
        """收集本插件全部 ``@engine_function`` 标注的函数定义。"""
        specs: list[FunctionDef] = []
        seen: set[str] = set()
        for attr in dir(self):
            if attr.startswith("_"):
                continue
            member = getattr(self, attr)
            func = getattr(member, "__func__", member)
            spec = getattr(func, "__engine_function__", None)
            if isinstance(spec, FunctionDef) and spec.name not in seen:
                seen.add(spec.name)
                specs.append(spec)
        return specs

    def init(self, runtime: Any) -> None:
        """初始化该插件的公共资源（懒装配时调用；默认无操作）。"""

    def call(self, name: str, args: dict[str, Any] | None = None) -> FunctionResult:
        """按函数名分发到插件方法，返回值包装为 ``FunctionResult``。"""
        func = getattr(self, name, None)
        if func is None or not callable(func):
            return FunctionResult.failure(f"插件 {self.name} 无函数: {name}")
        try:
            raw = func(**(args or {}))
        except TypeError as exc:
            return FunctionResult.failure(f"函数 {name} 参数错误: {exc}")
        except Exception as exc:  # noqa: BLE001 - agent 语义：异常转失败结果
            return FunctionResult.failure(f"函数 {name} 执行异常: {exc}")
        return _wrap_result(raw)


__all__ = [
    "PluginError",
    "FunctionResult",
    "FunctionDef",
    "engine_function",
    "PluginBase",
]
