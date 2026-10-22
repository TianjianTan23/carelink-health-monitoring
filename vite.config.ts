import {defineConfig} from 'vitest/config';
export default defineConfig({
  build:{outDir:'build',target:'es2022'},
  server:{host:'127.0.0.1',port:5173},
  test:{environment:'jsdom',include:['src/**/*.test.{ts,tsx}'],setupFiles:['./src/test/setup.ts'],restoreMocks:true},
});
