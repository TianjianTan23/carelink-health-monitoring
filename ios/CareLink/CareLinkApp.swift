import SwiftUI

@main
@MainActor
struct CareLinkApp: App {
    @StateObject private var store = DemoStore()
    var body: some Scene {
        WindowGroup {
            RootView().environmentObject(store).foregroundStyle(Color("CareInk")).tint(Color("AccentColor"))
                .preferredColorScheme(store.appearance == "system" ? nil : store.appearance == "dark" ? .dark : .light)
                .environment(\.locale, Locale(identifier: store.language == .zh ? "zh-Hans" : "en"))
        }
    }
}
