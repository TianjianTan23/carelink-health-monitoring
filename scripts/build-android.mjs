import {spawnSync} from 'node:child_process';
import {existsSync,mkdirSync,readFileSync,writeFileSync,copyFileSync,chmodSync} from 'node:fs';
import {resolve} from 'node:path';
import {randomBytes,createHash} from 'node:crypto';
const root=process.cwd(),task=resolve('.coursework');mkdirSync(task,{recursive:true,mode:0o700});
const localJdk=existsSync('.coursework/jdk-home.txt')?readFileSync('.coursework/jdk-home.txt','utf8').trim():undefined;
const candidates=[process.env.JAVA_HOME,localJdk,'/Applications/Android Studio.app/Contents/jbr/Contents/Home','/Applications/PyCharm.app/Contents/jbr/Contents/Home'].filter(Boolean);
const java=candidates.find(p=>existsSync(p+'/bin/javac')&&existsSync(p+'/bin/jlink'));
const sdk=process.env.ANDROID_HOME??resolve('.coursework/sdk');
if(!java||!existsSync(sdk+'/platforms/android-36/android.jar'))throw new Error('Java21 and Android SDK36 required. Set JAVA_HOME/ANDROID_HOME; see README.');
const env={...process.env,JAVA_HOME:java,ANDROID_HOME:sdk,ANDROID_SDK_ROOT:sdk,ANDROID_USER_HOME:resolve('.coursework/android-user'),GRADLE_USER_HOME:resolve('.coursework/gradle')};
function run(cmd,args,opts={}){const r=spawnSync(cmd,args,{stdio:'inherit',env,...opts});if(r.status!==0)process.exit(r.status??1);}
run('npm',['run','android:sync']);
const signing=resolve('.coursework/signing');mkdirSync(signing,{recursive:true,mode:0o700});
const props=signing+'/release.properties',keystore=signing+'/coursework-release.keystore';
if(!existsSync(props)){
 if(existsSync(keystore))throw new Error('Existing signing material without properties: preserve it and inspect locally.');
 const password=randomBytes(32).toString('base64url');
 run(java+'/bin/keytool',['-genkeypair','-keystore',keystore,'-storetype','PKCS12','-storepass:env','CARELINK_BUILD_PASSWORD','-keypass:env','CARELINK_BUILD_PASSWORD','-alias','coursework','-keyalg','RSA','-keysize','3072','-validity','3650','-dname','CN=CareLink Coursework'],{env:{...env,CARELINK_BUILD_PASSWORD:password},stdio:'pipe'});
 writeFileSync(props,`storeFile=${keystore.replaceAll('\\','/') }\nstorePassword=${password}\nkeyAlias=coursework\nkeyPassword=${password}\n`,{mode:0o600,flag:'wx'});
 console.log('Created private coursework signing identity in ignored .coursework/signing (no passwords printed).');
}
writeFileSync('android/local.properties','sdk.dir='+sdk.replaceAll('\\','/')+'\n');
const tasks=['--no-daemon','--console=plain','assembleRelease','testDebugUnitTest'];
if(process.argv.includes('--device-tests')){
 tasks.push('connectedDebugAndroidTest');
 for(const [key,name] of [['CARELINK_ANDROID_TEST_ORIGIN','gatewayOrigin'],['CARELINK_ANDROID_TEST_DEVICE','expectedDeviceId'],['CARELINK_ANDROID_TEST_TIMESTAMP','expectedTimestamp']])if(env[key])tasks.push('-Pandroid.testInstrumentationRunnerArguments.'+name+'='+env[key]);
}
run('./gradlew',tasks,{cwd:resolve('android')});
chmodSync(keystore,0o600);
const output=resolve('.coursework/deliverables');mkdirSync(output,{recursive:true});
const apk='android/app/build/outputs/apk/release/app-release.apk';
run(sdk+'/build-tools/36.0.0/apksigner',['verify','--verbose',resolve(apk)]);
const target=output+'/CareLink-integrated-release.apk';copyFileSync(apk,target);
writeFileSync(output+'/CareLink-integrated-release.apk.sha256',createHash('sha256').update(readFileSync(target)).digest('hex')+'  CareLink-integrated-release.apk\n');
console.log('Signed release APK: '+target);
