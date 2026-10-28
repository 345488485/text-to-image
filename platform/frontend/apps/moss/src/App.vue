<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue';
import { VbenAdminLayout } from '@vben-core/layout-ui';
import { VbenButton } from '@vben-core/shadcn-ui';
import { NConfigProvider, NInput, NInputNumber, NSelect, NButton, NModal, NTag, NAlert, NPopconfirm, NPagination, darkTheme, zhCN, dateZhCN } from 'naive-ui';
import { ApiClient, ApiError, type User, type Session, type Job, type JobList, type EngineStatus } from './api';
import GenerationWaiting from './GenerationWaiting.vue';
import { aspectOptions, defaultAspect, inferAspect, aspectDimensions, type AspectRatio } from './aspect';
import { canEnterWorkspace, changeOwnPassword } from './auth';
import { startTheme, type ThemeMode, type EffectiveTheme } from './theme';

const user = ref<User|null>(null), checking = ref(true), page = ref('studio');
const busy = ref(false), error = ref(''), notice = ref('');
const username = ref(''), password = ref('');
const initialSetup = ref(false);
const ownPassword = reactive({current:'',next:'',confirm:''});
const selectedTheme = ref<ThemeMode>('auto'), effectiveTheme = ref<EffectiveTheme>('light');
const mobile = ref(window.innerWidth<900), collapsed = ref(false);
const api = new ApiClient(fetch, () => {user.value=null;jobs.value=[];selected.value=null;status.value=null;});
const jobs = ref<Job[]>([]), total = ref(0), currentPage = ref(1), filter = ref<string|null>(null);
const selected = ref<Job|null>(null), detailOpen=ref(false), status=ref<EngineStatus|null>(null);
const users = ref<User[]>([]), userForm=reactive({username:'',password:''}), resetUser=ref<User|null>(null), resetPassword=ref('');
const form=reactive({prompt:'',negative_prompt:'',steps:8,seed:null as number|null,aspect_ratio:defaultAspect(window.innerWidth)});
const drafting=ref(false);
const formDimensions=computed(()=>aspectDimensions(form.aspect_ratio));
const previewDimensions=computed(()=>selected.value ? {width:selected.value.width,height:selected.value.height}:formDimensions.value);
const previewRatio=computed(()=>`${previewDimensions.value.width}/${previewDimensions.value.height}`);
function setAspect(value:AspectRatio) {drafting.value=true;form.aspect_ratio=value;if(selected.value&&!['queued','running'].includes(selected.value.status))selected.value=null;}
const activeJob=computed(()=>jobs.value.find(j=>j.status==='queued'||j.status==='running'));
const active = ref(false);
const labels:Record<string,string>={queued:'排队中',running:'生成中',succeeded:'已完成',failed:'失败',cancelled:'已取消'};
const statusOptions=[{label:'全部状态',value:''},...Object.entries(labels).map(([value,label])=>({value,label}))];
const themeOptions=[{label:'跟随时间',value:'auto'},{label:'亮色',value:'light'},{label:'暗色',value:'dark'}];
const titles:Record<string,string>={studio:'创作工作台',gallery:'个人图库',users:'账号管理'};
const overrides={common:{primaryColor:'#147D64',primaryColorHover:'#0E6C55',primaryColorPressed:'#0B5E49',borderRadius:'7px',fontFamily:'"Segoe UI", "Microsoft YaHei", sans-serif'},Button:{fontWeight:'600'}};
let disposeTheme:ReturnType<typeof startTheme>, timer:ReturnType<typeof setInterval>, refreshing=false;
function setTheme(mode: ThemeMode) {disposeTheme?.setMode(mode);}
function resize() {mobile.value=window.innerWidth<900;}
function clearMessages() {error.value='';notice.value='';}
function message(e:unknown) {error.value=e instanceof Error ? e.message : '操作失败，请重试。';}
function date(value:string|null) {return value ? new Date(value.endsWith('Z')||/[+-]\d\d:\d\d$/.test(value)?value:`${value}Z`).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}) : '—';}
function image(job:Job|null) {return job?.status==='succeeded' ? `/api/jobs/${encodeURIComponent(job.id)}/image` : '';}
function statusType(value:string):'success'|'error'|'warning'|'info'|'default' {return ({succeeded:'success',failed:'error',queued:'warning',running:'info'} as const)[value as 'succeeded'] ?? 'default';}
async function run(action:()=>Promise<void>) {clearMessages();busy.value=true;try {await action();}catch(e){message(e);}finally{busy.value=false;}}
async function login() {
 await run(async()=>{const session=await api.request<Session>('/auth/login',{method:'POST',body:{username:username.value,password:password.value}});user.value=session.user;password.value='';ownPassword.current='';ownPassword.next='';ownPassword.confirm='';await refresh();});
}
async function logout() {await run(async()=>{await api.request('/auth/logout',{method:'POST'});api.csrfToken='';user.value=null;jobs.value=[];selected.value=null;status.value=null;page.value='studio';ownPassword.current='';ownPassword.next='';ownPassword.confirm='';await loadBootstrap();});}
async function refresh() {
 if(!canEnterWorkspace(user.value)||refreshing)return;refreshing=true;
 try {
  const [info, list, allActive]=await Promise.all([api.request<EngineStatus>('/status'),api.request<JobList>(`/jobs?page=${currentPage.value}&page_size=12${filter.value ? `&status=${filter.value}`:''}`),api.request<JobList>('/jobs?page=1&page_size=1&status=queued'),]);
  if(!user.value)return;status.value=info;jobs.value=list.items;total.value=list.total;
  // Running jobs may be outside the filtered/page results; backend enforces the same active limit.
  active.value=!!activeJob.value||allActive.total>0;
  if(!active.value) {const running=await api.request<JobList>('/jobs?page=1&page_size=1&status=running');active.value=running.total>0;}
  if(selected.value)selected.value=await api.request<Job>(`/jobs/${encodeURIComponent(selected.value.id)}`);
  else if(page.value==='studio'&&!drafting.value&&list.items.length)selected.value=list.items[0]??null;
 } catch(e){message(e);}finally{refreshing=false;}
}
async function navigate(value:string) {if(!canEnterWorkspace(user.value))return;page.value=value;clearMessages();if(value==='users')await loadUsers();else await refresh();}
async function generate() {
 await run(async()=>{if(!form.prompt.trim())throw new Error('请先描述你想生成的画面。');const job=await api.request<Job>('/jobs',{method:'POST',body:{...form,seed:form.seed??Math.floor(Math.random()*4294967296)}});drafting.value=false;selected.value=job;currentPage.value=1;filter.value=null;active.value=true;await refresh();notice.value='任务已加入队列。可留在此页等待，或稍后到图库查看。';});
}
async function cancel(job:Job) {await run(async()=>{await api.request(`/jobs/${encodeURIComponent(job.id)}/cancel`,{method:'POST'});await refresh();notice.value='已取消排队任务。';});}
async function remove(job:Job) {await run(async()=>{await api.request(`/jobs/${encodeURIComponent(job.id)}`,{method:'DELETE'});if(selected.value?.id===job.id)selected.value=null;detailOpen.value=false;if(jobs.value.length===1&&currentPage.value>1)currentPage.value--;await refresh();notice.value='记录及平台图片副本已删除。';});}
function reuse(job:Job) {drafting.value=true;Object.assign(form,{prompt:job.prompt,negative_prompt:job.negative_prompt,steps:job.steps,seed:job.seed,aspect_ratio:inferAspect(job)});selected.value=job;detailOpen.value=false;page.value='studio';notice.value='参数已载入，可修改后再次生成。';}
function view(job:Job) {drafting.value=false;selected.value=job;detailOpen.value=true;}
async function setFilter(value:string|null) {filter.value=value;currentPage.value=1;await refresh();}
async function changePage(value:number) {currentPage.value=value;await refresh();}
async function loadUsers() {if(!canEnterWorkspace(user.value))return;try{users.value=(await api.request<{items:User[]}>('/admin/users')).items;}catch(e){message(e);}}
async function createUser() {await run(async()=>{await api.request('/admin/users',{method:'POST',body:{...userForm}});userForm.username='';userForm.password='';await loadUsers();notice.value='账号已创建，请安全地告知本人初始密码。';});}
async function toggleUser(target:User) {await run(async()=>{await api.request(`/admin/users/${target.id}`,{method:'PATCH',body:{is_active:!target.is_active}});await loadUsers();notice.value=target.is_active?'账号已禁用，会话已撤销。':'账号已启用。';});}
async function savePassword() {await run(async()=>{if(!resetUser.value)return;await api.request(`/admin/users/${resetUser.value.id}`,{method:'PATCH',body:{password:resetPassword.value}});resetUser.value=null;resetPassword.value='';notice.value='密码已重置，该账号现有会话已撤销。';});}
async function loadBootstrap() {
 try {initialSetup.value=(await api.request<{initial_setup_required:boolean}>('/auth/bootstrap')).initial_setup_required===true;} catch {initialSetup.value=false;}
}
async function changePassword() {
 await run(async()=>{
  const session=await changeOwnPassword(api,ownPassword.current,ownPassword.next,ownPassword.confirm);
  user.value=session.user;initialSetup.value=false;ownPassword.current='';ownPassword.next='';ownPassword.confirm='';page.value='studio';
  await refresh();notice.value='密码已更新，欢迎进入工作室。';
 });
}
onMounted(async()=>{
 disposeTheme=startTheme({now:()=>new Date(),storage:localStorage,apply:(theme,mode)=>{effectiveTheme.value=theme;selectedTheme.value=mode;document.documentElement.classList.toggle('dark',theme==='dark');document.documentElement.style.colorScheme=theme;},on:(e,f)=>window.addEventListener(e,f),off:(e,f)=>window.removeEventListener(e,f),schedule:(f,ms)=>setTimeout(f,ms),clear:t=>clearTimeout(t as ReturnType<typeof setTimeout>)});
 window.addEventListener('resize',resize);
 await loadBootstrap();
 try {user.value=(await api.request<Session>('/auth/session')).user;await refresh();} catch(e) {if(!(e instanceof ApiError&&e.status===401))message(e);} finally {checking.value=false;}
 timer=setInterval(()=>{if(document.visibilityState==='visible'&&canEnterWorkspace(user.value)&&page.value!=='users')void refresh();},4000);
});
onUnmounted(()=>{disposeTheme?.stop();clearInterval(timer);window.removeEventListener('resize',resize);});
</script>

<template>
 <NConfigProvider :theme="effectiveTheme==='dark'?darkTheme:null" :theme-overrides="overrides" :locale="zhCN" :date-locale="dateZhCN">
  <div v-if="checking" class="loading-screen" role="status">正在连接 MOSS Studio…</div>
  <div v-else-if="!user" class="login-page">
   <div class="login-art">
    <a class="brand login-brand" href="#"><span class="brand-mark">M</span><span>MOSS <b>Studio</b></span></a>
    <div class="login-statement"><div class="art-grid" aria-hidden="true"><div class="art-frame"><svg viewBox="0 0 200 200"><path d="M42 145V55L100 117L158 55V145"/></svg></div><span>{{formDimensions.width}} × {{formDimensions.height}}</span></div><h1>给想象，<br>一个画面。</h1><p>从一句描述开始，在本地完成创作。<br>你的图像与灵感，只属于你。</p></div>
    <small>MOSS-Image · 本地创作空间</small>
   </div>
   <div class="login-panel">
    <div class="login-theme"><NSelect aria-label="主题模式" :value="selectedTheme" :options="themeOptions" @update:value="setTheme" /></div>
    <form class="login-form" @submit.prevent="login">
     <span class="small-brand">MOSS Studio</span><h2>欢迎回来</h2><p class="muted">登录你的私人创作空间</p>
     <NAlert v-if="error" type="error" class="feedback" role="alert">{{error}}</NAlert>
     <NAlert v-if="initialSetup" type="warning" class="feedback" role="status">首次使用：默认用户名 <strong>admin</strong>，初始密码 <strong>123456</strong>。登录后必须设置新密码，完成后才能进入工作室。</NAlert>
     <label for="login-username">用户名</label><NInput id="login-username" v-model:value="username" autocomplete="username" placeholder="请输入用户名" size="large" required />
     <label for="login-password">密码</label><NInput id="login-password" v-model:value="password" type="password" autocomplete="current-password" placeholder="请输入密码" size="large" show-password-on="click" required />
     <VbenButton type="submit" :loading="busy" class="login-submit">登录工作室</VbenButton>
     <p class="login-help">暂未开放注册。需要账号或忘记密码？请联系管理员。</p>
    </form><small class="login-footer">在本地生成，在私有空间保存。</small>
   </div>
  </div>
  <section v-else-if="user.must_change_password" class="password-change-page" aria-labelledby="change-password-heading">
   <header class="password-change-header"><a class="brand" href="#"><span class="brand-mark">M</span><span>MOSS <b>Studio</b></span></a><div class="password-change-tools"><NSelect aria-label="主题模式" :value="selectedTheme" :options="themeOptions" @update:value="setTheme"/><NButton :disabled="busy" @click="logout">退出登录</NButton></div></header>
   <form class="password-change-form panel" @submit.prevent="changePassword">
    <span class="small-brand">保护你的工作室</span><h1 id="change-password-heading">首次登录，请修改密码</h1><p class="muted">{{user.username}}，当前密码为初始密码。设置独立的新密码后，才能访问创作、图库和账号管理。</p>
    <NAlert v-if="error" type="error" role="alert" class="feedback">{{error}}</NAlert>
    <label for="current-password">当前密码</label><NInput id="current-password" v-model:value="ownPassword.current" type="password" autocomplete="current-password" show-password-on="click" placeholder="请输入当前密码（初始密码为 123456）" required/>
    <label for="own-new-password">新密码</label><NInput id="own-new-password" v-model:value="ownPassword.next" type="password" autocomplete="new-password" show-password-on="click" placeholder="至少 10 个字符，不能与当前密码相同" required/>
    <label for="confirm-new-password">确认新密码</label><NInput id="confirm-new-password" v-model:value="ownPassword.confirm" type="password" autocomplete="new-password" show-password-on="click" placeholder="再次输入新密码" :status="ownPassword.confirm&&ownPassword.confirm!==ownPassword.next?'error':undefined" required/>
    <p v-if="ownPassword.confirm&&ownPassword.confirm!==ownPassword.next" class="password-mismatch" role="alert">两次输入的新密码不一致。</p>
    <VbenButton type="submit" :loading="busy" class="login-submit" :disabled="!ownPassword.current||!ownPassword.next||!ownPassword.confirm">更新密码并进入工作室</VbenButton><p class="parameter-hint">新密码只用于当前账号，不会保存到浏览器本地存储。更新后，初始密码将立即失效。</p>
   </form>
  </section>
  <VbenAdminLayout v-else v-model:sidebar-collapse="collapsed" :is-mobile="mobile" :sidebar-width="212" :side-collapse-width="64" :sidebar-expand-on-hover="true" :sidebar-logo-visible="true" :header-height="72" :tabbar-enable="false" :sidebar-collapsed-button="false" :sidebar-fixed-button="false" :sidebar-draggable="false" :sidebar-theme="effectiveTheme" :header-theme="effectiveTheme" @toggle-sidebar="collapsed=!collapsed">
   <template #logo><a class="brand" :class="{'is-collapsed':collapsed&&!mobile}" href="#studio" @click.prevent="navigate('studio')"><span class="brand-mark">M</span><span v-if="!collapsed||mobile">MOSS <b>Studio</b></span></a></template>
   <template #menu><nav class="navigation" :class="{'is-collapsed':collapsed&&!mobile}" aria-label="主导航">
    <div v-if="!collapsed||mobile" class="nav-caption">创作空间</div>
    <button :class="{active:page==='studio'}" title="创作工作台" @click="navigate('studio')"><svg viewBox="0 0 24 24"><path d="m14 4 6 6M4 20l4-1 12-12a2 2 0 0 0-3-3L5 16z"/></svg><span v-if="!collapsed||mobile">创作工作台</span></button>
    <button :class="{active:page==='gallery'}" title="个人图库" @click="navigate('gallery')"><svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="3"/><path d="m3 16 5-5 5 5 3-3 5 5"/><circle cx="16" cy="8" r="1"/></svg><span v-if="!collapsed||mobile">个人图库</span></button>
    <template v-if="user.role==='admin'"><div v-if="!collapsed||mobile" class="nav-caption admin-caption">管理</div><button :class="{active:page==='users'}" title="账号管理" @click="navigate('users')"><svg viewBox="0 0 24 24"><circle cx="9" cy="8" r="4"/><path d="M2 21v-3a7 7 0 0 1 14 0v3M16 4a4 4 0 0 1 0 8m3 9v-3a7 7 0 0 0-2-5"/></svg><span v-if="!collapsed||mobile">账号管理</span></button></template>
    <div v-if="!collapsed||mobile" class="sidebar-foot"><span class="device-icon">◈</span><strong>本地推理</strong><p>MOSS-Image<br>{{formDimensions.width}} × {{formDimensions.height}} · 单图生成</p><span class="privacy-note">私有记录 · 共享 GPU 队列</span></div>
   </nav></template>
   <template #header><div class="topbar"><div class="breadcrumb">创作空间 <span>/</span> <strong>{{titles[page]}}</strong></div><div class="topbar-right"><span class="engine-pill" :class="{online:status?.engine_online}"><i></i>{{status?.engine_online?'引擎在线':'引擎离线'}}</span><NSelect aria-label="主题模式" class="theme-control" :value="selectedTheme" :options="themeOptions" @update:value="setTheme"/><div class="user-chip"><span class="avatar">{{user.username.slice(0,1).toUpperCase()}}</span><span>{{user.username}}<small>{{user.role==='admin'?'管理员':'创作者'}}</small></span></div><NButton quaternary size="small" @click="logout">退出</NButton></div></div></template>
   <template #content><main class="workspace" :class="{'studio-workspace':page==='studio'}">
    <header class="page-heading"><div><h1>{{titles[page]}}</h1><p>{{page==='studio'?'将脑海中的画面，变成看得见的作品。':page==='gallery'?'每一次灵感，都在这里留下痕迹。':'为每位创作者保留独立的空间。'}}</p></div><span v-if="page!=='users'" class="queue-summary">共享队列 <strong>{{status?.queue_length??'—'}}</strong> 个等待 <span>·</span> {{status?.running?'GPU 正在工作':'GPU 空闲'}}</span></header>
    <NAlert v-if="error" type="error" closable class="feedback" role="alert" @close="error=''">{{error}}</NAlert><NAlert v-if="notice" type="success" closable class="feedback" role="status" @close="notice=''">{{notice}}</NAlert>
    <NAlert v-if="status&&!status.engine_online&&page==='studio'" type="warning" class="feedback">推理服务尚未就绪。请启动本机 MOSS 引擎后刷新状态；离线时不会开始生成。</NAlert>
    <NAlert v-if="status?.worker_online===false&&page==='studio'" type="warning" class="feedback">任务调度服务已暂停。请启动后台 worker 后再生成；已有记录仍可查看。</NAlert>
    <div v-if="page==='studio'" class="studio-grid">
     <form class="parameters panel" @submit.prevent="generate"><div class="panel-title"><h2>创作参数</h2><span class="muted">固定模型</span></div><div class="model-block"><span class="model-symbol">M</span><div><strong>MOSS-Image</strong><small>本地文生图 · {{formDimensions.width}} × {{formDimensions.height}}</small></div><span class="model-check">✓</span></div>
      <label for="prompt">画面描述 <span class="required">*</span></label><NInput id="prompt" v-model:value="form.prompt" type="textarea" :autosize="{minRows:3,maxRows:6}" maxlength="4000" show-count placeholder="描述主体、场景、光线和风格，例如：清晨窗边的一壶红茶，陶瓷质感，自然柔光，静物摄影。" required />
      <label for="aspect-ratio">画幅尺寸</label><NSelect id="aspect-ratio" aria-label="画幅尺寸" :value="form.aspect_ratio" :options="aspectOptions" @update:value="setAspect"/>
      <label for="steps">采样步数</label><NSelect id="steps" aria-label="采样步数" v-model:value="form.steps" :options="[{label:'8 步 · 快速探索',value:8},{label:'16 步 · 均衡创作',value:16},{label:'20 步 · 细节优先',value:20}]"/>
      <details class="advanced-controls"><summary>高级设置 · 排除内容与随机种子</summary>
      <div class="field-label"><label for="negative">不希望出现的内容</label><span>可选</span></div><NInput id="negative" v-model:value="form.negative_prompt" type="textarea" :autosize="{minRows:2,maxRows:4}" maxlength="2000" placeholder="例如：模糊、文字、水印"/>
      <div class="field-label"><label for="seed">随机种子</label><NButton text size="tiny" @click="form.seed=null">使用随机</NButton></div><NInputNumber id="seed" v-model:value="form.seed" :min="0" :max="4294967295" :precision="0" placeholder="留空随机生成" :show-button="false"/>
      </details>
      <p class="parameter-hint">每次生成 1 张 · 每人最多 1 个活动任务<br>实际耗时取决于设备状态，不显示虚构进度。</p>
      <VbenButton type="submit" class="generate-button" :loading="busy" :disabled="active||!status?.engine_online||status?.worker_online===false||!form.prompt.trim()"><span class="sparkle">✦</span>{{active?'等待当前任务完成':'开始生成'}}</VbenButton>
     </form>
     <section class="canvas panel" :style="{'--preview-scale':previewDimensions.width/previewDimensions.height}"><div class="panel-title"><h2>作品预览</h2><NTag v-if="selected" :type="statusType(selected.status)" size="small" :bordered="false">{{labels[selected.status]}}</NTag><span v-else class="muted">等待灵感</span></div>
      <div class="canvas-stage" :style="{aspectRatio:previewRatio}" :class="{hasImage:image(selected),'is-portrait':previewDimensions.height>previewDimensions.width}"><img v-if="image(selected)" :src="image(selected)" :alt="selected?.prompt" @click="detailOpen=true"><GenerationWaiting v-else-if="selected&&(selected.status==='queued'||selected.status==='running')" :status="selected.status" :queue-position="selected.queue_position" @cancel="cancel(selected!)"/><div v-else class="canvas-empty" aria-live="polite"><div class="canvas-placeholder" :class="{processing:selected?.status==='running'}"><svg viewBox="0 0 48 48"><rect x="6" y="6" width="36" height="36" rx="5"/><path d="m7 32 11-11 9 9 5-5 10 10"/><circle cx="31" cy="17" r="3"/></svg></div><h3>{{selected?labels[selected.status]:'你的下一幅作品，从这里开始'}}</h3><p v-if="!selected">在左侧描述画面，点击「开始生成」。<br>生成的作品仅对你可见。</p><p v-else-if="selected.status==='queued'">队列位置：{{selected.queue_position??'等待确认'}}<br>轮到你时会自动开始，无需重复提交。</p><p v-else-if="selected.status==='running'">正在本机 GPU 上生成，请耐心等待。<br>完成后预览将自动更新。</p><p v-else-if="selected.status==='failed'">{{selected.error||'本次任务未完成，请检查引擎状态后重试。'}}</p><p v-else>排队任务已取消。可调整参数重新开始。</p><NButton v-if="selected?.status==='queued'" :disabled="busy" @click="cancel(selected)">取消排队</NButton></div></div>
      <div class="canvas-footer"><div><strong>{{previewDimensions.width}} × {{previewDimensions.height}}</strong><span>{{selected?`${selected.steps} 步 · 种子 ${selected.seed}`:'所选画幅 · PNG 格式'}}</span></div><div class="canvas-actions"><NButton v-if="selected" secondary @click="reuse(selected)">复用参数</NButton><a v-if="image(selected)" class="download-button" :href="`${image(selected)}?download=true`" download>下载 PNG</a></div></div>
     </section>
    </div>
    <section v-else-if="page==='gallery'" class="gallery-section"><div class="gallery-toolbar"><strong>{{total}} 条私有记录</strong><div class="toolbar-actions"><NSelect aria-label="筛选生成状态" :value="filter??''" :options="statusOptions" @update:value="setFilter"/><NButton @click="refresh">刷新</NButton></div></div>
     <div v-if="!jobs.length" class="empty-gallery panel"><div class="empty-icon">▧</div><h2>{{filter?'没有这个状态的记录':'还没有作品'}}</h2><p>{{filter?'选择其他状态，或返回查看全部记录。':'先去创作工作台，生成你的第一幅作品。'}}</p><NButton type="primary" @click="filter?setFilter(null):navigate('studio')">{{filter?'查看全部':'开始创作'}}</NButton></div>
     <div v-else class="gallery-grid"><article v-for="job in jobs" :key="job.id" class="gallery-card panel"><button class="gallery-image" :aria-label="`查看作品 ${job.prompt}`" @click="view(job)"><img v-if="image(job)" :src="image(job)" :alt="job.prompt" loading="lazy"><div v-else class="gallery-placeholder"><span>▧</span><NTag :type="statusType(job.status)" :bordered="false">{{labels[job.status]}}</NTag></div><span v-if="image(job)" class="image-dimension">{{job.width}} × {{job.height}}</span></button><div class="gallery-card-info"><p :title="job.prompt">{{job.prompt}}</p><div><span>{{date(job.created_at)}}</span><div class="gallery-card-actions"><NButton text size="small" @click="reuse(job)">复用参数</NButton><NPopconfirm v-if="!['queued','running'].includes(job.status)" positive-text="确认删除" negative-text="取消" @positive-click="remove(job)"><template #trigger><NButton text size="small" type="error" :disabled="busy">删除</NButton></template>删除这张作品和生成记录？此操作无法撤销。</NPopconfirm><NButton v-else text size="small" type="error" disabled title="请先取消排队或等待生成完成">删除</NButton></div></div></div></article></div><NPagination v-if="total>12" class="pagination" :page="currentPage" :page-size="12" :item-count="total" @update:page="changePage"/></section>
    <div v-else-if="page==='users'" class="admin-grid"><section class="panel user-table-panel"><div class="panel-title"><h2>工作室成员</h2><NButton size="small" @click="loadUsers">刷新</NButton></div><div class="table-scroll"><table><thead><tr><th>用户名</th><th>角色</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="member in users" :key="member.id"><td><strong>{{member.username}}</strong><small v-if="member.id===user.id">当前账号</small></td><td>{{member.role==='admin'?'管理员':'创作者'}}</td><td><NTag size="small" :type="member.is_active?'success':'default'" :bordered="false">{{member.is_active?'已启用':'已禁用'}}</NTag></td><td><div class="table-actions"><NButton text size="small" @click="resetUser=member;resetPassword=''">重置密码</NButton><NPopconfirm v-if="member.id!==user.id" @positive-click="toggleUser(member)"><template #trigger><NButton text size="small" :type="member.is_active?'error':'primary'">{{member.is_active?'禁用':'启用'}}</NButton></template>{{member.is_active?'禁用会立即撤销该账号所有会话。确认继续？':'确认启用此账号？'}}</NPopconfirm></div></td></tr></tbody></table></div><p class="admin-note">管理员管理账号和共享队列，不浏览其他成员的私有作品。</p></section><form class="panel create-user" @submit.prevent="createUser"><h2>添加创作者</h2><p class="muted">创建后，请通过安全渠道发送初始密码。</p><label for="new-username">用户名</label><NInput id="new-username" v-model:value="userForm.username" autocomplete="off" maxlength="40" placeholder="新成员用户名" required/><label for="new-password">初始密码</label><NInput id="new-password" v-model:value="userForm.password" type="password" autocomplete="new-password" show-password-on="click" placeholder="至少 10 个字符" required/><VbenButton type="submit" :loading="busy" class="create-user-button" :disabled="!userForm.username||userForm.password.length<10">创建账号</VbenButton><p class="parameter-hint">禁用账号或重置密码后，已有会话将失效。</p></form></div>
    <footer class="workspace-footer"><span>MOSS Studio</span><span>本地推理，私有创作。图像内容不会因主题切换而反色。</span></footer>
   </main></template>
  </VbenAdminLayout>
  <NModal v-if="canEnterWorkspace(user)" v-model:show="detailOpen" preset="card" title="作品详情" class="detail-modal" :style="{width:'min(900px, 94vw)'}"><div v-if="selected" class="detail-layout"><div class="detail-image"><img v-if="image(selected)" :src="image(selected)" :alt="selected.prompt"><NTag v-else :type="statusType(selected.status)">{{labels[selected.status]}}</NTag></div><div class="detail-info"><NTag :type="statusType(selected.status)" :bordered="false">{{labels[selected.status]}}</NTag><h3>画面描述</h3><p class="prompt-text">{{selected.prompt}}</p><h3>排除内容</h3><p class="prompt-text muted">{{selected.negative_prompt||'未设置'}}</p><dl><dt>参数</dt><dd>{{selected.steps}} 步 · {{selected.width}} × {{selected.height}}</dd><dt>种子</dt><dd>{{selected.seed}}</dd><dt>创建时间</dt><dd>{{date(selected.created_at)}}</dd></dl><NAlert v-if="selected.error" type="error">{{selected.error}}</NAlert><div class="detail-actions"><NButton type="primary" @click="reuse(selected)">复用参数</NButton><a v-if="image(selected)" class="download-button" :href="`${image(selected)}?download=true`" download>下载 PNG</a><NButton v-if="selected.status==='queued'" @click="cancel(selected)">取消排队</NButton><NPopconfirm v-if="!['queued','running'].includes(selected.status)" @positive-click="remove(selected)"><template #trigger><NButton type="error" secondary>删除记录</NButton></template>删除这条记录和平台图片副本？此操作无法撤销。</NPopconfirm></div></div></div></NModal>
  <NModal v-if="canEnterWorkspace(user)" :show="!!resetUser" preset="card" title="重置密码" :style="{width:'420px',maxWidth:'94vw'}" @update:show="v=>{if(!v){resetUser=null;resetPassword=''}}"><form @submit.prevent="savePassword"><p class="muted">为 {{resetUser?.username}} 设置新密码，已有会话会立即失效。</p><label for="reset-password">新密码</label><NInput id="reset-password" v-model:value="resetPassword" type="password" autocomplete="new-password" show-password-on="click" placeholder="至少 10 个字符" required/><NButton class="create-user-button" attr-type="submit" type="primary" :loading="busy" :disabled="resetPassword.length<10">确认重置</NButton><NAlert v-if="error" class="feedback" type="error">{{error}}</NAlert></form></NModal>
 </NConfigProvider>
</template>
