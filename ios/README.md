# CareLink optional iPhone client

Android is the required coursework delivery. This optional SwiftUI project has real API login, role/patient scope, heart-rate/temperature/fall readings, five-second charts, stored alerts and caregiver acknowledgement. It does not require SpO2. The fixed header shows only the current backend assessment.

Open `CareLink.xcodeproj` in full Xcode. Set an HTTP server address on the login screen: `http://127.0.0.1:8000` for a simulator on the Mac, or `http://<Mac-LAN-IP>:8000` on a phone. The local coursework configuration permits HTTP; no certificate installation is required. Change any previously saved HTTPS address to HTTP. Cookies and CSRF tokens remain in memory; passwords are not saved.

The project uses the resources in `../shared/`, so retain the folder structure. Configure your own signing team before installing on an iPhone. This Mac has Command Line Tools but no full Xcode/iOS SDK; no full SwiftUI build, signed IPA or iPhone runtime verification is claimed.

From the repository root, `npm run test:ios-core` runs Foundation/core checks. On this Mac set `CARELINK_MACOS_SDK=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk`. These checks do not establish an iOS app build. Current evidence and remaining work are recorded in `../INTEGRATION.md` and `../review/http-delivery/RESULTS.md`.
