#include <CommonCrypto/CommonDigest.h>
#include <CommonCrypto/CommonHMAC.h>
#include <iostream>
#include "device_signing.h"
int hashBody(const uint8_t *body,size_t size,uint8_t *out){return CC_SHA256(body,(CC_LONG)size,out)?0:-1;}
int signBody(const uint8_t *key,size_t keySize,const uint8_t *body,size_t size,uint8_t *out){CCHmac(kCCHmacAlgSHA256,key,keySize,body,size,out);return 0;}
int main(int argc,char **argv){
 if(argc!=6)return 2;char out[65];
 if(!carelink::signature(argv[2],argv[3],argv[4],(const uint8_t *)argv[1],strlen(argv[1]),argv[5],hashBody,signBody,out))return 3;
 std::cout<<out;return 0;
}
