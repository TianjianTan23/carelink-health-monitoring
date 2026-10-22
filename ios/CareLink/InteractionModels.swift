import Foundation

// Demo form behavior only: never use this as authentication for a real backend.
enum LoginIssue: Equatable { case usernameRequired, passwordRequired, rejected }
enum DemoLogin {
    static func validate(username: String, password: String) -> LoginIssue? {
        if username.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return .usernameRequired }
        if password.isEmpty { return .passwordRequired }
        return password == "demo1234" ? nil : .rejected
    }
}

struct DemoAlert: Identifiable {
    let id: UUID
    let patientID: String
    let level: RiskLevel
    let reasons: [ReadingReason]
    let occurredAt: Date
    var lastObservedAt: Date
    var acknowledgedAt: Date?
    var resolvedAt: Date?
}

// Keeps local demo episodes, rather than treating every refreshed sample as a new alert.
// Acknowledging an episode never clears a fall flag or changes triage rules.
struct DemoAlertLedger {
    private(set) var records = [DemoAlert]()
    mutating func reconcile(_ patients: [Patient], rules: DemoRules, now: Date) {
        for patient in patients {
            let report = Monitoring.triage(patient.reading, rules: rules, now: now)
            let active = records.indices.filter { records[$0].patientID == patient.id && records[$0].resolvedAt == nil }
            if report.level != .green, let index = active.first(where: { records[$0].level == report.level && records[$0].reasons == report.reasons }) {
                records[index].lastObservedAt = now
                continue
            }
            for index in active { records[index].resolvedAt = now }
            if report.level != .green {
                records.append(DemoAlert(id: UUID(), patientID: patient.id, level: report.level, reasons: report.reasons,
                    occurredAt: now, lastObservedAt: now, acknowledgedAt: nil, resolvedAt: nil))
            }
        }
    }
    mutating func acknowledge(_ id: UUID, at date: Date) {
        guard let index = records.firstIndex(where: { $0.id == id }), records[index].acknowledgedAt == nil else { return }
        records[index].acknowledgedAt = date
    }
}

enum AlertFeedState: String, CaseIterable, Identifiable {
    case live, loading, failed, empty
    var id: String { rawValue }
}

// Small display adapter retains the native alert views while the wire shape is shared.
extension Alert {
    var patientID: String { patientId }
    var level: RiskLevel { severity }
    var lastObservedAt: Date { updatedAt }
    var reasons: [ReadingReason] {
        guard source == "mock" else { return [.backend(summary)] }
        return summary.components(separatedBy: " · ").map { code in
            switch code {
            case "fall": return .fall
            case "offline": return .offline
            case "stale": return .stale
            case "no_data": return .noData
            case "fall_unavailable": return .fallUnavailable
            case "stable": return .stable
            default:
                for key in MetricKey.allCases {
                    if code == key.rawValue + "_poor" { return .poor(key) }
                    if code == key.rawValue + "_unavailable" { return .unavailable(key) }
                    if code == key.rawValue + "_red" { return .deviation(key,.red) }
                    if code == key.rawValue + "_yellow" { return .deviation(key,.yellow) }
                }
                return .backend(code)
            }
        }
    }
}
