# CareLink 本轮改造与结构

## 改造前检查

原工程为 `dist/` 原生 JS Web、`ios/` SwiftUI、`shared/` JSON 与 19 项 Node / 91 项 Swift 核心检查。保留所有既有测试、演示规则、档案和 LCD 逻辑。Figma 风格以本次对话已经成功读取的记录为依据，详见 FIGMA_CHECK_2026-10-22.md；本阶段零次 Figma 写入，文件未改。

## 现在的结构

```text
src/
  App.tsx                     React 登录、角色范围、语言、主题及导航
  data/models.ts              TypeScript + Zod 运行时模型
  data/service.ts             DataService 与 DataError
  data/MockDataService.ts      复用原 MockService、分级及本地事件
  data/LiveApiService.ts       草案 API 通信与响应校验，无模拟回退
  data/config.ts              配置读取与显式启用检查
  ui/                         页面、通用状态、指标显示、图标与资源加载
  styles.css / tokens.css     macOS 风格 Web 和生成的设计令牌
ios/CareLink/
  Models.swift                相同 JSON 字段，SensorReading 兼容原 Reading
  Services.swift              原模拟实现与扩展服务协议
  LiveApiService.swift        注入式 URLSession 传输、配置与校验
  DemoStore.swift             选择服务、分离各资源的加载/错误/空状态
  *Views.swift                保留 NavigationStack / TabView / List / Charts
shared/
  carelink-config.json        默认 mock，端点草案，apiConfirmed=false
  design-tokens.json          两端颜色，Web 与 iOS 平台字阶说明
  schema.json                 扩展原模型，新增 Prediction / Alert
  openapi.draft.json          待确认接口
  api-examples/               两端共同解码的虚构响应示例
dist/                         原 Web 保留作回归参考，非当前构建输出
review/                       上一轮离线手机评审伴随文件，非原生运行环境
build/                        React 静态构建输出
tests/                        19 项原 Node 检查完整保留
src/**/*.test.*               新服务、模型、React 流程检查
ios/CoreTests/                扩展原 Swift 检查，非 SwiftUI UI 测试
```

主要改动位于上述 src、新配置/契约、Swift Models/Services/Store/Views、package.json、Vite/TS 配置、工程资源引用及文档。没有创建第二个项目或第二个站点；现有托管身份保留，静态目录由 dist 改为 build。

## 数据流与状态

UI → DataService → MockDataService 或 LiveApiService。配置在启动时选择。患者、历史、预测、告警分别维护加载/错误/空状态；错误不会被当作空记录，也不会自动启用模拟服务。相同资源刷新保留原采集时间，换患者清空前一个缓存，响应代次防止过时请求覆盖。

显示当前数值要求设备连接、采集时间有效、通道可用且 quality=good、value 非 null。无效值用 `—`；历史值始终是历史，趋势中的无效记录不连线。Pro 与 Basic 共用底层模型，Basic 不展示病史、原始数据或 AI 详情，也不能执行医护确认；后端仍必须实施真正授权。

模拟判断明确标注“可配置演示规则”。真实模式只使用后端 assessment 或明确上报的跌倒事件，不用 demo 数值边界推断真实状态。预测与测量分别展示，保留原置信度，不生成医学结论。

## 设计规范

沿用 Figma 的 #197b6e 品牌、#f6f8f7 背景、#233e38 主文字、薄荷表面及 12px 卡片圆角。次文字为阅读对比度略加深；深色为既有本地提案。令牌源在 shared/design-tokens.json；生成器同时输出 Web CSS 与 iOS 命名色资产。字阶/布局因平台而异：Web 系统 SF/PingFang 栈及侧栏工具栏，iOS 系统动态字号、SF Symbols、原生导航与列表。状态均有图标、文字与颜色。

## 环境与未完成项

Web 需要支持当前构建依赖的 Node（建议 Node 22.19+ 或当前 26）；npm ci 使用锁定依赖。现有 Mac 仅有 Command Line Tools，无完整 Xcode/iOS SDK。原生 SwiftUI 的目标编译、模拟器/真机运行、签名仍未验证；核心 Swift 编译/运行不能代替这些检查。未接通组员 FastAPI、SQLite 或 AI。认证、CSRF/CORS、服务端事件处理待联调。Figma 原先 iPhone 空画板未填充。

官方构建参考：[React TypeScript](https://react.dev/learn/typescript)、[Vite 构建](https://vite.dev/guide/build)、[Vite 静态部署](https://vite.dev/guide/static-deploy.html)。
