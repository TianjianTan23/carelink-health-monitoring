# 当前更新：2026-10-26 KY-039 UI

本轮保留独立 SwiftUI 工程和原有 Pro/Basic/导航交互，移除所有血氧卡片、趋势、历史、规则文案与指标枚举。心率卡片显示 BPM、质量/计算状态、连接信息和独立采样时间；normalized Metric 的 sensor=KY-039 但 calculationValidated 不是 true 时不可显示数值。缺失字段时不假定已接线或已计算成功。

此原生工程仍使用 CareService 的 mock/患者 API 配置，未新增对 FastAPI latest 设备桥接的调用；两种契约保持独立。硬件采集与算法仍待组员提供。历史血氧 wire 字段只作可选兼容，不在 UI 枚举中；Mock 值为 null。详见根目录 KY039_UI_UPDATE.md。以下旧更新是历史记录，以本节为当前范围。

# CareLink · 原生 iPhone Demo

这是独立 SwiftUI App，不是网页套壳。目标设备为 iPhone，最低 iOS 17；不包含 Android、iPad 或 Mac Catalyst target。Web 继续作为电脑端运行，两端都有 Pro / Basic，并支持中文与 English。

## 当前完成与验证范围

- 工程包含原生登录/角色选择、Pro 患者列表、关注与警报、患者详情、十分钟趋势与历史、原始数据/AI 占位、Basic 关键指标、演示控制台和账户页。
- 使用 `NavigationStack`、`TabView`、`List`、`Form`、Swift Charts、系统字号、SF Symbols、系统语义色及深浅色外观。较大辅助功能字号时指标改为单列。
- iOS target 直接加载 `../shared/` 的三份 JSON 资源，与 Web 使用同一患者、会话和规则源。Pro 展示 8 位授权演示患者，Basic 只关联 p004。
- 本轮本机没有完整 Xcode 或 iOS SDK，**尚未完成 iOS target 编译、模拟器交互或 iPhone 真机安装**。Swift 语法检查和 Foundation 核心模型/规则检查不等同于 iOS 构建成功。具体检查结果见根目录交付说明。
- 当前全部为本地虚构数据，没有网络后端、真实登录或 AI，也没有推送通知、HealthKit 或硬件权限请求。

## 用完整 Xcode 运行

1. 在 Mac 上安装完整 Xcode，版本需支持你准备使用的 iPhone/iOS 版本。工程使用 iOS 17+ API，不能只依靠 Command Line Tools。
2. 保留项目目录结构；双击本目录的 `CareLink.xcodeproj`。`shared/` 是工程引用的相邻目录，不要只移动 `.xcodeproj` 文件。
3. 在顶部 Scheme 选择 **CareLink**，运行目标选择已安装的 iPhone 模拟器。必要时先在 Xcode 中下载对应模拟器运行环境。
4. 按 Run（⌘R）。模拟数据从 App bundle 读取，无需先启动 Web 或 API。
5. 在首页选择 Pro / Basic，保留预填虚构账号和密码 `demo1234`，点击“登录演示”。清空输入或改错密码可体验错误提示。顶部可切换语言；账户页可切换模式或退出。

若工程文件被误改，根目录运行 `python3 scripts/generate-ios-project.py` 可从现有 Swift 文件重新生成工程；不需要安装 XcodeGen 或其他第三方生成器。

## iPhone 真机运行

1. 用数据线连接 iPhone 与 Mac，按设备提示完成信任/配对。
2. 在 Xcode 的 **Signing & Capabilities** 中启用自动签名并选择自己的开发 Team；必要时为 Bundle Identifier 使用你自己的唯一名称。项目没有预置别人的 Team 或证书。
3. 按 Apple/Xcode 提示完成 iPhone Developer Mode 与设备支持设置，再把运行目标切换为该 iPhone。
4. 按 Run。签名、系统版本兼容和设备授权须由持有设备与 Apple 账户的人完成；本交付没有已签名 IPA。

官方步骤：[在模拟器或真机运行 App](https://developer.apple.com/documentation/xcode/running-your-app-on-simulated-or-physical-devices)。具体界面以安装的 Xcode 版本为准。

## 首轮体验清单

- Pro：搜索某位患者，筛选不同状态，点击进入正确档案，查看三种趋势、十分钟历史、原始数据和 AI 未接入提示。
- 告警页：点击进入告警详情，Pro 可确认本地演示告警；显示发生、最近观察、确认时间及历史。确认后跌倒事件仍保持原分级。Basic 只看到关联患者提醒，不能执行医护确认。
- Basic：只出现关联患者 p004，不展示其他患者的姓名、病史、原始数据和 AI 详情。
- 演示页：为当前模式的授权患者切换跌倒、轻度/严重异常、MAX 信号不稳、KY-005 备用、离线、过期和无数据。
- KY-005 场景：心率和血氧显示 `—`，不能显示替代测量值；体温卡片继续注明是表面测温。
- 关闭自动更新后超过共享规则中的有效时限，正常旧值应变为待确认；未处理跌倒事件不随离线消失。
- 中文/English 切换、默认浅色、账户中的深色提案/跟随系统、较大系统字号、VoiceOver、下拉刷新和系统返回手势。

## 核心逻辑检查（无需完整 Xcode）

在支持 Swift/Foundation 的 Mac 上，从根目录运行：

```sh
npm run test:ios-core
```

它编译并运行 Models / Monitoring / Services 与共享黄金向量，验证字段解码、ISO 时间、与 Web 一致的红黄绿/未知逻辑、十分钟窗口、KY-005 缺失值以及 AI 占位。临时二进制和模块缓存放在临时目录，检查结束后清理。

在完整 Xcode 中可额外执行以下构建检查；模拟器 destination 请先用自己的环境确认：

```sh
xcodebuild -project ios/CareLink.xcodeproj -scheme CareLink \
  -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath /tmp/carelink-ios-build CODE_SIGNING_ALLOWED=NO build
```

该命令目前没有在本机成功执行，因为缺少 iOS SDK；不能将其写成已通过。

## 后续 API 接入

`CareService` 是数据隔离层，默认使用 `MockCareService`。`APICareService` 提供建议接口的 GET 适配，不会在失败时替换成假数据。真实接入时需由后端返回认证后的 Session，并替换 Store 中的演示初始化与角色切换逻辑；原始数据/AI 的真实授权、响应校验、事件处理、重试和凭据安全存储仍需联调。

默认 Mock 无需网络。iPhone 上的 localhost 指 iPhone 自己；连接组员电脑的本地服务时应使用正确的后端地址，并按实际连接方式处理 iOS 网络权限和传输配置，不要把这些工作误当成已有能力。


## 2026-10-22 更新

- 登录新增邮箱/用户名、密码、必填校验、模拟登录失败；这不是正式账号验证，不保存输入密码。
- 患者列表新增采集时间与异常摘要；Basic 区分最后成功更新与采集时间。
- 告警为本地事件记录：发生/最近观察/确认时间、状态变化历史、独立详情与确认对话框。连续刷新同一条件不会重复建记录；新一轮事件不会继承旧确认。
- 演示控制台增加连接失败以及告警加载中、加载失败、无记录的页面状态开关。它们明确标注“模拟”，不会冒充真实服务响应。
- 使用命名颜色资产保留 Figma 品牌浅色；默认浅色，深色为后续设计的本地提案。iPhone 使用系统 SF/PingFang 字体与动态字号，没有将 Web 的 Noto Sans SC 字体文件嵌入 App。
- `InteractionModels.swift` 是可独立编译的表单/告警逻辑；`DemoStore` 管理 UI 状态，`CareService` 管理数据访问。真实 API 联调时还需要服务器事件 ID、服务端发生时间和确认接口，当前不会向服务器提交确认。
- 新增浏览器评审伴随文件 `carelink-iphone-review.html`（位于完整工程包顶层）。双击用浏览器体验主要流程，无需安装依赖。这是 HTML/CSS/JS 布局预览，**不是原生 iOS App，也不验证 SwiftUI 或真机兼容性**。原生代码与预览共用患者/会话/规则 JSON，交互代码分别实现，不自动双向同步。
- 本轮 91 项 Swift Foundation 检查通过；SwiftUI 仅语法解析通过。再次尝试 `xcodebuild` 仍因缺少完整 Xcode 失败；原生 UI 类型检查、运行、签名与真机测试仍待完成。


## v2：共享数据与 API 适配

- `shared/carelink-config.json` 现为第四份 bundle 资源，默认 mock。两端共用同一配置字段；iPhone 改为 live 前必须设置可达的绝对 baseUrl、确认端点并设 apiConfirmed=true，随后重新构建。没有在页面中替换数据源的硬编码步骤。
- `CareServiceFactory` 选择现有 MockDataService 或新 LiveApiService，后者覆盖 session、患者列表/详情、十分钟读数、独立预测、告警和确认。请求与 Codable 校验可注入传输测试；真实错误绝不使用演示数据回退。
- live 登录界面不发送演示密码、不选择真实角色；使用后端已认证会话。认证方式和凭据安全存储须等团队确认，未自行实现登录端点。
- 新模型 `SensorReading` 保留原 Reading 兼容名；Prediction 扩展时间、模型版本、输入时间、confidenceMeaning；Alert 使用服务端字符串 ID 及状态。UI 只在确认请求成功后更新状态，不清除 active 事件。
- 真实数据不调用演示数值分级，仅展示 backend assessment 或明确跌倒事件；无后端判断显示待确认。实际 source 字段决定读数来源标签。API 模式手动刷新；频率待组员确认。
- 每种资源保留加载/错误/空状态；指标仍按测量时间和质量过滤，无效值为 `—`。预测与测量独立，置信度显示实际值，不推断百分比。
- 共享设计令牌生成现有颜色资产，原生导航、系统动态字号和 List/Charts 保留。本轮未写入 Figma。

契约见根目录 API_CONTRACT.md，具体当前验证结果以 DESIGN_STATUS.md 为准。此前 HTML 手机伴随预览不会自动同步本轮 SwiftUI/API 改动；不能将其当作最新原生 App 的运行证明。


## Code-first Apple UI Sprint（当前）

现有工程新增 DesignTokens.swift（共享 JSON 生成的间距/圆角）、DesignSystem.swift（原生卡片/图标规范）。登录增加密码显隐和输入焦点；Pro 增加优先关注入口；详情改为概览、十分钟、数据与 AI 分区；Basic 使用四项图标指标卡；告警增加处理状态筛选和安全区底部确认。两端品牌、状态和圆角共用，字体保留 Dynamic Type。

数据架构未改。当前核验仍是 116 项 Foundation 检查、Swift 语法和工程格式；SwiftUI 目标未在完整 Xcode 编译或运行。本节与根目录 DESIGN_STATUS.md 为当前状态，前述历史更新计数不代表本次结果。详见 UI_DESIGN.md。
