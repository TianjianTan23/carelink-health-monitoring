# 安护 CareLink · 完整桌面与手机 Web 工作区

在原工程上升级：**React + TypeScript 响应式网站**，桌面使用 macOS 风格侧栏与工具栏，手机使用底部导航与触控布局。Pro / Basic、中英切换、深浅色与原有患者功能保留。按本轮确认，手机版以网站交付；独立 SwiftUI 工程保留，没有声称它已经完成硬件接入。

默认是明确标记的虚构模拟数据。同一套完整页面现在也支持 ESP32 本地桥接，运行 `npm run dev:hardware`，详见 [硬件连接与启动说明](HARDWARE_BRIDGE.md)。HardwareDataService 将 FastAPI 上报接入原 DataService：硬件视图保留 MPU6050 运动、MLX90614 表面/环境温度，并准备 KY-039 独立心率通道。所有产品页面移除血氧；KY-039 算法与契约未确认时心率显示不可用。本地设备档案不冒充真实患者；无认证、AI 或临床分级。历史与原始报警记录仅在本次浏览器会话保留。LiveApiService 仍是待确认的患者 API 草案，见 [API_CONTRACT.md](API_CONTRACT.md)。

当前完整运行与评审说明见 [PRODUCT_UI.md](PRODUCT_UI.md)。工具栏可选 Mock / ESP32 / API，无需修改页面组件；切换数据源进入各自独立会话。

## Mac 安装与本机运行

解压 ZIP 后，在终端进入解压得到的 `carelink-health-monitoring` 文件夹。需要 Node.js 22.19+；本次 Web 验证使用 Node 26。桥接需要 Python 3.10+；本次使用 Python 3.14。安装 Node/Python 后重新打开终端；Swift 核心检查另需 Apple Command Line Tools (`xcode-select --install`)。

```sh
cd carelink-health-monitoring
node --version
python3 --version
npm ci
npm start
```

打开 http://127.0.0.1:5173/ 。默认是模拟数据，演示密码 `demo1234`；不要输入真实凭据。Pro / Basic 是演示视角。停止服务按 Ctrl+C；端口 5173 被占用时先停止原服务。

## FastAPI 桥接与硬件 UI

包内 `hardware-bridge/main.py` 是已有实验桥接源码的原样副本，未替换正在使用的外部桥接。首次安装，在项目根目录的终端一执行：

```sh
python3 -m venv hardware-bridge/.venv
hardware-bridge/.venv/bin/python -m pip install -r hardware-bridge/requirements.txt
hardware-bridge/.venv/bin/python -m uvicorn main:app --app-dir hardware-bridge --host 127.0.0.1 --port 8000
```

若现有桥接已经运行在 8000，继续使用即可，不必重复启动。默认仅本机可达，ESP32 实际上报时按下一节开放受控 LAN 访问。此服务只在单个进程内保留最后一条上报，重启清空；请使用默认单 worker，不添加多 worker。POST 会输出完整载荷到终端，不要发送真实患者数据。

终端二在同一项目根目录执行：

```sh
npm run dev:hardware
```

打开 http://127.0.0.1:5173/ ，数据源选择 **ESP32 · 本地桥接**，选 Pro / Basic，点击进入设备工作区，无需账号。**Backend API 用于另一套待确认的患者接口，不能用它连接此桥接。** 未收到设备上报时应显示等待；收到之后展示运动、表面温度与环境温度，并保留 KY-039 心率通道。算法与契约未确认时心率显示 `—`，不展示血氧。表面温度不是核心体温；跌倒分类未验证，AI 未接入。

Vite 的 `hardware` 模式直接选择硬件数据源，无需 `.env.hardware`。配置例子见 `.env.example`，实际覆盖写入未提交的 `.env.hardware.local`，例如 `CARELINK_BRIDGE_TARGET=http://127.0.0.1:8001`。不要把 `.env.example` 原样复制为 `.env` 后仍保留 `VITE_DATA_MODE=mock`，否则会覆盖硬件默认值。浏览器配置 `public/hardware-bridge-config.json` 默认设备 `esp32-01`，更换设备时同步修改 `deviceId`。

只读排查（这些命令不会向设备写入测试数据）：

```sh
curl -i http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/sensor-data/latest
curl -i http://127.0.0.1:5173/hardware-bridge/sensor-data/latest
```

首次上报前 latest 返回 503 / `No sensor data received yet` 是预期行为。`received_at` 长时间不变表示设备没有新上报，约 5 秒后 UI 显示过期；不是不断刷新网页就能产生新读数。历史与原始报警只在当前浏览器会话积累，刷新清空。字段语义和错误处理详见 [HARDWARE_BRIDGE.md](HARDWARE_BRIDGE.md)。ESP32 固件未包含在本包内，继续使用已有固件。

## 同一 Wi-Fi / 热点的 iPhone 访问

iPhone 不能通过 `127.0.0.1` 或 `localhost` 打开 Mac 服务，因为那指向手机自身。Mac、ESP32 和 iPhone 须处在允许设备互访的受信任网络。先在 Mac「系统设置 → Wi-Fi → 详情 → TCP/IP」确认当前 IP；热点重连后地址可能改变。

如需 ESP32 和手机接入，先在原终端 Ctrl+C 停止上述服务，再运行下列命令。**仅在受信任的私人 LAN 使用**：桥接没有认证，开放后同网设备可以读取、覆盖最新上报；前端开发服务也暴露源码。不要用于真实患者数据，不要做路由器端口转发或公共隧道；使用完停止进程。

终端一，在项目根目录运行桥接，让它同时接受本机代理与 LAN 中的 ESP32：

```sh
hardware-bridge/.venv/bin/python -m uvicorn main:app --app-dir hardware-bridge --host 0.0.0.0 --port 8000
```

终端二，填入 **Mac 当前 LAN IP**（下方只是示例地址）：

```sh
CARELINK_MAC_IP=192.168.1.10
npm run dev:hardware -- --host "$CARELINK_MAC_IP"
```

ESP32 固件的上报 URL 应是 `http://<MAC_LAN_IP>:8000/sensor-data`，iPhone Safari 打开 `http://<MAC_LAN_IP>:5173/`，不要把尖括号占位符原样输入。按实际网络允许 Mac 的入站连接；如果无法访问，检查防火墙、VPN、访客 Wi-Fi/热点的设备隔离，不要关闭整个防火墙。手机系统若询问本地网络访问，请允许此次访问。本次交付未实际开放 LAN，也未完成真实 iPhone Safari 验证。

浏览器继续请求同源 `/hardware-bridge/...`，Vite 在 Mac 代理到 `127.0.0.1:8000`，因此手机不必直接跨域调用 FastAPI。**CORS 不是认证或防火墙**，无法阻止其他同网客户端 POST。若主动改为浏览器直连后端，需在 `hardware-bridge/main.py` 的 `allow_origins` 中列出网页的准确协议、主机和端口（如 `http://192.168.1.10:5173`），然后重启桥接；默认仅允许两种本机 5173 origin。不要放开 `*`、不要启用 Vite `allowedHosts: true`。官方说明：[FastAPI CORS](https://fastapi.tiangolo.com/tutorial/cors/)、[Vite 网络与主机设置](https://vite.dev/config/server-options)。

HTTPS 公网站点直接调用 HTTP LAN 后端可能被浏览器混合内容或本地网络策略拦截；静态托管也不会自动带上 Vite 代理。正式部署需要受控 HTTPS 同源反向代理、认证授权和数据保护；`vite preview` 仅供预览。

## 构建、预览与检查

```sh
npm test
npm run build
npm run build:hardware
npm run preview:hardware
npm run test:ios-core
hardware-bridge/.venv/bin/python -m unittest discover -s hardware-bridge -p 'test_*.py' -v
```

默认与硬件构建都输出到 `build/`，最后一次构建决定默认数据源。硬件预览通常在 http://127.0.0.1:4173/ ，带同样的本机桥接代理；恢复模拟版运行 `npm run build`。Swift 核心检查不等于原生 App 编译。桥接测试在隔离的内存应用内运行，不会写入正在使用的桥接。

包内 `dist/` 是现有手写旧版 JS 源码和共享夹具，React 模拟服务及测试仍依赖其中模块，故特意保留；它不是本次生成的构建目录。`build/`、缓存、依赖、虚拟环境、`.git` 与本地 `.env*` 都不分发，只有不含密钥的 `.env.example` 配置模板保留。旧评审文件运行 `npm run review:mobile` 生成于 `build/carelink-iphone-review.html`，不再写出项目目录。

## 体验流程

- **Pro**：8 位虚构患者，初始红 2、黄 2、绿 3、待确认 1；搜索、分级筛选、卡片/列表切换。优先关注区可直接打开患者；详情分为概览、十分钟记录、原始数据与 AI 三个可切换区，保留档案、保留指标、十分钟趋势/21 条历史。
- **Basic**：只显示会话关联的 p004，关键指标、易懂状态、成功更新与采集时间。不会展示其他患者、病史、原始数据或 AI 详情，也不能执行医护确认。
- **告警**：查看事件与数据质量记录、发生/更新时间、处理状态和详情；Pro 可确认，只有服务成功响应才更新。确认不解除跌倒或更改分级。
- **演示场景**：切换平稳、轻度/严重异常、跌倒、读数不可靠、不可用、离线、过期、无数据；可暂停模拟更新和模拟网络失败。
- **LCD 1602A**：保留 16×2 ASCII 概念，不是可烧录固件。心率不可用场景使用 `—`，不伪造替代读数。
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

## iPhone 网站与保留的原生工程

手机浏览器使用同一个网站；无须安装 App。浏览器手机尺寸检查通过，不等于已在真实 iPhone Safari 运行。原生工程是保留的另一实现，本轮未修改其 UI 或硬件服务。


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
