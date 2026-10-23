# ESP32 接入完整 CareLink UI

当前不再使用独立简化调试页。`HardwareBridgeService` 继续负责原来的 GET 通信与载荷校验；`HardwareDataService` 适配现有 `DataService`，与 MockDataService / LiveApiService 共用 `App`、Pro/Basic、详情、趋势、历史与事件页面。`HardwareApp` 只是兼容入口，渲染同一完整 UI。

## 启动与配置

已运行的 FastAPI 桥接无需重启。项目目录运行 `npm run dev:hardware`，打开 `http://127.0.0.1:5173/`，选择 Pro / Basic 后进入设备工作区。无需账号；这只是本地视角切换，不是身份认证或真实患者授权。

- 默认 `npm run dev` 仍为 mock。登录页和顶部工具栏均可选择 Mock / ESP32 / API；切换数据源清除当前 UI 会话，不会把错误替换为模拟数据。
- Vite 的 hardware 模式选择硬件默认数据源（无需分发 `.env.hardware`）。`public/hardware-bridge-config.json` 默认 deviceId=esp32-01、轮询间隔 1000ms、过期 5000ms、超时 4000ms。
- 前端 GET `/hardware-bridge/sensor-data/latest`，开发及本地预览由 Vite 代理到 `http://127.0.0.1:8000/sensor-data/latest`。`CARELINK_BRIDGE_TARGET` 可覆盖桥接目标；不发送认证凭据。
- `VITE_HARDWARE_BASE_URL` 可指定浏览器使用的同源路径或 HTTP(S) 地址。跨域方式须另行配置准确 CORS。
- 桥接源码随包放在 `hardware-bridge/`，Mac 安装与运行、ESP32 上报地址和 LAN/iPhone 步骤见 [README](README.md)。已有运行中的桥接无需替换；本轮不修改固件、不向实际桥接写入测试数据。
- 默认仅在本机开放网站预览。受控 LAN/iPhone 可按 README 手动绑定 Mac 当前 LAN 地址；手机的 localhost 指手机自身。本次未启动 LAN 服务，也未完成真实 iPhone Safari 验证。

## 字段与真实含义

| 字段 | UI 与适配 |
| --- | --- |
| object_temp_c / ambient_temp_c | 表面/环境温度 °C；要求 mlx90614_ok=true 且数值存在，不当作核心体温 |
| accel_total_g | 总加速度 g；要求 mpu6050_ok=true 且有数值 |
| accel_x_g / y_g / z_g、accel_peak_g | Pro 原始数据保留 g，未假装为 m/s²；缺失保留 null |
| received_at | 桥接接收时间，决定数据年龄；没有设备采集日期，不把 uptime_ms 当日期 |
| uptime_ms | 设备运行时长，Pro 原始数据保留毫秒 |
| alarm | 原始固件报警事件，含义尚未验证；不自动推断为运动阈值、跌倒或临床风险 |
| MAX30102 / HR / SpO₂ | 已从硬件视图移除；即使旧固件返回有效心率也不展示 |
| 跌倒分类 | 始终未验证；新鲜且 MPU6050 有效时只显示“运动已连接” |
| AI | 尚未接入；不填预测结果、模型或置信度 |

桥接只提供最新一台设备。硬件工作区因此显示一个明确的本地设备档案，不伪造患者姓名、年龄、床位或多台设备。完整多患者功能继续在 mock 与已确认的患者 API 下使用。指定 deviceId 时由传输层校验，不匹配显示错误。

## 历史、事件和连接状态

- 历史只积累当前浏览器实例真实收到的唯一 received_at，最多十分钟/1200 条，不补历史曲线。刷新页面或切换数据源后清空。
- 原始固件报警仅在新鲜记录的 alarm=true 时建立本地事件。持续 true 不重复创建；明确 false 结束该轮条件。确认只记录本地查看，不能静音固件或解除风险。最多 200 条本地事件，刷新后清空。
- 连续轮询相同 received_at 不刷新其年龄；过期、离线、无效标记或缺失数值显示 `—`。网络错误立即让当前数值不可用，保留原采样时间供追溯；自动重试恢复，不回退 mock。
- 仅 `503` 且 detail 为 `No sensor data received yet` 视为等待首次上报/桥接重启，并清空当前快照、采样和本地事件。其他 HTTP/JSON/设备错误显示失败。
- 自动轮询在请求结束后等待一个间隔，手动与自动刷新共用一个在途请求；请求超时由原传输层处理。离开页面停止后续轮询。

## 构建与验证

`npm test`、`npm run build`、`npm run build:hardware`。两个构建共用 `build/`，最后一次构建决定默认模式；`npm run preview:hardware` 提供本地硬件预览。静态生产部署还需要自己的桥接反向代理，Vite 开发代理不会随文件一起部署。

浏览器测试响应只在测试页面拦截；未写入实际桥接。当前本机桥接最后上报停在 2026-10-23 15:23（上海时间），现场截图因此显示过期。需要 ESP32 恢复上报才能看到新的真实数值。
