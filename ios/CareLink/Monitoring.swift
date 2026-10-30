import Foundation

enum RiskLevel: String, Codable, CaseIterable, Identifiable {
    case red, yellow, green, unknown
    var id: String { rawValue }
    var rank: Int { switch self { case .red: return 0; case .yellow: return 1; case .unknown: return 2; case .green: return 3 } }
}
enum MetricKey: String, CaseIterable, Identifiable {
    case hr, spo2, temp
    var id: String { rawValue }
    var unit: String { self == .hr ? "bpm" : self == .spo2 ? "%" : "°C" }
    var symbol: String { self == .hr ? "heart.fill" : self == .spo2 ? "drop.fill" : "thermometer" }
    func metric(in reading: Reading) -> Metric {
        switch self { case .hr: return reading.metrics.hr; case .spo2: return reading.metrics.spo2; case .temp: return reading.metrics.temp }
    }
}
enum ReadingReason: Equatable {
    case noData, fall, offline, stale, stable, fallUnavailable, backendPending, backendStale
    case backend(String)
    case unavailable(MetricKey), poor(MetricKey), deviation(MetricKey, RiskLevel)
}
struct StatusReport { var level: RiskLevel; var reasons: [ReadingReason]; var incomplete: Bool }

// These mirror the shared JS demo rules, not clinical decision criteria.
enum Monitoring {
    static func isFresh(_ reading: Reading?, rules: DemoRules, now: Date = Date()) -> Bool {
        guard let reading = reading, reading.connected else { return false }
        let age = now.timeIntervalSince(reading.measuredAt)
        return age >= -5 && age <= rules.staleAfterSeconds
    }
    static func usable(_ metric: Metric) -> Bool {
        metric.available != false && metric.quality == .good && metric.value?.isFinite == true
    }
    static func severity(_ value: Double, metric: MetricKey, rules: DemoRules) -> RiskLevel {
        if metric == .spo2 {
            return value < rules.spo2.severeLow ? .red : value < rules.spo2.mildLow ? .yellow : .green
        }
        let bounds = metric == .hr ? rules.hr : rules.temp
        if value < bounds.severeLow || value > bounds.severeHigh { return .red }
        if value < bounds.mildLow || value > bounds.mildHigh { return .yellow }
        return .green
    }
    static func triage(_ reading: Reading?, rules: DemoRules, now: Date = Date()) -> StatusReport {
        guard let reading = reading else { return StatusReport(level: .unknown, reasons: [.noData], incomplete: true) }
        var reasons = [ReadingReason](), levels = [RiskLevel]()
        let fresh = isFresh(reading, rules: rules, now: now)
        var incomplete = !fresh || reading.fall.quality != .good
        if reading.fall.active { levels.append(.red); reasons.append(.fall) }
        if !fresh { reasons.append(reading.connected ? .stale : .offline) }
        for key in MetricKey.allCases where key != .spo2 || reading.metrics.spo2.available != false {
            let metric = key.metric(in: reading)
            guard fresh, usable(metric), let value = metric.value else {
                incomplete = true
                if fresh { reasons.append(metric.quality == .poor ? .poor(key) : .unavailable(key)) }
                continue
            }
            let level = severity(value, metric: key, rules: rules)
            levels.append(level)
            if level != .green { reasons.append(.deviation(key, level)) }
        }
        if reading.fall.quality != .good && !reading.fall.active { reasons.append(.fallUnavailable) }
        let level: RiskLevel = levels.contains(.red) ? .red : levels.contains(.yellow) ? .yellow : incomplete ? .unknown : .green
        return StatusReport(level: level, reasons: reasons.isEmpty ? [.stable] : reasons, incomplete: incomplete)
    }
    static func display(_ reading: Reading?, key: MetricKey, rules: DemoRules, now: Date = Date()) -> String {
        guard isFresh(reading, rules: rules, now: now), let reading = reading else { return "—" }
        let metric = key.metric(in: reading)
        guard usable(metric), let value = metric.value else { return "—" }
        return key == .temp ? String(format: "%.1f", value) : String(Int(value.rounded()))
    }
    static func liveReport(_ reading: Reading?, rules: DemoRules, now: Date = Date()) -> StatusReport {
        guard let reading = reading else { return StatusReport(level: .unknown, reasons: [.noData], incomplete: true) }
        let incomplete = !isFresh(reading, rules: rules, now: now) || MetricKey.allCases.filter { $0 != .spo2 || reading.metrics.spo2.available != false }.contains { !usable($0.metric(in: reading)) } || reading.fall.quality != .good
        if let assessment = reading.assessment {
            let age = now.timeIntervalSince(assessment.assessedAt)
            let stale = age > rules.staleAfterSeconds || age < -5
            let level: RiskLevel = (incomplete || stale) && assessment.level == .green ? .unknown : assessment.level
            return StatusReport(level: level, reasons: assessment.reasons.map { .backend($0) } + (stale ? [.backendStale] : []), incomplete: incomplete || stale)
        }
        return StatusReport(level: reading.fall.active ? .red : .unknown, reasons: reading.fall.active ? [.fall] : [.backendPending], incomplete: true)
    }
}
