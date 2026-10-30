#pragma once
#include <stdint.h>
#include <stdio.h>
#include <string.h>

// Portable canonicalization shared by the actual firmware and host vector tests.
// Crypto callbacks return zero on success. Never print key/canonical/header values.
namespace carelink {
using Sha256 = int (*)(const uint8_t *, size_t, uint8_t *);
using Hmac256 = int (*)(const uint8_t *, size_t, const uint8_t *, size_t, uint8_t *);
inline void hex(const uint8_t *bytes, size_t count, char *out) {
  const char *alphabet = "0123456789abcdef";
  for (size_t i = 0; i < count; ++i) { out[2*i] = alphabet[bytes[i] >> 4]; out[2*i+1] = alphabet[bytes[i] & 15]; }
  out[count*2] = 0;
}
inline int nibble(char value) {
  if (value >= '0' && value <= '9') return value - '0';
  if (value >= 'a' && value <= 'f') return value - 'a' + 10;
  return -1;
}
inline bool signature(const char *device, const char *timestamp, const char *nonce,
                      const uint8_t *body, size_t size, const char *keyHex,
                      Sha256 sha256, Hmac256 hmac256, char out[65]) {
  size_t deviceSize = strlen(device), timeSize = strlen(timestamp);
  if (!deviceSize || deviceSize > 64 || timeSize < 10 || timeSize > 12 || timestamp[0] == '0' || strlen(nonce) != 32 || strlen(keyHex) != 64) return false;
  for (size_t i=0; i<deviceSize; ++i) {
    char c=device[i]; bool letter=(c>='A'&&c<='Z')||(c>='a'&&c<='z')||(c>='0'&&c<='9');
    if (!letter && (i==0 || (c!='_' && c!='-'))) return false;
  }
  for (size_t i=0; i<timeSize; ++i) if (timestamp[i]<'0'||timestamp[i]>'9') return false;
  for (size_t i=0; i<32; ++i) if (nibble(nonce[i])<0) return false;
  uint8_t key[32], digest[32], signedDigest[32]; char bodyHash[65], canonical[320];
  for (size_t i=0; i<32; ++i) {
    int high=nibble(keyHex[2*i]), low=nibble(keyHex[2*i+1]);
    if (high<0||low<0) return false;
    key[i]=(uint8_t)((high<<4)|low);
  }
  if (sha256(body,size,digest)) { memset(key,0,sizeof(key)); return false; }
  hex(digest,32,bodyHash);
  int length=snprintf(canonical,sizeof(canonical),"CARELINK-HMAC-SHA256-V1\nPOST\n/sensor-data\n%s\n%s\n%s\n%s",device,timestamp,nonce,bodyHash);
  if (length<0 || (size_t)length>=sizeof(canonical)) { memset(key,0,sizeof(key)); return false; }
  int result=hmac256(key,sizeof(key),(const uint8_t *)canonical,(size_t)length,signedDigest);
  memset(key,0,sizeof(key));
  if (result) return false;
  hex(signedDigest,32,out);
  return true;
}
}
