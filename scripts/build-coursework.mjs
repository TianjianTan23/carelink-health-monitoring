import {spawnSync} from 'node:child_process';
import {readFile,writeFile} from 'node:fs/promises';
const target=process.argv[2];if(!['android','web'].includes(target))throw new Error('Use android or web.');
const output=target==='android'?'build-android':'build-demo';
const result=spawnSync('npm',['run','build','--','--outDir',output],{stdio:'inherit',env:{...process.env,VITE_COURSEWORK:'1',VITE_DEFAULT_MODE:target==='android'?'live':'mock'}});
if(result.status!==0)process.exit(result.status??1);
const config=JSON.parse(await readFile('shared/carelink-config.json','utf8'));
await writeFile(output+'/carelink-config.json',JSON.stringify({...config,mode:target==='android'?'live':'mock',baseUrl:'',apiConfirmed:target==='android'},null,2)+'\n');
console.log('Coursework bundle: '+output+'; Android defaults to gateway API; Web demo is explicitly selected. No production config changed.');
