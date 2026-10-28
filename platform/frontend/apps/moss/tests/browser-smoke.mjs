import {chromium} from 'file:///C:/Users/cndws/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs';
import fs from 'node:fs';
import assert from 'node:assert/strict';
const browser=await chromium.launch({channel:'msedge',headless:true});
try {
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 const sessionResponse=page.waitForResponse(r=>r.url().endsWith('/api/auth/session'));
 await page.goto('http://127.0.0.1:5173');await page.waitForLoadState('networkidle');
 await page.screenshot({path:'F:/uv/text-to-image/platform/frontend/logs/login-desktop.png',fullPage:true});
 assert.equal((await sessionResponse).status(),401);
 assert.equal(await page.getByText('无法连接平台服务，请检查后端是否已启动。',{exact:true}).count(),0);
 assert.deepEqual(errors,[]);
 console.log('REAL_WINDOW_FETCH', '401 session response handled, no false offline warning');
 console.log('TITLE',await page.title());console.log('BODY',await page.locator('body').innerText());console.log('ERRORS',JSON.stringify(errors));
 console.log('THEME LABELS',await page.locator('[aria-label="主题模式"]').count());
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:'F:/uv/text-to-image/platform/frontend/logs/login-mobile.png',fullPage:true});
 console.log('MOBILE_OVERFLOW',await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth));
 fs.writeFileSync('F:/uv/text-to-image/platform/frontend/logs/browser-initial.json',JSON.stringify({errors},null,2));
}finally {await browser.close()}
