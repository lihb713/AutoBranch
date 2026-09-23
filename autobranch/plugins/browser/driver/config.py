"""浏览器驱动配置（M1 spec §3.1 输入）。"""

from __future__ import annotations

from dataclasses import dataclass

_BROWSER_TYPES = ("chromium", "firefox", "webkit")


@dataclass(frozen=True)
class BrowserConfig:
    """浏览器会话配置。

    :param browser_type: Playwright 浏览器类型（chromium/firefox/webkit）。
    :param headless: 是否无头运行。
    :param timeout_ms: 全局操作超时（毫秒）。
    :param screenshot_dir: 截图默认保存目录；screenshot 给出相对路径时拼接于此。
    :param ignore_https_errors: 关闭 HTTPS 证书校验（默认 False；内网/私有 CA
      环境开启后信任所有证书，含自签/中间人）。
    """

    browser_type: str = "chromium"
    headless: bool = True
    timeout_ms: int = 30000
    screenshot_dir: str | None = None
    ignore_https_errors: bool = False

    def __post_init__(self) -> None:
        if self.browser_type not in _BROWSER_TYPES:
            raise ValueError(
                f"非法浏览器类型: {self.browser_type}（应为 {', '.join(_BROWSER_TYPES)}）"
            )
        if self.timeout_ms <= 0:
            raise ValueError(f"timeout_ms 必须为正数: {self.timeout_ms}")
