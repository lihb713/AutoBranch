## ADDED Requirements

### Requirement: 浏览器证书豁免配置

系统 SHALL 支持通过配置 `ignore_https_errors` 关闭浏览器会话的 HTTPS 证书校验（默认关闭）。开启后，会话内访问证书不受信任的站点（自签名 / 私有 CA / 中间人代理）SHALL 正常打开，不报证书错误；用于内网 / 私有 CA 环境。关闭时保持默认证书校验行为不变。

#### Scenario: 默认校验证书

- **WHEN** 未开启 `ignore_https_errors`，访问证书不受信任的站点
- **THEN** 打开页面失败并报告证书类错误

#### Scenario: 开启后信任全部证书

- **WHEN** 开启 `ignore_https_errors`，访问自签名 / 私有 CA 站点
- **THEN** 页面正常打开，不报证书校验错误