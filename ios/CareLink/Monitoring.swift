import Foundation

enum RiskLevel: String, Codable, CaseIterable, Identifiable {
    case red, yellow, green, unknown
    var id: String { rawValue }
    var rank: Int { switch self { case .red: return 0; case .yellow: return 1; case .unknown: return 2; case .green: return 3 } }
}
enum MetricKey: String, CaseIterable, Identifiable {
    case hr, spo2, temp
    static var monitored: [MetricKey] { [.hr, .temp] }
    var id: String { rawValue }
    var unit: String { self == .hr ? "bpm" : self == .spo2 ? "%" : "°C" }
    var symbol: String { self == .hr ? "heart.fill" : self == .spo2 ? "drop.fill" : "thermometer" }
    func metric(in reading: Reading) -> Metric {
        switch self { case .hr: return reading.metrics.hr; case .spo2: return reading.metrics.spo2 ?? Metric(value: nil, quality: .unavailable); case .temp: return reading.metrics.temp }
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
        for key in MetricKey.monitored {
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
        guard let reading = reading else { return "—" }
        let metric = key.metric(in: reading)
        if isFresh(reading, rules: rules, now: now), usable(metric), let value = metric.value {
            return key == .temp ? String(format: "%.1f", value) : String(Int(value.rounded()))
        }
        if key == .hr, let held = metric.displayValue ?? (usable(metric) ? metric.value : nil),
           held.isFinite, now.timeIntervalSince(metric.lastValidAt ?? reading.measuredAt) <= 30 {
            return String(Int(held.rounded()))
        }
        return "—"
    }
    static func liveReport(_ reading: Reading?, rules: DemoRules, now: Date = Date()) -> StatusReport {
        guard let reading = reading else { return StatusReport(level: .unknown, reasons: [.noData], incomplete: true) }
        let incomplete = !isFresh(reading, rules: rules, now: now) || MetricKey.monitored.contains { !usable($0.metric(in: reading)) } || reading.fall.quality != .good
        if let assessment = reading.assessment {
            let age = now.timeIntervalSince(assessment.assessedAt)
            let stale = age > rules.staleAfterSeconds || age < -5
            let level: RiskLevel = (incomplete || stale) && assessment.level == .green ? .unknown : assessment.level
            return StatusReport(level: level, reasons: assessment.reasons.map { .backend($0) } + (stale ? [.backendStale] : []), incomplete: incomplete || stale)
        }
        return StatusReport(level: reading.fall.active ? .red : .unknown, reasons: reading.fall.active ? [.fall] : [.backendPending], incomplete: true)
    }
}

struct TrendSample: Identifiable {
    let id: Int; let time: Date; let value: Double; let segment: Int
}
enum TrendAggregation {
    static func points(_ history: [Reading], key: MetricKey, now: Date) -> [TrendSample] {
        let end = floor(now.timeIntervalSince1970 / 5) * 5
        var buckets = [Int:[Double]](), seen = Set<String>(), first = Int(end)
        for reading in history.sorted(by: { $0.measuredAt < $1.measuredAt }) {
            let stamp = reading.measuredAt.timeIntervalSince1970, bucket = Int(floor(stamp / 5) * 5)
            guard stamp >= end - 600, Double(bucket) < end else { continue }
            first = min(first, bucket)
            let metric = key.metric(in: reading)
            guard Monitoring.usable(metric), metric.held != true, let value = metric.value else { continue }
            let sampleID = metric.sampleId ?? "\(reading.deviceId):\(stamp)"
            guard seen.insert(sampleID).inserted else { continue }
            buckets[bucket, default: []].append(value)
        }
        var result = [TrendSample](), segment = 0
        for stamp in stride(from: first, to: Int(end), by: 5) {
            let values = (buckets[stamp] ?? []).sorted()
            guard !values.isEmpty else { segment += 1; continue }
            let mid = values.count / 2
            let median = values.count % 2 == 1 ? values[mid] : (values[mid - 1] + values[mid]) / 2
            result.append(TrendSample(id: stamp, time: Date(timeIntervalSince1970: Double(stamp)), value: median, segment: segment))
        }
        return result
    }
}
