import SwiftUI
import Charts

private struct TrendPoint: Identifiable {
    let id: Int
    let time: Date
    let value: Double
    let segment: Int
}

@MainActor
struct PatientDetailView: View {
    @EnvironmentObject private var store: DemoStore
    let patientID: String
    @State private var metric: MetricKey = .hr
    @State private var section: PatientSection = .overview
    @State private var showAllHistory = false
    var history: [Reading] { store.histories[patientID] ?? [] }

    private func points(for patient: Patient) -> [TrendPoint] {
        guard store.fresh(patient.reading) else { return [] }
        var result = [TrendPoint](), segment = 0
        for (index, reading) in history.reversed().enumerated() {
            let value = metric.metric(in: reading)
            if reading.connected && reading.scenario != "stale" && (store.rules.map { Monitoring.sampleUsable(reading, key: metric, rules: $0) } == true), let number = value.value {
                result.append(TrendPoint(id: index, time: reading.measuredAt, value: number, segment: segment))
            } else { segment += 1 }
        }
        return result
    }
    private func json<T: Encodable>(_ value: T?) -> String {
        guard let value = value, let data = try? WireJSON.encoder().encode(value) else { return "null" }
        return String(decoding: data, as: UTF8.self)
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: CareDesign.Space.s20) {
                if store.mode == .pro, let patient = store.patient(patientID) {
                    DemoNotice(); ErrorNotice()
                    HStack(spacing: 12) {
                        AvatarView(patient: patient)
                        VStack(alignment: .leading, spacing: 4) {
                            Text(store.name(patient)).font(.title2.bold())
                            Text("\(patient.age) · \(store.t(patient.sex, patient.sex == "女" ? "Female" : "Male")) · \(store.t("床位", "Bed")) \(patient.bed)")
                                .font(.subheadline).foregroundStyle(.secondary)
                        }
                    }
                    Picker(store.t("患者信息分区", "Patient information sections"), selection: $section) {
                        ForEach(PatientSection.allCases) { Text($0.title(store.language)).tag($0) }
                    }.pickerStyle(.segmented).accessibilityIdentifier("patientSections")
                    if section == .overview {
                    let report = store.report(patient.reading)
                    VStack(alignment: .leading, spacing: 10) {
                        StatusBadge(report: report)
                        ForEach(Array(report.reasons.enumerated()), id: \.offset) { _, reason in
                            Text(store.reason(reason)).font(.footnote)
                        }
                    }.frame(maxWidth: .infinity, alignment: .leading).padding(16)
                        .background(report.level.color.opacity(0.09), in: RoundedRectangle(cornerRadius: CareDesign.Corner.card, style: .continuous))
                    Label("\(store.t("最近采集", "Last sample")): \(store.time(patient.reading?.measuredAt))", systemImage: "clock").font(.caption).foregroundStyle(.secondary)
                    MetricGrid(reading: patient.reading)
                    GroupBox {
                        VStack(alignment: .leading, spacing: 12) {
                            Text(store.t("告警历史", "Alert history")).font(.headline)
                            let records = store.alerts.filter { $0.patientID == patientID }
                            if records.isEmpty { Text(store.t("暂无告警记录", "No alert records")).foregroundStyle(.secondary) }
                            ForEach(records) { alert in
                                NavigationLink { AlertDetailView(alertID: alert.id) } label: { AlertRow(alert: alert) }
                            }
                        }.frame(maxWidth: .infinity, alignment: .leading)
                    }
                    GroupBox {
                        VStack(alignment: .leading, spacing: 14) {
                            Text(store.t("最近 10 分钟趋势", "Last 10 minutes: trends")).font(.headline)
                            Picker(store.t("指标", "Metric"), selection: $metric) {
                                ForEach(MetricKey.allCases) { Text(store.metricName($0)).tag($0) }
                            }.pickerStyle(.segmented)
                            let trend = points(for: patient)
                            if trend.count < 2 {
                                Text(store.t("暂无可用趋势数据，请检查设备与数据质量。", "No usable trend data. Check the device and data quality."))
                                    .foregroundStyle(.secondary).frame(maxWidth: .infinity, minHeight: 140)
                            } else {
                                Chart(trend) { point in
                                    LineMark(x: .value("Time", point.time), y: .value(metric.unit, point.value), series: .value("Segment", point.segment))
                                        .foregroundStyle(Color("AccentColor"))
                                }.chartLegend(.hidden).chartYScale(domain: .automatic(includesZero: false)).frame(height: 180)
                                    .accessibilityLabel(store.t("十分钟模拟趋势，缺失读数不连线。", "Ten-minute mock trend; gaps indicate invalid readings."))
                            }
                            Text(store.dataMode == .mock ? store.t("每 30 秒一条模拟记录；非有效读数不连线。", "Mock samples every 30 seconds; invalid readings create gaps.") : store.t("仅显示 API 返回的采样；不会用模拟数据补齐。", "Only API samples are shown; gaps are not filled with mock data.")).font(.caption).foregroundStyle(.secondary)
                        }.padding(.vertical, 4)
                    }
                    GroupBox {
                        VStack(alignment: .leading, spacing: 12) {
                            Text(store.t("个人档案", "Patient profile")).font(.headline)
                            LabeledContent(store.t("入住日期", "Admission date"), value: patient.admittedAt)
                            LabeledContent(store.t("过敏记录", "Allergies"), value: store.t(patient.allergies, "Not recorded (demo)"))
                            Divider()
                            Text(store.t("既往病史 / 病例摘要", "Medical history / case summary")).font(.subheadline)
                            Text(store.historyText(patient)).font(.body)
                            Text(store.dataMode == .mock ? store.t("以上档案均为虚构。", "All profile information is fictional.") : store.t("档案来自授权 API。", "Profile from the authorized API.")).font(.caption).foregroundStyle(.secondary)
                        }.frame(maxWidth: .infinity, alignment: .leading)
                    }
                    }
                    if section == .history {
                    GroupBox {
                        VStack(alignment: .leading, spacing: CareDesign.Space.s12) {
                            Text(store.t("最近 10 分钟数据", "Last 10 minutes: readings")).font(.headline)
                            Text("\(history.count) \(store.t("条返回采样 · 设备本地时间", "returned samples · Device local time"))").font(.caption).foregroundStyle(.secondary)
                            if store.historyLoadStates[patientID] == .loading { ProgressView(store.t("加载历史…", "Loading history…")) }
                            if store.historyLoadStates[patientID] == .failed {
                                Text(store.t("历史加载失败", "History could not load")).foregroundStyle(Color("CareRed"))
                                Button(store.t("重试历史", "Retry history")) { Task { await store.loadHistory(patientID) } }
                            }
                            if history.isEmpty && store.historyLoadStates[patientID] == .empty { Text(store.t("尚无历史数据", "No history yet")).foregroundStyle(.secondary) }
                            ForEach(Array((showAllHistory ? history : Array(history.prefix(6))).enumerated()), id: \.offset) { _, reading in
                                VStack(alignment: .leading, spacing: 5) {
                                    HStack {
                                        Text(store.time(reading.measuredAt)).font(.subheadline.monospacedDigit())
                                        Spacer()
                                        if reading.fall.active { Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.red).accessibilityLabel(store.t("跌倒事件待核实", "Unverified fall event")) }
                                    }
                                    HStack {
                                        ForEach(MetricKey.allCases) { key in
                                            let item = key.metric(in: reading)
                                            Text("\(reading.connected && reading.scenario != "stale" && (store.rules.map { Monitoring.sampleUsable(reading, key: key, rules: $0) } == true) ? (key == .temp ? String(format: "%.1f", item.value ?? 0) : String(Int((item.value ?? 0).rounded()))) : "—") \(key.unit)")
                                                .font(.caption.monospacedDigit()).frame(maxWidth: .infinity, alignment: .leading)
                                        }
                                    }
                                    Text(reading.connected && reading.scenario != "stale" ? store.t("历史采样；数值仍须结合信号质量", "Historical sample; consider signal quality") : store.t("离线或过期的历史记录", "Offline or stale historical record"))
                                        .font(.caption2).foregroundStyle(.secondary)
                                }.padding(.vertical, 4)
                                Divider()
                            }
                            if history.count > 6 { Button(showAllHistory ? store.t("收起记录", "Show fewer") : store.t("查看全部记录", "Show all readings")) { showAllHistory.toggle() } }
                        }
                    }
                    }
                    if section == .data {
                    Label(store.t("测量与预测分开查看", "Measurements and predictions are separate"), systemImage: "info.circle").font(.footnote).foregroundStyle(.secondary)
                    GroupBox {
                        VStack(alignment: .leading, spacing: CareDesign.Space.s12) {
                            Label(store.t("AI 预测", "AI predictions"), systemImage: "waveform.path.ecg").font(.headline)
                            if store.predictionLoadStates[patientID] == .loading { ProgressView(store.t("加载预测…", "Loading predictions…")) }
                            if let error = store.predictionErrors[patientID] {
                                Text(error).foregroundStyle(Color("CareRed"))
                                Button(store.t("重试", "Retry")) { Task { await store.loadPredictions(patientID) } }
                            }
                            let outputs = store.predictions[patientID] ?? []
                            if outputs.isEmpty && store.predictionLoadStates[patientID] == .empty {
                                Text(store.t("暂无 AI 输出；不会生成替代结论。", "No AI output; no replacement result is generated.")).foregroundStyle(.secondary)
                            }
                            ForEach(Array(outputs.enumerated()), id: \.offset) { _, prediction in
                                VStack(alignment: .leading, spacing: 10) {
                                    LabeledContent(store.t("预测时间", "Predicted at"), value: store.time(prediction.predictedAt))
                                    LabeledContent(store.t("输入采集时间", "Input measured at"), value: store.time(prediction.inputsMeasuredAt))
                                    LabeledContent(store.t("模型 / 版本", "Model / version"), value: "\(prediction.model ?? "—") / \(prediction.modelVersion ?? "—")")
                                    LabeledContent(store.t("状态", "State"), value: prediction.state)
                                    LabeledContent(store.t("来源", "Source"), value: prediction.source ?? "—")
                                    LabeledContent(store.t("返回置信度", "Returned confidence"), value: prediction.confidence.map { String($0) } ?? "—")
                                    if let meaning = prediction.confidenceMeaning { Text(meaning).font(.caption) }
                                    if prediction.state == "available" { Text(json(prediction.result)).font(.system(.caption, design: .monospaced)).textSelection(.enabled) }
                                    Divider()
                                }
                            }
                            Text(store.t("预测与测量独立展示；只显示实际返回的置信度。", "Predictions are separate from measurements. Confidence appears only when actually returned.")).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    GroupBox {
                        DisclosureGroup(store.t("原始传感器数据", "Raw sensor data")) {
                            VStack(alignment: .leading, spacing: 12) {
                                Text(store.time(patient.reading?.measuredAt)).font(.caption)
                                if let raw = patient.reading?.raw { Text(json(raw)).font(.system(.caption, design: .monospaced)).textSelection(.enabled) } else { Text(store.t("原始数据未提供或无访问权限。", "Raw data is unavailable or not permitted.")) }
                                Text(store.t("加速度 m/s²、角速度 °/s、原始信号与 BPM 分开。", "Acceleration: m/s²; angular velocity: °/s; raw signals are separate from BPM.")).font(.caption).foregroundStyle(.secondary)
                            }.frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                    }
                    Text(store.t("温度为表面测温演示值；这些范围只演示交互，没有医学权威性。", "Temperature is a mock surface reading. Ranges demonstrate interactions and are not medically validated."))
                        .font(.footnote).foregroundStyle(.secondary)
                } else {
                    ContentUnavailableView(store.t("该患者不在当前角色授权范围", "Patient is outside this role's scope"), systemImage: "lock")
                }
            }.padding(CareDesign.Space.s20)
        }.groupBoxStyle(CareGroupBoxStyle()).background(Color("CareBackground")).navigationTitle(store.t("患者详情", "Patient details"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { LanguageButton() } }
            .task(id: patientID) { await store.loadPatientDetail(patientID); await store.loadHistory(patientID); await store.loadPredictions(patientID) }
            .refreshable { await store.refresh(); await store.loadPatientDetail(patientID); await store.loadHistory(patientID); await store.loadPredictions(patientID) }
    }
}
