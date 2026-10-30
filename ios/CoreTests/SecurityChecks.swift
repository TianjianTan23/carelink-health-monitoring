import Foundation

@main
@MainActor
struct SecurityChecks {
    static func main() async throws {
        let shared=URL(fileURLWithPath:CommandLine.arguments[1])
        var config=try WireJSON.decoder().decode(ServiceConfiguration.self,from:Data(contentsOf:shared.appendingPathComponent("carelink-config.json")))
        config.baseUrl="https://backend.example";config.apiConfirmed=true;config.mode = .live
        let rules=try WireJSON.decoder().decode(DemoRules.self,from:Data(contentsOf:shared.appendingPathComponent("demo-rules.json")))
        let origin="https://backend.example"
        let token="cl_s1_"+String(repeating:"a",count:43),next="cl_s1_"+String(repeating:"b",count:43)
        let identity=Session(userId:"fixture",role:"patient",mode:.basic,patientIds:["ttj"])
        var checks=0
        func check(_ value: Bool,_ name: String) { if !value { fatalError("FAIL: "+name) };checks += 1 }
        func response(_ request: URLRequest,_ status: Int=200,_ cookie: String?=nil) -> HTTPURLResponse {
            var fields=["Content-Type":"application/json"]
            if let cookie=cookie { fields["Set-Cookie"]="carelink_session="+cookie+"; Max-Age=28800; Path=/; HttpOnly; SameSite=lax; Secure" }
            return HTTPURLResponse(url:request.url!,statusCode:status,httpVersion:nil,headerFields:fields)!
        }
        let store=MemorySessionStore();var valid=Set<String>();var requests=0;var logoutCalls=0
        let transport:LiveApiService.Transport={ request in
            requests += 1
            check(request.url!.scheme == "https","HTTPS always")
            check(request.httpShouldHandleCookies == false,"No ambient cookie persistence")
            let path=request.url!.path
            if request.httpMethod == "POST" {
                check(request.value(forHTTPHeaderField:"X-CareLink-CSRF") == "1","CSRF mutation header")
                check(request.value(forHTTPHeaderField:"Origin") == origin,"Bound origin")
                check(request.value(forHTTPHeaderField:"Content-Type") == "application/json","JSON mutation")
            }
            if path == "/api/login" {
                let body=try JSONSerialization.jsonObject(with:request.httpBody!) as! [String:String]
                check(body["username"] == "fixture" && body["password"] == "synthetic-test-password","Existing login contract")
                check(request.value(forHTTPHeaderField:"Cookie") == nil,"No old account on login")
                valid.insert(token)
                return (try WireJSON.encoder().encode(identity),response(request,200,token))
            }
            let supplied=request.value(forHTTPHeaderField:"Cookie")?.replacingOccurrences(of:"carelink_session=",with:"") ?? ""
            guard valid.contains(supplied) else { return (Data(),response(request,401)) }
            if path == "/api/logout" { logoutCalls += 1;valid.remove(supplied);return (Data("{\"status\":\"signed_out\"}".utf8),response(request)) }
            if path == "/api/session/rotate" { valid.remove(supplied);valid.insert(next);return (Data("{}".utf8),response(request,200,next)) }
            return (try WireJSON.encoder().encode(identity),response(request))
        }
        let api=try LiveApiService(configuration:config,rules:rules,credentials:store,transport:transport)
        let absent=try await api.restoreSession();check(absent == nil && requests == 0,"No credential means no cached identity")
        let signed=try await api.authenticate(username:"fixture",password:"synthetic-test-password",mode:.pro)
        check(signed.mode == .basic,"Client role does not override server")
        check(store.values[origin]?.token == token,"Opaque cookie stored via secure interface")
        let restarted=try LiveApiService(configuration:config,rules:rules,credentials:store,transport:transport)
        let restored=try await restarted.restoreSession();check(restored?.userId == "fixture","Restart validates server before restoring")
        try await restarted.rotateSession()
        check(store.values[origin]?.token == next && !valid.contains(token),"Rotation updates credential and invalidates old token")
        try await restarted.logout()
        check(store.values[origin] == nil && !valid.contains(next),"Logout revokes server and clears storage")
        let oldRequest=URLRequest(url:URL(string:origin+"/api/session")!)
        var copied=oldRequest;copied.httpShouldHandleCookies=false;copied.setValue("carelink_session="+next,forHTTPHeaderField:"Cookie")
        check(try await transport(copied).1.statusCode == 401,"Copied prelogout cookie rejected")
        _ = try await api.authenticate(username:"fixture",password:"synthetic-test-password",mode:.basic)
        _ = try await api.authenticate(username:"fixture",password:"synthetic-test-password",mode:.basic)
        check(logoutCalls == 2,"Account switch revokes prior login before new login")
        valid.removeAll()
        let revoked=try LiveApiService(configuration:config,rules:rules,credentials:store,transport:transport)
        check(try await revoked.restoreSession() == nil && store.values.isEmpty,"Server-revoked token not restored")
        store.values[origin]=StoredSession(token:token,expiresAt:Date(timeIntervalSince1970:1));let before=requests
        check(try await revoked.restoreSession() == nil && requests == before,"Expired credential rejected locally")
        store.values[origin]=StoredSession(token:"invalid",expiresAt:Date().addingTimeInterval(3600))
        check(try await revoked.restoreSession() == nil && store.values.isEmpty,"Malformed token rejected and cleared")
        store.unavailable=true
        do { _ = try await revoked.restoreSession();fatalError("Storage must fail closed") } catch ServiceError.credentialStorage { checks += 1 }
        store.unavailable=false
        for insecure in ["http://gateway.example","https://user:pass@gateway.example","https://gateway.example/path","https://gateway.example/#fragment"] {
            var invalid=config;invalid.baseUrl=insecure
            do { try invalid.validate();fatalError("Insecure configuration accepted") } catch { checks += 1 }
        }
        let broken=MemorySessionStore()
        let noCookie=try LiveApiService(configuration:config,rules:rules,credentials:broken,transport:{ r in (try WireJSON.encoder().encode(identity),response(r)) })
        do { _ = try await noCookie.authenticate(username:"fixture",password:"synthetic-test-password",mode:.pro);fatalError("Missing cookie accepted") } catch ServiceError.invalidResponse { checks += 1 }
        check(broken.values.isEmpty,"No secret persisted on malformed login")
        let offline=MemorySessionStore();offline.values[origin]=StoredSession(token:token,expiresAt:Date().addingTimeInterval(3600))
        let failed=try LiveApiService(configuration:config,rules:rules,credentials:offline,transport:{ _ in throw URLError(.notConnectedToInternet) })
        do { _ = try await failed.restoreSession();fatalError("Offline identity restored") } catch ServiceError.network { checks += 1 }
        do { try await failed.logout();fatalError("Offline logout claimed server success") } catch ServiceError.network { checks += 1 }
        check(offline.values.isEmpty,"Offline logout clears local credential without claiming remote revocation")
        let redirect=MemorySessionStore();redirect.values[origin]=StoredSession(token:token,expiresAt:Date().addingTimeInterval(3600))
        let redirected=try LiveApiService(configuration:config,rules:rules,credentials:redirect,transport:{ r in (Data(),response(r,307)) })
        do { _ = try await redirected.restoreSession();fatalError("Redirect accepted") } catch ServiceError.http(307) { checks += 1 }
        for cookie in [
            "carelink_session="+token+"; Max-Age=28800; Path=/; HttpOnly; SameSite=lax",
            "carelink_session="+token+"; Max-Age=28800; Path=/; Secure; SameSite=lax",
            "carelink_session="+token+"; Max-Age=28800; Path=/; HttpOnly; Secure; SameSite=none",
            "carelink_session="+token+"; Max-Age=28800; Path=/; HttpOnly; Secure; SameSite=lax; Domain=backend.example",
            "carelink_session="+token+"; Max-Age=28800; Path=/; HttpOnly; Secure; SameSite=lax; SameSite=none",
            "carelink_session="+token+"; Max-Age=28800; Path=/; HttpOnly; Secure; SameSite=lax, carelink_session="+next
        ] {
            let vault=MemorySessionStore()
            let bad=try LiveApiService(configuration:config,rules:rules,credentials:vault,transport:{ r in
                (try WireJSON.encoder().encode(identity),HTTPURLResponse(url:r.url!,statusCode:200,httpVersion:nil,headerFields:["Set-Cookie":cookie])!)
            })
            do { _ = try await bad.authenticate(username:"fixture",password:"synthetic-test-password",mode:.basic);fatalError("Unsafe cookie accepted") }
            catch ServiceError.invalidResponse { checks += 1 }
            check(vault.values.isEmpty,"Unsafe cookie never persisted")
        }
        let staleStore=MemorySessionStore();staleStore.values[origin]=StoredSession(token:token,expiresAt:Date().addingTimeInterval(3600))
        var pending:CheckedContinuation<(Data,HTTPURLResponse),Error>?
        var pendingRequest:URLRequest?
        let staleClient=try LiveApiService(configuration:config,rules:rules,credentials:staleStore,transport:{ request in
            if request.url!.path == "/api/session" {
                pendingRequest=request
                return try await withCheckedThrowingContinuation { pending=$0 }
            }
            return (Data("{}".utf8),response(request))
        })
        let waiting=Task { try await staleClient.getSession(mode:.basic) }
        while pending == nil { await Task.yield() }
        try await staleClient.logout()
        pending!.resume(returning:(try WireJSON.encoder().encode(identity),response(pendingRequest!)))
        do { _ = try await waiting.value;fatalError("Late response resurrected logged-out identity") }
        catch ServiceError.sessionChanged { checks += 1 }
        check(staleStore.values.isEmpty,"Late response cannot restore credential")
        do { _ = try await staleClient.getPatients();fatalError("Late response restored authorization") }
        catch ServiceError.forbidden { checks += 1 }
        let sharedStore=MemorySessionStore();sharedStore.values[origin]=StoredSession(token:token,expiresAt:Date().addingTimeInterval(3600))
        var oldResponse:CheckedContinuation<(Data,HTTPURLResponse),Error>?
        var sharedPendingRequest:URLRequest?
        let sharedClient=try LiveApiService(configuration:config,rules:rules,credentials:sharedStore,transport:{ request in
            sharedPendingRequest=request;return try await withCheckedThrowingContinuation { oldResponse=$0 }
        })
        let oldCall=Task { try await sharedClient.getSession(mode:.basic) }
        while oldResponse == nil { await Task.yield() }
        sharedStore.values[origin]=StoredSession(token:next,expiresAt:Date().addingTimeInterval(3600))
        oldResponse!.resume(returning:(Data(),response(sharedPendingRequest!,401)))
        do { _ = try await oldCall.value;fatalError("Old response affected replacement identity") }
        catch ServiceError.sessionChanged { checks += 1 }
        check(sharedStore.values[origin]?.token == next,"Old 401 cannot erase another client's replacement credential")
        // Explicit continuation barriers: B replaces storage only after A sent
        // its request, and before A receives success, HTTP error or network error.
        for operation in ["rotate", "logout", "switch-logout", "login", "switch-login"] {
            for outcome in ["success", "401", "500", "network", "malformed"] {
                let vault=MemorySessionStore()
                if operation != "login" {
                    try vault.write(StoredSession(token:token,expiresAt:Date().addingTimeInterval(3600)),origin:origin)
                }
                var barrier:CheckedContinuation<(Data,HTTPURLResponse),Error>?
                var sent:URLRequest?
                var calls=0
                let client=try LiveApiService(configuration:config,rules:rules,credentials:vault,transport:{ request in
                    calls += 1
                    if operation == "switch-login",request.url!.path == "/api/logout" {
                        return (Data("{}".utf8),response(request))
                    }
                    sent=request
                    return try await withCheckedThrowingContinuation { barrier=$0 }
                })
                let call=Task {
                    switch operation {
                    case "rotate": try await client.rotateSession()
                    case "logout": try await client.logout()
                    default: _ = try await client.authenticate(username:"fixture",password:"synthetic-test-password",mode:.basic)
                    }
                }
                while barrier == nil { await Task.yield() }
                check(sent!.value(forHTTPHeaderField:"Cookie") == (["login","switch-login"].contains(operation) ? nil : "carelink_session="+token),"A request binds original token")
                try vault.write(StoredSession(token:next,expiresAt:Date().addingTimeInterval(3600)),origin:origin)
                if outcome == "network" { barrier!.resume(throwing:URLError(.notConnectedToInternet)) }
                else {
                    let status=Int(outcome) ?? 200
                    let body=outcome == "malformed" ? Data("invalid".utf8) : try WireJSON.encoder().encode(identity)
                    barrier!.resume(returning:(body,response(sent!,status,token)))
                }
                do { try await call.value;fatalError("Stale authentication operation succeeded") }
                catch ServiceError.sessionChanged { check(outcome != "network","Replacement detected before response processing") }
                catch ServiceError.network { check(outcome == "network","Network error remains explicit") }
                check(try vault.read(origin:origin)?.token == next,"Stale operation preserves B credential: \(operation)/\(outcome)")
                check(calls == (operation == "switch-login" ? 2 : 1),"Account switching stops before login when prior identity changes")
                do { _ = try await client.getPatients();fatalError("Stale operation retained authorization") }
                catch ServiceError.forbidden { checks += 1 }
            }
        }
        print("PASS: \(checks) native authentication/storage contract checks; synthetic store only.")
    }
}
