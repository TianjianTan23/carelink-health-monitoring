import Foundation
import Security

@main
@MainActor
struct TLSChecks {
    static func main() async throws {
        let files=URL(fileURLWithPath:CommandLine.arguments[1])
        let origin=CommandLine.arguments[2]
        let rootData=try Data(contentsOf:files.appendingPathComponent("root.cer"))
        let root=SecCertificateCreateWithData(nil,rootData as CFData)!
        var count=0
        func check(_ condition: Bool,_ label: String) { if !condition { fatalError("FAIL: "+label) };count += 1;print("PASS: "+label) }
        for (filename,host,expected) in [("leaf.cer","localhost",true),("leaf.cer","wrong.invalid",false),("expired.cer","localhost",false),("untrusted.cer","localhost",false)] {
            let data=try Data(contentsOf:files.appendingPathComponent(filename))
            let certificate=SecCertificateCreateWithData(nil,data as CFData)!
            var trust:SecTrust?
            check(SecTrustCreateWithCertificates([certificate] as CFArray,SecPolicyCreateSSL(true,host as CFString),&trust) == errSecSuccess,"Construct synthetic trust")
            check(GatewayTrust.accepts(trust!,host:host,anchor:root) == expected,"Certificate/hostname/validity decision: "+filename+" / "+host)
        }
        let shared=URL(fileURLWithPath:CommandLine.arguments[3])
        var config=try WireJSON.decoder().decode(ServiceConfiguration.self,from:Data(contentsOf:shared.appendingPathComponent("carelink-config.json")))
        config.baseUrl=origin;config.apiConfirmed=true;config.mode = .live
        let rules=try WireJSON.decoder().decode(DemoRules.self,from:Data(contentsOf:shared.appendingPathComponent("demo-rules.json")))
        let store=MemorySessionStore()
        let client=try LiveApiService(configuration:config,rules:rules,credentials:store,anchorDER:rootData)
        guard let password=readLine(),!password.isEmpty else { fatalError("Missing synthetic input") }
        let identity=try await client.authenticate(username:"fixture_native",password:password,mode:.pro)
        check(identity.userId == "fixture_native" && identity.mode == .basic,"Actual HTTPS login and server scope")
        let patients=try await client.getPatients();check(patients.count == 1 && patients[0].id == "ttj","Actual authenticated readings API")
        check(patients[0].reading?.metrics.hr.value == nil && patients[0].reading?.metrics.spo2.available == false,"Actual backend omitted optional metric and null HR preserved")
        let before=store.values[origin]!
        let restarted=try LiveApiService(configuration:config,rules:rules,credentials:store,anchorDER:rootData)
        check(try await restarted.restoreSession()?.userId == "fixture_native","Actual server validation on client restart")
        try await restarted.rotateSession()
        let rotated=store.values[origin]!
        check(rotated.token != before.token,"Actual server session rotation")
        let raw=try SecureGatewayTransport(origin:origin,anchorDER:rootData)
        func copiedStatus(_ value: StoredSession) async throws -> Int {
            var request=URLRequest(url:URL(string:origin+"/api/session")!)
            request.httpShouldHandleCookies=false;request.setValue("carelink_session="+value.token,forHTTPHeaderField:"Cookie")
            return try await raw.send(request).1.statusCode
        }
        check(try await copiedStatus(before) == 401,"Old token after actual rotation: HTTP 401")
        try await restarted.logout()
        check(store.values.isEmpty,"Actual logout clears synthetic credential store")
        check(try await copiedStatus(rotated) == 401,"Copied prelogout token: HTTP 401")
        let anonymous=URLRequest(url:URL(string:origin+"/api/patients")!)
        check(try await raw.send(anonymous).1.statusCode == 401,"No session: HTTP 401")
        let noAnchor=try SecureGatewayTransport(origin:origin)
        do { _ = try await noAnchor.send(anonymous);fatalError("Untrusted certificate accepted") }
        catch { count += 1;print("PASS: Network rejects missing trust anchor") }
        let wrongOrigin=origin.replacingOccurrences(of:"localhost",with:"127.0.0.1")
        let wrong=try SecureGatewayTransport(origin:wrongOrigin,anchorDER:rootData)
        do { _ = try await wrong.send(URLRequest(url:URL(string:wrongOrigin+"/health")!));fatalError("Wrong network identity accepted") }
        catch { count += 1;print("PASS: Network rejects wrong hostname") }
        print("PASS: \(count) native TLS and real isolated backend checks; no hardware or OS Keychain used.")
    }
}
