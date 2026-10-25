# CareLink 可移植源码包 · 2026-10-26

本包来自 `experiment/live-sensor-ui` 的 KY-039 UI 更新版本，基线提交为 `8aeb29c7e6f59038ba97c0a4bd477995c027b7f6`。具体发布提交见 ZIP 内 `RELEASE_INFO.json` 和 ZIP 旁交付记录；ZIP 从该提交生成，逐文件校验对应同一版本。

## 包内内容

- 完整 React/TypeScript/Vite Pro/Basic 响应式网站、共享模型与 DataService、独立 SwiftUI iPhone 工程、旧版 Web/手机评审源码、测试和文档。
- 所有产品界面移除血氧。旧接口字段仅保留可选兼容，Mock 不再产生血氧数值。
- KY-039 心率卡片、状态、独立时间和历史/趋势已准备。`heartRateContractConfirmed=false` 默认不变，真实算法与字段未确认时不显示 BPM；原始 ADC 不作 BPM。
- MPU6050 运动、MLX90614 表面/环境温度、LCD 显示概念、告警和时间线保留；跌倒分类未验证，AI 未接入。
- `hardware-bridge/` 为已有实验 FastAPI 桥接副本及依赖和隔离测试。本轮没有改写桥接或 Arduino 固件，ESP32 固件不包含在源码包内。

## 安装和运行

解压后进入 `carelink-health-monitoring`，使用 Node.js 22.19+：

```sh
npm ci
npm run dev
# 或显式选择硬件模式：
npm run dev:hardware
```

默认地址 http://127.0.0.1:5173/ ，Mock 演示密码 demo1234。包中不需要开发者本机 `.env.hardware`，Vite hardware 模式会显式选择硬件。硬件桥接启动与配置见 README.md，KY-039 所需建议字段和待完成事项见 KY039_UI_UPDATE.md。

## 验证范围

- Web：19 项 Node + 78 项 Vitest，共 97 项通过，包括原有 HTTP、权限、告警及旧 UI 回归。
- Swift：122 项核心检查通过，全部 Swift 源码语法解析通过。当前只有 Command Line Tools，没有完成完整 Xcode/SwiftUI 目标构建或真机测试。
- `npm run build` 和 `npm run build:hardware` 均通过；`git diff --check` 通过。
- 浏览器在 320–1512 像素宽度检查无整页横向溢出，覆盖 Pro/Basic、双语/主题、心率有效性、断线和恢复。
- 测试心率响应只用于隔离测试，不代表真实 KY-039 算法已验证。未向实际桥接写入测试数据，未开放 LAN 服务。

## ZIP 分发规则

只分发提交的项目文件，另附 `RELEASE_INFO.json` 和逐文件 SHA-256 清单 `SOURCE_MANIFEST.sha256`。排除 `.git`、`node_modules`、`build/`、缓存、虚拟环境、本地 `.env*`、日志和开发机器文件；只保留无密钥配置模板 `.env.example`。保留 `dist/`，因为该目录包含现有模拟适配和测试依赖的手写 JS 源码，并非本次构建产物。

解压包不会自带依赖；运行前需 `npm ci`。如需旧版离线手机评审伴随页面，可运行 `npm run review:mobile`，生成 `build/carelink-iphone-review.html`；它不是原生 iOS App。

只更新实验分支，不切换、不合并 main。GitHub 和 ZIP 的提交编号以交付记录为准。
