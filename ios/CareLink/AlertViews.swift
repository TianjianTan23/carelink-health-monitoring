import SwiftUI

@MainActor
struct AlertRow: View {
    @EnvironmentObject private var store: DemoStore
    let alert: Alert
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let patient = store.patient(alert.patientID) {
                HStack(spacing: CareDesign.Space.s12) {
                    AvatarView(patient: patient)
                    VStack(alignment: .leading, spacing: 4) {
                        Text(store.name(patient)).font(.headline)
                        Text(patient.id).font(.caption2).foregroundStyle(.secondary)
                    }
                }
            }
            StatusBadge(report: StatusReport(level: alert.level, reasons: alert.reasons, incomplete: false))
            Text(store.reason(alert.reasons.first ?? .noData)).font(.subheadline)
            Text("\(store.t("发生", "Occurred")): \(store.time(alert.occurredAt))").font(.caption).foregroundStyle(.secondary)
            Text(alert.resolvedAt == nil ? store.t("当前仍存在", "Still present") : store.t("当前已不再触发规则", "No longer triggering the rule"))
                .font(.caption).foregroundStyle(.secondary)
            Label(alert.acknowledgedAt == nil ? store.t("待确认", "Unacknowledged") : (store.dataMode == .mock ? store.t("本地已确认", "Acknowledged locally") : store.t("服务器已确认", "Server confirmed")),
                systemImage: alert.acknowledgedAt == nil ? "circle" : "checkmark.circle")
                .font(.caption).foregroundStyle(Color("AccentColor"))
        }.padding(.vertical, 6).accessibilityElement(children: .combine)
    }
}

@MainActor
struct AlertsView: View {
    @EnvironmentObject private var store: DemoStore
    @State private var filter = "all"
    private var visibleAlerts: [Alert] {
        store.alerts.filter { filter == "all" || $0.status == filter }.sorted {
            if ($0.status == "new") != ($1.status == "new") { return $0.status == "new" }
            if $0.level.rank != $1.level.rank { return $0.level.rank < $1.level.rank }
            return $0.occurredAt > $1.occurredAt
        }
    }
    var body: some View {
        List {
            Section {
                DemoNotice(); ErrorNotice()
                if store.alertLoadState == .loading { ProgressView(store.t("加载告警…", "Loading alerts…")) }
                if let error = store.alertError {
                    Text(error).foregroundStyle(Color("CareRed"))
                    Button(store.t("重试", "Retry")) { Task { await store.loadAlerts() } }
                }
            }
            if store.alertFeedState != .live {
                Section {
                    Text(store.t("页面状态演示，不代表真实服务器响应。", "Page-state simulation; not a real server response.")).font(.caption).foregroundStyle(.secondary)
                    if store.alertFeedState == .loading {
                        ProgressView(store.t("正在加载告警…", "Loading alerts…"))
                    } else if store.alertFeedState == .failed {
                        Label(store.t("告警加载失败（模拟）", "Alerts could not load (simulated)"), systemImage: "wifi.slash")
                    } else {
                        ContentUnavailableView(store.t("暂无告警记录（模拟）", "No alert records (simulated)"), systemImage: "bell.slash")
                    }
                    Button(store.t("返回实际演示记录", "Return to demo records")) { store.alertFeedState = .live }
                }
            } else {
                if store.alerts.isEmpty && store.alertLoadState == .empty {
                    ContentUnavailableView(store.t("暂无告警记录", "No alert records"), systemImage: "checkmark.shield")
                }
                Section {
                    Picker(store.t("处理状态", "Review status"), selection: $filter) {
                        Text(store.t("全部", "All")).tag("all")
                        Text(store.t("待确认", "New")).tag("new")
                        Text(store.t("已确认", "Reviewed")).tag("acknowledged")
                        Text(store.t("条件结束", "Ended")).tag("resolved")
                    }.pickerStyle(.menu)
                }
                Section(store.t("新告警与历史", "New alerts & history")) {
                    if visibleAlerts.isEmpty && !store.alerts.isEmpty { Text(store.t("此筛选下没有记录", "No records for this filter")).foregroundStyle(.secondary) }
                    ForEach(visibleAlerts) { alert in
                        NavigationLink { AlertDetailView(alertID: alert.id) } label: { AlertRow(alert: alert) }
                    }
                }
            }
            Section {
                Text(store.t("请结合采集时间与设备状态查看数据。确认不解除事件；模拟模式存在内存，API 模式等待服务器确认。", "Check sample time and device state. Acknowledgement never clears an event. Mock mode stores in memory; API mode waits for server confirmation."))
                    .font(.footnote).foregroundStyle(.secondary)
            }
        }.listStyle(.insetGrouped).scrollContentBackground(.hidden).background(Color("CareBackground"))
            .navigationTitle(store.t("告警与提醒", "Alerts"))
            .task { await store.loadAlerts() }
            .refreshable { await store.loadAlerts() }
            .toolbar { ToolbarItem(placement: .topBarTrailing) { LanguageButton() } }
    }
}

@MainActor
struct AlertDetailView: View {
    @EnvironmentObject private var store: DemoStore
    let alertID: String
    @State private var confirm = false
    var body: some View {
        List {
            if let alert = store.alerts.first(where: { $0.id == alertID }), let patient = store.patient(alert.patientID) {
                Section { DemoNotice(); AlertRow(alert: alert); if let error = store.alertError { Text(error).foregroundStyle(Color("CareRed")) } }
                Section(store.t("告警详情", "Alert details")) {
                    ForEach(Array(alert.reasons.enumerated()), id: \.offset) { _, reason in Text(store.reason(reason)) }
                    LabeledContent(store.t("发生时间", "Occurred"), value: store.time(alert.occurredAt))
                    LabeledContent(store.t("最近观察", "Last observed"), value: store.time(alert.lastObservedAt))
                    LabeledContent(store.t("确认时间", "Acknowledged"), value: store.time(alert.acknowledgedAt))
                    if let resolved = alert.resolvedAt { LabeledContent(store.t("状态变更", "Condition changed"), value: store.time(resolved)) }
                    StatusBadge(report: store.report(patient.reading))
                    Text(store.firstReason(store.report(patient.reading))).font(.footnote)
                }
                if store.mode == .pro {
                    Section {
                        NavigationLink(store.t("打开患者详情", "Open patient details")) { PatientDetailView(patientID: patient.id) }

                    }
                } else {
                    Text(store.t("这是家属可见的关联患者提醒；告警处理由医护角色操作。", "This reminder is for your linked patient. Clinicians handle acknowledgements.")).font(.footnote).foregroundStyle(.secondary)
                }
            } else {
                ContentUnavailableView(store.t("记录不可用或无访问权限", "Record unavailable or outside your scope"), systemImage: "lock")
            }
        }.listStyle(.insetGrouped).scrollContentBackground(.hidden).background(Color("CareBackground"))
            .safeAreaInset(edge: .bottom) {
                if store.mode == .pro, let alert = store.alerts.first(where: { $0.id == alertID }), store.patient(alert.patientID) != nil {
                    VStack(spacing: CareDesign.Space.s8) {
                        Button { confirm = true } label: {
                            Label(alert.status == "new" ? store.t("确认告警", "Acknowledge alert") : alert.status == "acknowledged" ? store.t("已记录确认", "Review recorded") : store.t("条件已结束", "Condition ended"), systemImage: "checkmark.circle")
                                .frame(maxWidth: .infinity, minHeight: 32)
                        }.buttonStyle(.borderedProminent).controlSize(.large).disabled(alert.status != "new" || store.loading)
                            .accessibilityIdentifier("acknowledgeAlert")
                        Text(store.t("确认不代表风险解除", "Acknowledgement does not resolve risk")).font(.caption).foregroundStyle(.secondary)
                    }.padding(CareDesign.Space.s16).background(.regularMaterial)
                }
            }
            .navigationTitle(store.t("告警详情", "Alert details")).navigationBarTitleDisplayMode(.inline)
            .confirmationDialog(store.t("确认已查看此演示告警？", "Acknowledge this demo alert?"), isPresented: $confirm, titleVisibility: .visible) {
                Button(store.t("确认", "Acknowledge")) { Task { await store.acknowledge(alertID) } }
                Button(store.t("取消", "Cancel"), role: .cancel) {}
            } message: {
                Text(store.t("确认不代表风险解除。API 模式会提交到已配置后端；模拟模式只保存在内存。", "Acknowledgement does not resolve risk. API mode submits to the configured backend; mock mode stores it in memory."))
            }
    }
}
