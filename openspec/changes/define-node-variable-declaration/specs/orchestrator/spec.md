## ADDED Requirements

### Requirement: Define 节点执行

编排器 SHALL 在执行到 `Define` 节点时**确定性创建变量**（不经 LLM）：对 `vars` 中每个 `(名, {type, value})`，求值 `value`（`Param.x` 读当前帧变量；否则按字面量），按 `type` **coerce** 后写入当前帧 `this/<名>`。全部成功后节点 SUCCESS；任一变量求值失败（如 `Param.x` 未定义）或类型 coerce 失败 → 节点 FAILURE，失败原因含变量名与错误。`Define` 无槽位、无截图。

#### Scenario: 创建变量供后续读取
- **WHEN** 执行一个 `Define` 节点声明 `{baseUrl: {type: str, value: "https://x"}}`
- **THEN** 当前帧写入 `baseUrl="https://x"`，节点 SUCCESS，后续叶子可 `Param.baseUrl` 读取

#### Scenario: 拷贝并重命名现有变量
- **WHEN** `Define` 声明 `{alias: {type: str, value: Param.user}}`，当前帧已有 `user`
- **THEN** 新建变量 `alias` 的值等于 `user`，且 `user` 不变

#### Scenario: 按类型 coerce
- **WHEN** `Define` 声明 `{n: {type: int, value: "42"}}`
- **THEN** 写入的 `n` 为整数 42

#### Scenario: value 读取未定义变量
- **WHEN** `Define` 的某 `value: Param.missing`，当前帧无 `missing`
- **THEN** 该节点 FAILURE，失败原因指出未定义变量