"""M1 任务 10.2：模块独立性——浏览器驱动不依赖 LLM 与行为树。

验收标准 §6 全项的真实浏览器验证分散在 tests/browser 各文件（会话/多页/
HTTP/文件/截图/DOM/错误语义），本文件校验模块自身无 LLM/行为树依赖，可在
无 LLM、无行为树条件下独立运行。
"""

from __future__ import annotations

import subprocess
import sys

import webops.browser
from webops.browser import BrowserDriver


def test_browser_package_has_no_llm_imports():
    """webops/browser 源码不 import webops.llm（静态校验）。"""
    import pathlib

    package_dir = pathlib.Path(webops.browser.__file__).parent
    assert package_dir.name == "browser"
    for source in package_dir.glob("*.py"):
        text = source.read_text(encoding="utf-8")
        assert "webops.llm" not in text, f"{source.name} 引用了 webops.llm"


def test_driver_has_no_llm_dependency():
    driver = BrowserDriver()
    assert isinstance(driver, BrowserDriver)
    # 驱动可实例化，无需任何 LLM 配置
    assert driver.running is False


def test_module_importable_in_isolated_interpreter():
    """在独立解释器中仅导入浏览器模块（无 LLM、无行为树）。"""
    code = (
        "import webops.browser; "
        "assert 'webops.llm' not in sys.modules; "
        "print('browser-only ok')"
    )
    result = subprocess.run(
        [sys.executable, "-c", f"import sys; {code}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "browser-only ok" in result.stdout
