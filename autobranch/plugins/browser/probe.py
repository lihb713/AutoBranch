"""引擎 DOM 探针（M5）：在 M1 ``DomProbe`` 基础上记录最近一次爬取快照。

``EngineProbe`` 是 M5 注入给 M4 ``semantic_graph`` 的爬取探针：M4 每次生成
都会调用 ``crawl``，本类把该次快照缓存到 ``last_snapshot``，供引擎在生成后
用同源快照刷新 ref 映射表（选择器推导，契约 §7.8）。无额外浏览器能力，
完全委托 M1 实现。
"""

from __future__ import annotations

from autobranch.plugins.browser.driver import DomProbe, DomSnapshot, LODSpec, PageRef


class EngineProbe(DomProbe):
    """M1 ``DomProbe`` 的引擎包装：缓存最近一次爬取快照。"""

    def __init__(self, driver) -> None:
        super().__init__(driver)
        self.last_snapshot: DomSnapshot | None = None

    def crawl(self, page_ref: PageRef, lod: LODSpec | None = None) -> DomSnapshot:
        self.last_snapshot = super().crawl(page_ref, lod)
        return self.last_snapshot


__all__ = ["EngineProbe"]
