# 参数语法重构设计：Param./NewParam. 统一读写记号

> 日期：2026-09-18
> 状态：已批准（2026-09-18，用户确认四点：语义英文映射迁移、旧语法彻底废弃、标识符规则、args 禁止 NewParam）

## 1. 背景与动机

当前参数读写语法不统一、不自然：

- 叶子自然语言描述用结构化 `[[get:变量]]` / `[[set:类型:变量]]`，与自然语言混排，观感割裂；
- ref / FunctionCall 的传参又用**裸变量名**（`args: [名...]`），运行时"命中变量才是变量、否则按字面量"存在二义性；
- 中文变量名（`苹果金额`、`水果合计`）在自然语言与参数语境中可读性差。

目标：**统一读写记号、贴近自然语言、保持引擎确定性**。

## 2. 新语法规范

### 2.1 记号

| 记号 | 语义 | 引擎行为 |
|---|---|---|
| `Param.<name>` | **读取/引用**变量 | 叶子执行前**确定性替换**为真实值；未声明即读 → 静态校验错误 |
| `NewParam.<name>[:<type>]` | **新建/保存**变量 | 引擎确定性解析为可写目标（+类型），驱动 coerce；LLM 把工具输出路由到该变量 |
| `` `Param` `` / `` `NewParam` `` | **转义**：纯文本 | 去掉反引号、内部不做任何替换 |

### 2.2 标识符与边界

- `<name>` = 合法标识符 `[A-Za-z_][A-Za-z0-9_]*`（ASCII，**不得以数字开头**，数字开头 → 校验错误）。
- **边界**：`Param.`/`NewParam.` 后连续消费 `[A-Za-z0-9_]+`，遇首个非 `[A-Za-z0-9_]` 字符（含中文、标点、空格）即结束。示例：`保存www.google.com参数到Param.base_url中` → 变量 `base_url`（「中」为边界）。中文变量名因首字符即边界而解析失败，天然失效并报错。
- `<type>` ∈ `{str, int, float, bool, page_ref, object}`；可省略，缺省按动作输出推断（`infer_type`）。类型标注驱动 `coerce`（`page_ref` 只能由 open() 产生）。
- 反引号 `\`` 为保留字符：未闭合 → 校验错误（`syntax.unclosed_backtick`）。

### 2.3 适用范围（全局统一）

| 场景 | 写法 | 说明 |
|---|---|---|
| Action 描述 | `访问 Param.base_url 网站`；`将 https://google.com 保存为 NewParam.base_url` | 读=Param，建=NewParam |
| Condition（expect/if/when/until） | `状态是 Param.status` | 读=Param |
| ref 入参 args | `Param.x`（引用本树变量）或字面量 | **禁止 NewParam**（传参不建变量） |
| ref 出参 returns | `NewParam.接收名:int` | 接收名=本树新建变量 |
| FunctionCall 入参 args | `Param.x` 或字面量 | 禁止 NewParam |
| FunctionCall 返回值 returns | `NewParam.接收名:int` | 接收名=本树新建变量 |
| 文档接口 inputs/outputs | 裸名（`base_url` / `- param2`） | 声明级，ASCII 标识符 |

### 2.4 旧语法废弃

- `[[get:...]]`、`[[set:...]]`、用户可见的 `this/名` 前缀**彻底废弃**：解析到 → 校验错误（`syntax.deprecated`），相关正则与兼容代码全部清理。
- 引擎**内部帧路径** `this/<name>` 保留为纯内部实现（帧存储/读写的内部表示），不视为用户语法；用户侧一律裸名。
- 读替换后描述中不得残留 `Param.`（除转义文本）。

## 3. 引擎改造

| 文件 | 改动 |
|---|---|
| `autobranch/parser/expand.py` | 新正则：`Param\.([A-Za-z_][A-Za-z0-9_]*)`、`NewParam\.([A-Za-z_][A-Za-z0-9_]*)(?::(str\|int\|float\|bool\|page_ref\|object))?`；删除旧 get/set 正则与 `this/` 兼容；`_iter_set_decls`/`_iter_get_paths`/`_iter_schema_paths`/`_check_get_defined` 适配；新增旧语法检测 → `syntax.deprecated`；未闭合反引号 → `syntax.unclosed_backtick` |
| `autobranch/parser/models.py` | `set_targets`/`set_decls` 语义不变（裸名），docstring 更新 |
| `autobranch/leaf_agent/executor.py` | `_resolve_get_refs` 改替换 `Param.x`；set 声明解析 `NewParam.x[:type]`；产出型工具目标校验基于声明集 |
| `autobranch/leaf_agent/prompts.py` | 提示文案改 `Param.`/`NewParam.` 教学；`PROMPT_VERSION` 递增（→1.5） |
| `autobranch/orchestrator/traverser.py` | `_eval_arg`：`Param.x`=读本树变量、其余=字面量（消除裸名二义性）；returns 从 `NewParam.x:int` 提取接收名+类型 |
| `autobranch/schema/space.py` | 写路径统一裸名（内部 `this/` 前缀仅内部保留或直接去前缀） |
| 其它引用旧正则/旧语法的模块 | 同步清理 |

## 4. 前端改造

| 文件 | 改动 |
|---|---|
| `src/features/tree-editor/validation.ts` | get/set 正则替换为 Param/NewParam；新增未闭合反引号、非法标识符、数字开头校验；args 变量引用改 `Param.` 前缀识别（字面量类型推断保留） |
| `src/components/HighlightedField.tsx`（新） | `TextField` 高亮变体：下层渲染高亮 span 叠加层 + 上层透明原生输入（保光标/IME）；`Param.x` 蓝色、`NewParam.x:int` 整体绿色；支持单行与多行 |
| `src/features/tree-editor/PropertyPanel.tsx` 等 | 将描述字段（Action.description、Step.expect、IfThenElse.if、LoopUntil.until、Retry 无、Branch when）与 ref/FunctionCall 的 args/returns 输入框替换为高亮字段 |

## 5. 存量迁移

### 5.1 DB 迁移脚本（`scripts/migrate_param_syntax.py`）

- 遍历 `data/autobranch.db` 全部行为树；解析每个树文档；
- 按**映射表**替换中文变量名（覆盖 inputs/outputs 键、`NewParam` 目标、`Param` 引用、returns 接收名、args 变量引用）；
- 重写旧语法 → 新语法（`[[get:x]]`→`Param.x`、`[[set:t:x]]`→`NewParam.x:t`、`this/名`→`Param.名`；args 裸名命中声明变量 → `Param.x`，否则按字面量保留）；
- 先 **dry-run**（输出每树 diff，不改库），确认后 `--apply` 写回；幂等可重跑。

### 5.2 映射表（已盘点）

| 中文 | 语义英文 | 来源树 |
|---|---|---|
| 苹果金额 | `appleAmount` | 表格求和演示(88) |
| 香蕉金额 | `bananaAmount` | 表格求和演示(88) |
| 水果合计 | `fruitTotal` | 表格求和演示(88) |
| 结果 | `result` | smoke(90)、e2eFC渲染(91) |
| 入参1 | `input1` | test333(89) |

### 5.3 代码/测试/文档 fixtures 全量重写

- 后端测试：`tests/parser/`、`tests/leaf_agent/test_get_replace.py`、`tests/orchestrator/test_ref_call.py`、`tests/test_parser_onedoc_integration.py` 等含旧语法用例 → 新语法；
- 前端测试：`validation`、编辑器相关测试中的 `[[set/get]]` → 新语法；
- E2E：`autobranch/frontend/e2e/function-call.spec.ts` 等（`苹果金额`/`香蕉金额`/`水果合计`/`结果`）→ 映射名 + 新语法；
- 文档示例：`docs/contract.md`、`docs/specs/M*.md`、`README.md`、`openspec/specs/*` 中旧语法示例 → 新语法（含 §5.3 变量、§5.7.3 ref、§13 FunctionCall 等章节）。

## 6. 测试与验证

1. 单元：新语法解析/作用域校验/执行替换用例；旧语法报错用例（`syntax.deprecated`）；未闭合反引号；非法标识符；
2. 集成：迁移后的真实树运行成功（用户验证目标：表格求和演示、test333 等）；
3. 前端：高亮组件测试（`Param.x`/`NewParam.x:int` 高亮、转义不触发）、validation 新用例；
4. E2E：更新后的 `function-call.spec.ts`、`workflow.spec.ts`、`ref-call.spec.ts` 跑通；
5. 全量：后端 `pytest` + `ruff`、前端 `typecheck/lint/test`、`npm run build`。

## 7. 文件影响清单（预估）

- 后端：`expand.py`、`models.py`、`executor.py`、`prompts.py`、`traverser.py`、`space.py`、`path.py`（如需）、相关测试若干
- 前端：`validation.ts`、`HighlightedField.tsx`（新）、`PropertyPanel.tsx`、`TreeCanvas/NodeCard`（如需）、相关测试
- 迁移：`scripts/migrate_param_syntax.py`（新）
- 文档：`docs/contract.md`、`docs/specs/M1/M2/M4/M5/M9`、`README.md`、`openspec/specs/*`
- E2E：`function-call.spec.ts`、`workflow.spec.ts`、`ref-call.spec.ts`