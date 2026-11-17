import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { schedulesApi } from "../../api/schedules";
import { treesApi } from "../../api/trees";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { ErrorMessage } from "../../components/ErrorMessage";
import type { RunOut } from "../../types/run";
import type {
  CronPeriod,
  IntervalUnit,
  ScheduleRule,
  ScheduleRuleInput,
  ScheduleMode,
} from "../../types/schedule";
import type { TreeOut } from "../../types/tree";
import {
  INTERVAL_UNITS,
  UNIT_LABELS,
  WEEKDAYS,
  runSourceLabel,
  scheduleModeLabel,
} from "./labels";

function formatTime(value: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString("zh-CN");
}

function emptyForm(trees: TreeOut[]): ScheduleRuleInput {
  return {
    name: "",
    target_tree_id: trees[0]?.id ?? 0,
    schedule_mode: "interval",
    interval: 30,
    interval_unit: "minutes",
    cron_period: "day",
    cron_time: "09:00",
    cron_weekday: 1,
    dependencies: [],
    on_failure: "immediate",
    max_retries: 3,
    retry_interval: 60,
    on_missed: "run",
    inputs: {},
    enabled: true,
  };
}

function toInput(rule: ScheduleRule): ScheduleRuleInput {
  return {
    name: rule.name,
    target_tree_id: rule.target_tree_id,
    schedule_mode: rule.schedule_mode,
    interval: rule.interval,
    interval_unit: rule.interval_unit,
    cron_period: rule.cron_period,
    cron_time: rule.cron_time,
    cron_weekday: rule.cron_weekday,
    dependencies: rule.dependencies,
    on_failure: rule.on_failure,
    max_retries: rule.max_retries,
    retry_interval: rule.retry_interval,
    on_missed: rule.on_missed,
    inputs: rule.inputs,
    enabled: rule.enabled,
  };
}

export function ScheduleListPage() {
  const [rules, setRules] = useState<ScheduleRule[]>([]);
  const [trees, setTrees] = useState<TreeOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [editing, setEditing] = useState<ScheduleRule | null>(null);
  const [form, setForm] = useState<ScheduleRuleInput | null>(null);
  const [inputsText, setInputsText] = useState("{}");
  const [records, setRecords] = useState<ScheduleRule | null>(null);
  const [recordRuns, setRecordRuns] = useState<RunOut[]>([]);
  const [recordsView, setRecordsView] = useState<"target" | "all">("target");

  const load = useCallback(async () => {
    try {
      const [ruleList, treeList] = await Promise.all([
        schedulesApi.listSchedules(),
        treesApi.listTrees(true),
      ]);
      setRules(ruleList);
      setTrees(treeList);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载调度规则失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm(trees));
    setInputsText("{}");
    setError(null);
  };

  const openEdit = (rule: ScheduleRule) => {
    setEditing(rule);
    setForm(toInput(rule));
    setInputsText(JSON.stringify(rule.inputs ?? {}, null, 2));
    setError(null);
  };

  const closeForm = () => {
    setEditing(null);
    setForm(null);
  };

  const save = async () => {
    if (!form) return;
    let inputs: Record<string, unknown>;
    try {
      inputs = JSON.parse(inputsText || "{}") as Record<string, unknown>;
    } catch {
      setError("入参必须是合法 JSON 对象");
      return;
    }
    const payload: ScheduleRuleInput = { ...form, inputs };
    try {
      if (editing) {
        await schedulesApi.updateSchedule(editing.id, payload);
      } else {
        await schedulesApi.createSchedule(payload);
      }
      closeForm();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存调度规则失败");
    }
  };

  const remove = async (rule: ScheduleRule) => {
    if (!window.confirm(`确认删除调度规则「${rule.name}」？`)) return;
    try {
      await schedulesApi.deleteSchedule(rule.id);
      setRules((prev) => prev.filter((item) => item.id !== rule.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除调度规则失败");
    }
  };

  const toggle = async (rule: ScheduleRule) => {
    try {
      const updated = await schedulesApi.toggleSchedule(rule.id);
      setRules((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "切换调度状态失败");
    }
  };

  const runNow = async (rule: ScheduleRule) => {
    setError(null);
    try {
      const { run_id } = await schedulesApi.runScheduleNow(rule.id);
      setNotice(`已触发执行 #${run_id}`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "立即执行失败");
    }
  };

  const loadRecords = async (rule: ScheduleRule, view: "target" | "all") => {
    setRecordsView(view);
    try {
      setRecordRuns(
        await schedulesApi.listScheduleRuns(rule.id, view === "target" ? "schedule" : undefined),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载执行记录失败");
    }
  };

  const showRecords = async (rule: ScheduleRule) => {
    setRecords(rule);
    await loadRecords(rule, "target");
  };

  const closeRecords = () => {
    setRecords(null);
    setRecordRuns([]);
  };

  const dependencyOptions = useMemo(
    () => trees.filter((tree) => tree.id !== form?.target_tree_id),
    [trees, form?.target_tree_id],
  );

  return (
    <section className="page" data-testid="schedule-list-page">
      <header className="page-header">
        <h1 className="page-title">调度管理</h1>
        <Button onClick={openCreate} data-testid="new-schedule" disabled={trees.length === 0}>
          新建调度
        </Button>
      </header>
      {error ? <ErrorMessage message={error} /> : null}
      {notice ? <div className="notice" data-testid="schedule-notice">{notice}</div> : null}
      {trees.length === 0 ? (
        <p className="hint">暂无正式版行为树，请先保存行为树为正式版后再创建调度。</p>
      ) : null}

      {loading && rules.length === 0 ? (
        <div className="page-loading">加载中…</div>
      ) : rules.length === 0 ? (
        <EmptyState title="暂无调度规则" hint="点击「新建调度」自动触发行为树" />
      ) : (
        <table className="tree-table" data-testid="schedule-table">
          <thead>
            <tr>
              <th>名称</th>
              <th>目标行为树</th>
              <th>调度方式</th>
              <th>下次执行</th>
              <th>上次结果</th>
              <th>启用</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {rules.map((rule) => (
              <tr key={rule.id} data-testid={`schedule-row-${rule.id}`}>
                <td>{rule.name}</td>
                <td>{rule.target_tree_name}</td>
                <td>{scheduleModeLabel(rule)}</td>
                <td>{formatTime(rule.next_run_at)}</td>
                <td>
                  <span className={`schedule-status schedule-status-${rule.last_status ?? "idle"}`}>
                    {rule.last_status ?? "—"}
                  </span>
                  {rule.last_error ? (
                    <div className="schedule-error" title={rule.last_error}>
                      {rule.last_error}
                    </div>
                  ) : null}
                </td>
                <td>
                  <button
                    type="button"
                    className="link"
                    onClick={() => void toggle(rule)}
                    data-testid={`schedule-toggle-${rule.id}`}
                  >
                    {rule.enabled ? "已启用" : "已停用"}
                  </button>
                </td>
                <td>
                  <div className="tree-table__actions">
                    <Button
                      variant="ghost"
                      onClick={() => void runNow(rule)}
                      data-testid={`schedule-run-now-${rule.id}`}
                    >
                      立即执行
                    </Button>
                    <button
                      className="link"
                      type="button"
                      onClick={() => void showRecords(rule)}
                      data-testid={`schedule-runs-${rule.id}`}
                    >
                      执行记录
                    </button>
                    <Button
                      variant="ghost"
                      onClick={() => openEdit(rule)}
                      data-testid={`schedule-edit-${rule.id}`}
                    >
                      编辑
                    </Button>
                    <Button
                      variant="danger"
                      onClick={() => void remove(rule)}
                      data-testid={`schedule-delete-${rule.id}`}
                    >
                      删除
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {form ? (
        <div className="modal-overlay" onMouseDown={closeForm}>
          <div
            className="schedule-dialog modal-panel"
            data-testid="schedule-form"
            onMouseDown={(e) => e.stopPropagation()}
          >
          <p className="run-dialog__title">
            {editing ? `编辑调度「${editing.name}」` : "新建调度"}
          </p>
          <label className="schedule-field">
            <span>规则名称</span>
            <input
              data-testid="schedule-name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </label>
          <label className="schedule-field">
            <span>目标行为树</span>
            <select
              data-testid="schedule-tree"
              value={String(form.target_tree_id)}
              onChange={(e) =>
                setForm({ ...form, target_tree_id: Number(e.target.value), dependencies: [] })
              }
            >
              {trees.map((tree) => (
                <option key={tree.id} value={String(tree.id)}>
                  {tree.name}
                </option>
              ))}
            </select>
          </label>
          <label className="schedule-field">
            <span>调度方式</span>
            <select
              data-testid="schedule-mode"
              value={form.schedule_mode}
              onChange={(e) =>
                setForm({ ...form, schedule_mode: e.target.value as ScheduleMode })
              }
            >
              <option value="interval">间隔触发</option>
              <option value="cron">定时触发</option>
            </select>
          </label>
          {form.schedule_mode === "interval" ? (
            <div className="schedule-inline">
              <label className="schedule-field">
                <span>间隔数值</span>
                <input
                  type="number"
                  min={1}
                  data-testid="schedule-interval"
                  value={form.interval ?? 1}
                  onChange={(e) =>
                    setForm({ ...form, interval: Number(e.target.value) || 1 })
                  }
                />
              </label>
              <label className="schedule-field">
                <span>单位</span>
                <select
                  data-testid="schedule-interval-unit"
                  value={form.interval_unit ?? "minutes"}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      interval_unit: e.target.value as IntervalUnit,
                    })
                  }
                >
                  {INTERVAL_UNITS.map((unit) => (
                    <option key={unit} value={unit}>
                      {UNIT_LABELS[unit]}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          ) : (
            <div className="schedule-inline">
              <label className="schedule-field">
                <span>周期</span>
                <select
                  data-testid="schedule-cron-period"
                  value={form.cron_period ?? "day"}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      cron_period: e.target.value as CronPeriod,
                    })
                  }
                >
                  <option value="hour">每小时</option>
                  <option value="day">每天</option>
                  <option value="week">每周</option>
                </select>
              </label>
              <label className="schedule-field">
                <span>时间</span>
                <input
                  data-testid="schedule-cron-time"
                  placeholder={form.cron_period === "hour" ? ":30" : "09:00"}
                  value={form.cron_time ?? ""}
                  onChange={(e) => setForm({ ...form, cron_time: e.target.value })}
                />
              </label>
              {form.cron_period === "week" ? (
                <label className="schedule-field">
                  <span>星期</span>
                  <select
                    data-testid="schedule-cron-weekday"
                    value={String(form.cron_weekday ?? 1)}
                    onChange={(e) =>
                      setForm({ ...form, cron_weekday: Number(e.target.value) })
                    }
                  >
                    {WEEKDAYS.map((label, index) => (
                      <option key={label} value={String(index)}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
            </div>
          )}
          <div className="schedule-field">
            <span>前置依赖（全部成功后才执行目标）</span>
            <div className="schedule-deps">
              {dependencyOptions.length === 0 ? (
                <span className="muted">无可选依赖</span>
              ) : (
                dependencyOptions.map((tree) => (
                  <label key={tree.id} className="schedule-check">
                    <input
                      type="checkbox"
                      data-testid={`schedule-dep-${tree.id}`}
                      checked={form.dependencies.includes(tree.id)}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          dependencies: e.target.checked
                            ? [...form.dependencies, tree.id]
                            : form.dependencies.filter((id) => id !== tree.id),
                        })
                      }
                    />
                    {tree.name}
                  </label>
                ))
              )}
            </div>
          </div>
          <div className="schedule-inline">
            <label className="schedule-field">
              <span>失败处理</span>
              <select
                data-testid="schedule-on-failure"
                value={form.on_failure}
                onChange={(e) =>
                  setForm({
                    ...form,
                    on_failure: e.target.value as ScheduleRuleInput["on_failure"],
                  })
                }
              >
                <option value="immediate">立即重试</option>
                <option value="next_schedule">等下次调度</option>
              </select>
            </label>
            <label className="schedule-field">
              <span>最大重试次数</span>
              <input
                type="number"
                min={0}
                data-testid="schedule-max-retries"
                value={form.max_retries}
                onChange={(e) =>
                  setForm({ ...form, max_retries: Number(e.target.value) || 0 })
                }
              />
            </label>
            <label className="schedule-field">
              <span>重试间隔（秒）</span>
              <input
                type="number"
                min={1}
                data-testid="schedule-retry-interval"
                value={form.retry_interval}
                onChange={(e) =>
                  setForm({ ...form, retry_interval: Number(e.target.value) || 1 })
                }
              />
            </label>
          </div>
          <label className="schedule-field">
            <span>错过调度处理</span>
            <select
              data-testid="schedule-on-missed"
              value={form.on_missed}
              onChange={(e) =>
                setForm({
                  ...form,
                  on_missed: e.target.value as ScheduleRuleInput["on_missed"],
                })
              }
            >
              <option value="run">补跑一次</option>
              <option value="skip">跳过</option>
            </select>
          </label>
          <label className="schedule-field">
            <span>静态入参（JSON）</span>
            <textarea
              data-testid="schedule-inputs"
              rows={4}
              value={inputsText}
              onChange={(e) => setInputsText(e.target.value)}
            />
          </label>
          <label className="schedule-check">
            <input
              type="checkbox"
              data-testid="schedule-enabled"
              checked={form.enabled}
              onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
            />
            启用
          </label>
            <div className="run-dialog__actions">
              <Button variant="ghost" onClick={closeForm} data-testid="schedule-cancel">
                取消
              </Button>
              <Button onClick={() => void save()} data-testid="schedule-save">
                保存
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {records ? (
        <div className="modal-overlay" onMouseDown={closeRecords}>
          <div
            className="schedule-dialog modal-panel"
            data-testid="schedule-records"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <p className="run-dialog__title">「{records.name}」执行记录</p>
            <div className="schedule-records-tabs">
              <button
                type="button"
                className={`schedule-records-tab${recordsView === "target" ? " schedule-records-tab--active" : ""}`}
                data-testid="schedule-records-target"
                onClick={() => void loadRecords(records, "target")}
              >
                仅目标行为树
              </button>
              <button
                type="button"
                className={`schedule-records-tab${recordsView === "all" ? " schedule-records-tab--active" : ""}`}
                data-testid="schedule-records-all"
                onClick={() => void loadRecords(records, "all")}
              >
                含依赖
              </button>
            </div>
            {recordRuns.length === 0 ? (
              <p className="muted">暂无执行记录</p>
            ) : (
              <table className="tree-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>行为树</th>
                    <th>状态</th>
                    <th>来源</th>
                    <th>耗时</th>
                    <th>开始时间</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {recordRuns.map((run) => (
                    <tr key={run.id}>
                      <td>{run.id}</td>
                      <td>{run.tree_name}</td>
                      <td>{run.status}</td>
                      <td>{runSourceLabel(run.source)}</td>
                      <td>{run.duration != null ? `${run.duration}s` : "—"}</td>
                      <td>{formatTime(run.created_at)}</td>
                      <td>
                        <Link
                          to={`/runs/${run.id}`}
                          data-testid={`schedule-record-view-${run.id}`}
                        >
                          查看
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <div className="run-dialog__actions">
              <Link to="/runs">查看执行列表</Link>
              <Button variant="ghost" onClick={closeRecords}>
                关闭
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
