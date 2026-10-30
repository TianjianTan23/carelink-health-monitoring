import Foundation

enum Scenario: String, CaseIterable, Identifiable {
    case normal, mild, severe, fall, poor, unavailable, offline, stale, noData
    var id: String { rawValue }
}
@MainActor
protocol CareService {
    var rules: DemoRules { get }
    var mode: DataMode { get }
    func authenticate(username: String, password: String, mode: AppMode) async throws -> Session
    func logout() async throws
    func restoreSession() async throws -> Session?
    func rotateSession() async throws
    func getPatient(id: String) async throws -> Patient?
    func getPredictions(patientID: String) async throws -> [Prediction]
    func getAlerts() async throws -> [Alert]
    func acknowledgeAlert(id: String) async throws -> Alert
    func getSession(mode: AppMode) async throws -> Session
    func getPatients() async throws -> [Patient]
    func getHistory(patientID: String) async throws -> [Reading]
    func refresh() async throws -> [Patient]
}
enum ServiceError: Error { case missingResource(String), configuration, invalidResponse, http(Int), forbidden, network, credentialStorage, authenticationBusy, sessionChanged }

@MainActor
final class MockCareService: CareService {
    let mode: DataMode = .mock
    let rules: DemoRules
    var simulateFailure = false
    private func checkConnection() throws { if simulateFailure { throw ServiceError.network } }
    private var session: Session?
    private var ledger = DemoAlertLedger()
    let profiles: [Patient]
    let sessions: DemoSessions
    private(set) var anchor: Date
    private var overrides = [String: String]()

    init(profiles: [Patient], rules: DemoRules, sessions: DemoSessions, now: Date = Date()) {
        self.profiles = profiles; self.rules = rules; self.sessions = sessions; self.anchor = now
    }
    convenience init(bundle: Bundle = .main) throws {
        func load<T: Decodable>(_ name: String, _ type: T.Type) throws -> T {
            guard let url = bundle.url(forResource: name, withExtension: "json") else { throw ServiceError.missingResource(name) }
            return try WireJSON.decoder().decode(type, from: Data(contentsOf: url))
        }
        try self.init(profiles: load("demo-patients", [Patient].self), rules: load("demo-rules", DemoRules.self), sessions: load("demo-sessions", DemoSessions.self))
    }
    func authenticate(username: String, password: String, mode: AppMode) async throws -> Session {
        guard DemoLogin.validate(username:username,password:password) == nil else { throw ServiceError.http(401) }
        return try await getSession(mode:mode)
    }
    func logout() async throws { session=nil;ledger=DemoAlertLedger() }
    func restoreSession() async throws -> Session? { nil } // Mock identities are not persisted.
    func rotateSession() async throws { throw ServiceError.forbidden }
    func getSession(mode: AppMode) async throws -> Session { try checkConnection(); let value = mode == .pro ? sessions.pro : sessions.basic; session = value; return value }
    func getPatients() async throws -> [Patient] {
        try checkConnection()
        guard let session = session else { throw ServiceError.forbidden }
        return profiles.filter { session.patientIds.contains($0.id) }.map { original in
            var patient = original
            patient.reading = makeReading(id: patient.id, scenario: overrides[patient.id] ?? patient.scenario ?? "normal", now: anchor)
            return patient
        }
    }
    func getHistory(patientID: String) async throws -> [Reading] {
        try checkConnection()
        guard session?.patientIds.contains(patientID) == true else { throw ServiceError.forbidden }
        guard let patient = profiles.first(where: { $0.id == patientID }) else { return [] }
        let scenario = overrides[patient.id] ?? patient.scenario ?? "normal"
        if scenario == "noData" { return [] }
        return (0...20).compactMap { index in
            let scene = index < 3 || ["offline", "stale"].contains(scenario) ? scenario : "normal"
            return makeReading(id: patientID, scenario: scene, now: anchor.addingTimeInterval(Double(-index * 30)), offset: index == 0 ? 0 : index % 3 - 1)
        }.filter { $0.measuredAt >= anchor.addingTimeInterval(-600) && $0.measuredAt <= anchor }
    }
    func refresh() async throws -> [Patient] { anchor = Date(); return try await getPatients() }
    func setScenario(patientID: String, scenario: Scenario) { overrides[patientID] = scenario.rawValue; anchor = Date() }
    func reset() { overrides = [:]; ledger = DemoAlertLedger(); anchor = Date() }

    func getPatient(id: String) async throws -> Patient? { guard session?.patientIds.contains(id) == true else { throw ServiceError.forbidden }; return try await getPatients().first { $0.id == id } }
    func getPredictions(patientID: String) async throws -> [Prediction] { try checkConnection(); guard session?.patientIds.contains(patientID) == true else { throw ServiceError.forbidden }; return [] }
    func getAlerts() async throws -> [Alert] {
        let patients = try await getPatients()
        ledger.reconcile(patients, rules: rules, now: Date())
        return ledger.records.filter { session?.patientIds.contains($0.patientID) == true }.map { record in
            Alert(id: record.id.uuidString, patientId: record.patientID, type: record.reasons.contains(.fall) ? "fall" : record.level == .unknown ? "data_quality" : "vital", severity: record.level, occurredAt: record.occurredAt, updatedAt: record.lastObservedAt,
                acknowledgedAt: record.acknowledgedAt, acknowledgedBy: record.acknowledgedAt == nil ? nil : session?.userId,
                status: record.resolvedAt != nil ? "resolved" : record.acknowledgedAt != nil ? "acknowledged" : "new", conditionActive: record.resolvedAt == nil,
                resolvedAt: record.resolvedAt, summary: record.reasons.map { Self.reasonCode($0) }.joined(separator: " · "), source: "mock")
        }
    }
    static func reasonCode(_ reason: ReadingReason) -> String {
        switch reason {
        case .fall: return "fall"
        case .offline: return "offline"
        case .stale: return "stale"
        case .noData: return "no_data"
        case .fallUnavailable: return "fall_unavailable"
        case .stable: return "stable"
        case .unavailable(let key): return key.rawValue + "_unavailable"
        case .poor(let key): return key.rawValue + "_poor"
        case .deviation(let key, let level): return key.rawValue + "_" + level.rawValue
        case .backend(let text): return text
        case .backendPending: return "backend_pending"
        case .backendStale: return "backend_stale"
        }
    }
    func acknowledgeAlert(id: String) async throws -> Alert {
        guard session?.mode == .pro, let uuid = UUID(uuidString: id), (try await getAlerts()).contains(where: { $0.id == id }) else { throw ServiceError.forbidden }
        if let existing = try await getAlerts().first(where: { $0.id == id }), existing.status == "resolved" { throw ServiceError.http(409) }
        ledger.acknowledge(uuid, at: Date())
        guard let result = try await getAlerts().first(where: { $0.id == id }) else { throw ServiceError.invalidResponse }
        return result
    }
    func makeReading(id: String, scenario: String, now: Date, offset: Int = 0) -> Reading? {
        if scenario == "noData" { return nil }
        let index = Int(id.dropFirst()) ?? 1
        let good: (Double) -> Metric = { Metric(value: $0, quality: .good) }
        var r = Reading(patientId: id, deviceId: String(format: "esp32-%02d", index), measuredAt: now,
            receivedAt: now.addingTimeInterval(0.1), connected: true,
            metrics: Metrics(hr: good(Double(72 + index + offset)), spo2: good(98), temp: good(((36.4 + Double(index) * 0.04) * 10).rounded() / 10)),
            fall: FallEvent(active: false, quality: .good, eventAt: nil),
            raw: RawData(accel_m_s2: Vector3(x: 0.12, y: 0.08, z: 9.79), gyro_deg_s: Vector3(x: 0.1, y: 0.2, z: 0.1), ir: 82000, red: 69000, object_temperature_c: 36.6, ambient_temperature_c: 24.1),
            ai: Prediction(state: "not_connected", model: nil, result: nil, confidence: nil), source: "mock", scenario: scenario)
        switch scenario {
        case "mild": r.metrics.hr = good(Double(108 + offset))
        case "warm": r.metrics.temp = good(38.1)
        case "severe": r.metrics.spo2 = good(87)
        case "fall": r.fall = FallEvent(active: true, quality: .good, eventAt: now.addingTimeInterval(-45)); r.raw?.accel_m_s2 = Vector3(x: 3.4, y: 9.6, z: 1.2)
        case "poor": r.metrics.hr = Metric(value: 148, quality: .poor); r.metrics.spo2 = Metric(value: 82, quality: .poor)
        case "unavailable": r.metrics.hr = Metric(value: nil, quality: .unavailable); r.metrics.spo2 = Metric(value: nil, quality: .unavailable); r.raw?.ir = nil; r.raw?.red = nil
        case "offline": r.connected = false
        case "stale": r.measuredAt = now.addingTimeInterval(-180)
        default: break
        }
        r.raw?.object_temperature_c = r.metrics.temp.value
        return r
    }
}


typealias MockDataService = MockCareService
