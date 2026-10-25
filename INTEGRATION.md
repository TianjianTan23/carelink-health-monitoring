# 组员联调与 LCD 1602A 约定

当前最终目标为 React + TypeScript Web Pro/Basic、独立 SwiftUI iPhone Pro/Basic，共享 FastAPI/SQLite/AI 的标准化 JSON。真实接口未确定，默认继续 mock。没有假设旧 `/sensor-data` 或 `/alerts` 已覆盖本轮要求，也没有修改组员服务。

软件接入以 [API_CONTRACT.md](API_CONTRACT.md) 为本轮草案；结构见 [ARCHITECTURE.md](ARCHITECTURE.md)。两端已实现 MockDataService / LiveApiService，配置在 `shared/carelink-config.json`；接口确认后只调整配置及服务映射，不修改页面。Web 的原 `dist/service.js` 继续作为回归/模拟逻辑参考，不再作为新版 React 的直接配置入口。

以下硬件与 LCD 约定保留原工程内容，尚不等于可烧录固件：

## 5. KY-039 心率接入准备（2026-10-26）

本轮按用户要求改为 KY-039 计划，血氧产品 UI 已全部移除。原 KY-005/MAX30102 方案不代表当前心率能力。原始模拟信号不能当作 BPM；算法与数据契约尚未在本地工程找到验证证据。默认不启用真实心率数值，见 [KY039_UI_UPDATE.md](KY039_UI_UPDATE.md)。

## 6. LCD 1602A 固件集成规范

用户已确认型号为 LCD 1602A。实际显示为 16 列 × 2 行，不按 320×240 彩屏假设。默认字符 ROM 不能保证中文显示，所以采用 ASCII 英文缩写。每次输出截断/补空格到 16 字符，以防旧字符残留；避免整屏频繁 clear 引起闪烁。

标准页面（下划线在此仅代表空格，实际写入空格）：

```text
HR:76 BPM
SURF T:36.6C
```

第二页：

```text
FALL:NONE
DEMO / SIMULATED
```

以下跌倒警报帧仅用于明确标记的 Mock 或可信事件接口；硬件原始 alarm 不触发它：

```text
! FALL DETECTED!
CHECK PERSON NOW
```

无 HR/SpO₂：

```text
HR:--- BPM
SURF T:36.6C
```

离线/过期：

```text
DEVICE OFFLINE
HR:--- BPM
```

过期时第一行改成 `DATA STALE`。严重数值异常优先轮播 `! VALUE ALERT !` / `CHECK PERSON NOW`，轻度异常显示 `VALUE ATTENTION` / `PLEASE CHECK`。每 3 秒翻页；跌倒页保持优先，不自动因为断线消失。实际刷新频率与声音/灯光策略由固件组确认，KY-005 不应被描述成可见警示灯或生理传感器。

网页的 `lcdFrames()` 是经过测试的显示逻辑参考，不能直接当作 ESP32 固件烧录。移植到 C++/Arduino 时使用与传感器采集一致的质量和时间规则，在固件端生成同样两行文本，再调用 LCD 驱动。真实运行时移除 DEMO / SIMULATED 文案，替换为已核实的设备状态。

仍需硬件组提供：并行接口还是 I²C 背板、I²C 地址（若有）、供电与逻辑电平、引脚分配、LCD 驱动库及版本、事件确认按钮/后端确认机制。确认这些信息前不猜测引脚接线。
