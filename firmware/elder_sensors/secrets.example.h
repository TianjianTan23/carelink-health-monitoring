#pragma once

// Copy this file to secrets.h and fill in your own local network values.
// secrets.h is ignored by Git and must never be committed.
const char *WIFI_SSID = "YOUR_2_4_GHZ_WIFI";
const char *WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// Use the Mac's LAN/hotspot address, not 127.0.0.1.
// Example: http://172.20.10.2:8000/sensor-data
const char *SERVER_URL = "http://YOUR_MAC_IP:8000/sensor-data";
