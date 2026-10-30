import Foundation

struct APIEndpoints: Codable {
    var login: String = "/api/login"
    var logout: String = "/api/logout"
    var rotate: String = "/api/session/rotate"
    var session: String; var patients: String; var patient: String; var readings: String
    var predictions: String; var alerts: String; var acknowledge: String
    enum CodingKeys: String,CodingKey { case login,logout,rotate,session,patients,patient,readings,predictions,alerts,acknowledge }
    init(from decoder: Decoder) throws {
        let c=try decoder.container(keyedBy:CodingKeys.self)
        login=try c.decodeIfPresent(String.self,forKey:.login) ?? login
        logout=try c.decodeIfPresent(String.self,forKey:.logout) ?? logout
        rotate=try c.decodeIfPresent(String.self,forKey:.rotate) ?? rotate
        session=try c.decode(String.self,forKey:.session);patients=try c.decode(String.self,forKey:.patients)
        patient=try c.decode(String.self,forKey:.patient);readings=try c.decode(String.self,forKey:.readings)
        predictions=try c.decode(String.self,forKey:.predictions);alerts=try c.decode(String.self,forKey:.alerts)
        acknowledge=try c.decode(String.self,forKey:.acknowledge)
    }
}
struct ServiceConfiguration: Codable {
    var mode: DataMode; var baseUrl: String; var apiConfirmed: Bool
    var staleAfterSeconds: Double; var endpoints: APIEndpoints
    var trustAnchorResource: String? = nil // Public DER root filename, never a private key.
    static func origin(_ input: String) throws -> String {
        guard let u=URLComponents(string:input),u.scheme == "https", let host=u.host,!host.isEmpty,!host.contains(where:{$0.isWhitespace || $0 == "\\" || $0 == "%"}),
              u.user == nil,u.password == nil,u.fragment == nil,
              u.port == nil || (1...65535).contains(u.port!) else { throw ServiceError.configuration }
        return "https://" + (host.contains(":") && !host.hasPrefix("[") ? "["+host+"]" : host) + (u.port == nil || u.port == 443 ? "" : ":\(u.port!)")
    }
    func validate() throws {
        guard staleAfterSeconds > 0,staleAfterSeconds.isFinite else { throw ServiceError.configuration }
        if mode == .live {
            _ = try Self.origin(baseUrl)
            guard apiConfirmed,let u=URLComponents(string:baseUrl),u.query == nil,["","/"].contains(u.path) else { throw ServiceError.configuration }
        }
        for path in [endpoints.login,endpoints.logout,endpoints.rotate,endpoints.session,endpoints.patients,endpoints.patient,endpoints.readings,endpoints.predictions,endpoints.alerts,endpoints.acknowledge] {
            guard path.hasPrefix("/api/"),!path.contains(".."),!path.contains("\\"),!path.contains("#"),!path.contains("%"),!path.contains("://") else { throw ServiceError.configuration }
        }
        if let name=trustAnchorResource, name.range(of:"^[A-Za-z0-9_-]+\\.cer$",options:.regularExpression) == nil { throw ServiceError.configuration }
    }
}
enum WireValidation {
    static func prediction(_ value: Prediction) throws {
        guard ["not_connected","pending","available","failed","unavailable"].contains(value.state), value.confidence?.isFinite != false else { throw ServiceError.invalidResponse }
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

// Implements a PROPOSED contract only; no endpoint is assumed to exist on the team's server.
// Transport is injectable for tests. Production uses URLSession; never substitutes fixtures.
@MainActor
final class LiveApiService: CareService {
    typealias Transport = (URLRequest) async throws -> (Data, HTTPURLResponse)
    let mode: DataMode = .live
    let rules: DemoRules
    let configuration: ServiceConfiguration
    private let transport: Transport
    private let gateway: SecureGatewayTransport?
    private let clock: () -> Date
    private var session: Session?
    private var sessionToken: String?
    private let credentials: SessionCredentialStore
    private let origin: String
    private var generation=0
    private var authenticationBusy=false
    init(configuration: ServiceConfiguration, rules: DemoRules, clock: @escaping () -> Date = Date.init,
         credentials: SessionCredentialStore? = nil, anchorDER: Data? = nil, transport: Transport? = nil) throws {
        try configuration.validate()
        guard configuration.mode == .live else { throw ServiceError.configuration }
        self.configuration=configuration;self.clock=clock;self.origin=try ServiceConfiguration.origin(configuration.baseUrl)
        self.credentials=credentials ?? KeychainSessionStore()
        var displayRules=rules;displayRules.staleAfterSeconds=configuration.staleAfterSeconds;self.rules=displayRules
        if let injected=transport { self.gateway=nil;self.transport=injected }
        else {
            let gateway=try SecureGatewayTransport(origin:origin,anchorDER:anchorDER)
            self.gateway=gateway;self.transport={ try await gateway.send($0) }
        }
    }
    private func path(_ template: String, id: String? = nil) -> String {
        let safe=id?.addingPercentEncoding(withAllowedCharacters:CharacterSet.alphanumerics.union(CharacterSet(charactersIn:"-_"))) ?? ""
        return template.replacingOccurrences(of:"{id}",with:safe)
    }
    private func stored() throws -> StoredSession? {
        guard let value=try credentials.read(origin:origin) else { return nil }
        guard value.expiresAt > clock(),value.token.range(of:"^cl_s1_[A-Za-z0-9_-]{43}$",options:.regularExpression) != nil else {
            try credentials.remove(origin:origin);session=nil;sessionToken=nil;return nil
        }
        return value
    }
    // All stores and clients run on MainActor: compare/remove has no suspension.
    private func removeCredential(matching token: String?) throws {
        guard let token=token,try credentials.read(origin:origin)?.token == token else { return }
        try credentials.remove(origin:origin)
    }
    private func send(_ path: String, method: String = "GET", body: Data? = nil, anonymous: Bool = false) async throws -> (Data,HTTPURLResponse) {
        let version=generation
        guard let url=URL(string:origin+path),try ServiceConfiguration.origin(url.absoluteString) == origin else { throw ServiceError.configuration }
        var request=URLRequest(url:url,cachePolicy:.reloadIgnoringLocalCacheData,timeoutInterval:8)
        request.httpMethod=method;request.httpShouldHandleCookies=false
        request.setValue("application/json",forHTTPHeaderField:"Accept")
        var suppliedToken: String? = try stored()?.token
        if !anonymous {
            guard let value=try stored() else { throw ServiceError.http(401) }
            suppliedToken=value.token
            request.setValue("carelink_session="+value.token,forHTTPHeaderField:"Cookie")
        }
        if method != "GET" {
            request.httpBody=body ?? Data("{}".utf8)
            request.setValue("application/json",forHTTPHeaderField:"Content-Type")
            request.setValue("1",forHTTPHeaderField:"X-CareLink-CSRF")
            request.setValue(origin,forHTTPHeaderField:"Origin")
        }
        let result:(Data,HTTPURLResponse)
        do { result=try await transport(request) }
        catch let error as ServiceError { throw error }
        catch { throw ServiceError.network }
        guard version == generation else { throw ServiceError.sessionChanged }
        guard result.1.url == request.url else { throw ServiceError.invalidResponse }
        if try stored()?.token != suppliedToken {
            session=nil;sessionToken=nil;throw ServiceError.sessionChanged
        }
        if result.1.statusCode == 401 {
            session=nil;sessionToken=nil;try removeCredential(matching:suppliedToken)
        }
        guard (200...299).contains(result.1.statusCode) else { throw ServiceError.http(result.1.statusCode) }
        return result
    }
    private func request<T: Decodable>(_ path: String, method: String = "GET", empty: T? = nil) async throws -> T {
        let (data,response)=try await send(path,method:method)
        if response.statusCode == 204,let empty=empty { return empty }
        guard let value=try? WireJSON.decoder().decode(T.self,from:data) else { throw ServiceError.invalidResponse }
        return value
    }
    private func remember(_ response: HTTPURLResponse) throws -> String {
        guard let url=response.url,try ServiceConfiguration.origin(url.absoluteString) == origin else { throw ServiceError.invalidResponse }
        let fields=Dictionary(uniqueKeysWithValues:response.allHeaderFields.map { (String(describing:$0.key),String(describing:$0.value)) })
        guard let raw=fields.first(where:{$0.key.lowercased()=="set-cookie"})?.value else { throw ServiceError.invalidResponse }
        let attributes=raw.split(separator:";").dropFirst().map { $0.trimmingCharacters(in:.whitespaces).lowercased() }
        let ages=attributes.filter { $0.hasPrefix("max-age=") }
        guard raw.components(separatedBy:"carelink_session=").count == 2,
              attributes.filter({$0 == "secure"}).count == 1,attributes.filter({$0 == "httponly"}).count == 1,
              attributes.filter({$0.hasPrefix("samesite=")}).count == 1,attributes.filter({$0.hasPrefix("path=")}).count == 1,
              ages.count == 1,let seconds=Int(ages[0].dropFirst(8)),(1...28800).contains(seconds),
              attributes.contains("secure"),attributes.contains("httponly"),attributes.contains("samesite=lax"),
              !attributes.contains(where:{$0.hasPrefix("domain=")}) else { throw ServiceError.invalidResponse }
        let cookies=HTTPCookie.cookies(withResponseHeaderFields:fields,for:url).filter { $0.name == "carelink_session" }
        guard cookies.count == 1,cookies[0].isSecure,cookies[0].isHTTPOnly,cookies[0].path == "/",
              cookies[0].value.range(of:"^cl_s1_[A-Za-z0-9_-]{43}$",options:.regularExpression) != nil else { throw ServiceError.invalidResponse }
        try credentials.write(StoredSession(token:cookies[0].value,expiresAt:clock().addingTimeInterval(Double(seconds))),origin:origin)
        return cookies[0].value
    }
    private func beginAuthentication() throws {
        guard !authenticationBusy else { throw ServiceError.authenticationBusy }
        authenticationBusy=true;generation += 1
    }
    func authenticate(username: String, password: String, mode: AppMode) async throws -> Session {
        try beginAuthentication();defer { authenticationBusy=false }
        session=nil;sessionToken=nil
        let previousToken=try stored()?.token
        if previousToken != nil {
            do { _ = try await send(configuration.endpoints.logout,method:"POST") }
            catch { try removeCredential(matching:previousToken);throw error }
        }
        try removeCredential(matching:previousToken)
        guard username.range(of:"^[A-Za-z0-9_.-]{1,64}$",options:.regularExpression) != nil,
              !password.isEmpty,password.utf8.count <= 1024 else { throw ServiceError.http(401) }
        let data=try JSONSerialization.data(withJSONObject:["username":username,"password":password])
        // Login has no owned stored token to clean up on failure. send also
        // checks that storage stayed unchanged before accepting the new cookie.
        let (body,response)=try await send(configuration.endpoints.login,method:"POST",body:data,anonymous:true)
        guard let value=try? WireJSON.decoder().decode(Session.self,from:body) else { throw ServiceError.invalidResponse }
        try validateSession(value);sessionToken=try remember(response);session=value;return value
    }
    func restoreSession() async throws -> Session? {
        session=nil;sessionToken=nil
        guard try stored() != nil else { return nil }
        do { return try await getSession(mode:.basic) }
        catch ServiceError.http(401) { return nil }
    }
    func logout() async throws {
        try beginAuthentication();defer { authenticationBusy=false }
        session=nil;sessionToken=nil
        let token=try stored()?.token
        do {
            if token != nil { _ = try await send(configuration.endpoints.logout,method:"POST") }
            try removeCredential(matching:token)
        } catch { try removeCredential(matching:token);throw error }
    }
    func rotateSession() async throws {
        try beginAuthentication();defer { authenticationBusy=false }
        let token=try stored()?.token
        do { let (_,response)=try await send(configuration.endpoints.rotate,method:"POST");sessionToken=try remember(response) }
        catch { session=nil;sessionToken=nil;try removeCredential(matching:token);throw error }
    }
    private func validateSession(_ value: Session) throws {
        guard ["clinician","family","patient"].contains(value.role),value.mode != .pro || value.role == "clinician",
              value.patientIds.count <= 256,value.patientIds.allSatisfy({!$0.isEmpty && $0.count <= 128}) else { throw ServiceError.invalidResponse }
    }
    private func requireCurrentIdentity() throws {
        guard session != nil else { throw ServiceError.forbidden }
        guard let token=sessionToken,try stored()?.token == token else {
            session=nil;sessionToken=nil;throw ServiceError.http(401)
        }
    }
    private func allowed(_ id: String) throws { try requireCurrentIdentity();guard session?.patientIds.contains(id) == true else { throw ServiceError.forbidden } }
    func getSession(mode: AppMode) async throws -> Session {
        let sentToken=try stored()?.token
        let value: Session = try await request(configuration.endpoints.session)
        guard try stored()?.token == sentToken else { throw ServiceError.sessionChanged }
        try validateSession(value)
        session = value;sessionToken=sentToken; return value // ignores requested demo mode: role comes only from the server
    }
    func getPatients() async throws -> [Patient] {
        try requireCurrentIdentity()
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
        let values: [Reading] = try await request(path(configuration.endpoints.readings,id:patientID),empty:[])
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
        try requireCurrentIdentity()
        let values: [Alert] = try await request(configuration.endpoints.alerts,empty:[])
        for a in values { try allowed(a.patientId); try WireValidation.alert(a) }
        return values
    }
    func acknowledgeAlert(id: String) async throws -> Alert {
        try requireCurrentIdentity()
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
    static func make(bundle: Bundle = .main) throws -> CareService {
        guard let url = bundle.url(forResource:"carelink-config",withExtension:"json") else { throw ServiceError.missingResource("carelink-config") }
        let config = try WireJSON.decoder().decode(ServiceConfiguration.self,from:Data(contentsOf:url))
        try config.validate()
        if config.mode == .mock { return try MockDataService(bundle:bundle) }
        guard let rulesURL = bundle.url(forResource:"demo-rules",withExtension:"json") else { throw ServiceError.missingResource("demo-rules") }
        let rules = try WireJSON.decoder().decode(DemoRules.self,from:Data(contentsOf:rulesURL))
        var anchor: Data?
        if let name=config.trustAnchorResource {
            guard let resource=bundle.url(forResource:String(name.dropLast(4)),withExtension:"cer") else { throw ServiceError.missingResource("Public trust anchor") }
            anchor=try Data(contentsOf:resource)
        }
        return try LiveApiService(configuration:config,rules:rules,anchorDER:anchor)
    }
}
