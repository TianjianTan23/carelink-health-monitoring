# CareLink 本地统一 API 契约

本契约对应本分支 `backend/app.py` 及 `src/data/LiveApiService.ts`，已用隔离HTTPS及Android模拟器执行。真实ESP32/手机仍需现场验收。Web与Android请求同一个网关origin，读取同一份`CARELINK_DATABASE_PATH`中的记录；不另建移动端数据源。

|方法/路径|实际行为|
|---|---|
|GET `/health`|进程健康，不等于传感器已连接|
|POST `/sensor-data`|HTTPS + 每设备API key + HMAC + ±60s时间窗 + 原子nonce；成功后才存readings/alerts|
|POST `/api/login`|`{username,password}`；Argon2id/兼容迁移；返回Session身份，Set-Cookie设置opaque Session|
|GET `/api/session`|验证服务器Session、过期/撤销/账号状态，返回身份和患者范围|
|POST `/api/session/rotate`|`{}`；替换Cookie并立即使旧Token无效，不延长绝对期限|
|POST `/api/logout`|`{}`；撤销Session并清Cookie|
|GET `/api/gateway`|认证后返回网关模式、接收路径、服务器患者映射和自动模拟器标记，不返回秘密或数据库路径|
|GET `/api/patients`|授权患者列表，reading为最新保存记录或null|
|GET `/api/patients/{id}`|授权范围内患者详情|
|GET `/api/patients/{id}/readings?minutes=1440`|指定窗口历史；当前最多2000条（不是完整高频24小时导出接口）|
|GET `/api/patients/{id}/predictions`|最近100条对应的模型结果，无效输入不伪造正常分类|
|GET `/api/alerts`|授权患者告警；可产生连接状态告警，因此也受写入gate保护|
|POST `/api/alerts/{id}/acknowledgement`|`{}`；仅护士且有患者权限；确认不清除设备跌倒状态|
|POST `/api/classify`|受认证的既有分类接口|

## 登录和传输

- Cookie `carelink_session` 为Secure、HttpOnly、SameSite=Lax、path=/。服务器保存Token的SHA-256摘要、绝对到期和撤销记录，当前8小时上限。
- 所有`/api`请求必须HTTPS、受信任同源Host/Origin；变更请求为JSON并带`X-CareLink-CSRF: 1`。不开放任意跨域CORS。
- 浏览器须访问网关自己的HTTPS页面；不要从HTTP Vite页面跨域登录。Android原生桥发送对应网关Origin，Cookie不交给JS。
- 登录限速与角色/患者授权在服务器执行，客户端选择角色或提交patient_id不能授予权限。
- Android使用现有Keystore/AES-GCM存储与独立OkHttp NO_COOKIES请求。证书链、有效期和主机身份都校验，禁止TLS/HTTP降级和跨origin重定向。

## 设备协议和数据来源

完整固件签名实现在`firmware/elder_sensors/device_signing.h`，服务器在`backend/device_auth.py`。签名7行、LF分隔、无末尾LF：

```text
CARELINK-HMAC-SHA256-V1
POST
/sensor-data
<device-id>
<Unix-seconds>
<32-lowercase-hex-nonce>
<SHA256-of-exact-UTF8-body>
```

设备凭据与签名只在认证头，不能放入raw_json或日志。nonce提交之后才发内部准入receipt；读数/告警写入消费receipt并持有同一gate租约。重放409、坏认证/过期401、缺损账本503，不创建空账本修复。nonce与读数是两个事务，保证最多一次准入，不承诺跨库exactly-once。

保持原服务器映射：`PATIENT_ID=ttj`，固件`patient_id=patient-01`仅作为原始字段留存；不直接信任客户端患者字段授权，不迁移历史记录。

`SensorReading`的来源独立于UI模式：`source=mock|device|backend`。API环境配置为simulation或body显式标注simulation时，不能返回device。硬件网关启动器无自动模拟器。API模式网络失败/401/数据过期不能转为mock。

- 必需核心指标仍为心率、物体/表面温度、跌倒。质量标记false或心率held时不当作新有效读数；null不转0。
- 可选血氧接收`spo2_percent`、`spo2.percent`、`max30102.spo2`，结合`spo2_ok`/对应ok；没有上报时保持缺失，UI显示未提供。有效值显示，坏值不当作正常；沿用项目95/90的课程规则生成独立血氧告警，不改变三输入模型，也不是临床标准。
- 原模拟脉搏ADC不能推算SpO₂。现有固件并未实现双光路血氧测量，不能声称已测得血氧。
- `measuredAt`当前取保存时的服务器接收时刻；`receivedAt`同值。固件uptime不是UTC采样时间；不能由它们推断真实采样延迟。重复查询不更新这些时间。
- `connected`是最近接收状态；UI还按显示有效期检查过期。模型域为心率/温度/跌倒；无效输入的label/confidence为null，表面温度须校准后才可作体温解释。

## 当前限制

历史窗口存在条数上限；患者映射仍为既有单患者方案。实际硬件/真实手机、旧网关历史账本兼容性没有在本轮验证。旧v1 ledger不能被当前运行代码自动转换；不能复制旧密钥配空账本冒充恢复。
