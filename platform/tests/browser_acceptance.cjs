const assert=require('node:assert/strict');
const fs=require('node:fs');
const {chromium}=require('C:/Users/cndws/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const ROOT='F:/uv/text-to-image';
const BASE='http://127.0.0.1:5173';
const PASSWORD='QA-only-local-fixture-42!'; // isolated QA database only
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const context=await browser.newContext({baseURL:BASE,viewport:{width:1440,height:1000},timezoneId:'Asia/Shanghai'});
 const p=await context.newPage();const errors=[];p.on('pageerror',e=>errors.push(e.message));
 async function login(name){await p.getByPlaceholder('请输入用户名').fill(name);await p.getByPlaceholder('请输入密码').fill(PASSWORD);await p.getByRole('button',{name:'登录工作室',exact:true}).click();await p.getByRole('button',{name:'退出',exact:true}).waitFor();await p.waitForLoadState('networkidle');}
 async function theme(label,dark){await p.locator('[aria-label="主题模式"]').click();await p.getByText(label,{exact:true}).last().click();await p.waitForTimeout(100);assert.equal(await p.locator('html').evaluate(e=>e.classList.contains('dark')),dark);}
 await p.goto(BASE);await p.waitForLoadState('networkidle');await login('qa_alice');
 assert.ok(await p.locator('[data-layout-region="layout"]').count(),'Real Vben layout missing');
 await theme('亮色',false);await p.screenshot({path:ROOT+'/platform/logs/studio-light.png',fullPage:true});
 await p.reload();await p.getByRole('button',{name:'退出',exact:true}).waitFor();assert.equal(await p.locator('html').evaluate(e=>e.classList.contains('dark')),false);
 await theme('暗色',true);await p.screenshot({path:ROOT+'/platform/logs/studio-dark.png',fullPage:true});
 await p.getByRole('button',{name:'个人图库',exact:true}).click();await p.locator('.gallery-image img').first().waitFor();await p.screenshot({path:ROOT+'/platform/logs/gallery-dark.png',fullPage:true});
 const list=await (await p.request.get(BASE+'/api/jobs')).json();assert.ok(list.total>=1);assert.ok(list.items.some(j=>j.prompt.includes('red ceramic')));
 const privateJob=list.items.find(j=>j.status==='succeeded');assert.ok(privateJob);
 await p.getByRole('button',{name:'退出',exact:true}).click();await p.getByPlaceholder('请输入用户名').waitFor();await login('qa_bravo');
 const cross=await p.request.get(BASE+'/api/jobs/'+privateJob.id+'/image');assert.equal(cross.status(),404);
 const other=await (await p.request.get(BASE+'/api/jobs')).json();assert.ok(other.items.every(j=>!j.prompt.includes('red ceramic')));
 await p.getByRole('button',{name:'退出',exact:true}).click();await p.getByPlaceholder('请输入用户名').waitFor();await login('qa_admin');
 await p.getByRole('button',{name:'账号管理',exact:true}).click();await p.getByText('工作室成员',{exact:true}).waitFor();
 const name='qa_browser_'+Date.now();await p.getByPlaceholder('新成员用户名').fill(name);await p.getByPlaceholder('至少 10 个字符',{exact:true}).fill(PASSWORD);await p.getByRole('button',{name:'创建账号',exact:true}).click();await p.getByText(name,{exact:true}).waitFor();
 await p.screenshot({path:ROOT+'/platform/logs/users-dark.png',fullPage:true});
 await p.getByRole('button',{name:'退出',exact:true}).click();await p.getByPlaceholder('请输入用户名').waitFor();await p.setViewportSize({width:390,height:844});await p.screenshot({path:ROOT+'/platform/logs/login-mobile.png',fullPage:true});
 assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth),false,'mobile overflow');
 assert.deepEqual(errors,[]);const report={status:'success',real_vben_layout:true,login_users:3,private_images_cross_user_status:404,admin_create_user:true,manual_light_dark:true,theme_persists_reload:true,mobile_no_horizontal_overflow:true,page_errors:errors,screenshots:['studio-light.png','studio-dark.png','gallery-dark.png','users-dark.png','login-mobile.png']};
 fs.writeFileSync(ROOT+'/platform/logs/browser-acceptance.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
