# CareLink API 契约草案 v2

**状态：待组员确认，不代表 FastAPI 已实现以下端点。** 本轮没有修改组员的 FastAPI 或 SQLite，也没有连接真实患者、设备或 AI。客户端实现的是此草案的通信与校验逻辑，测试使用注入的响应。

## 数据与接口文件

- `shared/schema.json`：Patient、SensorReading（兼容原 Reading 名称）、Prediction、Alert、Session、BackendAssessment。
- `shared/openapi.draft.json`：可供后端评审的 OpenAPI 3.1 草案。
- `shared/api-examples/`：完整响应示例，全部虚构，来源均标记 `mock`；不会作为真实 API 失败的备用数据。
- `src/data/`：Web TypeScript 模型、运行时校验、MockDataService / LiveApiService。
- `ios/CareLink/Models.swift`、`LiveApiService.swift`：相同字段含义的 Codable 模型与适配器。

## 待确认接口

| 方法 | 草案路径 | 返回 | 空数据及错误 |
|---|---|---|---|
| GET | `/api/session` | Session | 401 未认证；不是本地角色选择 |
| GET | `/api/patients` | Patient[] | `[]` 或 204 代表空列表 |
| GET | `/api/patients/{id}` | Patient | 404 表示不存在/不可见，客户端显示空详情 |
| GET | `/api/patients/{id}/readings?minutes=10` | SensorReading[] | `[]` 或 204；须完整覆盖可用窗口，不能静默截断 |
| GET | `/api/patients/{id}/predictions` | Prediction[] | `[]` 或 204；未产出不得返回默认预测 |
| GET | `/api/alerts` | Alert[] | `[]` 或 204；仅当前角色可见记录 |
| POST | `/api/alerts/{id}/acknowledgement` | 已更新的 Alert | 请求体 `{}`；200 必须返回正确 ID 和确认时间；不能用 204 假定确认成功 |

列表响应当前按裸数组解析，不支持未经约定的 `{items: ...}` 包裹。若后端选择分页/包裹格式，只在服务层映射，不改页面。所有非成功 HTTP、无效 JSON、格式不符、超时/网络失败均显示错误，不回退成模拟数据。确认失败保持原状态。重复确认建议幂等；事件已结束或版本冲突可返回 409，UI 重新加载后再处理。

## 字段含义

`Patient` 沿用原工程字段：`id, name, age, sex, bed, history, color, admittedAt, allergies, reading`。`reading` 为最新返回快照或 null。`age` 为整数。没有病史或床位信息时可用空字符串；请与团队确认哪些是必填业务字段。Basic 的响应必须在服务端限制患者范围，并对病史/原始数据等无权字段做脱敏或返回空值。前端过滤不是后端授权的替代。

`SensorReading`：

- `patientId, deviceId, measuredAt, receivedAt, connected, metrics, fall, raw, ai, source`。
- `measuredAt` 是采集时间；`receivedAt` 是后端接收时间，不能互相替代。时间均为带时区 ISO 8601；建议后端 UTC 存储。两端以设备本地时区显示。
- `metrics.hr / spo2 / temp` 各有 `value: number | null`、`quality: good | poor | unavailable | unknown`，可选 `available: boolean`。显式 false、非 good、null、离线或过期均不作为有效当前数值；不会填 0 或沿用上一有效值。温度为表面/物体温度，尚未校准为核心体温。
- `fall.active` 表示仍需关注的设备事件，不能因断线或“已确认”自动变为 false；`fall.quality` 为监测质量，`eventAt` 可空。
- `raw` 可为 null（未提供或无权限）；内含 `accel_m_s2`、`gyro_deg_s`、`ir`、`red`、`object_temperature_c`、`ambient_temperature_c`，缺失量可空。两个向量可为 null。
- `source: mock | device | backend` 是来源，不由当前 UI 模式猜测。API 也可返回明确标记的 mock 联调记录；界面不能把它标为真实硬件测量。
- `assessment` 可空；存在时必须为 `origin: backend`，含 `level, reasons, assessedAt, ruleSetId`。真实模式优先展示它；未提供则显示待确认，已上报跌倒事件单独保留警报。**不会用课堂数值阈值给真实读数推断分级。** 过期/缺失信息不能显示为完整绿色健康状态，已有红/黄后端判断可保留并标注时效问题。

`Prediction`：

- `state: not_connected | pending | available | failed | unavailable`；独立于测量显示。
- `id, patientId, predictedAt, inputsMeasuredAt, model, modelVersion, result, confidence, confidenceMeaning, source`。新元数据兼容旧内嵌 ai，缺失时不合成。
- 独立预测接口的每项必须能归属请求的 patientId。`result` 可为任意 JSON 或 null，不假定某种算法输出。
- `confidence` 只保留后端实际数值或 null，**不自动变成百分比，不假定 0–1，不填默认值**。0 是合法的实际返回值；含义/标定/单位由后端确认，并通过 confidenceMeaning 说明。无实际输出不生成结论、置信度或时间。

`Alert`：

- `id, patientId, type, severity, occurredAt, updatedAt, summary, source`。
- `status: new | acknowledged | resolved`；`conditionActive` 独立于处理状态。
- `acknowledgedAt, acknowledgedBy, resolvedAt` 可空。acknowledged 必须有确认时间；resolved 必须有结束时间且 conditionActive 为 false。
- 确认仅记录查看，不能代表风险解除、不能改变测量或分级。真实告警 ID、发生时间及状态由后端返回，不能在客户端生成。模拟模式的 ID 和发生时间仅表示本次本地演示首次观察，关闭页面/App 会丢失。

## 配置与认证边界

`shared/carelink-config.json` 是两端共用的配置源，默认 `mode: mock`。Web 生成到 `public/carelink-config.json`，构建后可修改部署文件 `build/carelink-config.json`；SwiftUI 从 bundle 读取同名 JSON，修改后重新构建安装。Web 支持 `.env.example` 所列的构建覆盖，无需更改页面。

启用真实模式前：确定 baseUrl/端点，改 `mode: live`，显式设置 `apiConfirmed: true`。iPhone 必须使用可达的绝对 HTTP(S) 地址；Web 可用同源代理。该开关只防止误启用草案，不是身份或安全授权。确认后也不等于已联调成功。

目前 Web 使用 `credentials: include`，iOS 使用 URLSession 的已认证会话；没有自行发明登录 POST，也不把演示密码发到后端。正式认证端点、Cookie/Token、iOS 安全凭据保存、CSRF、跨域 CORS、证书与退出流程均须组员确定后接入。本轮没有保存真实凭据或硬编码密钥。不要为了联调关闭全局 iOS 传输安全；本地 HTTP 的必要例外应等地址和开发方式确定后限定处理。

## 后端组需确认的清单

1. FastAPI 的实际 OpenAPI、可达开发地址、版本路径、认证/退出方式及各角色权限；Basic 关联一位还是多位患者。
2. SQLite 中患者、设备关联和时间字段的真实定义，能否返回 measuredAt 与 receivedAt；设备心跳与 connected 判定方式。
3. 列表/详情格式、空值策略、数据质量来源、传感器可用标志和测温校准方式。
4. 最近十分钟时间边界、排序、分页与采样聚合；客户端目前不补齐缺失记录。确认刷新频率；API 模式目前手动刷新。
5. AI 输出样例、模型/版本、输入采样时间、预测时间及 confidence 的真实含义。
6. 后端分级规则/版本、显示有效期，以及跌倒事件的产生、确认、结束和并发更新机制。现有 30 秒为演示显示有效期，真实部署须确认。
7. 告警类型/严重度枚举、幂等确认、冲突返回、历史保留及服务端审计。

在这些信息确定前，默认继续 mock。无需更改 React 或 SwiftUI 页面来切换服务；若 JSON 有差异，改适配与契约测试。
