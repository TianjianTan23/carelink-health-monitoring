import Foundation
import Security

struct StoredSession: Codable, CustomStringConvertible {
    let token: String
    let expiresAt: Date
    var description: String { "StoredSession([redacted])" }
}
@MainActor
protocol SessionCredentialStore {
    func read(origin: String) throws -> StoredSession?
    func write(_ credential: StoredSession, origin: String) throws
    func remove(origin: String) throws
}

// No fallback to defaults, files, cookie storage or shared access groups.
@MainActor
final class KeychainSessionStore: SessionCredentialStore {
    private let service = "com.carelink.gateway.session.v1"
    private func query(_ origin: String) -> [String: Any] {
        [kSecClass as String:kSecClassGenericPassword, kSecAttrService as String:service,
         kSecAttrAccount as String:origin, kSecAttrSynchronizable as String:false]
    }
    func read(origin: String) throws -> StoredSession? {
        var q=query(origin);q[kSecReturnData as String]=true;q[kSecMatchLimit as String]=kSecMatchLimitOne
        var item: CFTypeRef?
        let result=SecItemCopyMatching(q as CFDictionary,&item)
        if result == errSecItemNotFound { return nil }
        guard result == errSecSuccess, let data=item as? Data,
              let value=try? JSONDecoder().decode(StoredSession.self,from:data) else { throw ServiceError.credentialStorage }
        return value
    }
    func write(_ credential: StoredSession, origin: String) throws {
        let data=try JSONEncoder().encode(credential)
        let attributes:[String:Any]=[kSecValueData as String:data,
            kSecAttrAccessible as String:kSecAttrAccessibleWhenUnlockedThisDeviceOnly]
        let q=query(origin)
        var status=SecItemUpdate(q as CFDictionary,attributes as CFDictionary)
        if status == errSecItemNotFound {
            status=SecItemAdd(q.merging(attributes) { _,new in new } as CFDictionary,nil)
            if status == errSecDuplicateItem { status=SecItemUpdate(q as CFDictionary,attributes as CFDictionary) }
        }
        guard status == errSecSuccess else { throw ServiceError.credentialStorage }
    }
    func remove(origin: String) throws {
        let result=SecItemDelete(query(origin) as CFDictionary)
        guard result == errSecSuccess || result == errSecItemNotFound else { throw ServiceError.credentialStorage }
    }
}
