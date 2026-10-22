import {readFileSync,writeFileSync} from 'node:fs';
const root=new URL('../',import.meta.url);
const read=name=>JSON.parse(readFileSync(new URL(`shared/${name}.json`,root),'utf8'));
const text='// Generated from shared/*.json. Run npm run generate:shared after editing fixtures.\n'+
  `export const DEMO_PATIENTS = ${JSON.stringify(read('demo-patients'),null,2)};\n`+
  `export const DEMO_RULES = ${JSON.stringify(read('demo-rules'),null,2)};\n`+
  `export const DEMO_SESSIONS = ${JSON.stringify(read('demo-sessions'),null,2)};\n`;
writeFileSync(new URL('dist/fixtures.js',root),text);

writeFileSync(new URL('../public/carelink-config.json', import.meta.url), readFileSync(new URL('../shared/carelink-config.json', import.meta.url),'utf8'));
