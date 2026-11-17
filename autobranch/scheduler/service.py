"""M10 调度规则管理服务（校验 / CRUD / 依赖环检测）。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from autobranch.scheduler.deps import detect_cycle
from autobranch.scheduler.models import ScheduleRule
from autobranch.scheduler.schemas import ScheduleRuleCreate, ScheduleRuleOut
from autobranch.scheduler.timecalc import calculate_next_run, normalize_cron_time
from autobranch.server.errors import AppError
from autobranch.server.models import Tree
from autobranch.server.services.runs import validate_run_inputs


class ScheduleService:
    """调度规则 CRUD；执行由 :class:`SchedulerEngine` 负责。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------- 查询

    def list_rules(self) -> list[ScheduleRuleOut]:
        rules = self.db.scalars(select(ScheduleRule).order_by(ScheduleRule.id)).all()
        return [self._out(rule) for rule in rules]

    def get_rule(self, rule_id: int) -> ScheduleRule:
        rule = self.db.get(ScheduleRule, rule_id)
        if rule is None:
            raise AppError(404, f"调度规则不存在 (id={rule_id})")
        return rule

    def get_out(self, rule_id: int) -> ScheduleRuleOut:
        return self._out(self.get_rule(rule_id))

    # ------------------------------------------------------------- 变更

    def create(self, payload: ScheduleRuleCreate) -> ScheduleRuleOut:
        values = self._validated_values(payload)
        rule = ScheduleRule(**values)
        self.db.add(rule)
        self.db.commit()
        self.db.refresh(rule)
        return self._out(rule)

    def update(self, rule_id: int, payload: ScheduleRuleCreate) -> ScheduleRuleOut:
        rule = self.get_rule(rule_id)
        values = self._validated_values(payload, rule_id=rule_id)
        for name, value in values.items():
            setattr(rule, name, value)
        self.db.commit()
        self.db.refresh(rule)
        return self._out(rule)

    def delete(self, rule_id: int) -> None:
        rule = self.get_rule(rule_id)
        self.db.delete(rule)
        self.db.commit()

    def toggle(self, rule_id: int) -> ScheduleRuleOut:
        rule = self.get_rule(rule_id)
        rule.enabled = not rule.enabled
        self.db.commit()
        self.db.refresh(rule)
        return self._out(rule)

    # ------------------------------------------------------------- 内部

    def _validated_values(
        self, payload: ScheduleRuleCreate, *, rule_id: int | None = None
    ) -> dict:
        tree = self.db.get(Tree, payload.target_tree_id)
        if tree is None:
            raise AppError(404, f"目标行为树不存在 (id={payload.target_tree_id})")
        if tree.status != "published":
            raise AppError(409, "目标行为树处于草稿状态，请先保存为正式版后再创建调度")

        dependencies = list(dict.fromkeys(int(dep) for dep in payload.dependencies))
        if payload.target_tree_id in dependencies:
            raise AppError(422, "目标行为树不能依赖自身")
        for dep in dependencies:
            if self.db.get(Tree, dep) is None:
                raise AppError(404, f"前置依赖行为树不存在 (id={dep})")

        existing = self.db.scalars(select(ScheduleRule)).all()
        if detect_cycle(
            payload.target_tree_id,
            dependencies,
            existing,
            exclude_rule_id=rule_id,
        ):
            raise AppError(422, "调度依赖存在循环，请检查前置依赖配置")

        try:
            validate_run_inputs(tree.content, payload.inputs or {})
        except AppError:
            raise

        values: dict = {
            "name": payload.name,
            "target_tree_id": payload.target_tree_id,
            "schedule_mode": payload.schedule_mode,
            "dependencies": dependencies,
            "on_failure": payload.on_failure,
            "max_retries": payload.max_retries,
            "retry_interval": payload.retry_interval,
            "on_missed": payload.on_missed,
            "inputs": dict(payload.inputs or {}),
            "enabled": payload.enabled,
            "interval": None,
            "interval_unit": None,
            "cron_period": None,
            "cron_time": None,
            "cron_weekday": None,
        }

        if payload.schedule_mode == "interval":
            if payload.interval is None or payload.interval_unit is None:
                raise AppError(422, "间隔调度必须填写间隔数值与单位")
            values["interval"] = payload.interval
            values["interval_unit"] = payload.interval_unit
        else:
            if payload.cron_period is None or not (payload.cron_time or "").strip():
                raise AppError(422, "定时调度必须填写定时周期与触发时间")
            if payload.cron_period == "week" and payload.cron_weekday is None:
                raise AppError(422, "每周调度必须选择星期几")
            try:
                values["cron_time"] = normalize_cron_time(
                    payload.cron_period, payload.cron_time or ""
                )
            except ValueError as exc:
                raise AppError(422, str(exc)) from None
            values["cron_period"] = payload.cron_period
            values["cron_weekday"] = (
                payload.cron_weekday if payload.cron_period == "week" else None
            )

        return values

    def _out(self, rule: ScheduleRule) -> ScheduleRuleOut:
        tree = self.db.get(Tree, rule.target_tree_id)
        next_run_at = (
            calculate_next_run(rule, rule.last_run_at)
            if rule.last_run_at is not None
            else None
        )
        return ScheduleRuleOut(
            id=rule.id,
            name=rule.name,
            target_tree_id=rule.target_tree_id,
            target_tree_name=tree.name if tree is not None else "",
            schedule_mode=rule.schedule_mode,
            interval=rule.interval,
            interval_unit=rule.interval_unit,
            cron_period=rule.cron_period,
            cron_time=rule.cron_time,
            cron_weekday=rule.cron_weekday,
            dependencies=list(rule.dependencies or []),
            on_failure=rule.on_failure,
            max_retries=rule.max_retries,
            retry_interval=rule.retry_interval,
            on_missed=rule.on_missed,
            inputs=dict(rule.inputs or {}),
            last_run_at=rule.last_run_at,
            last_run_id=rule.last_run_id,
            last_status=rule.last_status,
            last_error=rule.last_error,
            next_run_at=next_run_at,
            enabled=rule.enabled,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
        )


__all__ = ["ScheduleService"]
