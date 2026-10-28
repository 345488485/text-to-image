import assert from 'node:assert/strict';
import { test } from 'node:test';
import { resolveTheme, startTheme } from '../src/theme.ts';
for (const [h, m, expected] of [[6,59,'dark'],[7,0,'light'],[18,59,'light'],[19,0,'dark']]) {
  test(`auto at ${h}:${m} is ${expected}`, () => assert.equal(resolveTheme('auto',new Date(2026,9,27,h,m)),expected));
}
test('manual overrides time', () => {
  assert.equal(resolveTheme('light',new Date(2026,9,27,23)), 'light');
  assert.equal(resolveTheme('dark',new Date(2026,9,27,12)), 'dark');
});
function fixture(saved = null) {
  let now = new Date(2026,9,27,18,59), scheduled, theme, mode;
  const listeners = new Map(), storage = new Map(saved ? [['moss-theme',saved]] : []);
  const host = { now: () => now, storage: {getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)}, apply:(t,m)=>{theme=t;mode=m}, on:(e,f)=>listeners.set(e,f), off:e=>listeners.delete(e), schedule:(f,ms)=>{scheduled={f,ms};return 1}, clear:()=>{} };
  return {host, storage,listeners,get theme(){return theme},get mode(){return mode},get scheduled(){return scheduled},set now(v){now=v}};
}
test('saved manual preference persists and never follows the clock',()=>{
  const f=fixture('light'), c=startTheme(f.host);
  assert.equal(f.theme,'light'); c.setMode('dark'); assert.equal(f.storage.get('moss-theme'),'dark');
  f.now=new Date(2026,9,27,8); f.listeners.get('focus')(); assert.equal(f.theme,'dark'); c.stop(); assert.equal(f.listeners.size,0);
});
test('auto updates at next boundary and on focus without reload',()=>{
  const f=fixture(), c=startTheme(f.host); assert.equal(f.theme,'light'); assert.equal(f.scheduled.ms,60000);
  f.now=new Date(2026,9,27,19); f.scheduled.f(); assert.equal(f.theme,'dark');
  f.now=new Date(2026,9,28,9); f.listeners.get('focus')(); assert.equal(f.theme,'light');
  c.stop();
});
test('invalid stored preference safely falls back to auto',()=>{const f=fixture('corrupt');startTheme(f.host);assert.equal(f.mode,'auto')});
