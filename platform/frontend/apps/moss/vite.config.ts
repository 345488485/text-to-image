import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import tailwindcss from '@tailwindcss/vite';
export default defineConfig({
 plugins:[vue(),tailwindcss()],
 resolve:{conditions:['source','production','development']},
 server:{host:'127.0.0.1',port:5173,strictPort:true,proxy:{'/api':{target:'http://127.0.0.1:8000',changeOrigin:false}}},
 preview:{host:'127.0.0.1',port:5173,strictPort:true},
 build:{target:'es2022',outDir:'dist'},
});
