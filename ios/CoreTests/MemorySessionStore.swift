import Foundation
// Test double only; never linked into the app target.
@MainActor
final class MemorySessionStore: SessionCredentialStore {
    var values=[String:StoredSession]()
    var unavailable=false
    func read(origin: String) throws -> StoredSession? { if unavailable { throw ServiceError.credentialStorage };return values[origin] }
    func write(_ credential: StoredSession, origin: String) throws { if unavailable { throw ServiceError.credentialStorage };values[origin]=credential }
    func remove(origin: String) throws { if unavailable { throw ServiceError.credentialStorage };values.removeValue(forKey:origin) }
}
