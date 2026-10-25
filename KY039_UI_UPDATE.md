# CareLink：移除血氧，准备 KY-039 心率 · 2026-10-26

本次基于原仓库 experiment/live-sensor-ui，在干净工作区开始；初始 HEAD 为 8aeb29c。原完整产品页面保留。实施阶段未提交或推送；随后用户明确授权将此版本更新到同一实验分支并生成源码 ZIP，发布记录见压缩包的 RELEASE_INFO.json。未切换或合并 main。

## 完成的产品调整

- Web Pro/Basic、SwiftUI、旧版 Web 入口和离线手机评审伴随预览：移除血氧卡片、患者列表指标、趋势选项、历史列、LCD O2 字段、专属演示规则和翻译。
- 产品 Mock 不再生成血氧值。严重异常场景改为心率演示，保留原红/黄/绿和未知状态分布。
- 心率继续独立展示，单位 BPM，并显示心率采样更新时间、连接信息、信号质量/等待/未验证/失败/过期状态。卡片、历史和趋势共用有效性规则，至少两条有效采样才绘制趋势。
- MPU6050 运动与三轴/合加速度、MLX90614 表面与环境温度、LCD 显示概念、告警确认、事件时间线和 AI 不可用区域均保留。原始固件 alarm 仍不被当作已验证跌倒。
- 保留中英双语、深浅色、键盘与无障碍标签、桌面侧栏及手机底部导航。

## 检查到的硬件事实

本地仓库没有 CareLink Arduino 固件源文件。本地 FastAPI main.py 仅保存收到的 JSON 并提供最新信封，没有滤波或 BPM 算法。Arduino 目录中未发现项目 KY-039 算法实现；已有旧上报含 heart_rate_bpm、heart_rate_ok 和 heart_signal_raw，但不足以确认 KY-039 来源及心率算法质量。因此本轮不声称真实 KY-039 测量已完成，也未修改固件、刷机或改动桥接。

## KY-039 数值何时可显示

public/hardware-bridge-config.json 新增 **heartRateContractConfirmed=false**（默认）。仅在组员验证固件滤波、峰值/周期计算与数据契约后才改为 true。除此以外，每条设备上报还必须同时具备以下字段；它们是本轮准备的建议扩展，不能假设现有固件已经发送：

| 字段 | 要求 |
| --- | --- |
| heart_rate_sensor | 精确为 KY-039 |
| heart_rate_algorithm_validated | true，代表组员已完成基本算法验证，不代表临床验证 |
| heart_rate_connected | true，单纯连接为 true 不能使 BPM 有效 |
| heart_rate_ok | true |
| heart_rate_quality | good |
| heart_rate_bpm | 经过计算的有限正数，不从 ADC 原始信号推算，也不填默认值 |
| heart_rate_measured_at | 实际心率采样的 ISO 8601 时间，不能用每次 HTTP 成功时间替代 |

心率采样、桥接信封都须在配置的时效内（默认 5 秒，允许最多 5 秒未来时钟偏差）。缺失/坏质量/断开/未经验证/过期都不进入数值、历史曲线或有效状态。原始 heart_signal_raw 仅以 rawSignalAdc 保留在 Pro 原始数据，并明确不是 BPM。没有原始信号也没有心率字段时等待传感器数据；已有信号但算法未确认时显示计算尚未验证。

## 两种 API 与兼容处理

- HardwareBridgeService：设备 latest 信封，无认证患者 API、预测或持久化历史；硬件模式只累积本次浏览器实际记录，不回退 Mock。
- LiveApiService / SwiftUI CareService：原有已认证患者端点，保持独立。未把 latest 地址冒充为患者接口，也未默认打开生产 Live。
- normalized Metric 仅新增可选 measuredAt/sensor/connected/state/calculationValidated。SwiftUI 不直连临时桥接，但能消费这些可选心率元数据，仍可读取旧患者接口。
- metrics.spo2 保留为可选旧 wire 兼容，允许旧后端继续返回；产品 MetricKey、规则与展示不再枚举它。共享旧形状样例保留字段但使用 null/unavailable。原有端点和其他模型不被整块删除。

## 本地运行与验收

```sh
cd carelink-health-monitoring
npm run dev
# 或显式进入现有硬件模式：
npm run dev:hardware
```

默认 Vite 地址 http://127.0.0.1:5173/。若已有服务占用端口，不要结束不明进程，可用 `npm run dev:hardware -- --port 5174`。顶部可切换 Mock/ESP32/API，切换来源重新进入会话。Mock 登录密码 demo1234；硬件是无认证的本地设备视角。当前 Web/SwiftUI 默认数据配置仍是 mock，硬件模式仍显式选择。

验证 Pro 搜索/筛选/患者详情/历史/事件、Basic、LCD、演示规则和两种语言均无血氧展示；硬件模式 KY-039 未验证时为 —，温度/运动独立可用。真实设备心率值必须等待固件与字段确认。测试使用专用夹具与浏览器 GET 拦截，不向真实桥接 POST 测试数据。

完整 Xcode/iOS SDK 当前不可用；Swift 核心和语法检查不等于 SwiftUI 目标已构建或真机已验证。源文件中的旧 Scenario 分支误用了 ReadingReason 的三个 case，本次在所改函数内修正；没有删去合法场景。

## 验证记录

| 检查 | 本轮结果 |
| --- | --- |
| npm test | 通过：19 项 Node + 78 项 React/数据测试，共 97 项；包含现有 HTTP、本地旧 UI 与离线评审回归 |
| npm run build | 通过，包含 TypeScript 检查与生产打包 |
| npm run build:hardware | 通过，包含 TypeScript 检查与硬件模式生产打包 |
| npm run test:ios-core | 通过，122 项 Swift Foundation/模型/规则/API 检查 |
| swiftc -frontend -parse ios/CareLink/*.swift | 全部 Swift 源码语法解析通过 |
| xcodebuild -version | 无完整 Xcode，当前为 Command Line Tools；未进行 SwiftUI 目标类型检查/构建或模拟器/真机运行 |
| git diff --check | 通过；无意外整文件删除 |
| 浏览器 | Chromium 中 320/375/393/430/768/1024/1512 宽度无整页横向溢出；Pro 详情分区、Basic、LCD、规则、双语/深色、心率未验证/有效/质量差/断开/等待/过期/失败/恢复均通过，零页面异常 |

浏览器检查使用 GET 拦截的测试信封与测试配置，包括正向验证所需的确认标志；没有给真实桥接发送假上报。硬件界面截图是测试响应的 UI 状态，不代表 KY-039 已完成实测。真实设备仍需固件和契约确认。

当前为评审额外启动了 http://127.0.0.1:5174/ ，没有停止原先占用 5173 的服务。本地桥接未在 8000 检测到监听；请由硬件组启动其原有服务并恢复 ESP32 上报。独立 iPhone App 本轮做了源码调整，真实 iPhone Safari 也尚未真机验证。


## 主要改动文件

| 范围 | 文件与用途 |
| --- | --- |
| Web UI | src/App.tsx、src/ui/components.tsx、pages.tsx、presentation.ts、src/product.css：移除旧指标；心率卡片/时间/状态、趋势/历史有效性和布局 |
| 硬件适配 | src/data/HardwareBridgeService.ts、HardwareDataService.ts、models.ts、public/hardware-bridge-config.json：新增默认关闭的 KY-039 契约准备、状态映射与元数据校验 |
| 独立 iPhone | ios/CareLink/Models.swift、Monitoring.swift、Services.swift、DemoStore.swift、Views.swift、DetailViews.swift、SettingsViews.swift：可选兼容字段、两项产品指标、心率时间/连接/质量与状态 |
| 旧入口与共享 | dist/app.js、rules.js、service.js、i18n.js、review/mobile.js：删除所有仍可运行旧页面中的血氧入口；shared/fixtures/vectors/API 样例不再模拟血氧值 |
| 回归测试 | 新增 src/data/KY039.test.ts、src/NoOxygenUI.test.tsx；更新已有 Web/Swift 核心用例，保留患者/告警/权限/网络测试 |
| 文档 | README、HARDWARE_BRIDGE、API_CONTRACT、INTEGRATION、PRODUCT_UI、UI_DESIGN、PLATFORM_REQUIREMENTS 与 ios/README：明确当前范围、兼容契约和待完成的真实硬件工作 |

## 组员仍需配合

1. 提供实际 CareLink Arduino 固件；完成/确认 KY-039 采集、滤波、周期计算、质量判断与参考设备对比，并提供独立采样时间。
2. 确认上述建议扩展字段的精确名称与语义，特别是连接状态与算法基本验证标志。尚未确认时保持 heartRateContractConfirmed=false。
3. 若采用认证患者 API，提供其真实会话、设备-患者关联、持久化历史、告警和预测接口；不能用临时 latest 信封替代它们。原生 App 依然通过该 API 契约工作。
4. 跌倒分类和 AI 预测仍未验证/未接入；本轮没有新增相关测量能力。
