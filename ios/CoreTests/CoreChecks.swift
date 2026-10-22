import Foundation

private struct TriageVector: Decodable {
    var name: String
    var now: Date
    var reading: Reading?
    var expected: RiskLevel
}

@main
@MainActor
struct CoreChecks {
    static func main() async throws {
        guard CommandLine.arguments.count == 2 else { fatalError("Pass the shared directory") }
        let directory = URL(fileURLWithPath: CommandLine.arguments[1])
        func load<T: Decodable>(_ filename: String, _ type: T.Type) throws -> T {
            try WireJSON.decoder().decode(type, from: Data(contentsOf: directory.appendingPathComponent(filename)))
        }
        let patients = try load("demo-patients.json", [Patient].self)
        let rules = try load("demo-rules.json", DemoRules.self)
        let sessions = try load("demo-sessions.json", DemoSessions.self)
        let vectors = try load("triage-vectors.json", [TriageVector].self)
        var checks = 0
        func check(_ condition: @autoclosure () -> Bool, _ message: String) {
            guard condition() else { fatalError("FAIL: \(message)") }
            checks += 1
        }
        check(patients.count == 8, "Decode all shared profiles")
        check(sessions.basic.mode == .basic && sessions.basic.patientIds == ["p004"], "Basic session scope")
        check(sessions.pro.patientIds.count == 8, "Pro session scope")
        for vector in vectors {
            check(Monitoring.triage(vector.reading, rules: rules, now: vector.now).level == vector.expected, "JS/Swift status parity: \(vector.name)")
        }
        let anchor = patients[0].reading!.measuredAt
        let service = MockCareService(profiles: patients, rules: rules, sessions: sessions, now: anchor)
        _ = try await service.getSession(mode:.pro)
        let loaded = try await service.getPatients()
        for (native, fixture) in zip(loaded, patients) {
            check(native.id == fixture.id && native.name == fixture.name, "Shared profile identity")
            check(native.reading?.metrics.hr.value == fixture.reading?.metrics.hr.value, "Shared HR fixture")
            check(native.reading?.metrics.spo2.value == fixture.reading?.metrics.spo2.value, "Shared SpO2 fixture")
            check(native.reading?.metrics.temp.value == fixture.reading?.metrics.temp.value, "Shared temperature fixture")
            check(native.reading?.fall.active == fixture.reading?.fall.active, "Shared fall fixture")
        }
        let history = try await service.getHistory(patientID: "p004")
        check(history.count == 21, "21 samples over 10 minutes")
        check(history.allSatisfy { $0.measuredAt >= anchor.addingTimeInterval(-600) && $0.measuredAt <= anchor }, "Bounded history window")
        service.setScenario(patientID: "p004", scenario: .unavailable)
        let unavailable = try await service.getPatients().first { $0.id == "p004" }!.reading
        check(Monitoring.display(unavailable, key: .hr, rules: rules) == "—", "KY-005 never supplies HR")
        check(Monitoring.display(unavailable, key: .spo2, rules: rules) == "—", "KY-005 never supplies SpO2")
        check(Monitoring.triage(unavailable, rules: rules).level == .unknown, "Missing data is not stable")
        check(unavailable?.ai.result == nil && unavailable?.ai.confidence == nil, "No fake AI result")
        service.setScenario(patientID: "p004", scenario: .stale)
        let staleHistory = try await service.getHistory(patientID: "p004")
        check(staleHistory.count == 15, "Stale history is still confined to ten minutes")
        service.setScenario(patientID: "p004", scenario: .noData)
        let noDataHistory = try await service.getHistory(patientID: "p004")
        check(noDataHistory.isEmpty, "No data has empty history")
        let encoded = try WireJSON.encoder().encode(patients)
        let decoded = try WireJSON.decoder().decode([Patient].self, from: encoded)
        check(decoded.count == patients.count && decoded[0].reading?.measuredAt == anchor, "ISO timestamp round-trip")
        check(DemoLogin.validate(username: " ", password: "demo1234") == .usernameRequired, "Empty username feedback")
        check(DemoLogin.validate(username: "demo", password: "") == .passwordRequired, "Empty password feedback")
        check(DemoLogin.validate(username: "demo", password: "wrong") == .rejected, "Simulated sign-in failure")
        check(DemoLogin.validate(username: "demo", password: "demo1234") == nil, "Valid demo form")
        var ledger = DemoAlertLedger()
        let incidentTime = anchor
        var one = loaded[0]
        one.reading!.connected = true
        one.reading!.measuredAt = incidentTime
        one.reading!.fall.active = true
        ledger.reconcile([one], rules: rules, now: incidentTime)
        check(ledger.records.count == 1 && ledger.records[0].level == .red, "Create fall episode")
        let episodeID = ledger.records[0].id
        ledger.acknowledge(episodeID, at: incidentTime.addingTimeInterval(1))
        ledger.acknowledge(episodeID, at: incidentTime.addingTimeInterval(2))
        check(ledger.records[0].acknowledgedAt == incidentTime.addingTimeInterval(1), "Acknowledgement is idempotent")
        ledger.reconcile([one], rules: rules, now: incidentTime.addingTimeInterval(5))
        check(ledger.records.count == 1 && ledger.records[0].id == episodeID, "Refresh does not duplicate episode")
        check(ledger.records[0].resolvedAt == nil && Monitoring.triage(one.reading, rules: rules, now: incidentTime).level == .red, "Acknowledgement never clears fall")
        one.reading!.fall.active = false
        one.reading!.metrics.hr = Metric(value: 76, quality: .good)
        one.reading!.metrics.spo2 = Metric(value: 98, quality: .good)
        one.reading!.metrics.temp = Metric(value: 36.6, quality: .good)
        ledger.reconcile([one], rules: rules, now: incidentTime.addingTimeInterval(10))
        check(ledger.records.count == 1 && ledger.records[0].resolvedAt != nil, "Resolved episode retained in history")
        one.reading!.fall.active = true
        ledger.reconcile([one], rules: rules, now: incidentTime.addingTimeInterval(15))
        check(ledger.records.count == 2 && ledger.records[1].acknowledgedAt == nil, "New episode is not pre-acknowledged")

        // Both implementations decode the exact same proposed JSON fixtures.
        let apiProfiles = try load("api-examples/patients.json", [Patient].self)
        let apiPatient = try load("api-examples/patient.json", Patient.self)
        let apiReadings = try load("api-examples/readings.json", [SensorReading].self)
        let apiPredictions = try load("api-examples/predictions.json", [Prediction].self)
        let apiAlerts = try load("api-examples/alerts.json", [Alert].self)
        let confirmed = try load("api-examples/acknowledgement.json", Alert.self)
        for p in apiProfiles { try WireValidation.patient(p) }
        for r in apiReadings { try WireValidation.reading(r) }
        for p in apiPredictions { try WireValidation.prediction(p) }
        for a in apiAlerts { try WireValidation.alert(a) }
        check(apiProfiles.count == 8 && apiPatient.id == "p001", "Shared proposed API profile fixtures")
        check(apiPredictions[0].confidence == nil && apiPredictions[0].predictedAt == nil, "No fabricated prediction confidence or time")
        var configuration = try load("carelink-config.json", ServiceConfiguration.self)
        configuration.mode = .live; configuration.baseUrl = "https://backend.example"
        do { try configuration.validate(); fatalError("Unconfirmed API must fail") } catch { checks += 1 }
        configuration.apiConfirmed = true
        let api = try LiveApiService(configuration: configuration, rules: rules, clock:{anchor}) { request in
            let path = request.url!.path
            var data = Data()
            var statusCode = 200
            switch path {
            case "/api/session": data = try WireJSON.encoder().encode(sessions.pro)
            case "/api/patients": data = try WireJSON.encoder().encode(apiProfiles)
            case "/api/patients/p001": data = try WireJSON.encoder().encode(apiPatient)
            case "/api/patients/p001/readings":
                check(request.url!.query == "minutes=10", "Native ten-minute query")
                data = try WireJSON.encoder().encode(apiReadings)
            case "/api/patients/p001/predictions": data = try WireJSON.encoder().encode(apiPredictions)
            case "/api/alerts": data = try WireJSON.encoder().encode(apiAlerts)
            case "/api/alerts/example-alert-001/acknowledgement":
                check(request.httpMethod == "POST" && request.httpBody == Data("{}".utf8), "Native acknowledgement request")
                data = try WireJSON.encoder().encode(confirmed)
            case "/api/patients/p004": statusCode = 404
            default: fatalError("Unexpected request \(path)")
            }
            return (data, HTTPURLResponse(url:request.url!,statusCode:statusCode,httpVersion:nil,headerFields:["Content-Type":"application/json"])!)
        }
        let backendSession = try await api.getSession(mode:.basic)
        check(backendSession.mode == .pro, "Native role comes from backend, not requested mode")
        let nativeList = try await api.getPatients()
        check(nativeList.count == 8, "Native API patients success")
        let nativeDetail = try await api.getPatient(id:"p001")
        check(nativeDetail?.id == "p001", "Native API patient detail success")
        let nativeReadings = try await api.getHistory(patientID:"p001")
        check(nativeReadings.count == 1, "Native API readings success")
        let nativePredictions = try await api.getPredictions(patientID:"p001")
        check(nativePredictions.count == 1 && nativePredictions[0].confidence == nil, "Native API prediction null preservation")
        let nativeAlerts = try await api.getAlerts()
        check(nativeAlerts.count == 1, "Native API alerts success")
        let nativeAck = try await api.acknowledgeAlert(id:"example-alert-001")
        check(nativeAck.acknowledgedAt != nil && nativeAck.conditionActive, "Native confirmation never resolves active condition")
        let missing = try await api.getPatient(id:"p004")
        check(missing == nil, "Native API 404 becomes absent detail")
        let emptyAPI = try LiveApiService(configuration:configuration,rules:rules, transport: { request in
            let data = request.url!.path == "/api/session" ? try WireJSON.encoder().encode(sessions.pro) : Data()
            let statusCode = request.url!.path == "/api/session" ? 200 : 204
            return (data,HTTPURLResponse(url:request.url!,statusCode:statusCode,httpVersion:nil,headerFields:nil)!)
        })
        _ = try await emptyAPI.getSession(mode:.pro)
        let emptyList = try await emptyAPI.getPatients()
        let emptyAlerts = try await emptyAPI.getAlerts()
        check(emptyList.isEmpty && emptyAlerts.isEmpty, "Native API 204 empty list handling")
        let failedAPI = try LiveApiService(configuration:configuration,rules:rules, transport: { request in
            if request.url!.path == "/api/session" { return (try WireJSON.encoder().encode(sessions.pro),HTTPURLResponse(url:request.url!,statusCode:200,httpVersion:nil,headerFields:nil)!) }
            return (Data(),HTTPURLResponse(url:request.url!,statusCode:500,httpVersion:nil,headerFields:nil)!)
        })
        _ = try await failedAPI.getSession(mode:.pro)
        do { _ = try await failedAPI.getPatients(); fatalError("HTTP error must propagate") } catch ServiceError.http(500) { checks += 1 }
        let malformedAPI = try LiveApiService(configuration:configuration,rules:rules, transport: { request in
            return (Data("{broken".utf8),HTTPURLResponse(url:request.url!,statusCode:200,httpVersion:nil,headerFields:nil)!)
        })
        do { _ = try await malformedAPI.getSession(mode:.pro); fatalError("Malformed JSON must fail") } catch ServiceError.invalidResponse { checks += 1 }
        let offlineAPI = try LiveApiService(configuration:configuration,rules:rules,transport: { _ in throw URLError(.notConnectedToInternet) })
        do { _ = try await offlineAPI.getSession(mode:.pro); fatalError("Network failure must propagate") } catch ServiceError.network { checks += 1 }
        var liveReading = loaded[1].reading!
        liveReading.source = "device"; liveReading.measuredAt = anchor
        check(Monitoring.liveReport(liveReading,rules:rules,now:anchor).level == .unknown, "Live does not apply demo numeric thresholds")
        liveReading.assessment = BackendAssessment(level:.yellow,reasons:["team-defined"],assessedAt:anchor,ruleSetId:"team-1",origin:"backend")
        check(Monitoring.liveReport(liveReading,rules:rules,now:anchor).level == .yellow, "Native backend assessment is authoritative")
        liveReading.metrics.hr.available = false
        check(Monitoring.display(liveReading,key:.hr,rules:rules,now:anchor) == "—", "Native explicit sensor availability respected")
        let basicAPI = try LiveApiService(configuration:configuration,rules:rules, transport: { request in
            return (try WireJSON.encoder().encode(sessions.basic),HTTPURLResponse(url:request.url!,statusCode:200,httpVersion:nil,headerFields:nil)!)
        })
        let basicSession = try await basicAPI.getSession(mode:.pro)
        check(basicSession.mode == .basic, "Native Basic role cannot be overridden locally")
        do { _ = try await basicAPI.getPatient(id:"p001"); fatalError("Out-of-scope detail must fail") } catch ServiceError.forbidden { checks += 1 }
        do { _ = try await basicAPI.acknowledgeAlert(id:"any"); fatalError("Basic cannot acknowledge") } catch ServiceError.forbidden { checks += 1 }
        _ = try await service.getSession(mode:.basic)
        let basicMock = try await service.getPatients()
        check(basicMock.map { $0.id } == ["p004"], "Native MockDataService enforces Basic scope")
        do { _ = try await service.getHistory(patientID:"p001"); fatalError("Basic cannot query another patient") } catch ServiceError.forbidden { checks += 1 }
        print("PASS: \(checks) Swift data/model/rule checks. iOS UI build is a separate Xcode check.")
    }
}
