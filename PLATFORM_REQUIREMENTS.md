# 最终平台要求（2026-10-20 确认）

本文件是后续开发的范围基准，替代“手机浏览器页面即可作为手机端”的早期方案。

| 平台 | 程序形态 | Pro 模式 | Basic 模式 |
| --- | --- | --- | --- |
| 电脑 | 浏览器运行的 Web UI | 医护人员查看多个授权患者、分级、详情、原始数据、历史与 AI 输出 | 患者/家属查看已授权对象的心率、表面温度和跌倒相关状态 |
| 手机 | 独立 iPhone 原生 App，SwiftUI，iOS 17+ 为本轮默认最低版本 | 适合手机的患者列表、警报、详情、历史与 AI 占位 | 适合手机的大字关键指标、简单状态及数据质量提示 |

- 手机端只开发 iOS；Android 不在范围内。
- 两端共用 API 契约、字段、单位、角色、患者关联及状态逻辑；布局各自适配，iOS 不嵌入网页替代原生 UI。
- 中英文切换继续保留。Basic 是显示模式，patient/family 是角色；Pro 对应 clinician。真实角色和 patientIds 必须由后端认证会话授权。
- 先用明确标记的虚构数据完成 Demo 与审阅修改，再联调真实后端、硬件、登录权限和 AI。
- 红/黄/绿与未知状态沿用演示规则；缺失或不可靠数据不得伪装成正常，KY-005 不产生 HR/SpO₂ 读数。
- LCD 1602A 仍是 ESP32 设备端的独立显示模块，不属于手机 App 的替代实现。
- Figma 提供可编辑设计，代码提供实际交互；两份成果没有自动双向同步。

## 工程组织

`dist/` 是 Web，`ios/` 是独立 iOS 项目，`shared/` 是共同的数据与角色契约。Web 对共享演示数据使用生成的模块；iOS 工程直接引用共享 JSON 资源。真实 API 接入各自的服务适配层。

## 验证边界

当前电脑仅检测到 Apple Command Line Tools（Swift 5.8.1），未发现完整 Xcode、iOS SDK 或模拟器。因此 Web 可以在本机运行验证；iOS 项目可做语法与跨端数据/逻辑检查，但原生 App 的 iOS 编译、模拟器交互与 iPhone 安装须在完整 Xcode 环境完成，不能将这些检查标为已经通过。


## 本阶段技术基准

电脑 Web 已升级为 React + TypeScript，源码 src/，构建 build/。iPhone 沿用独立 SwiftUI。共享契约扩展为 Patient / SensorReading / Prediction / Alert，默认 mock，由 carelink-config.json 切换服务；LiveApiService 对应待确认草案，尚未接通组员后端。Figma 本轮禁止写入，保留原文件。新文档 API_CONTRACT.md 与 ARCHITECTURE.md 取代旧版服务层切换方式。

2026-10-26：Web 与独立 SwiftUI 均移除血氧 UI，保留心率、温度、告警和全部 Pro/Basic 页面。KY-039 原始信号不能代替 BPM，算法/契约待确认。
