<script setup lang="ts">
defineProps<{status:'queued'|'running';queuePosition:number|null}>();
defineEmits<{cancel:[]}>();
</script>
<template>
 <div class="generation-waiting" :class="`is-${status}`" role="status" aria-live="polite" aria-atomic="true">
  <div class="waiting-art" aria-hidden="true">
   <svg viewBox="0 0 180 110" class="waiting-drawing"><rect class="waiting-paper paper-back" x="38" y="14" width="108" height="78" rx="9"/><rect class="waiting-paper" x="23" y="21" width="116" height="78" rx="9"/><path class="waiting-landscape" d="m25 79 31-31 25 25 17-17 40 39"/><circle class="waiting-sun" cx="108" cy="43" r="9"/><path class="waiting-pencil" d="m116 16 8-8 12 12-8 8-20 12z"/></svg>
   <span v-if="status==='running'" class="waiting-scan"></span>
   <div v-else class="waiting-dots"><i></i><i></i><i></i></div>
  </div>
  <div class="waiting-copy"><h3>{{status==='queued'?'灵感已就位，等待画笔':'正在把想象绘成画面'}}</h3>
   <p v-if="status==='queued'">队列位置：<strong>{{queuePosition??'等待确认'}}</strong>。轮到你时自动开始。</p>
   <p v-else>本机 GPU 正在生成，完成后自动呈现。</p>
   <small>这里没有虚构进度，只有正在发生的创作。</small>
   <button v-if="status==='queued'" type="button" class="waiting-cancel" @click="$emit('cancel')">取消排队</button>
  </div>
 </div>
</template>
<style scoped>
.generation-waiting{width:100%;max-width:340px;text-align:center;color:var(--moss-muted);padding:8px;overflow-wrap:anywhere}.waiting-art{width:160px;height:108px;margin:0 auto 18px;position:relative}.waiting-drawing{width:100%;height:100%;fill:none;stroke:var(--moss-green);stroke-width:1.7;stroke-linejoin:round}.waiting-paper{fill:var(--moss-panel);stroke:var(--moss-line)}.paper-back{opacity:.55;transform:rotate(7deg);transform-origin:center}.waiting-landscape{stroke-dasharray:180;stroke-dashoffset:0}.waiting-pencil{fill:var(--moss-soft)}.waiting-sun{fill:var(--moss-soft)}.is-running .waiting-landscape{animation:draw-scene 4.5s ease-in-out infinite}.is-running .waiting-pencil{animation:paint-pencil 3s ease-in-out infinite}.waiting-scan{position:absolute;inset:24px 23px auto;height:1px;background:var(--moss-green);opacity:.4;animation:scan-scene 3.5s ease-in-out infinite}.waiting-dots{position:absolute;bottom:1px;left:0;right:0;display:flex;gap:6px;justify-content:center}.waiting-dots i{width:4px;height:4px;border-radius:50%;background:var(--moss-green);animation:queue-dot 1.8s ease-in-out infinite}.waiting-dots i:nth-child(2){animation-delay:.2s}.waiting-dots i:nth-child(3){animation-delay:.4s}.waiting-copy h3{font-size:15px;font-weight:600;color:var(--moss-text);margin:0 0 10px}.waiting-copy p{font-size:12px;line-height:1.8;margin:0}.waiting-copy p strong{color:var(--moss-green);font-weight:600}.waiting-copy small{font-size:10px;display:block;margin-top:9px;line-height:1.7}.waiting-cancel{display:inline-block;margin-top:16px;padding:7px 16px;border:1px solid var(--moss-line);border-radius:6px;background:var(--moss-panel);color:var(--moss-text);font-size:12px}.waiting-cancel:hover{border-color:var(--moss-green);color:var(--moss-green)}
@keyframes draw-scene{0%,100%{stroke-dashoffset:180;opacity:.35}40%,80%{stroke-dashoffset:0;opacity:1}}@keyframes paint-pencil{0%,100%{transform:translate(0,0)}50%{transform:translate(-18px,10px)}}@keyframes scan-scene{0%,100%{transform:translateY(0);opacity:.1}50%{transform:translateY(65px);opacity:.5}}@keyframes queue-dot{0%,100%{transform:translateY(0);opacity:.3}50%{transform:translateY(-3px);opacity:.9}}
@media(max-width:700px){.generation-waiting{padding:0;max-width:300px}.waiting-art{width:100px;height:65px;margin-bottom:10px}.waiting-copy h3{font-size:13px;margin-bottom:5px}.waiting-copy p{font-size:11px}.waiting-copy small{display:none}.waiting-cancel{margin-top:9px;padding:5px 13px}.waiting-scan{inset:14px 14px auto}@keyframes scan-scene{0%,100%{transform:translateY(0);opacity:.1}50%{transform:translateY(38px);opacity:.5}}}
@media(prefers-reduced-motion:reduce){.generation-waiting *{animation:none!important;transition:none!important}.waiting-landscape{stroke-dashoffset:0}.waiting-scan{display:none}.waiting-dots i{opacity:.7;transform:none}}
</style>
