import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ApiClient } from '../src/api.ts';
test('session credentials and CSRF use cookie + memory, never a bearer token',async()=>{
 const calls=[];const api=new ApiClient(async(path,options)=>{calls.push({path,options});return Response.json({user:{id:1,username:'alice',role:'user'},csrf_token:'test-csrf'})});
 await api.request('/auth/session');await api.request('/jobs',{method:'POST',body:{prompt:'forest',steps:8,seed:1}});
 assert.equal(calls[0].path,'/api/auth/session');assert.equal(calls[1].options.credentials,'same-origin');
 assert.equal(calls[1].options.headers['X-CSRF-Token'],'test-csrf');assert.equal(calls[1].options.headers.Authorization,undefined);
 assert.equal(JSON.parse(calls[1].options.body).prompt,'forest');
});
test('401 clears memory session and signals expired session',async()=>{
 let expired=false;const api=new ApiClient(async()=>Response.json({detail:'请重新登录'},{status:401}),()=>expired=true);
 api.csrfToken='old';await assert.rejects(api.request('/jobs'),/请重新登录/);assert.equal(api.csrfToken,'');assert.equal(expired,true);
});
test('rejects off-origin API paths',async()=>{const api=new ApiClient();await assert.rejects(api.request('https://outside.example'),/API路径/)});
test('fetch receiver is the real global, not ApiClient (Window.fetch binding)',async()=>{
 const api=new ApiClient(async function(path,options){assert.equal(this,globalThis,'Illegal invocation: wrong fetch receiver');return Response.json({ok:true})});
 assert.equal((await api.request('/status')).ok,true);
});
