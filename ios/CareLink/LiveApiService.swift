import Foundation

struct APIEndpoints: Codable {
    var login: String? = nil
    var logout: String? = nil
    var session: String
    var patients: String
    var patient: String
    var readings: String
    var predictions: String
    var alerts: String
    var acknowledge: String
}
struct ServiceConfiguration: Codable {
    var mode: DataMode
    var baseUrl: String
    var apiConfirmed: Bool
    var staleAfterSeconds: Double
    var endpoints: APIEndpoints
    func validate() throws {
        guard staleAfterSeconds > 0, staleAfterSeconds.isFinite else { throw ServiceError.configuration }
        if mode == .live {
            guard apiConfirmed, let url = URL(string: baseUrl), ["http", "https"].contains(url.scheme ?? ""), url.host != nil, url.user == nil, url.password == nil, url.query == nil, url.fragment == nil else { throw ServiceError.configuration }
        }
        for path in [endpoints.session,endpoints.patients,endpoints.patient,endpoints.readings,endpoints.predictions,endpoints.alerts,endpoints.acknowledge] + [endpoints.login, endpoints.logout].compactMap({ $0 }) {
            guard path.hasPrefix("/"), !path.hasPrefix("//"), !path.contains("://") else { throw ServiceError.configuration }
        }
    }
}
enum WireValidation {
    static func prediction(_ value: Prediction) throws {
        guard ["not_connected","pending","available","failed","unavailable"].contains(value.state), value.confidence?.isFinite != false, value.confidence.map({ (0...1).contains($0) }) != false else { throw ServiceError.invalidResponse }
    }
    static func reading(_ value: Reading) throws {
        guard !value.patientId.isEmpty, !value.deviceId.isEmpty, ["mock","device","backend"].contains(value.source) else { throw ServiceError.invalidResponse }
        for key in MetricKey.allCases { if let number = key.metric(in: value).value, !number.isFinite { throw ServiceError.invalidResponse } }
        try prediction(value.ai)
        if let assessment = value.assessment, assessment.origin != "backend" { throw ServiceError.invalidResponse }
    }
    static func patient(_ value: Patient) throws {
        guard !value.id.isEmpty, !value.name.isEmpty, value.age >= 0 else { throw ServiceError.invalidResponse }
        if let reading = value.reading { guard reading.patientId == value.id else { throw ServiceError.invalidResponse }; try self.reading(reading) }
    }
    static func alert(_ value: Alert) throws {
        guard !value.id.isEmpty, !value.patientId.isEmpty, !value.type.isEmpty, ["new","acknowledged","resolved"].contains(value.status), ["mock","device","backend"].contains(value.source) else { throw ServiceError.invalidResponse }
        if value.status == "acknowledged", value.acknowledgedAt == nil { throw ServiceError.invalidResponse }
        if value.status == "resolved", value.resolvedAt == nil || value.conditionActive { throw ServiceError.invalidResponse }
    }
}

// Implements the authenticated CareLink FastAPI contract.
// Transport is injectable for tests. Production uses URLSession; never substitutes fixtures.
@MainActor
final class LiveApiService: CareService {
    typealias Transport = (URLRequest) async throws -> (Data, HTTPURLResponse)
    let mode: DataMode = .live
    let rules: DemoRules
    let configuration: ServiceConfiguration
    private let transport: Transport
    private let clock: () -> Date
    private var session: Session?
    init(configuration: ServiceConfiguration, rules: DemoRules, clock: @escaping () -> Date = Date.init, transport: Transport? = nil) throws {
        try configuration.validate()
        guard configuration.mode == .live else { throw ServiceError.configuration }
        self.configuration = configuration; self.clock = clock
        var displayRules = rules; displayRules.staleAfterSeconds = configuration.staleAfterSeconds; self.rules = displayRules
        let sessionConfiguration = URLSessionConfiguration.ephemeral
        sessionConfiguration.requestCachePolicy = .reloadIgnoringLocalCacheData
        let httpSession = URLSession(configuration: sessionConfiguration)
        self.transport = transport ?? { request in
            let (data, response) = try await httpSession.data(for: request)
            guard let http = response as? HTTPURLResponse else { throw ServiceError.invalidResponse }
            return (data,http)
        }
    }
    private func path(_ template: String, id: String? = nil) -> String {
        let safe = id?.addingPercentEncoding(withAllowedCharacters: CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-_"))) ?? ""
        return template.replacingOccurrences(of: "{id}", with: safe)
    }
    private func request<T: Decodable>(_ path: String, method: String = "GET", body: Data? = nil, empty: T? = nil) async throws -> T {
        let base = configuration.baseUrl.hasSuffix("/") ? String(configuration.baseUrl.dropLast()) : configuration.baseUrl
        guard let url = URL(string: base + path) else { throw ServiceError.configuration }
        var request = URLRequest(url: url, timeoutInterval: 8)
        request.httpMethod = method; request.setValue("application/json", forHTTPHeaderField: "Accept")
        if method == "POST" { request.httpBody = body ?? Data("{}".utf8); request.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        if method != "GET", let token = session?.csrfToken { request.setValue(token, forHTTPHeaderField: "X-CSRF-Token") }
        let pair: (Data,HTTPURLResponse)
        do { pair = try await transport(request) } catch let error as ServiceError { throw error } catch { throw ServiceError.network }
        let (data,response) = pair
        if response.statusCode == 204, let empty = empty { return empty }
        guard (200...299).contains(response.statusCode) else { throw ServiceError.http(response.statusCode) }
        do { return try WireJSON.decoder().decode(T.self, from: data) } catch { throw ServiceError.invalidResponse }
    }
    private func allowed(_ id: String) throws { guard session?.patientIds.contains(id) == true else { throw ServiceError.forbidden } }
    func authenticate(username: String, password: String) async throws -> Session {
        let body = try JSONSerialization.data(withJSONObject: ["username": username, "password": password])
        let value: Session = try await request(configuration.endpoints.login ?? "/api/login", method: "POST", body: body)
        guard ["clinician", "patient", "family"].contains(value.role), value.mode != .pro || value.role == "clinician" else { throw ServiceError.invalidResponse }
        session = value
        return value
    }
    func logout() async {
        struct SignedOut: Decodable { let status: String }
        let _: SignedOut? = try? await request(configuration.endpoints.logout ?? "/api/logout", method: "POST")
        session = nil
    }
    func getSession(mode: AppMode) async throws -> Session {
        let value: Session = try await request(configuration.endpoints.session)
        guard ["clinician","family","patient"].contains(value.role), value.mode != .pro || value.role == "clinician" else { throw ServiceError.invalidResponse }
        session = value; return value // ignores requested demo mode: role comes only from the server
    }
    func getPatients() async throws -> [Patient] {
        guard session != nil else { throw ServiceError.forbidden }
        let values: [Patient] = try await request(configuration.endpoints.patients, empty: [])
        for p in values { try allowed(p.id); try WireValidation.patient(p) }
        return values
    }
    func getPatient(id: String) async throws -> Patient? {
        try allowed(id)
        do { let value: Patient = try await request(path(configuration.endpoints.patient,id:id)); guard value.id == id else { throw ServiceError.invalidResponse }; try WireValidation.patient(value); return value }
        catch ServiceError.http(404) { return nil }
    }
    func getHistory(patientID: String) async throws -> [Reading] {
        try allowed(patientID)
        let values: [Reading] = try await request(path(configuration.endpoints.readings,id:patientID).replacingOccurrences(of: "minutes=1440", with: "minutes=10"),empty:[])
        for r in values { guard r.patientId == patientID else { throw ServiceError.invalidResponse }; try WireValidation.reading(r) }
        let now = clock()
        return values.filter { $0.measuredAt >= now.addingTimeInterval(-600) && $0.measuredAt <= now.addingTimeInterval(5) }.sorted { $0.measuredAt > $1.measuredAt }
    }
    func getPredictions(patientID: String) async throws -> [Prediction] {
        try allowed(patientID)
        let values: [Prediction] = try await request(path(configuration.endpoints.predictions,id:patientID),empty:[])
        for p in values { guard p.patientId == patientID else { throw ServiceError.invalidResponse }; try WireValidation.prediction(p) }
        return values
    }
    func getAlerts() async throws -> [Alert] {
        guard session != nil else { throw ServiceError.forbidden }
        let values: [Alert] = try await request(configuration.endpoints.alerts,empty:[])
        for a in values { try allowed(a.patientId); try WireValidation.alert(a) }
        return values
    }
    func acknowledgeAlert(id: String) async throws -> Alert {
        guard session?.mode == .pro else { throw ServiceError.forbidden }
        let value: Alert = try await request(path(configuration.endpoints.acknowledge,id:id),method:"POST")
        try allowed(value.patientId); try WireValidation.alert(value)
        guard value.id == id, value.status != "new", value.acknowledgedAt != nil else { throw ServiceError.invalidResponse }
        return value
    }
    func refresh() async throws -> [Patient] { try await getPatients() }
}
typealias APICareService = LiveApiService

@MainActor
enum CareServiceFactory {
    static func make(bundle: Bundle = .main, baseURL: String? = nil) throws -> CareService {
        guard let url = bundle.url(forResource:"carelink-config",withExtension:"json") else { throw ServiceError.missingResource("carelink-config") }
        var config = try WireJSON.decoder().decode(ServiceConfiguration.self,from:Data(contentsOf:url))
        if config.mode == .live {
            config.baseUrl = baseURL ?? UserDefaults.standard.string(forKey: "carelink-server-url") ?? (config.baseUrl.isEmpty ? "http://127.0.0.1:8000" : config.baseUrl)
        }
        try config.validate()
        if config.mode == .mock { return try MockDataService(bundle:bundle) }
        guard let rulesURL = bundle.url(forResource:"demo-rules",withExtension:"json") else { throw ServiceError.missingResource("demo-rules") }
        let rules = try WireJSON.decoder().decode(DemoRules.self,from:Data(contentsOf:rulesURL))
        return try LiveApiService(configuration:config,rules:rules)
    }
}
