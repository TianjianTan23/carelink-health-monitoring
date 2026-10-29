#!/bin/sh
# Reproducible native Java build using official SDK tools; no downloaded app code or WebView.
set -eu
cd "$(dirname "$0")"
: "${JAVA_HOME:?Set JAVA_HOME to a JDK 17 directory}"
: "${ANDROID_HOME:?Set ANDROID_HOME to an SDK containing platform 35 and build-tools 35.0.0}"
SDK_TOOLS="$ANDROID_HOME/build-tools/35.0.0"
PLATFORM_JAR="$ANDROID_HOME/platforms/android-35/android.jar"
BUILD_DIR="$PWD/app/build/manual"
mkdir -p "$BUILD_DIR/classes" "$BUILD_DIR/dex" "$BUILD_DIR/res" "$BUILD_DIR/generated/org/carelink/monitor" "$PWD/app/build/outputs/apk/debug"
# Framework tooling needs the JDK; settings apply only to this build process.
export PATH="$JAVA_HOME/bin:$PATH"
cat > "$BUILD_DIR/generated/org/carelink/monitor/BuildConfig.java" <<'JAVA'
package org.carelink.monitor; public final class BuildConfig { public static final boolean DEBUG=true; }
JAVA
python3 - "$BUILD_DIR/AndroidManifest.xml" <<'PY'
from pathlib import Path
import sys
s=Path('app/src/main/AndroidManifest.xml').read_text().replace('<manifest xmlns:', '<manifest package="org.carelink.monitor" android:versionCode="1" android:versionName="1.0" xmlns:')
s=s.replace('android:usesCleartextTraffic="true"','android:usesCleartextTraffic="true" android:debuggable="true"')
Path(sys.argv[1]).write_text(s)
PY
"$SDK_TOOLS/aapt2" compile --dir app/src/main/res -o "$BUILD_DIR/resources.zip"
"$SDK_TOOLS/aapt2" link -o "$BUILD_DIR/unsigned.apk" -I "$PLATFORM_JAR" --manifest "$BUILD_DIR/AndroidManifest.xml" --min-sdk-version 26 --target-sdk-version 35 --java "$BUILD_DIR/generated" "$BUILD_DIR/resources.zip"
find app/src/main/java "$BUILD_DIR/generated" -name '*.java' > "$BUILD_DIR/sources.list"
"$JAVA_HOME/bin/javac" -encoding UTF-8 --release 8 -classpath "$PLATFORM_JAR" -d "$BUILD_DIR/classes" @"$BUILD_DIR/sources.list"
"$JAVA_HOME/bin/jar" cf "$BUILD_DIR/classes.jar" -C "$BUILD_DIR/classes" .
"$SDK_TOOLS/d8" --lib "$PLATFORM_JAR" --min-api 26 --output "$BUILD_DIR/dex" "$BUILD_DIR/classes.jar"
python3 - "$BUILD_DIR" <<'PY'
import sys,zipfile
from pathlib import Path
p=Path(sys.argv[1])
with zipfile.ZipFile(p/'unsigned.apk','a',compression=zipfile.ZIP_STORED) as z:
 for d in (p/'dex').glob('*.dex'):z.write(d,d.name)
PY
"$SDK_TOOLS/zipalign" -f 4 "$BUILD_DIR/unsigned.apk" "$BUILD_DIR/aligned.apk"
if [ ! -f "$BUILD_DIR/debug.keystore" ]; then
  "$JAVA_HOME/bin/keytool" -genkeypair -keystore "$BUILD_DIR/debug.keystore" -storepass android -keypass android -alias androiddebugkey -dname 'CN=Android Debug,O=CareLink Coursework,C=CN' -keyalg RSA -keysize 2048 -validity 3650 -noprompt
fi
APK="$PWD/app/build/outputs/apk/debug/carelink-debug.apk"
"$SDK_TOOLS/apksigner" sign --ks "$BUILD_DIR/debug.keystore" --ks-pass pass:android --key-pass pass:android --out "$APK" "$BUILD_DIR/aligned.apk"
"$SDK_TOOLS/apksigner" verify --verbose "$APK"
printf '\nBuilt %s\n' "$APK"
