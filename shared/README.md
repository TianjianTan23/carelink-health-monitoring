# 两端共享契约与资源

- `demo-patients.json`、`demo-sessions.json`、`demo-rules.json`：保留原演示患者、角色范围和课堂规则；只用于 mock。
- `triage-vectors.json`：既有 Web/Swift 演示逻辑黄金向量，保留回归。
- `schema.json`：v2 草案，兼容原 Reading，新增 SensorReading 别名、Prediction、Alert、BackendAssessment、可用标志与 nullable raw。
- `api-examples/`：两端共同解码测试的虚构响应；`source` 保持 mock，没有真实硬件或模型输出。
- `openapi.draft.json`：拟议端点，非已部署 FastAPI 的描述；以 API_CONTRACT.md 列表向组员确认。
- `carelink-config.json`：默认 mock，apiConfirmed=false。生成到 Web public；iOS 直接引用同一资源。
- `design-tokens.json`：共享品牌浅色、深色提案、间距和圆角。Web 与 iOS 保留各自平台字体、布局与交互。

运行 `npm run generate:shared` 同步原 JS 资源和 Web 配置。修改设计令牌后运行 `npm run generate:tokens`（Python 3），生成 CSS 与 iOS 颜色资产；无需把网页布局移植到原生 App。

服务端必须执行角色与患者权限。Basic 仅能收到关联患者及必要字段；前端过滤不构成安全边界。Mock 状态与确认存在各客户端内存，尚不跨设备同步；接入共同 API 后才能共享真实状态。
