"""浏览器驱动独立性：驱动自身不依赖 LLM 与行为树（物理位于浏览器插件内）。"""

from __future__ import annotations

import subprocess
import sys

from autobranch.browser import BrowserDriver


def test_browser_package_has_no_llm_imports():
    """autobranch/plugins/browser/driver 源码不 import autobranch.llm（静态校验）。"""
    import pathlib

    import autobranch.plugins.browser.driver as driver

    package_dir = pathlib.Path(driver.__file__).parent
    assert package_dir.name == "driver"
    for source in package_dir.glob("*.py"):
        text = source.read_text(encoding="utf-8")
        assert "autobranch.llm" not in text, f"{source.name} 引用了 autobranch.llm"


def test_driver_has_no_llm_dependency():
    driver = BrowserDriver()
    assert isinstance(driver, BrowserDriver)
    # 驱动可实例化，无需任何 LLM 配置
    assert driver.running is False


def test_module_importable_in_isolated_interpreter():
    """在独立解释器中可导入浏览器驱动子包并实例化。"""
    code = (
        "from autobranch.plugins.browser.driver import BrowserDriver; "
        "d = BrowserDriver(); "
        "assert d.running is False; "
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
