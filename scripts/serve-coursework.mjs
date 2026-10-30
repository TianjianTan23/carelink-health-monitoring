import {spawnSync,spawn} from 'node:child_process';
const result=spawnSync('npm',['run','build:demo'],{stdio:'inherit'});
if(result.status!==0)process.exit(result.status??1);
const child=spawn('node_modules/.bin/vite',['preview','--outDir','build-demo','--host','127.0.0.1','--port','18500','--strictPort'],{stdio:'inherit'});
for(const event of ['SIGTERM','SIGINT'])process.on(event,()=>child.kill(event));
child.on('exit',code=>process.exit(code??0));
