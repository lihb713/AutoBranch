"""叶子执行终止条件检测（契约 §5.7.2.1/§9.7，design D2）。

- ``LeafTermination``：终止信号异常（携带触发条件名，供 ``LeafTrace.terminator``）。
- ``NoProgressTracker``：连续无进展检测——对连续多轮的调用/结果指纹比较，
  结果未变或重复相同调用达到阈值即判定卡住（契约 §9.7 ② 连续 2 轮）。

引擎只设置与检测终止条件、不干预 LLM 处理过程（契约 §5.7.2.1），检测点
集中在 agent 驱动循环内。
"""

from __future__ import annotations

__all__ = ["LeafTermination", "NoProgressTracker"]


class LeafTermination(Exception):
    """叶子执行终止信号：携带触发的终止条件名。

    :param terminator: 触发条件（round_limit / no_progress / timeout）。
    """

    def __init__(self, terminator: str) -> None:
        super().__init__(f"叶子执行终止: {terminator}")
        self.terminator = terminator


class NoProgressTracker:
    """连续无进展检测。

    :param threshold: 连续相同指纹轮数阈值（契约 §9.7 默认 2 轮；首轮不计数）。
    """

    def __init__(self, threshold: int = 2) -> None:
        self.threshold = max(threshold, 1)
        self._streak = 0
        self._prev: str | None = None

    def record(self, fingerprint: str) -> bool:
        """记录一轮指纹；返回 True 表示已连续 ``threshold`` 轮无进展。"""
        had_prev = self._prev is not None
        if had_prev and fingerprint == self._prev:
            self._streak += 1
        else:
            self._streak = 1
        self._prev = fingerprint
        return had_prev and self._streak >= self.threshold
