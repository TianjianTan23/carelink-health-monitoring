#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
: "${JAVA_HOME:?Set JAVA_HOME}"
: "${ANDROID_HOME:?Set ANDROID_HOME}"
export PATH="$JAVA_HOME/bin:$PATH"
SDK_TOOLS="$ANDROID_HOME/build-tools/35.0.0"
PLATFORM_JAR="$ANDROID_HOME/platforms/android-35/android.jar"
DIR="$PWD/app/build/runtime-checks"
mkdir -p "$DIR/classes" "$DIR/dex"
cat > "$DIR/AndroidManifest.xml" <<'XML'
<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="org.carelink.monitor.tests"><uses-permission android:name="android.permission.INTERNET"/><application android:label="CareLink runtime checks" android:debuggable="true" android:usesCleartextTraffic="true"/><instrumentation android:name="org.carelink.monitor.tests.RuntimeChecks" android:targetPackage="org.carelink.monitor" /></manifest>
XML
"$JAVA_HOME/bin/javac" --release 8 -encoding UTF-8 -classpath "$PLATFORM_JAR:app/build/manual/classes.jar" -d "$DIR/classes" tests/RuntimeChecks.java
"$JAVA_HOME/bin/jar" cf "$DIR/tests.jar" -C "$DIR/classes" .
"$SDK_TOOLS/d8" --lib "$PLATFORM_JAR" --classpath app/build/manual/classes.jar --min-api 26 --output "$DIR/dex" "$DIR/tests.jar"
"$SDK_TOOLS/aapt2" link -o "$DIR/unsigned.apk" -I "$PLATFORM_JAR" --manifest "$DIR/AndroidManifest.xml" --min-sdk-version 26 --target-sdk-version 35
python3 - "$DIR" <<'PY'
from pathlib import Path
import zipfile,sys
p=Path(sys.argv[1])
with zipfile.ZipFile(p/'unsigned.apk','a',compression=zipfile.ZIP_STORED) as z:
 for f in (p/'dex').glob('*.dex'):z.write(f,f.name)
 for f in Path('tests/fixtures').glob('*.json'):z.write(f,'assets/'+f.name)
PY
"$SDK_TOOLS/zipalign" -f 4 "$DIR/unsigned.apk" "$DIR/aligned.apk"
"$SDK_TOOLS/apksigner" sign --ks app/build/manual/debug.keystore --ks-pass pass:android --key-pass pass:android --out "$DIR/runtime-checks.apk" "$DIR/aligned.apk"
