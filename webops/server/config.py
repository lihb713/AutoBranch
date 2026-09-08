"""M9b 服务端配置（数据库路径 / 报告根目录）。

配置来源：代码内默认值 + 环境变量覆盖（``WEBOPS_DB_PATH`` /
``WEBOPS_REPORT_DIR``）。开发期单用户本地服务，不引入配置文件。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from webops.config import WebOpsConfig

#: 项目根（服务通常从项目根启动）。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
#: 默认数据库文件路径。
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "webops.db"
#: 默认报告/截图持久化根目录。
DEFAULT_REPORT_ROOT = PROJECT_ROOT / "data" / "reports"


@dataclass(frozen=True)
class ServerConfig:
    """M9b 服务端配置。

    :param db_path: SQLite 数据库文件路径。
    :param report_root: 报告/截图文件持久化根目录（库中只存其相对路径）。
    """

    db_path: Path
    report_root: Path

    @classmethod
    def load(cls) -> ServerConfig:
        db_path = Path(os.environ.get("WEBOPS_DB_PATH", DEFAULT_DB_PATH))
        report_root = Path(os.environ.get("WEBOPS_REPORT_DIR", DEFAULT_REPORT_ROOT))
        return cls(db_path=db_path.resolve(), report_root=report_root.resolve())

    def webops_config(self) -> WebOpsConfig:
        """引擎统一配置（api_key 由环境变量 ``WEB_OPS_LLM_API_KEY`` 注入，契约 §6.3）。"""
        return WebOpsConfig.load()


__all__ = ["ServerConfig", "DEFAULT_DB_PATH", "DEFAULT_REPORT_ROOT"]
