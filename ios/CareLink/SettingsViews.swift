import SwiftUI

@MainActor
struct ScenariosView: View {
    @EnvironmentObject private var store: DemoStore
    @State private var selectedID = ""
    var targetID: String { store.patient(selectedID)?.id ?? store.visiblePatients.first?.id ?? "" }
    var body: some View {
        Form {
            Section { DemoNotice(); ErrorNotice() }
            Section(store.t("演示患者", "Demo patient")) {
                Picker(store.t("患者", "Patient"), selection: Binding(get: { targetID }, set: { selectedID = $0 })) {
                    ForEach(store.visiblePatients) { Text(store.name($0)).tag($0.id) }
                }
                Text(store.t("Basic 仅能为已关联的演示患者切换场景。", "Basic can change scenarios only for its linked demo patient.")).font(.caption).foregroundStyle(.secondary)
            }
            Section(store.t("切换模拟场景", "Change mock scenario")) {
                ForEach(Scenario.allCases) { scenario in
                    Button { Task { await store.applyScenario(scenario, patientID: targetID) } } label: {
                        HStack {
                            Text(store.scenarioName(scenario)); Spacer()
                            if store.patient(targetID)?.reading?.scenario == scenario.rawValue { Image(systemName: "checkmark") }
                        }
                    }.disabled(targetID.isEmpty)
                }
            }
            Section(store.t("连接与告警页面状态", "Connection & alert page states")) {
                Toggle(store.t("模拟连接失败", "Simulate connection failure"), isOn: $store.simulateConnectionFailure)
                    .onChange(of: store.simulateConnectionFailure) { _, _ in Task { await store.refresh() } }
                Picker(store.t("告警页", "Alert feed"), selection: $store.alertFeedState) {
                    Text(store.t("实时演示记录", "Live demo records")).tag(AlertFeedState.live)
                    Text(store.t("加载中（模拟）", "Loading (simulated)")).tag(AlertFeedState.loading)
                    Text(store.t("加载失败（模拟）", "Load failure (simulated)")).tag(AlertFeedState.failed)
                    Text(store.t("无记录（模拟）", "Empty (simulated)")).tag(AlertFeedState.empty)
                }
                Text(store.t("这些开关仅演示页面状态，不删除记录。", "These controls preview page states without deleting records.")).font(.caption).foregroundStyle(.secondary)
            }
            Section {
                Toggle(store.t("每 5 秒自动更新模拟数据", "Refresh mock data every 5 seconds"), isOn: $store.autoRefresh)
                Text(store.t("关闭后可测试数据过期。KY-005 是红外发射模块；备用模式不产生心率/血氧数值。", "Turn off updates to test stale data. KY-005 is an IR transmitter; fallback mode produces no HR/SpO₂ values."))
                    .font(.caption).foregroundStyle(.secondary)
                Button(store.t("重置所有演示数据", "Reset all mock data")) { Task { await store.reset() } }
            }
        }.navigationTitle(store.t("演示控制台", "Demo controls"))
            .toolbar { ToolbarItem(placement: .topBarTrailing) { LanguageButton() } }
    }
}

@MainActor
struct AccountView: View {
    @EnvironmentObject private var store: DemoStore
    var body: some View {
        Form {
            Section { DemoNotice(); ErrorNotice() }
            Section(store.t("当前演示角色", "Current demo role")) {
                LabeledContent(store.t("模式", "Mode"), value: store.mode.title)
                LabeledContent(store.t("角色", "Role"), value: store.mode == .pro ? store.t("医护人员", "Clinician") : store.t("患者 / 家属", "Patient / family"))
                Text(store.t("演示角色切换不验证身份。正式应用由后端会话决定角色及患者权限。", "Demo mode switching does not verify identity. The real backend session must determine roles and patient access."))
                    .font(.footnote).foregroundStyle(.secondary)
                if store.dataMode == .mock { Button(store.mode == .pro ? store.t("体验 Basic 模式", "Try Basic mode") : store.t("体验 Pro 模式", "Try Pro mode")) {
                    Task { await store.signIn(store.mode == .pro ? .basic : .pro) }
                } }
            }
            Section(store.t("偏好", "Preferences")) {
                Picker(store.t("语言", "Language"), selection: $store.language) { ForEach(AppLanguage.allCases) { Text($0.title).tag($0) } }
                Picker(store.t("外观", "Appearance"), selection: $store.appearance) {
                    Text(store.t("浅色（默认）", "Light (default)")).tag("light")
                    Text(store.t("深色预览", "Dark preview")).tag("dark")
                    Text(store.t("跟随系统", "System")).tag("system")
                }
            }
            Section(store.t("设备与后端", "Devices & backend")) {
                Text(store.dataMode == .mock ? store.t("数据来源：本地共享 JSON 演示数据。未连接传感器、真实登录或 AI。", "Source: local shared JSON fixtures. Sensors, real authentication and AI are not connected.") : store.t("数据来源：已配置 API。来源、时间、预测及可用性以实际返回值为准。", "Source: configured API. Provenance, timestamps, predictions and availability follow actual responses."))
                Text(store.t("MPU6050：运动/跌倒；MLX90614：表面温度；MAX30102：心率/血氧。LCD 1602A 由 ESP32 显示，不是手机端的替代程序。", "MPU6050: motion/fall; MLX90614: surface temperature; MAX30102: HR/SpO₂. The ESP32's LCD 1602A is a separate device display."))
                    .font(.footnote).foregroundStyle(.secondary)
            }
            Section { Button(store.t("退出演示", "Exit demo"), role: .destructive) { store.signOut() } }
        }.navigationTitle(store.t("账户", "Account"))
    }
}
