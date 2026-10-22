import SwiftUI

/// Native text styles scale with the user's preferred text size.
struct CareGroupBoxStyle: GroupBoxStyle {
    func makeBody(configuration: Configuration) -> some View {
        VStack(alignment: .leading, spacing: CareDesign.Space.s16) {
            configuration.label
            configuration.content
        }.careCard()
    }
}

struct CareMetricLabel: View {
    let title: String
    let symbol: String
    let color: Color
    var body: some View {
        HStack(spacing: CareDesign.Space.s8) {
            Image(systemName: symbol).font(.subheadline.weight(.semibold))
                .foregroundStyle(color).frame(width: 30, height: 30)
                .background(color.opacity(0.1), in: RoundedRectangle(cornerRadius: CareDesign.Corner.control, style: .continuous))
                .accessibilityHidden(true)
            Text(title).font(.subheadline.weight(.medium)).fixedSize(horizontal: false, vertical: true)
        }
    }
}

enum PatientSection: String, CaseIterable, Identifiable {
    case overview, history, data
    var id: String { rawValue }
    func title(_ language: AppLanguage) -> String {
        switch self {
        case .overview: return language == .zh ? "概览" : "Overview"
        case .history: return language == .zh ? "十分钟" : "10 minutes"
        case .data: return language == .zh ? "数据与 AI" : "Data & AI"
        }
    }
}
