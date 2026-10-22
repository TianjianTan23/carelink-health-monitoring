import SwiftUI
import Charts

extension RiskLevel {
    var color: Color { switch self { case .red: return Color("CareRed"); case .yellow: return Color("CareYellow"); case .green: return Color("CareGreen"); case .unknown: return .secondary } }
    var symbol: String { self == .green ? "checkmark.shield.fill" : self == .unknown ? "questionmark.circle.fill" : "exclamationmark.triangle.fill" }
}

@MainActor
struct RootView: View {
    @EnvironmentObject private var store: DemoStore
    @Environment(\.scenePhase) private var scenePhase
    var body: some View {
        Group {
            if store.session == nil { LoginView() }
            else {
                TabView {
                    if store.mode == .pro {
                        NavigationStack { PatientListView() }.tabItem { Label(store.t("患者", "Patients"), systemImage: "person.2.fill") }
                        NavigationStack { AlertsView() }.tabItem { Label(store.t("警报", "Alerts"), systemImage: "exclamationmark.triangle") }
                    } else {
                        NavigationStack { BasicView() }.tabItem { Label(store.t("健康", "Health"), systemImage: "heart.fill") }
                        NavigationStack { AlertsView() }.tabItem { Label(store.t("提醒", "Alerts"), systemImage: "bell") }
                    }
                    if store.dataMode == .mock { NavigationStack { ScenariosView() }.tabItem { Label(store.t("演示", "Demo"), systemImage: "slider.horizontal.3") } }
                    NavigationStack { AccountView() }.tabItem { Label(store.t("账户", "Account"), systemImage: "person.crop.circle") }
                }.id(store.mode)
            }
        }
        .task {
            while !Task.isCancelled {
                do { try await Task.sleep(nanoseconds: 5_000_000_000) } catch { break }
                store.now = Date()
                if scenePhase == .active && store.autoRefresh && store.dataMode == .mock && store.session != nil { await store.refresh() }
            }
        }
    }
}

@MainActor
struct LanguageButton: View {
    @EnvironmentObject private var store: DemoStore
    var body: some View {
        Button(store.language == .zh ? "English" : "中文") { store.language = store.language == .zh ? .en : .zh }
            .accessibilityIdentifier("languageSwitch")
    }
}
@MainActor
struct DemoNotice: View {
    @EnvironmentObject private var store: DemoStore
    var body: some View {
        Label(store.dataMode == .mock ? store.t("虚构数据 · 演示规则，非真实照护判断", "Fictional data · Demo rules, not real health assessment") : store.t("API 模式 · 仅显示后端返回记录", "API mode · Backend records only"), systemImage: "info.circle")
            .font(.caption).foregroundStyle(.secondary).accessibilityIdentifier("demoNotice")
    }
}
@MainActor
struct ErrorNotice: View {
    @EnvironmentObject private var store: DemoStore
    var body: some View {
        if let error = store.error {
            VStack(alignment: .leading, spacing: 8) {
                Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.red)
                Button(store.t("重试", "Retry")) { Task { await store.refresh() } }
            }.font(.footnote)
        }
    }
}
@MainActor
struct LoginView: View {
    @EnvironmentObject private var store: DemoStore
    @State private var mode: AppMode = .pro
    @State private var username = "demo@carelink.example"
    @State private var password = "demo1234"
    @State private var issue: LoginIssue?
    @State private var showPassword = false
    @FocusState private var focusedField: LoginField?
    private enum LoginField: Hashable { case username, password }
    private var issueText: String? {
        switch issue {
        case .usernameRequired: return store.t("请输入邮箱或用户名。", "Enter an email or username.")
        case .passwordRequired: return store.t("请输入演示密码。", "Enter the demo password.")
        case .rejected: return store.t("登录失败（模拟）：演示密码为 demo1234。", "Sign-in failed (simulated): the demo password is demo1234.")
        case nil: return nil
        }
    }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: CareDesign.Space.s24) {
                    Image(systemName: "heart.fill").font(.system(size: 34, weight: .medium)).foregroundStyle(Color("AccentColor"))
                        .frame(width: 76, height: 76).background(Color("CareMint"), in: RoundedRectangle(cornerRadius: CareDesign.Corner.dialog, style: .continuous)).padding(.top, CareDesign.Space.s24).accessibilityHidden(true)
                    Text("CareLink").font(.largeTitle.bold())
                    Text(store.t("把关心，连接起来", "Keep care connected")).font(.title2)
                    Text(store.t("让专业照护与家人的牵挂，时刻相伴。", "A shared space for professional care and family connection.")).foregroundStyle(.secondary)
                    if store.dataMode == .mock {
                    Picker(store.t("演示模式", "Demo mode"), selection: $mode) {
                        Text("Pro").tag(AppMode.pro); Text("Basic").tag(AppMode.basic)
                    }.pickerStyle(.segmented).accessibilityIdentifier("loginMode")
                    Label(mode == .pro ? store.t("医护视角：多患者、历史、原始数据与 AI", "Clinician view: multiple patients, history, raw data & AI") : store.t("患者/家属视角：已关联患者的四项关键指标", "Patient/family view: four key metrics for your linked patient"), systemImage: mode == .pro ? "person.2" : "heart")
                        .font(.subheadline)
                    VStack(alignment: .leading, spacing: 12) {
                        Text(store.t("邮箱或用户名", "Email or username")).font(.subheadline)
                        TextField(store.t("演示用户名", "Demo username"), text: $username)
                            .textInputAutocapitalization(.never).autocorrectionDisabled().textFieldStyle(.plain)
                            .keyboardType(.emailAddress).submitLabel(.next).focused($focusedField, equals: .username)
                            .onSubmit { focusedField = .password }
                            .padding(CareDesign.Space.s12).background(Color("CareBackground"), in: RoundedRectangle(cornerRadius: CareDesign.Corner.control))
                            .accessibilityIdentifier("loginUsername")
                        Text(store.t("密码", "Password")).font(.subheadline)
                        HStack {
                            Group {
                                if showPassword { TextField(store.t("演示密码", "Demo password"), text: $password) }
                                else { SecureField(store.t("演示密码", "Demo password"), text: $password) }
                            }.textInputAutocapitalization(.never).autocorrectionDisabled()
                                .focused($focusedField, equals: .password).accessibilityIdentifier("loginPassword")
                            Button { showPassword.toggle() } label: { Image(systemName: showPassword ? "eye.slash" : "eye").frame(minWidth: 44, minHeight: 44) }
                                .accessibilityLabel(showPassword ? store.t("隐藏密码", "Hide password") : store.t("显示密码", "Show password"))
                        }.padding(CareDesign.Space.s12).background(Color("CareBackground"), in: RoundedRectangle(cornerRadius: CareDesign.Corner.control))
                        if let text = issueText {
                            Label(text, systemImage: "exclamationmark.circle").font(.footnote).foregroundStyle(Color("CareRed"))
                                .accessibilityIdentifier("loginError")
                        }
                    }
                    .careCard()
                    Text(store.t("预填虚构账号，密码 demo1234。请勿输入真实凭据。", "Fictional account prefilled; password: demo1234. Do not enter real credentials."))
                        .font(.caption).foregroundStyle(.secondary)
                    } else {
                        Text(store.t("使用后端已认证会话，角色和患者范围由服务器决定。此页面不发送账号密码。", "Use an authenticated backend session. Server determines role and patient scope; this screen does not send credentials.")).font(.subheadline)
                    }
                    Button {
                        issue = store.dataMode == .mock ? DemoLogin.validate(username: username, password: password) : nil
                        if issue == nil { Task { await store.signIn(mode) } }
                    } label: {
                        HStack { if store.loading { ProgressView().tint(.white) }; Text(store.dataMode == .mock ? store.t("登录演示", "Sign in to demo") : store.t("读取已认证会话", "Load authenticated session")); Spacer(); Image(systemName: "arrow.right") }
                            .frame(minHeight: 32)
                    }.buttonStyle(.borderedProminent).controlSize(.large).clipShape(RoundedRectangle(cornerRadius: CareDesign.Corner.control)).disabled(store.loading || !store.configured).accessibilityIdentifier("enterDemo")
                    ErrorNotice()
                    DemoNotice()
                    Text(store.dataMode == .mock ? store.t("此登录仅模拟表单交互，不验证真实身份。后端和 AI 尚未接入。", "This form simulates sign-in only and does not verify real identity. Backend and AI are not connected.") : store.t("接口契约仍需与组员确认；不会将 API 失败替换成模拟数据。", "The contract still needs team confirmation. API failures never substitute mock data."))
                        .font(.footnote).foregroundStyle(.secondary)
                }.padding(CareDesign.Space.s24)
            }.background(Color("CareBackground"))
                .toolbar { ToolbarItem(placement: .topBarTrailing) { LanguageButton() } }
        }
    }
}

@MainActor
struct StatusBadge: View {
    @EnvironmentObject private var store: DemoStore
    let report: StatusReport
    var body: some View {
        Label(store.levelName(report.level), systemImage: report.level.symbol)
            .font(.caption.weight(.semibold)).foregroundStyle(report.level.color)
            .padding(.horizontal, 9).padding(.vertical, 6)
            .background(report.level.color.opacity(0.1), in: Capsule())
    }
}
@MainActor
struct AvatarView: View {
    @EnvironmentObject private var store: DemoStore
    let patient: Patient
    var body: some View {
        Text(String(store.name(patient).prefix(1))).font(.headline)
            .frame(width: 44, height: 44).background(Color("CareMint"), in: Circle()).foregroundStyle(Color("AccentColor"))
            .accessibilityHidden(true)
    }
}
@MainActor
struct PatientRow: View {
    @EnvironmentObject private var store: DemoStore
    let patient: Patient
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 12) {
                AvatarView(patient: patient)
                VStack(alignment: .leading, spacing: 3) {
                    Text(store.name(patient)).font(.headline)
                    Text("\(patient.age) · \(store.t("床位", "Bed")) \(patient.bed)").font(.caption).foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
            }
            StatusBadge(report: store.report(patient.reading))
            Text(store.firstReason(store.report(patient.reading))).font(.caption).foregroundStyle(.secondary)
            Text("\(store.t("最近采集", "Last sample")): \(store.time(patient.reading?.measuredAt))").font(.caption2).foregroundStyle(.secondary)
            HStack {
                ForEach(MetricKey.allCases) { key in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(store.metricName(key)).font(.caption2).foregroundStyle(.secondary)
                        Text("\(store.value(patient.reading, key)) \(key.unit)").font(.subheadline.monospacedDigit())
                    }.frame(maxWidth: .infinity, alignment: .leading)
                }
            }
        }.padding(.vertical, 6).accessibilityElement(children: .combine)
    }
}
@MainActor
struct PatientListView: View {
    @EnvironmentObject private var store: DemoStore
    @State private var search = ""
    @State private var filter = "all"
    var filtered: [Patient] {
        store.visiblePatients.filter { patient in
            (filter == "all" || store.report(patient.reading).level.rawValue == filter) &&
            (search.isEmpty || "\(store.name(patient)) \(patient.name) \(patient.bed) \(patient.id)".localizedCaseInsensitiveContains(search))
        }.sorted { store.report($0.reading).level.rank < store.report($1.reading).level.rank }
    }
    var body: some View {
        List {
            Section { DemoNotice(); ErrorNotice(); if store.patientLoadState == .loading { ProgressView(store.t("加载患者…", "Loading patients…")) } }
            Section {
                HStack {
                    ForEach([RiskLevel.red, .yellow, .green]) { level in
                        Button { filter = level.rawValue } label: {
                            VStack(alignment: .leading, spacing: 6) {
                                Image(systemName: level.symbol).foregroundStyle(level.color)
                                Text("\(store.visiblePatients.filter { store.report($0.reading).level == level }.count)").font(.title2.bold())
                                Text(store.levelName(level)).font(.caption2).foregroundStyle(.secondary)
                            }.frame(maxWidth: .infinity, alignment: .leading)
                        }.buttonStyle(.plain)
                    }
                }
                Picker(store.t("状态", "Status"), selection: $filter) {
                    Text(store.t("全部", "All")).tag("all")
                    ForEach(RiskLevel.allCases) { Text(store.levelName($0)).tag($0.rawValue) }
                }
            }
            if search.isEmpty && filter == "all" {
                let priority = store.visiblePatients.filter { store.report($0.reading).level == .red }
                if !priority.isEmpty {
                    Section {
                        ForEach(priority.prefix(2)) { patient in
                            NavigationLink { PatientDetailView(patientID: patient.id) } label: {
                                HStack(spacing: CareDesign.Space.s12) {
                                    Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(Color("CareRed"))
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(store.name(patient)).font(.headline)
                                        Text(store.firstReason(store.report(patient.reading))).font(.caption).foregroundStyle(.secondary)
                                    }
                                }.padding(.vertical, CareDesign.Space.s8)
                            }
                        }
                    } header: { Text(store.t("优先关注", "Needs your attention")) }
                }
            }
            Section(store.t("授权患者", "Authorized patients")) {
                if filtered.isEmpty { Text(store.t("没有匹配的患者，请调整搜索或筛选。", "No matching patients. Try another search or filter.")).foregroundStyle(.secondary) }
                ForEach(filtered) { patient in
                    NavigationLink { PatientDetailView(patientID: patient.id) } label: { PatientRow(patient: patient) }
                        .accessibilityIdentifier("patient-\(patient.id)")
                }
            }
        }.listStyle(.insetGrouped).scrollContentBackground(.hidden).background(Color("CareBackground"))
            .navigationTitle(store.t("患者 · Pro", "Patients · Pro"))
            .searchable(text: $search, prompt: Text(store.t("姓名、床位或编号", "Name, bed or ID")))
            .refreshable { await store.refresh() }
            .toolbar { ToolbarItem(placement: .topBarTrailing) { LanguageButton() } }
    }
}

@MainActor
struct MetricCard: View {
    @EnvironmentObject private var store: DemoStore
    let reading: Reading?
    let key: MetricKey
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            CareMetricLabel(title: store.metricName(key), symbol: key.symbol, color: key == .hr ? Color("CareRed") : key == .temp ? Color("CareYellow") : Color("AccentColor"))
            HStack(alignment: .firstTextBaseline, spacing: 5) {
                Text(store.value(reading, key)).font(.system(.largeTitle, design: .rounded).weight(.semibold)).minimumScaleFactor(0.65).lineLimit(1)
                Text(key.unit).font(.caption).foregroundStyle(.secondary)
            }
            Text(store.qualityNote(reading, key: key)).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }.frame(maxWidth: .infinity, minHeight: 150, alignment: .topLeading).careCard()
            .accessibilityElement(children: .combine)
    }
}
@MainActor
struct FallCard: View {
    @EnvironmentObject private var store: DemoStore
    let reading: Reading?
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            CareMetricLabel(title: store.t("跌倒监测", "Fall monitoring"), symbol: "checkmark.shield", color: Color("AccentColor"))
            Text(reading?.fall.active == true ? store.t("可能跌倒", "Possible fall") : store.fresh(reading) && reading?.fall.quality == .good ? store.t("未检测到", "Not detected") : store.t("暂不可用", "Unavailable"))
                .font(.title2.weight(.semibold)).foregroundStyle(reading?.fall.active == true ? Color("CareRed") : Color("CareInk"))
            Text(store.t("设备提示需人工核实", "Device alerts need human review")).font(.caption).foregroundStyle(.secondary)
        }.frame(maxWidth: .infinity, minHeight: 150, alignment: .topLeading).careCard()
            .accessibilityElement(children: .combine)
    }
}
@MainActor
struct MetricGrid: View {
    @Environment(\.dynamicTypeSize) private var size
    let reading: Reading?
    var body: some View {
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), alignment: .top), count: size.isAccessibilitySize ? 1 : 2), spacing: CareDesign.Space.s12) {
            ForEach(MetricKey.allCases) { MetricCard(reading: reading, key: $0) }
            FallCard(reading: reading)
        }
    }
}
@MainActor
struct BasicView: View {
    @EnvironmentObject private var store: DemoStore
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: CareDesign.Space.s20) {
                DemoNotice(); ErrorNotice()
                if store.patientLoadState == .loading { ProgressView(store.t("加载中…", "Loading…")) }
                if let patient = store.visiblePatients.first {
                    Text(store.t("今天，也在好好守护。", "Here for your family, every day.")).font(.title2.weight(.semibold))
                    HStack(spacing: CareDesign.Space.s12) {
                        AvatarView(patient: patient)
                        VStack(alignment: .leading, spacing: 4) {
                            Text(store.name(patient)).font(.headline)
                            Text(store.t("关联家人", "Your linked family member")).font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer(minLength: 0)
                        Image(systemName: "heart.fill").foregroundStyle(Color("AccentColor")).accessibilityHidden(true)
                    }.careCard()
                    let report = store.report(patient.reading)
                    VStack(alignment: .leading, spacing: 12) {
                        StatusBadge(report: report)
                        Text(store.firstReason(report)).font(.body)
                        if report.incomplete { Text(store.t("部分数据待确认，请检查设备。", "Some information is unverified. Please check the device.")).font(.footnote) }
                    }.frame(maxWidth: .infinity, alignment: .leading).padding(CareDesign.Space.s20)
                        .background(report.level.color.opacity(0.09), in: RoundedRectangle(cornerRadius: CareDesign.Corner.card, style: .continuous))
                    MetricGrid(reading: patient.reading)
                    VStack(alignment: .leading, spacing: CareDesign.Space.s12) {
                    Text("\(store.t("记录来源", "Snapshot source")): \(patient.reading?.source ?? "—")").font(.caption).foregroundStyle(.secondary)
                    Label("\(store.t("最后成功更新", "Last successful update")): \(store.time(store.lastSuccessfulUpdate))", systemImage: "clock").font(.footnote).foregroundStyle(.secondary)
                    Text("\(store.t("最近采集", "Last sample")): \(store.time(patient.reading?.measuredAt))").font(.caption).foregroundStyle(.secondary)
                    Button(store.t("刷新状态", "Refresh status")) { Task { await store.refresh() } }.buttonStyle(.bordered).controlSize(.large).frame(maxWidth: .infinity, alignment: .trailing)
                    }.careCard()
                    Text(store.t("温度是表面测温演示值，未转换为核心体温。", "Temperature is a mock surface reading, not core body temperature.")).font(.footnote).foregroundStyle(.secondary)
                } else {
                    ContentUnavailableView(store.t("暂无授权患者", "No linked patient"), systemImage: "person.crop.circle.badge.questionmark")
                }
            }.padding(CareDesign.Space.s20)
        }.background(Color("CareBackground")).navigationTitle(store.t("健康 · Basic", "Health · Basic"))
            .refreshable { await store.refresh() }
            .toolbar { ToolbarItem(placement: .topBarTrailing) { LanguageButton() } }
    }
}
