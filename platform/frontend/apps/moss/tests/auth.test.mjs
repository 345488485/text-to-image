import assert from 'node:assert/strict';
import {test} from 'node:test';
import {canEnterWorkspace,passwordChangeError,changeOwnPassword} from '../src/auth.ts';
import {ApiClient} from '../src/api.ts';
test('first-login account cannot enter any workspace until password changed',()=>{
 assert.equal(canEnterWorkspace(null),false);
 assert.equal(canEnterWorkspace({must_change_password:true}),false);
 assert.equal(canEnterWorkspace({must_change_password:false}),true);
});
test('password change requires current password, ten characters, different secret, and matching confirmation',()=>{
 assert.match(passwordChangeError('','replacement1','replacement1'),/当前密码/);
 assert.match(passwordChangeError('123456','short','short'),/10/);
 assert.match(passwordChangeError('replacement1','replacement1','replacement1'),/旧密码/);
 assert.match(passwordChangeError('123456','replacement1','replacement2'),/一致/);
 assert.equal(passwordChangeError('123456','replacement1','replacement1'),'');
});
test('first password change posts CSRF credentials and accepts rotated session',async()=>{
 let captured;
 const api=new ApiClient(async(path,options)=>{captured={path,options};return Response.json({user:{id:'admin-id',username:'admin',role:'admin',must_change_password:false},csrf_token:'rotated-csrf'})});
 api.csrfToken='initial-csrf';
 const session=await changeOwnPassword(api,'123456','replacement1','replacement1');
 assert.equal(captured.path,'/api/auth/change-password');
 assert.equal(captured.options.method,'POST');
 assert.equal(captured.options.credentials,'same-origin');
 assert.equal(captured.options.headers['X-CSRF-Token'],'initial-csrf');
 assert.deepEqual(JSON.parse(captured.options.body),{current_password:'123456',new_password:'replacement1'});
 assert.equal(api.csrfToken,'rotated-csrf');assert.equal(canEnterWorkspace(session.user),true);
});
test('mismatched confirmation never sends a password request',async()=>{
 let sent=false;const api=new ApiClient(async()=>{sent=true;return Response.json({})});
 await assert.rejects(changeOwnPassword(api,'123456','replacement1','not-same'),/一致/);assert.equal(sent,false);
});
test('bootstrap is public same-origin and hint is server controlled',async()=>{
 const api=new ApiClient(async(path,options)=>{assert.equal(path,'/api/auth/bootstrap');assert.equal(options.method,'GET');return Response.json({initial_setup_required:false})});
 const state=await api.request('/auth/bootstrap');assert.equal(state.initial_setup_required,false);
});
