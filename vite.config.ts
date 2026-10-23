import {defineConfig} from 'vitest/config';
import {loadEnv} from 'vite';
export default defineConfig(({mode})=>{
 const env=loadEnv(mode,process.cwd(),'');
 const proxy={'^/hardware-bridge(?:/|$)':{target:env.CARELINK_BRIDGE_TARGET||'http://127.0.0.1:8000',changeOrigin:true,rewrite:(path:string)=>path.replace(/^\/hardware-bridge(?=\/|$)/,'')}};
 return {
  ...(mode==='hardware'&&!env.VITE_DATA_MODE?{define:{'import.meta.env.VITE_DATA_MODE':JSON.stringify('hardware')}}:{}),
  build:{outDir:'build',target:'es2022'},
  server:{host:'127.0.0.1',port:5173,strictPort:true,proxy},
  preview:{proxy},
  test:{environment:'jsdom',include:['src/**/*.test.{ts,tsx}'],setupFiles:['./src/test/setup.ts'],restoreMocks:true},
 };
});
