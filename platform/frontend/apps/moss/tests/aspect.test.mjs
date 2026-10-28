import assert from 'node:assert/strict';
import {test} from 'node:test';
import fs from 'node:fs';
import {aspectOptions,defaultAspect,inferAspect,aspectDimensions} from '../src/aspect.ts';
test('offers all three real output sizes',()=>{
 assert.deepEqual(aspectOptions.map(o=>o.value),['16:9','9:16','1:1']);
 assert.deepEqual(aspectDimensions('16:9'),{width:768,height:432});assert.deepEqual(aspectDimensions('9:16'),{width:432,height:768});assert.deepEqual(aspectDimensions('1:1'),{width:512,height:512});
});
test('new form defaults to landscape desktop and portrait phone',()=>{assert.equal(defaultAspect(1440),'16:9');assert.equal(defaultAspect(390),'9:16')});
test('history uses explicit ratio or infers from actual legacy dimensions',()=>{
 assert.equal(inferAspect({aspect_ratio:'9:16',width:432,height:768}),'9:16');
 assert.equal(inferAspect({width:768,height:432}),'16:9');assert.equal(inferAspect({width:432,height:768}),'9:16');assert.equal(inferAspect({width:512,height:512}),'1:1');
});
test('waiting component exposes different queued/running states, real position, polite updates and no percent',()=>{
 const source=fs.readFileSync(new URL('../src/GenerationWaiting.vue',import.meta.url),'utf8');
 for(const text of ['aria-live="polite"','queuePosition','queued','running','waiting-scan','waiting-dots'])assert.ok(source.includes(text),text);
 assert.ok(!source.includes('% 完成'));assert.match(source,/@media\s*\(prefers-reduced-motion:\s*reduce\)/);assert.match(source,/animation:\s*none\s*!important/);
});
test('preview ratio follows selected image or form, uses contain without cropping',()=>{
 const app=fs.readFileSync(new URL('../src/App.vue',import.meta.url),'utf8');const css=fs.readFileSync(new URL('../src/style.css',import.meta.url),'utf8');
 assert.ok(app.includes(':style="{aspectRatio:previewRatio}"'));assert.ok(app.includes('aspect_ratio:inferAspect(job)'));assert.ok(css.includes('.gallery-image>img{object-fit:contain}'));
});
