"""配置加载模块测试（autobranch/config.py）。

覆盖：默认值、JSON 文件加载、字段映射、api_key 环境变量注入、
to_llm_config/to_browser_config/to_run_config 构建。
"""

from __future__ import annotations

import json

import pytest

from autobranch.config import AutoBranchConfig, LLMOptions, RunOptions


@pytest.fixture
def config_file(tmp_path):
    path = tmp_path / "autobranch.config.json"
    path.write_text(
        json.dumps(
            {
                "llm": {
                    "base_url": "https://api.example.com/v1",
                    "api_key": "from-file",
                    "model": "my-model",
                    "timeout": 30,
                },
                "browser": {"browser_type": "firefox", "headless": False, "timeout_ms": 5000},
                "run": {
                    "timeout": 200,
                    "max_rounds": 6,
                    "report_dir": "custom_reports",
                },
                "max_concurrent_runs": 5,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_defaults_when_no_file(tmp_path, monkeypatch):
    monkeypatch.delenv("AUTOBRANCH_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)  # 无 autobranch.config.json
    cfg = AutoBranchConfig.load()
    assert cfg.llm.base_url == "https://opencode.ai/zen/go/v1"
    assert cfg.llm.model == "deepseek-v4-flash"
    assert cfg.llm.api_key == ""
    assert cfg.run.report_dir == "reports"
    assert cfg.browser.browser_type == "chromium"
    assert cfg.run.timeout == 240.0
    assert cfg.run.max_rounds == 10
    assert cfg.max_concurrent_runs == 3  # 默认并发上限


def test_load_from_file(config_file):
    cfg = AutoBranchConfig.load(config_file, apply_env=False)
    assert cfg.llm.base_url == "https://api.example.com/v1"
    assert cfg.llm.api_key == "from-file"
    assert cfg.llm.model == "my-model"
    assert cfg.llm.timeout == 30.0
    assert cfg.browser.browser_type == "firefox"
    assert cfg.browser.headless is False
    assert cfg.browser.timeout_ms == 5000
    assert cfg.run.timeout == 200.0
    assert cfg.run.max_rounds == 6
    assert cfg.run.report_dir == "custom_reports"
    assert cfg.max_concurrent_runs == 5  # 配置文件覆盖


def test_env_api_key_overrides_file(config_file, monkeypatch):
    monkeypatch.setenv("AUTOBRANCH_LLM_API_KEY", "sk-env-secret")
    cfg = AutoBranchConfig.load(config_file, apply_env=True)
    assert cfg.llm.api_key == "sk-env-secret"  # 环境变量优先
    assert cfg.llm.base_url == "https://api.example.com/v1"  # 文件字段保留
    assert cfg.max_concurrent_runs == 5  # env 覆盖不影响并发上限


def test_env_config_path(config_file, monkeypatch):
    monkeypatch.setenv("AUTOBRANCH_CONFIG", str(config_file))
    monkeypatch.delenv("AUTOBRANCH_LLM_API_KEY", raising=False)
    cfg = AutoBranchConfig.load(apply_env=False)
    assert cfg.llm.model == "my-model"


def test_empty_api_key_allowed_in_file(tmp_path, monkeypatch):
    """配置文件 api_key 留空合法（内部工具亦可直接写入 key，两种用法均支持）。"""
    # 用临时空配置目录，避免依赖真实 autobranch.config.json 的内容
    monkeypatch.delenv("AUTOBRANCH_CONFIG", raising=False)
    monkeypatch.delenv("AUTOBRANCH_LLM_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    cfg = AutoBranchConfig.load()
    assert cfg.llm.api_key == ""


def test_api_key_read_from_file(tmp_path, monkeypatch):
    """配置文件 api_key 直接写入时被加载（内部工具用法）。"""
    path = tmp_path / "autobranch.config.json"
    path.write_text(
        json.dumps({"llm": {"api_key": "sk-from-file"}}), encoding="utf-8"
    )
    monkeypatch.delenv("AUTOBRANCH_LLM_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    cfg = AutoBranchConfig.load()
    assert cfg.llm.api_key == "sk-from-file"


def test_to_llm_config_requires_key(config_file):
    cfg = AutoBranchConfig.load(config_file, apply_env=False)
    llm = cfg.to_llm_config()
    assert llm.base_url == "https://api.example.com/v1"
    assert llm.api_key == "from-file"
    assert llm.model == "my-model"
    # 空 key 构造应抛 ValueError
    empty = AutoBranchConfig()
    with pytest.raises(ValueError):
        empty.to_llm_config()


def test_to_browser_config(config_file):
    cfg = AutoBranchConfig.load(config_file, apply_env=False)
    bc = cfg.to_browser_config()
    assert bc.browser_type == "firefox"
    assert bc.headless is False
    assert bc.timeout_ms == 5000
    assert bc.ignore_https_errors is False


def test_browser_ignore_https_errors_default_and_override(tmp_path, monkeypatch):
    from autobranch.browser import BrowserConfig
    from autobranch.config import BrowserOptions

    assert BrowserOptions().ignore_https_errors is False
    assert BrowserConfig().ignore_https_errors is False

    path = tmp_path / "autobranch.config.json"
    path.write_text(
        '{"browser": {"ignore_https_errors": true}}', encoding="utf-8"
    )
    monkeypatch.delenv("AUTOBRANCH_LLM_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    cfg = AutoBranchConfig.load()
    assert cfg.browser.ignore_https_errors is True
    assert cfg.to_browser_config().ignore_https_errors is True


def test_to_run_config(config_file):
    cfg = AutoBranchConfig.load(config_file, apply_env=False)
    rc = cfg.to_run_config(max_rounds=3)
    assert rc.timeout == 200.0
    assert rc.report_dir == "custom_reports"
    assert rc.max_rounds == 3  # 覆盖生效


def test_run_options_from_dict_with_none():
    opts = RunOptions.from_dict({"timeout": None, "budget_limit": None})
    assert opts.timeout is None
    assert opts.budget_limit is None
    assert opts.report_dir == "reports"


def test_llm_options_from_dict():
    opts = LLMOptions.from_dict({"base_url": "u", "api_key": "k", "model": "m", "timeout": 9})
    assert opts.base_url == "u"
    assert opts.timeout == 9.0
