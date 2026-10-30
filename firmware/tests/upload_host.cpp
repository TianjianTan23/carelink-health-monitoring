#include <cassert>
#include <cstring>
#include <iostream>
#include "upload_diagnostics.h"
int main() {
  assert(carelink::uploadClockReady(true, 1793100000, 1000, 500));
  assert(!carelink::uploadClockReady(false, 1793100000, 1000, 500));
  assert(!carelink::uploadClockReady(true, 100, 1000, 500));
  assert(!carelink::uploadClockReady(true, 1793100000, 21600001, 0));
  assert(carelink::uploadClockReady(true, 1793100000, 21600000, 0));
  assert(carelink::uploadClockReady(true, 1793100000, 10, UINT32_MAX - 10));
  const int denied[] = {201,204,301,400,401,403,404,405,408,409,413,415,422,429,500,503,504};
  for (int code : denied)
    assert(strcmp(carelink::uploadHttpOutcome(code), "Upload accepted") != 0);
  assert(strcmp(carelink::uploadHttpOutcome(200), "Upload accepted") == 0);
  assert(strcmp(carelink::uploadHttpOutcome(401), "Authentication rejected") == 0);
  assert(strcmp(carelink::uploadHttpOutcome(409), "Nonce rejected") == 0);
  std::cout << "Upload diagnostic policy: 26 assertions passed\n";
}
