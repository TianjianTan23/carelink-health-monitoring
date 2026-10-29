import Foundation
@main @MainActor struct LiveServerCheck {
 static func main() async throws {
  let env=ProcessInfo.processInfo.environment
  guard let username=env["CARELINK_TEST_USER"], let password=env["CARELINK_TEST_PASSWORD"] else { fatalError("Set test account environment variables") }
  let root=URL(fileURLWithPath:CommandLine.arguments[1])
  var config=try WireJSON.decoder().decode(ServiceConfiguration.self,from:Data(contentsOf:root.appendingPathComponent("carelink-config.json")))
  config.baseUrl=CommandLine.arguments[2];config.mode = .live;config.apiConfirmed=true
  let rules=try WireJSON.decoder().decode(DemoRules.self,from:Data(contentsOf:root.appendingPathComponent("demo-rules.json")))
  let api=try LiveApiService(configuration:config,rules:rules)
  let session=try await api.authenticate(username:username,password:password)
  let patients=try await api.getPatients()
  guard let patient=patients.first,session.patientIds.contains(patient.id) else { fatalError("Missing authorized patient") }
  let history=try await api.getHistory(patientID:patient.id)
  let predictions=try await api.getPredictions(patientID:patient.id)
  let alerts=try await api.getAlerts()
  guard patient.reading?.metrics.spo2 == nil else { fatalError("Unexpected SpO2") }
  print("PASS native URLSession login/cookie, authorized patients, three-sensor JSON, history, predictions, alerts: \(history.count) readings, \(predictions.count) predictions, \(alerts.count) alerts")
  await api.logout()
  do { _ = try await api.getPatients(); fatalError("Signed-out request succeeded") } catch ServiceError.forbidden { print("PASS native sign-out") }
 }
}
