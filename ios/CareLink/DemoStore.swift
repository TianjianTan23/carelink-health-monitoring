import SwiftUI

enum AppLanguage: String, CaseIterable, Identifiable {
    case zh, en
    var id: String { rawValue }
    var title: String { self == .zh ? "中文" : "English" }
}

@MainActor
final class DemoStore: ObservableObject {
    @Published var language: AppLanguage {
        didSet { UserDefaults.standard.set(language.rawValue, forKey: "carelink-language") }
    }
    @Published private(set) var session: Session?
    @Published private(set) var patients = [Patient]()
    @Published private(set) var histories = [String: [Reading]]()
    @Published var now = Date()
    @Published var autoRefresh = true
    @Published var loading = false
    enum StoreIssue { case resources, signIn, connection, refresh, history, detail }
    @Published private(set) var issue: StoreIssue?
    var error: String? {
        switch issue {
        case .detail: return t("患者详情加载失败或患者不存在，请重试。", "Patient details could not load or patient was not found. Please retry.")
        case .resources: return t("配置或共享资源无效。请检查 carelink-config 与 Xcode 资源。", "Configuration or shared resources are invalid. Check carelink-config and Xcode resources.")
        case .signIn: return t("加载失败，请重试；不会以假数据替代真实 API 错误。", "Loading failed. Retry; API errors never fall back to mock data.")
        case .connection: return t("连接失败（模拟），未收到新数据。上次读数不会被当作新测量。", "Connection failed (simulated). No new data; earlier samples are not new measurements.")
        case .refresh: return t("更新失败，已有读数可能过期。", "Update failed. Existing readings may be stale.")
        case .history: return t("历史记录加载失败，请重试。", "History could not be loaded. Please retry.")
        case nil: return nil
        }
    }
    @Published private(set) var alertRecords = [Alert]()
    @Published private(set) var predictions = [String:[Prediction]]()
    @Published private(set) var patientLoadState: LoadState = .idle
    @Published private(set) var alertLoadState: LoadState = .idle
    @Published private(set) var historyLoadStates = [String:LoadState]()
    @Published private(set) var predictionLoadStates = [String:LoadState]()
    enum AlertIssue { case load, acknowledge }
    @Published private var alertIssue: AlertIssue?
    @Published private var predictionErrorIDs = Set<String>()
    var alertError: String? {
        switch alertIssue {
        case .load: return t("告警加载失败，请重试。", "Alerts could not load. Please retry.")
        case .acknowledge: return t("确认失败，状态未更新，请重试。", "Acknowledgement failed. State was not changed. Please retry.")
        case nil: return nil
        }
    }
    var predictionErrors: [String:String] {
        Dictionary(uniqueKeysWithValues: predictionErrorIDs.map { ($0,t("预测加载失败，请重试；没有生成替代结论。", "Predictions could not load. Retry; no replacement result was generated.")) })
    }
    @Published var alertFeedState: AlertFeedState = .live
    @Published var simulateConnectionFailure = false { didSet { mock?.simulateFailure = simulateConnectionFailure } }
    @Published private(set) var lastSuccessfulUpdate: Date?
    @Published var appearance = UserDefaults.standard.string(forKey: "carelink-appearance") ?? "light" {
        didSet { UserDefaults.standard.set(appearance, forKey: "carelink-appearance") }
    }
    private var refreshing = false
    private var generation = 0
    var serverURL: String { UserDefaults.standard.string(forKey: "carelink-server-url") ?? "http://127.0.0.1:8000" }
    var dataMode: DataMode { service?.mode ?? .mock }
    var configured: Bool { service != nil }
    var alerts: [Alert] {
        alertRecords.filter { session?.patientIds.contains($0.patientId) == true }.sorted { $0.occurredAt > $1.occurredAt }
    }
    func acknowledge(_ id: String) async {
        guard mode == .pro, alerts.contains(where: { $0.id == id }), let service = service else { return }
        do {
            let confirmed = try await service.acknowledgeAlert(id:id)
            if let index = alertRecords.firstIndex(where: { $0.id == confirmed.id }) { alertRecords[index] = confirmed }
            alertIssue = nil
        } catch { alertIssue = .acknowledge }
    }
    func loadAlerts() async {
        guard session != nil, let service = service else { return }
        alertLoadState = .loading
        do { alertRecords = try await service.getAlerts(); alertLoadState = alertRecords.isEmpty ? .empty : .ready; alertIssue = nil }
        catch { alertLoadState = .failed; alertIssue = .load }
    }
    func loadPredictions(_ id: String) async {
        guard patient(id) != nil, let service = service else { return }
        predictionLoadStates[id] = .loading
        do { predictions[id] = try await service.getPredictions(patientID:id); predictionLoadStates[id] = predictions[id]?.isEmpty == true ? .empty : .ready; predictionErrorIDs.remove(id) }
        catch { predictionLoadStates[id] = .failed; predictionErrorIDs.insert(id) }
    }
    private var service: CareService?
    private(set) var mock: MockCareService?

    init() {
        language = AppLanguage(rawValue: UserDefaults.standard.string(forKey: "carelink-language") ?? "zh") ?? .zh
        do {
            let selected = try CareServiceFactory.make()
            self.service = selected; self.mock = selected as? MockCareService
        } catch {
            self.mock = nil; self.service = nil; self.issue = .resources
        }
    }
    var mode: AppMode { session?.mode ?? .pro }
    var rules: DemoRules? { service?.rules }
    var visiblePatients: [Patient] {
        guard let session = session else { return [] }
        return patients.filter { session.patientIds.contains($0.id) }
    }
    func patient(_ id: String) -> Patient? { visiblePatients.first { $0.id == id } }
    func t(_ zh: String, _ en: String) -> String { language == .zh ? zh : en }
    func signIn(_ mode: AppMode) async {
        guard let service = service else { return }
        loading = true; patientLoadState = .loading; defer { loading = false }
        do {
            let authorizedSession = try await service.getSession(mode: mode)
            let loaded = try await service.refresh()
            session = authorizedSession; patients = loaded; histories = [:]; issue = nil; now = Date()
            lastSuccessfulUpdate = now; patientLoadState = loaded.isEmpty ? .empty : .ready; await loadAlerts()
        } catch { self.issue = .signIn; patientLoadState = .failed }
    }
    func authenticate(username: String, password: String, baseURL: String) async {
        loading = true; defer { loading = false }
        generation += 1
        let expected = generation
        do {
            let selected = try CareServiceFactory.make(baseURL: baseURL.trimmingCharacters(in: .whitespacesAndNewlines))
            let authorized = try await selected.authenticate(username: username, password: password)
            let loaded = try await selected.refresh()
            guard expected == generation else { return }
            service = selected; mock = nil; session = authorized; patients = loaded
            UserDefaults.standard.set(baseURL, forKey: "carelink-server-url")
            histories = [:]; predictions = [:]; issue = nil; now = Date(); lastSuccessfulUpdate = now
            patientLoadState = loaded.isEmpty ? .empty : .ready
            await loadAlerts()
        } catch { issue = .signIn; patientLoadState = .failed }
    }
    func signOut() { generation += 1; let previous = service; Task { await previous?.logout() }; session = nil; patients = []; histories = [:]; alertRecords = []; predictions = [:]; predictionErrorIDs = []; alertIssue = nil; patientLoadState = .idle; alertLoadState = .idle; historyLoadStates = [:]; predictionLoadStates = [:]; lastSuccessfulUpdate = nil; simulateConnectionFailure = false; alertFeedState = .live; issue = nil }
    func refresh() async {
        guard let service = service, session != nil, !refreshing else { return }
        refreshing = true; defer { refreshing = false }
        let expected = generation
        if simulateConnectionFailure && dataMode == .mock {
            now = Date(); patientLoadState = .failed
            issue = .connection
            return
        }
        if patients.isEmpty { patientLoadState = .loading }
        do {
            let refreshed = try await service.refresh()
            guard expected == generation else { return }
            patients = refreshed; now = Date(); issue = nil; lastSuccessfulUpdate = now; patientLoadState = patients.isEmpty ? .empty : .ready; await loadAlerts()
            for id in Array(histories.keys) where patient(id) != nil { histories[id] = try await service.getHistory(patientID: id); historyLoadStates[id] = .ready }
            for id in Array(predictions.keys) where patient(id) != nil { await loadPredictions(id) }
        } catch { self.issue = .refresh; patientLoadState = .failed }
    }
    func loadPatientDetail(_ id: String) async {
        guard patient(id) != nil, let service = service else { return }
        do {
            if let detail = try await service.getPatient(id:id), let index = patients.firstIndex(where: { $0.id == id }) { patients[index] = detail }
            else { patients.removeAll { $0.id == id }; issue = .detail }
        } catch { issue = .detail }
    }
    func loadHistory(_ id: String) async {
        guard patient(id) != nil, let service = service else { return }
        historyLoadStates[id] = .loading
        do { histories[id] = try await service.getHistory(patientID: id); historyLoadStates[id] = histories[id]?.isEmpty == true ? .empty : .ready }
        catch { self.issue = .history; historyLoadStates[id] = .failed }
    }
    func applyScenario(_ scenario: Scenario, patientID: String) async {
        guard patient(patientID) != nil else { return }
        mock?.setScenario(patientID: patientID, scenario: scenario)
        await refresh()
    }
    func reset() async { mock?.reset(); alertRecords = []; predictions = [:]; predictionErrorIDs = []; alertIssue = nil; patientLoadState = .idle; alertLoadState = .idle; historyLoadStates = [:]; predictionLoadStates = [:]; simulateConnectionFailure = false; alertFeedState = .live; await refresh() }
    func report(_ reading: Reading?) -> StatusReport {
        guard let rules = rules else { return StatusReport(level: .unknown, reasons: [.noData], incomplete: true) }
        return dataMode == .mock ? Monitoring.triage(reading, rules: rules, now: now) : Monitoring.liveReport(reading, rules:rules, now:now)
    }
    func value(_ reading: Reading?, _ key: MetricKey) -> String {
        guard let rules = rules else { return "—" }
        return Monitoring.display(reading, key: key, rules: rules, now: now)
    }
    func fresh(_ reading: Reading?) -> Bool { rules.map { Monitoring.isFresh(reading, rules: $0, now: now) } ?? false }
    func metricName(_ key: MetricKey) -> String {
        switch key { case .hr: return t("心率", "Heart rate"); case .spo2: return t("血氧", "SpO₂"); case .temp: return t("温度", "Temperature") }
    }
    func levelName(_ level: RiskLevel) -> String {
        switch level {
        case .red: return "CRITICAL"
        case .yellow: return "WARNING"
        case .green: return "NORMAL"
        case .unknown: return t("数据待确认", "Data unverified")
        }
    }
    func reason(_ reason: ReadingReason) -> String {
        switch reason {
        case .backend(let text): return text
        case .backendPending: return t("等待后端状态判断", "Awaiting backend assessment")
        case .backendStale: return t("后端判断已过期", "Backend assessment is stale")
        case .noData: return t("尚无读数", "No readings yet")
        case .fall: return t("检测到跌倒事件，待人工核实", "Fall event detected; needs human review")
        case .offline: return t("设备离线", "Device offline")
        case .stale: return t("数据已过期", "Readings are stale")
        case .stable: return t("各项数据处于演示平稳范围", "All readings are within the demo's stable ranges")
        case .fallUnavailable: return t("跌倒监测暂不可用", "Fall monitoring unavailable")
        case .unavailable(let key): return metricName(key) + t("暂不可用", " unavailable")
        case .poor(let key): return metricName(key) + t("信号不稳", " signal unreliable")
        case .deviation(let key, let level): return metricName(key) + (level == .red ? t("超出演示严重范围", " outside the severe demo range") : t("超出演示平稳范围", " outside the stable demo range"))
        }
    }
    func firstReason(_ report: StatusReport) -> String {
        report.reasons.first.map { reason($0) } ?? t("后端未提供详细说明", "Backend did not provide a detailed explanation")
    }
    func qualityNote(_ reading: Reading?, key: MetricKey) -> String {
        guard let reading = reading else { return t("尚无数据", "No data yet") }
        let current = key.metric(in: reading)
        if key == .hr, (!fresh(reading) || !Monitoring.usable(current)),
           let number = current.displayValue ?? current.value, number.isFinite,
           now.timeIntervalSince(current.lastValidAt ?? reading.measuredAt) <= 30 {
            let age = Int(max(0, now.timeIntervalSince(current.lastValidAt ?? reading.measuredAt)))
            return t("上次有效值 · \(age)秒前 · 不参与分类", "Last valid value · \(age)s ago · Not a current measurement")
        }
        guard fresh(reading) else { return reading.connected ? t("数据已过期", "Stale reading") : t("设备离线", "Device offline") }
        let metric = key.metric(in: reading)
        guard Monitoring.usable(metric) else { return metric.quality == .poor ? t("信号不稳，请重新采集", "Unreliable signal; collect a new sample") : t("暂不可用", "Unavailable") }
        return key == .temp ? t("表面测温 · 待校准", "Surface reading · Calibration pending") : reading.source == "mock" ? t("模拟读数", "Mock reading") : reading.source == "device" ? t("来源：设备记录", "Source: device record") : t("来源：后端记录", "Source: backend record")
    }
    func scenarioName(_ scene: Scenario) -> String {
        switch scene {
        case .normal: return t("数据平稳", "Stable readings")
        case .mild: return t("轻度异常", "Mild deviation")
        case .severe: return t("严重异常", "Severe deviation")
        case .fall: return t("跌倒警报", "Fall alert")
        case .poor: return t("MAX 信号不稳", "MAX signal unreliable")
        case .unavailable: return t("KY-005 备用模式", "KY-005 fallback mode")
        case .offline: return t("设备离线", "Device offline")
        case .stale: return t("数据过期", "Stale readings")
        case .noData: return t("尚无数据", "No data yet")
        }
    }
    func name(_ patient: Patient) -> String {
        guard language == .en, dataMode == .mock else { return patient.name }
        return ["p001": "Lin Zhiqiu", "p002": "Zhou Yuanshan", "p003": "Chen Jinghe", "p004": "Xu Wangshu", "p005": "Shen Huaichuan", "p006": "Lu Qinghe", "p007": "Gu Yunzhou", "p008": "Su Wanqing"][patient.id] ?? patient.name
    }
    func historyText(_ patient: Patient) -> String {
        guard language == .en, dataMode == .mock else { return patient.history }
        return ["p001": "History of hypertension; regular follow-up.", "p002": "Chronic respiratory disease history; monitor daily activity.", "p003": "Postoperative rehabilitation; uses a walking aid.", "p004": "No notable medical history (fictional profile).", "p005": "History of hypertension; routine follow-up.", "p006": "History of diabetes; ongoing follow-up.", "p007": "Limited joint mobility; needs support with daily activities.", "p008": "No notable medical history (fictional profile)."][patient.id] ?? patient.history
    }
    func time(_ date: Date?) -> String {
        guard let date = date else { return "—" }
        let formatter = DateFormatter(); formatter.locale = Locale(identifier: language == .zh ? "zh_CN" : "en_GB")
        formatter.timeZone = .current; formatter.dateFormat = "HH:mm:ss"
        return formatter.string(from: date)
    }
}
