"""AutoBranch 统一配置加载（工具侧配置，非用户行为树文档）。

集中管理程序运行参数：LLM 配置（base_url/api_key/model）、浏览器配置
（类型/无头/超时）、运行参数（叶子超时/轮数上限/报告目录等）。配置来源：

1. 默认值（代码内）
2. 配置文件（JSON，路径由 ``--config`` 或环境变量 ``AUTOBRANCH_CONFIG`` 指定）
3. 环境变量覆盖（当前仅 ``AUTOBRANCH_LLM_API_KEY`` 用于密钥安全注入）

**api_key 安全**：api_key 属于敏感信息，配置文件中的 ``api_key`` 可为空，
加载时优先取环境变量 ``AUTOBRANCH_LLM_API_KEY``（不把密钥写入配置文件/仓库）。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: 默认配置文件路径（项目根）。
DEFAULT_CONFIG_PATH = "autobranch.config.json"
#: 运行目录（报告/截图等产物的默认根目录）。
DEFAULT_REPORT_DIR = "reports"


@dataclass(frozen=True)
class LLMOptions:
    """LLM 配置项（契约 §6.1）。

    :param base_url: OpenAI 兼容接口地址。
    :param api_key: 鉴权密钥（可为空，加载时环境变量优先）。
    :param model: 模型名。
    :param timeout: 单次请求超时秒数（对应 LLMSession.timeout）。
    """

    base_url: str = "https://opencode.ai/zen/go/v1"
    api_key: str = ""
    model: str = "deepseek-v4-flash"
    timeout: float = 60.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LLMOptions:
        return cls(
            base_url=str(data.get("base_url", cls.base_url)),
            api_key=str(data.get("api_key", "")),
            model=str(data.get("model", cls.model)),
            timeout=float(data.get("timeout", cls.timeout)),
        )


@dataclass(frozen=True)
class BrowserOptions:
    """浏览器配置项（M1 spec §3.1）。"""

    browser_type: str = "chromium"
    headless: bool = True
    timeout_ms: int = 30000

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BrowserOptions:
        return cls(
            browser_type=str(data.get("browser_type", cls.browser_type)),
            headless=bool(data.get("headless", cls.headless)),
            timeout_ms=int(data.get("timeout_ms", cls.timeout_ms)),
        )


@dataclass(frozen=True)
class RunOptions:
    """运行参数（M7 spec §5.1/§5.4）。

    :param timeout: 全局叶子超时秒数（None 不检测）。
    :param max_rounds: 叶子 LLM 工具调用轮数上限（传 M6）。
    :param no_progress_rounds: 连续无进展判定轮数（传 M6）。
    :param session_timeout: 单次 LLM 请求超时秒数（传 M6）。
    :param initial_graph_scope: 初始语义图范围（传 M6）。
    :param initial_graph_lod: 初始语义图 LOD（传 M6）。
    :param report_dir: 报告持久化根目录。
    :param page_var: ``open`` 写入的页面引用变量名（传 M5）。
    :param budget_limit: 语义图 token 预算上限（None 不检测）。
    """

    timeout: float | None = 240.0
    max_rounds: int = 10
    no_progress_rounds: int = 2
    session_timeout: float = 60.0
    initial_graph_scope: str = "full"
    initial_graph_lod: int = 2
    report_dir: str = DEFAULT_REPORT_DIR
    page_var: str = "page"
    budget_limit: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunOptions:
        timeout = data["timeout"] if "timeout" in data else cls.timeout
        budget = data["budget_limit"] if "budget_limit" in data else cls.budget_limit
        return cls(
            timeout=float(timeout) if timeout is not None else None,
            max_rounds=int(data.get("max_rounds", cls.max_rounds)),
            no_progress_rounds=int(data.get("no_progress_rounds", cls.no_progress_rounds)),
            session_timeout=float(data.get("session_timeout", cls.session_timeout)),
            initial_graph_scope=str(data.get("initial_graph_scope", cls.initial_graph_scope)),
            initial_graph_lod=int(data.get("initial_graph_lod", cls.initial_graph_lod)),
            report_dir=str(data.get("report_dir", cls.report_dir)),
            page_var=str(data.get("page_var", cls.page_var)),
            budget_limit=int(budget) if budget is not None else None,
        )


@dataclass(frozen=True)
class AutoBranchConfig:
    """AutoBranch 统一配置（配置文件的根结构）。

    JSON 结构示例（``autobranch.config.json``）：

    .. code-block:: json

        {
          "llm": {"base_url": "https://opencode.ai/zen/go/v1",
                  "api_key": "", "model": "deepseek-v4-flash", "timeout": 60},
          "browser": {"browser_type": "chromium", "headless": true, "timeout_ms": 30000},
          "run": {"timeout": 120, "max_rounds": 10, "report_dir": "reports"}
        }
    """

    llm: LLMOptions = field(default_factory=LLMOptions)
    browser: BrowserOptions = field(default_factory=BrowserOptions)
    run: RunOptions = field(default_factory=RunOptions)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutoBranchConfig:
        llm_data = data.get("llm") or {}
        browser_data = data.get("browser") or {}
        run_data = data.get("run") or {}
        return cls(
            llm=LLMOptions.from_dict(llm_data),
            browser=BrowserOptions.from_dict(browser_data),
            run=RunOptions.from_dict(run_data),
        )

    @classmethod
    def load(cls, path: str | Path | None = None, *, apply_env: bool = True) -> AutoBranchConfig:
        """从配置文件加载；缺失配置项回落默认值。

        :param path: 配置文件路径；None 依次尝试 ``AUTOBRANCH_CONFIG`` 环境变量与
          项目根 ``autobranch.config.json``（不存在则用全默认）。
        :param apply_env: 是否应用环境变量覆盖（``AUTOBRANCH_LLM_API_KEY``）。
        """
        resolved = _resolve_path(path)
        data: dict[str, Any] = {}
        if resolved is not None and Path(resolved).is_file():
            with open(resolved, encoding="utf-8") as handle:
                loaded = json.load(handle)
            if isinstance(loaded, dict):
                data = loaded
        cfg = cls.from_dict(data)
        if apply_env:
            cfg = _apply_env_overrides(cfg)
        return cfg

    def to_llm_config(self) -> Any:
        """构建 M0 ``LLMConfig``（api_key 缺失时抛 ValueError）。"""
        from autobranch.llm import LLMConfig

        return LLMConfig(
            base_url=self.llm.base_url,
            api_key=self.llm.api_key,
            model=self.llm.model,
        )

    def to_browser_config(self) -> Any:
        """构建 M1 ``BrowserConfig``。"""
        from autobranch.browser import BrowserConfig

        return BrowserConfig(
            browser_type=self.browser.browser_type,
            headless=self.browser.headless,
            timeout_ms=self.browser.timeout_ms,
        )

    def to_run_config(self, **overrides: Any) -> Any:
        """构建 M7 ``RunConfig``（额外覆盖参数可直接传入）。"""
        from autobranch.orchestrator import RunConfig

        base = dict(
            timeout=self.run.timeout,
            max_rounds=self.run.max_rounds,
            no_progress_rounds=self.run.no_progress_rounds,
            session_timeout=self.run.session_timeout,
            initial_graph_scope=self.run.initial_graph_scope,
            initial_graph_lod=self.run.initial_graph_lod,
            report_dir=self.run.report_dir,
        )
        base.update(overrides)
        return RunConfig(**base)


def _resolve_path(path: str | Path | None) -> str | None:
    if path is not None:
        return str(path)
    env_path = os.environ.get("AUTOBRANCH_CONFIG")
    if env_path:
        return env_path
    if Path(DEFAULT_CONFIG_PATH).is_file():
        return DEFAULT_CONFIG_PATH
    return None


def _apply_env_overrides(cfg: AutoBranchConfig) -> AutoBranchConfig:
    """环境变量覆盖：``AUTOBRANCH_LLM_API_KEY`` 优先于配置文件（安全注入密钥）。"""
    key = os.environ.get("AUTOBRANCH_LLM_API_KEY")
    if key:
        return AutoBranchConfig(
            llm=LLMOptions(
                base_url=cfg.llm.base_url,
                api_key=key,
                model=cfg.llm.model,
                timeout=cfg.llm.timeout,
            ),
            browser=cfg.browser,
            run=cfg.run,
        )
    return cfg


__all__ = [
    "AutoBranchConfig",
    "LLMOptions",
    "BrowserOptions",
    "RunOptions",
    "DEFAULT_CONFIG_PATH",
    "DEFAULT_REPORT_DIR",
]
