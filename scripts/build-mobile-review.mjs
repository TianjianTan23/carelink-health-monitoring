import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const root=new URL('../',import.meta.url);
const read=path=>readFile(new URL(path,root),'utf8');
// Package the existing fixtures/service/rules into one offline file; no CDN or server.
const core=(await Promise.all(['dist/fixtures.js','dist/rules.js','dist/service.js'].map(read)))
 .map(s=>s.replace(/^import .*;\n/gm,'').replace(/^export /gm,''));
const css=await read('review/mobile.css'),js=await read('review/mobile.js');
const script=[...core,js].join('\n').replaceAll('</script','<\\/script');
const html=`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>CareLink · iPhone UI review</title><style>${css}</style></head><body><div id="app" class="shell"></div><p class="outside">CareLink · iPhone 布局交互预览 / Browser review companion · 非原生 iOS 运行环境 / Not a native iOS runtime<br>模拟数据 · 本地处理，不提交表单到服务器 / Mock data · No form submission to a server</p><dialog id="confirm"><form method="dialog"><h2></h2><p></p><div class="row"><button value="cancel">取消</button><button value="confirm" class="primary">确认</button></div></form></dialog><script>${script}</script></body></html>`;
const target=new URL('../work/carelink-iphone-review.html',import.meta.url);
await mkdir(new URL('../work/',import.meta.url),{recursive:true});
await writeFile(target,html);
console.log('Built offline review:',fileURLToPath(target));
