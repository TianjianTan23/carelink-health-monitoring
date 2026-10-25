# 完整 CareLink 产品 UI · 2026-10-23

按最新确认，桌面与手机均使用响应式网站。现有完整产品 UI 保留并接入实时硬件，不再用简化传感器页替代它。

## 可体验内容

- 桌面：macOS 风格固定侧栏、半透明工具栏、数据源选择、Pro/Basic 视角与账户操作。
- 手机：固定底部导航、适合触控的控件、安全区、双列指标与单列患者卡；表格只在自身区域横向滚动。顶部账户按钮可切换视角/退出。
- Pro：多患者卡片/列表、搜索、严重度筛选、优先关注、详情三分区、实际采样趋势、十分钟记录、患者事件时间线、全局告警及查看确认、原始数据与明确不可用的 AI 区域。
- Basic：关联患者/本地设备、关键指标、易懂状态、更新时间；不开放技术详情或医护确认。
- 两种语言、深浅色、键盘详情标签导航、文字与图标状态、加载/错误/无数据/离线/过期/传感器不可用均保留。

## 本地运行

在实际仓库目录执行：

```sh
cd carelink-health-monitoring
npm run dev:hardware
```

打开 http://127.0.0.1:5173/，选择 Pro 或 Basic 后进入设备工作区。默认 mock 可运行 `npm run dev`；如果 5173 已有服务，先在原终端停止再启动，避免运行多个副本。无需重新安装已有依赖。

工具栏/登录页的数据源选择：

| 数据源 | 内容和前置配置 |
| --- | --- |
| Mock | 8 位虚构患者，演示密码 demo1234，完整演示场景 |
| ESP32 | 现有 FastAPI latest 接口；配置 public/hardware-bridge-config.json；无需临床 API |
| API | 患者服务契约；shared/carelink-config.json 中配置真实端点/baseUrl/apiConfirmed 后生成共享资源；未确认时拒绝启用 |

切换数据源重新进入其会话。真实 API 的角色仍由后端决定；本地硬件 Pro/Basic 只是视角，不是权限认证。前端预览目前仅绑定 127.0.0.1，手机可先用浏览器设备模式评审；默认没有开放局域网访问；受控 LAN/iPhone 启动方法见 README.md。

## 硬件范围与限制

MPU6050 运动 + MLX90614 表面/环境温度。所有产品视图不再显示血氧。心率恢复为 KY-039 准备通道，未确认算法和契约时显示不可用，即使旧固件返回 heart_rate_ok=true。运动传感器有效不等于验证了跌倒算法；原始 alarm 仅作“原始固件报警”，不推断为跌倒。温度未校准为核心体温。AI 未接入。

桥接只有一台设备的 latest 记录，因此本地只展示一个“未关联患者”的设备档案；不会把它伪装成多患者临床系统。多患者功能在 mock / 已确认患者 API 中完整保留。历史和报警是本次浏览器会话的实际记录，不是后端持久化历史；刷新网页会清空。详见 HARDWARE_BRIDGE.md。

## 本轮修改位置

| 文件 | 作用 |
| --- | --- |
| src/main.tsx | 统一产品入口与数据源选择；配置失败反馈 |
| src/App.tsx | 全功能壳、账户/视角、硬件轮询、动态指标与真实设备档案 |
| src/product.css / index.html | 桌面/手机布局、底部导航、触控大小、安全区、深浅色继承 |
| src/data/HardwareDataService.ts | DataService 硬件适配、唯一采样历史、原始报警本地事件、单请求去重 |
| src/data/HardwareBridgeService.ts | 保留原传输并校验可选 alarm；没有新造患者 API |
| src/data/models.ts / service.ts / config.ts | 可选环境温度/运动、硬件来源与显示能力；保留原 HR/SpO₂ 契约供 mock/API |
| src/ui/components.tsx / pages.tsx / presentation.ts / Icons.tsx | 共享指标、连接状态、趋势/历史、患者时间线、AI 未连接与双语显示 |
| src/HardwareApp.tsx | 原入口改为完整 App 的兼容封装 |
| src/HardwareApp.test.tsx / src/data/HardwareDataService.test.ts | 全产品硬件 UI 与适配测试 |
| README.md / HARDWARE_BRIDGE.md / UI_DESIGN.md / PRODUCT_UI.md | 当前运行方法、数据语义、手机 Web 范围和限制 |

进入本轮前已有未提交的硬件文件，全部工作仍保留在 experiment/live-sensor-ui。没有提交、推送、合并、切换或改动 main。

## 验证与保留的 iOS 工程

本轮 Web 测试为 19 项原 Node 测试 + 55 项 React/数据测试；默认与硬件生产构建均通过。Swift 核心 116 项检查通过。浏览器在 320/375/393/430/768/1024/1512 宽度检查无整页横向溢出，检查了手机视角切换、语言、深色、数据源切换和硬件无 HR/SpO₂。

浏览器检查使用本机 Chromium 和手机尺寸，并非真 iPhone Safari 或真实触控设备验证。独立 ios/CareLink.xcodeproj 保留，本轮没有改写其服务或 UI；本机仍只有 Command Line Tools，xcodebuild 不可用，不能声称原生 UI 已编译/运行。旧 build/carelink-iphone-review.html 是另一份历史预览，不是本轮响应式网站，评审请打开当前 Vite 地址。


## 2026-10-26 当前传感器范围

本轮继续修改同一产品，不重建 UI。Web/SwiftUI、旧 Web 入口和离线手机伴随预览均移除血氧。KY-039 心率带有独立采样时间、质量与连接状态；卡片、历史和趋势共用有效性规则。原有登录、搜索、档案、告警确认、时间线、AI 不可用占位、双语、主题与响应式布局保留。本节后续验证以 KY039_UI_UPDATE.md 为准，前文 2026-10-23 的测试数量与硬件范围是历史记录。
