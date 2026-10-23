# CareLink 可移植源码包 · 2026-10-23

本包来自 `experiment/live-sensor-ui`，基础提交为 `52353043ad60454139967325913729d724cc7a80`。包括完整响应式 React UI、硬件 DataService/传输适配、配置模板、共享契约与夹具、Web/Swift 核心测试、保留的 iOS 工程，以及实验 FastAPI 桥接副本。

## 本次整理

- 收录先前尚未提交的产品 UI 与硬件集成改动，没有丢弃或重置这些改动。
- `hardware-bridge/main.py` 为当前外部实验桥接的原样副本，原桥接未被修改；SHA-256：`f506071ae9c8044d7063627de3afcdf73a1c48da241c77f6aabbfd4d74a1e908`。新增隔离桥接测试与明确版本的 Python 依赖。
- README 增加 Mac 安装、FastAPI 启动、ESP32/硬件模式、LAN/iPhone、CORS、网络暴露限制与故障排查。
- hardware 模式无需本地 `.env.hardware`；保留开发者自己的该文件并忽略它，不打包或提交。
- 旧手机评审生成器和相应测试改为使用项目内 `build/`，不再写入父目录。
- 文档使用相对路径，未包含开发机器绝对路径。较旧状态说明保留为历史记录，当前接入范围以 README、HARDWARE_BRIDGE.md 和 PRODUCT_UI.md 为准。

## 验证

- Node 26.0.0 / npm 11.12.1；现有依赖与锁文件一致。
- Web：19 项 Node + 55 项 Vitest = 74 项通过。HTTP 测试使用临时回环服务器；沙箱最初禁止监听，获准回环监听后完整重跑通过。
- Swift：116 项核心检查通过；未编译 SwiftUI App，未进行真机 iPhone Safari 验证。
- FastAPI / uvicorn / Pydantic：0.161.1 / 0.54.0 / 2.14.1，Python 3.14；6 项进程内桥接检查通过，不访问运行中的设备桥接。
- `npm run build` 与 `npm run build:hardware` 均通过；移除本机环境文件的独立副本也完成两种构建。
- `git diff --check` 通过。

依赖安装检查使用已有本机依赖；未声明在全新 Mac 上重新联网安装成功。本轮未修改设备固件、未向实际桥接写入测试数据，未主动开放 LAN 服务。

## 分发范围

ZIP 仅包含提交的项目文件。排除 `.git`、`node_modules`、`build/`、缓存、虚拟环境、本地 `.env*`、凭据、日志、机器专用路径；唯一环境文件是无密钥的 `.env.example`。保留 `dist/`，因为其中手写旧版 JS 是现有 React 模拟适配与测试依赖的源码，删除后不能正常测试。ESP32 固件不包含在本包。

ZIP 随附逐文件 SHA-256 清单 `SOURCE_MANIFEST.sha256`；GitHub 上传和提交编号以 ZIP 旁的交付记录为准。不会合并 main。
