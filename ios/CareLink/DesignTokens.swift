// Generated from shared/design-tokens.json. Edit the source tokens instead.
import SwiftUI

enum CareDesign {
    enum Corner {
        static let control: CGFloat = 10
        static let card: CGFloat = 18
        static let dialog: CGFloat = 24
    }
    enum Space {
        static let s4: CGFloat = 4
        static let s8: CGFloat = 8
        static let s12: CGFloat = 12
        static let s16: CGFloat = 16
        static let s20: CGFloat = 20
        static let s24: CGFloat = 24
        static let s32: CGFloat = 32
        static let s40: CGFloat = 40
        static let s48: CGFloat = 48
    }
}

struct CareCard: ViewModifier {
    func body(content: Content) -> some View {
        content.padding(CareDesign.Space.s20)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color("CareSurface"), in: RoundedRectangle(cornerRadius: CareDesign.Corner.card, style: .continuous))
    }
}
extension View { func careCard() -> some View { modifier(CareCard()) } }
