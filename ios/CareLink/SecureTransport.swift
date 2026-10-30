import Foundation
import Security

// Every custom trust decision still checks chain, current validity and hostname.
// A public DER root is optional; without it, use the operating system trust store.
enum GatewayTrust {
    static func accepts(_ trust: SecTrust, host: String, anchor: SecCertificate) -> Bool {
        guard SecTrustSetPolicies(trust,SecPolicyCreateSSL(true,host as CFString)) == errSecSuccess,
              SecTrustSetAnchorCertificates(trust,[anchor] as CFArray) == errSecSuccess,
              SecTrustSetAnchorCertificatesOnly(trust,true) == errSecSuccess else { return false }
        guard SecTrustSetNetworkFetchAllowed(trust,false) == errSecSuccess else { return false }
        return SecTrustEvaluateWithError(trust,nil)
    }
}
private final class GatewayDelegate: NSObject, URLSessionDelegate, URLSessionTaskDelegate {
    let host: String
    let anchor: SecCertificate?
    init(host: String, anchor: SecCertificate?) { self.host=host;self.anchor=anchor }
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil) // Never forward an authentication cookie to a redirect.
    }
    func urlSession(_ session: URLSession, didReceive challenge: URLAuthenticationChallenge,
                    completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
        guard challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust else {
            completionHandler(.cancelAuthenticationChallenge,nil);return
        }
        guard challenge.protectionSpace.host.lowercased() == host.lowercased() else {
            completionHandler(.cancelAuthenticationChallenge,nil);return
        }
        guard let anchor=anchor else { completionHandler(.performDefaultHandling,nil);return }
        guard let trust=challenge.protectionSpace.serverTrust, GatewayTrust.accepts(trust,host:host,anchor:anchor) else {
            completionHandler(.cancelAuthenticationChallenge,nil);return
        }
        completionHandler(.useCredential,URLCredential(trust:trust))
    }
}
final class SecureGatewayTransport {
    private let origin: String
    private let session: URLSession
    init(origin: String, anchorDER: Data? = nil) throws {
        guard let url=URL(string:origin),url.scheme == "https", let host=url.host else { throw ServiceError.configuration }
        self.origin=origin
        var anchor: SecCertificate?
        if let der=anchorDER {
            guard let certificate=SecCertificateCreateWithData(nil,der as CFData) else { throw ServiceError.configuration }
            anchor=certificate
        }
        let config=URLSessionConfiguration.ephemeral
        config.tlsMinimumSupportedProtocolVersion = .TLSv12
        config.httpCookieStorage=nil;config.httpShouldSetCookies=false
        config.urlCredentialStorage=nil;config.urlCache=nil
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        self.session=URLSession(configuration:config,delegate:GatewayDelegate(host:host,anchor:anchor),delegateQueue:nil)
    }
    func send(_ request: URLRequest) async throws -> (Data,HTTPURLResponse) {
        guard let url=request.url, try ServiceConfiguration.origin(url.absoluteString) == origin else { throw ServiceError.configuration }
        let (data,response)=try await session.data(for:request)
        guard let http=response as? HTTPURLResponse,http.url == request.url else { throw ServiceError.invalidResponse }
        return (data,http)
    }
    deinit { session.invalidateAndCancel() }
}
