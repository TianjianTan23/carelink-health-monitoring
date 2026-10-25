import Foundation

enum AppMode: String, Codable, CaseIterable, Identifiable {
    case pro, basic
    var id: String { rawValue }
    var title: String { self == .pro ? "Pro" : "Basic" }
}

struct Session: Codable {
    var userId: String
    var role: String
    var mode: AppMode
    var patientIds: [String]
}
struct DemoSessions: Codable { var pro: Session; var basic: Session }

enum Quality: String, Codable {
    case good, poor, unavailable, unknown
    init(from decoder: Decoder) throws {
        self = Quality(rawValue: try decoder.singleValueContainer().decode(String.self)) ?? .unknown
    }
}

struct Metric: Codable {
    var value: Double?
    var quality: Quality
    var available: Bool? = nil
    var measuredAt: Date? = nil
    var sensor: String? = nil
    var connected: Bool? = nil
    var state: String? = nil
    var calculationValidated: Bool? = nil
}
struct Metrics: Codable {
    var hr: Metric
    // Deprecated wire compatibility only. Never part of MetricKey.
    var spo2: Metric? = nil
    var temp: Metric
}
struct FallEvent: Codable { var active: Bool; var quality: Quality; var eventAt: Date? }
struct Vector3: Codable { var x: Double; var y: Double; var z: Double }
struct RawData: Codable {
    var accel_m_s2: Vector3?
    var gyro_deg_s: Vector3?
    var ir: Double?
    var red: Double?
    var object_temperature_c: Double?
    var ambient_temperature_c: Double?
}

// Preserves future structured AI results without pretending that a model exists.
enum JSONValue: Codable {
    case object([String: JSONValue]), array([JSONValue]), string(String), number(Double), bool(Bool), null
    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let value = try? c.decode(Bool.self) { self = .bool(value) }
        else if let value = try? c.decode(Double.self) { self = .number(value) }
        else if let value = try? c.decode(String.self) { self = .string(value) }
        else if let value = try? c.decode([JSONValue].self) { self = .array(value) }
        else { self = .object(try c.decode([String: JSONValue].self)) }
    }
    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .object(let v): try c.encode(v)
        case .array(let v): try c.encode(v)
        case .string(let v): try c.encode(v)
        case .number(let v): try c.encode(v)
        case .bool(let v): try c.encode(v)
        case .null: try c.encodeNil()
        }
    }
}
struct Prediction: Codable {
    var state: String
    var model: String?
    var result: JSONValue?
    var confidence: Double?
    var id: String? = nil
    var patientId: String? = nil
    var predictedAt: Date? = nil
    var inputsMeasuredAt: Date? = nil
    var modelVersion: String? = nil
    var confidenceMeaning: String? = nil
    var source: String? = nil
}
struct Reading: Codable {
    var patientId: String
    var deviceId: String
    var measuredAt: Date
    var receivedAt: Date
    var connected: Bool
    var metrics: Metrics
    var fall: FallEvent
    var raw: RawData?
    var ai: Prediction
    var source: String
    var scenario: String?
    var assessment: BackendAssessment? = nil
}
typealias SensorReading = Reading
struct BackendAssessment: Codable {
    var level: RiskLevel
    var reasons: [String]
    var assessedAt: Date
    var ruleSetId: String?
    var origin: String
}
struct Alert: Codable, Identifiable {
    var id: String
    var patientId: String
    var type: String
    var severity: RiskLevel
    var occurredAt: Date
    var updatedAt: Date
    var acknowledgedAt: Date?
    var acknowledgedBy: String?
    var status: String
    var conditionActive: Bool
    var resolvedAt: Date?
    var summary: String
    var source: String
}
enum DataMode: String, Codable { case mock, live }
enum LoadState { case idle, loading, ready, empty, failed }
struct Patient: Codable, Identifiable {
    var id: String
    var name: String
    var age: Int
    var sex: String
    var bed: String
    var history: String
    var color: String
    var scenario: String?
    var admittedAt: String
    var allergies: String
    var reading: Reading?
}

struct ValueBounds: Codable {
    var severeLow: Double
    var mildLow: Double
    var mildHigh: Double
    var severeHigh: Double
}
struct LowerBounds: Codable { var severeLow: Double; var mildLow: Double }
struct DemoRules: Codable {
    var hr: ValueBounds
    var spo2: LowerBounds?
    var temp: ValueBounds
    var staleAfterSeconds: Double
}

enum WireJSON {
    static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let text = try decoder.singleValueContainer().decode(String.self)
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let value = formatter.date(from: text) { return value }
            formatter.formatOptions = [.withInternetDateTime]
            if let value = formatter.date(from: text) { return value }
            throw DecodingError.dataCorruptedError(in: try decoder.singleValueContainer(), debugDescription: "Expected ISO 8601 timestamp")
        }
        return decoder
    }
    static func encoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .custom { value, encoder in
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            var c = encoder.singleValueContainer()
            try c.encode(formatter.string(from: value))
        }
        return encoder
    }
}
