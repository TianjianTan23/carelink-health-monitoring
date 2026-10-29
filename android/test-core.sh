#!/bin/sh
set -eu
cd "$(dirname "$0")"
: "${JAVA_HOME:?Set JAVA_HOME to JDK 17}"
: "${CARELINK_JSON_JAR:?Set CARELINK_JSON_JAR to org.json 20240303 jar (host tests only)}"
mkdir -p app/build/host-tests
"$JAVA_HOME/bin/javac" -encoding UTF-8 -cp "$CARELINK_JSON_JAR" -d app/build/host-tests app/src/main/java/org/carelink/monitor/Models.java app/src/main/java/org/carelink/monitor/Monitoring.java app/src/main/java/org/carelink/monitor/ApiClient.java app/src/main/java/org/carelink/monitor/MonitoringController.java tests/NativeChecks.java
"$JAVA_HOME/bin/java" -cp "app/build/host-tests:$CARELINK_JSON_JAR" org.carelink.monitor.NativeChecks "$@"
