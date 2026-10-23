# CareLink · Code-first UI sprint

2026-10-22。本轮直接改现有 React / SwiftUI 源码，保留 `src/data/`、原生服务、共享模型和接口契约。没有调用 Figma MCP。

## 设计源与修改位置

| 内容 | 源文件 | 实际应用 |
| --- | --- | --- |
| 绿品牌、四色状态、深浅色 | `shared/design-tokens.json` | Web `tokens.css`、iOS 命名颜色资产 |
| 间距 4–48、圆角 10/18/24 | 同上 | CSS 变量、生成的 `DesignTokens.swift` |
| 字体层级 | 同上，原生 Dynamic Type | Web caption/body/heading/title；iOS caption/body/headline/title/largeTitle |
| Web 图标 | `src/ui/Icons.tsx` | 统一线条 SVG、状态文字与图标并用 |
| iOS 图标/卡片 | `ios/CareLink/DesignSystem.swift` | SF Symbols、CareMetricLabel、CareGroupBoxStyle、CareCard |
| 桌面布局 | `src/App.tsx`、`src/ui/pages.tsx`、`src/styles.css` | 固定侧栏、半透明工具栏、主内容与详情面板 |
| 原生布局 | `ios/CareLink/Views.swift`、`DetailViews.swift`、`AlertViews.swift` | NavigationStack、TabView、分组 List、原生确认、底部安全区操作 |

修改 token 后运行 `npm run generate:tokens`；生成文件不要直接编辑。添加 Swift 文件后运行 `python3 scripts/generate-ios-project.py` 更新现有工程引用。两端使用系统 SF/PingFang 字体；iOS 使用可缩放语义字号，不强制套用 Web 像素字号。默认浅色，主题切换使用已有偏好逻辑。

## 页面与真实交互

- Login：Pro/Basic 角色选择、双语、输入错误、密码显示/隐藏、加载反馈；装饰波形不是测量数据。
- Pro 首页：分级统计可筛选；优先关注区可直接打开对应患者；姓名/床位/编号搜索、卡片/列表、明确数据待确认。
- 患者详情：概览 / 十分钟记录 / 原始数据与 AI 三个分区。Web 支持左右方向键、Home/End；打开患者从页面顶部开始。
- 概览：四项核心监测、风险说明、十分钟趋势、实际返回读数范围及采样时间、档案与病例摘要。趋势缺失值仍留断点。
- 十分钟记录：保留全部返回记录和原采集时间，未将历史数据标为当前值。iOS 默认六条，可展开全部。
- 原始数据与 AI：分开卡片与来源说明；AI 的时间、模型、版本和置信度仅展示实际返回字段。
- Basic：首页只展示关联患者、四项核心指标、易懂状态和最后成功更新时间；无技术数据区。
- 告警：患者身份、严重度、当前条件、处理状态、详情时间线、患者入口和确认；确认仍须服务成功，且不会自动改变患者风险。iOS 新增处理状态筛选及底部安全区确认按钮。
- 数据缺失/不可用/不可靠/过期/网络失败：保留已有状态及原时间戳，不补正常值。场景开关继续从 MockDataService 驱动。

## 平台差异与评审

2026-10-23 范围更新：本轮桌面和手机版均以响应式 Web 交付，手机使用底部导航、安全区和触控布局。独立 SwiftUI 工程保留，未将本轮 Web 硬件适配声称为原生 App 的功能。Pro/Basic 通过演示角色切换体验；真实角色仍由既有后端会话契约决定。

绿色表示未触发配置规则；黄色表示轻度异常；红色表示跌倒或严重异常；灰色表示待确认。始终配文字/符号。演示规则不是临床标准；本轮未添加医学阈值。

Web 已在实际浏览器预览。iOS 仅源码完善、语法解析、工程格式检查和 Foundation 核心检查；完整 Xcode 构建、真机/模拟器视觉、键盘与动态字号、VoiceOver、系统手势尚待验证。没有签名 IPA，也没有连接真实硬件或 AI。


## 2026-10-23 完整硬件产品 UI

HardwareDataService 将桥接接入同一完整 App。新增 product.css 手机底部导航、账户菜单与数据源选择，详情内新增患者事件时间线，动态指标支持表面温度/环境温度/总加速度。硬件模式删除 HR/SpO₂ 元素；运动连接与跌倒分类未验证分开表达。历史只记录本次会话真实采样，AI 未连接。最新验证和运行说明以 PRODUCT_UI.md 为准。
