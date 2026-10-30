import {test} from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
import {X509Certificate} from 'node:crypto';
const read=p=>readFileSync(new URL('../'+p,import.meta.url),'utf8');
test('packaged Android uses local assets with strict transport and no remote navigation',()=>{const c=JSON.parse(read('capacitor.config.json'));assert.equal(c.webDir,'build-android');assert.equal(c.loggingBehavior,'none');assert.equal(c.server.cleartext,false);assert.equal(c.android.allowMixedContent,false);assert.equal(c.server.url,undefined);assert.equal(c.server.allowNavigation,undefined);});
test('Android backup is disabled and release trust is explicit',()=>{const xml=read('android/app/src/main/AndroidManifest.xml');assert.match(xml,/allowBackup="false"/);assert.match(xml,/usesCleartextTraffic="false"/);assert.match(read('android/app/src/main/res/xml/network_security_config.xml'),/cleartextTrafficPermitted="false"/);});
test('native bridge never logs credentials or overrides certificate validation',()=>{const java=read('android/app/src/main/java/com/carelink/coursework/CareLinkApiPlugin.java');assert.doesNotMatch(java,/setHostnameVerifier|setSSLSocketFactory|Log\.|System\.out/);assert.match(java,/followRedirects\(false\)/);assert.match(java,/cookieJar\(CookieJar.NO_COOKIES\)/);assert.doesNotMatch(java,/put\("(?:token|cookie)"[^;]+call.resolve/s);});
test('gateway CA is public and additional trust is limited to explicit local hosts',()=>{
 const pem=read('android/app/src/main/res/raw/carelink_gateway_ca.crt');
 assert.doesNotMatch(pem,/PRIVATE KEY/);assert.equal(new X509Certificate(pem).ca,true);
 const xml=read('android/app/src/main/res/xml/network_security_config.xml');
 const base=xml.match(/<base-config[\s\S]*?<\/base-config>/)[0];assert.doesNotMatch(base,/@raw\/carelink_gateway_ca/);
 const domain=xml.match(/<domain-config[\s\S]*?<\/domain-config>/)[0];
 assert.match(domain,/cleartextTrafficPermitted="false"/);
 assert.deepEqual([...domain.matchAll(/<domain includeSubdomains="false">([^<]+)<\/domain>/g)].map(m=>m[1]),['172.20.10.11','10.0.2.2','127.0.0.1']);
 assert.match(domain,/<certificates src="@raw\/carelink_gateway_ca"\/>/);
});
