# 安护 CareLink · Web + iPhone Demo · Apple UI Sprint

在原工程上升级：电脑端 **React + TypeScript**，独立 iPhone **SwiftUI**；两端均有 Pro / Basic、中英切换和深浅色外观。保留原有患者、模拟规则、LCD 1602A 逻辑和全部旧测试。本轮不写入 Figma。

默认是明确标记的虚构模拟数据。尚未连接组员的 FastAPI、SQLite、真实设备或 AI；LiveApiService 实现的是待确认草案，不表示真实后端已可用。见 [API_CONTRACT.md](API_CONTRACT.md)。

## 先运行电脑 Web

需要 Node 22.19+（或当前 Node 26）。在本目录运行：

```sh
npm ci
npm start
```

打开终端显示的本地地址，通常为 http://127.0.0.1:5173/ 。默认账号已填，演示密码 `demo1234`；不要输入真实凭据。选择 Pro / Basic 进入，右上角切换语言及主题；侧栏可体验另一模式。关闭服务按 Ctrl+C。

构建和静态预览：

```sh
npm run build
npm run preview
```

构建输出为 `build/`，在线站点沿用原网址与私有访问范围。`vite preview` 用于本地预览，部署使用静态构建文件。

## 体验流程

- **Pro**：8 位虚构患者，初始红 2、黄 2、绿 3、待确认 1；搜索、分级筛选、卡片/列表切换。优先关注区可直接打开患者；详情分为概览、十分钟记录、原始数据与 AI 三个可切换区，保留档案、四项指标、十分钟趋势/21 条历史。
- **Basic**：只显示会话关联的 p004，四项大指标、易懂状态、成功更新与采集时间。不会展示其他患者、病史、原始数据或 AI 详情，也不能执行医护确认。
- **告警**：查看事件与数据质量记录、发生/更新时间、处理状态和详情；Pro 可确认，只有服务成功响应才更新。确认不解除跌倒或更改分级。
- **演示场景**：切换平稳、轻度/严重异常、跌倒、读数不可靠、不可用、离线、过期、无数据；可暂停模拟更新和模拟网络失败。
- **LCD 1602A**：保留 16×2 ASCII 概念，不是可烧录固件。KY-005 场景 HR/SpO₂ 为 `—`，不伪造替代读数。
- **演示规则**：保留并可编辑原课堂阈值，仅模拟会话生效。真实 API 模式不使用它们给设备读数分级。

本轮界面改动与可编辑设计源见 [UI_DESIGN.md](UI_DESIGN.md)。

## 数据架构与配置

`src/data/` 提供统一 DataService，MockDataService 复用原模拟实现，LiveApiService 负责通信、字段校验和错误传播。React 页面不直接调用 fetch。SwiftUI 通过相同含义的 CareService 协议与配置选择服务。

`shared/carelink-config.json` 是配置源，默认 mock / apiConfirmed=false。`npm run generate:shared` 同步到 `public/carelink-config.json`；构建后部署文件为 `build/carelink-config.json`。端点和真实 JSON 确认后，设置 live、可达 baseUrl、端点映射、apiConfirmed=true；无需修改页面。Web 可用同源代理，iPhone 配置必须为绝对 URL。可选构建覆盖见 `.env.example`。

真实模式只读取后端已认证会话，不发送演示账号密码，不允许用户自行取得 Pro 权限。认证/CORS/CSRF/安全凭据等仍需联调。失败不会转成 mock，404 详情为空，列表 []/204 为空列表，无效 JSON/HTTP/网络失败显示错误。

`Patient / SensorReading / Prediction / Alert` 定义和示例在 `shared/`。读数无效时显示 `—`，不填 0、不保留旧值伪装新值。预测单独显示时间、模型/版本及实际返回的置信度，不合成结论或默认分数。详见 [架构与文件说明](ARCHITECTURE.md)、[接口草案及待确认清单](API_CONTRACT.md)、[硬件/LCD 约定](INTEGRATION.md)。

## 设计修改

共享颜色、圆角、间距在 `shared/design-tokens.json`。修改后运行：

```sh
npm run generate:tokens
```

此设计生成器需要 Python 3，会同时生成 Web CSS、iOS 颜色资产和 DesignTokens.swift 间距/圆角常量。正常运行已提交源码无需先生成令牌。Web 使用系统 SF/PingFang 字体栈与侧栏工具栏；SwiftUI 保留系统动态字号、SF Symbols、NavigationStack、TabView 和 List。浅色为默认，深色源自本地方案。状态都有文字和图标辅助。

Figma 原文件仍为 https://www.figma.com/design/bOI1cB8GMKvUde0avJFkjJ ，Web/LCD 内容未改，iPhone 空画板本轮未填充。两份代码不自动同步到 Figma。

## iPhone

保留 `ios/CareLink.xcodeproj`，最低 iOS 17、仅 iPhone、无 Android。共享 JSON 以 bundle 资源引用；在完整 Xcode 中打开，选择模拟器运行；真机需自己的 Team/签名。详细步骤见 [ios/README.md](ios/README.md)。

**当前环境只有 Command Line Tools，缺少完整 Xcode/iOS SDK。尚未完成 SwiftUI 目标构建、模拟器交互或真机安装。核心 Swift 检查通过不等于 App 运行成功。**

## 测试

```sh
npm test
npm run build
npm run test:ios-core
```

`npm test` 保留原 19 项 Node 检查，并增加 React 组件、双模式/双语、模型、真实服务适配与 HTTP 流程检查。`src/data/http.integration.test.ts` 使用本机临时 HTTP 响应服务验证真实 fetch 的成功、空数据和 HTTP 失败，不是组员的后端。Swift 核心测试扩展旧测试，并解码同一套 API 示例、验证原生服务成功/空/失败与确认。实际结果见 [DESIGN_STATUS.md](DESIGN_STATUS.md)。

## 保留的原成果

原原生 JS Web 仍在 `dist/`，可 `npm run legacy` 运行，供回归和参考；不再是默认 Web。原 `tests/` 未删；新增检查在 `src/`。上一轮离线手机评审文件通过 `npm run review:mobile` 生成，仍是旧评审伴随成果，不代表最新 React Web 或原生 iOS 运行环境。本阶段应优先评审新 Web 和现有 SwiftUI 工程。

官方参考：[React TypeScript](https://react.dev/learn/typescript)、[Vite 构建](https://vite.dev/guide/build)、[Vite 静态部署](https://vite.dev/guide/static-deploy.html)。
