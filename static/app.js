'use strict';
const $ = (selector) => document.querySelector(selector);
const esc = (text) => String(text ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state = {user:null, rules:null, task:null, labels:null, dirty:false, generation:0, timer:null, saving:Promise.resolve(), busy:false, imageReady:false, view:'work'};
let scale=1, panX=0, panY=0, drag=null, toastTimer=null, passwordUser=null;

function toast(message) { $('#toast').textContent=message; $('#toast').hidden=false; clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('#toast').hidden=true,4500); }
async function api(path, options={}) {
  const headers={'Content-Type':'application/json', ...(options.headers||{})};
  if(state.user) headers['X-CSRF-Token']=state.user.csrf;
  const response=await fetch(path,{...options, headers, credentials:'same-origin'});
  const data=await response.json().catch(()=>({detail:'服务器响应异常'}));
  if(!response.ok) {
    if(response.status===401 && path!=='/api/login') showLogin();
    const detail=data.detail;
    throw new Error(typeof detail==='string'?detail:detail?.message||'请求失败，请检查输入或稍后重试');
  }
  return data;
}
function showLogin() {
  clearTimeout(state.timer);
  $('#login-view').hidden=false;
  for(const name of ['work','history','admin']) $(`#${name}-view`).hidden=true;
  $('#navigation').hidden=true; $('#account').hidden=true;
}
function setView(name) {
  state.view=name; $('#login-view').hidden=true;
  for(const view of ['work','history','admin']) { $(`#${view}-view`).hidden=view!==name; $(`#${view}-nav`).classList.toggle('active',view===name); }
}
async function boot() {
  state.user=await api('/api/me'); state.rules=await api('/api/rules');
  $('#navigation').hidden=false; $('#account').hidden=false;
  $('#display-name').textContent=state.user.display_name;
  $('#admin-nav').hidden=state.user.role!=='admin';
  setView('work'); await nextTask();
}
async function refreshProgress() {
  const data=await api('/api/progress');
  $('#dataset-name').textContent=data.dataset?.name || '等待管理员启用图像集';
  $('#progress-count').textContent=`${data.completed} / ${data.total}`;
  $('#progress-bar').max=data.total || 1; $('#progress-bar').value=data.completed;
}
async function nextTask() {
  const data=await api('/api/tasks/next',{method:'POST'});
  await refreshProgress();
  $('#workspace').hidden=!data.task; $('#empty-work').hidden=!!data.task;
  if(!data.task) { state.task=null; state.dirty=false; $('#empty-title').textContent=data.reason; return; }
  loadTask(data.task);
}
function loadTask(task) {
  clearTimeout(state.timer); state.task=task; state.labels=structuredClone(task.labels); state.dirty=false; state.generation=0; state.imageReady=false;
  $('#workspace').hidden=false; $('#empty-work').hidden=true; $('#work-error').textContent='';
  $('#image-number').textContent=`NO. ${String(task.image_id).padStart(5,'0')}`;
  $('#dataset-name').textContent=task.dataset_name;
  if(task.submitted) {
    $('#progress-count').textContent='历史记录'; $('#progress-bar').max=1; $('#progress-bar').value=1;
  }
  $('#save-status').textContent=task.draft_reset?'规则已更新，请重新填写':task.has_draft?'已恢复草稿':task.submitted?'正在修改已提交记录':'等待标注';
  $('#image-loading').hidden=false; $('#image-loading').textContent='正在载入原图…';
  $('#specimen').style.visibility='hidden'; panX=panY=0;
  $('#specimen').src=task.image_url+`?revision=${task.revision}`;
  renderQuestions(); updateSubmit();
}
function slotControl(key, options, value, disabled=false, area=null, group=null) {
  const index=options.findIndex(x=>x.id===value);
  const title=area?`${state.rules.layers.find(l=>l.id===area).name}面积`:group?`Q3 ${state.rules.q3.find(o=>o.id===group).name}数量`:'Q2 SBNP 可追踪性';
  const scope=area?`data-area="${area}"`:group?`data-group="${group}"`:'';
  return `<div class="slot-control ${disabled?'disabled':''} ${index<0?'unset':''}" style="--slots:${options.length}"><div class="slot-track"><input type="range" min="0" max="${options.length-1}" step="1" value="${Math.max(0,index)}" data-key="${key}" ${scope} aria-label="${esc(title)}" aria-valuetext="${index<0?'待选择':esc(options[index].name+(options[index].detail?' '+options[index].detail:''))}" ${disabled?'disabled':''}><div class="slot-dots" aria-hidden="true">${options.map((_,i)=>`<i style="--stop:${i}" class="${i===index?'chosen':''}"></i>`).join('')}</div></div><div class="slot-labels">${options.map(o=>`<button type="button" data-slot="${o.id}" data-key="${key}" ${scope} class="${value===o.id?'selected':''}" ${disabled?'disabled':''} aria-label="${esc(title+'：'+o.name+(o.detail?' '+o.detail:''))}" aria-pressed="${value===o.id}"><strong>${esc(o.name)}</strong>${o.detail?`<small>${esc(o.detail)}</small>`:''}</button>`).join('')}</div></div>`;
}
function renderQuestions() {
  const labels=state.labels, rules=state.rules, keys=Object.keys(labels.q1), applicable=CCMForm.applicable(labels);
  const disabled=!applicable, interference=labels.q3 || [];
  const skipped=keys.length?'已跳过 · Q1 包含非 SBNP 层面或区域':'先完成 Q1';
  const details=(option)=>{
    if(!option.options) return '';
    const controls=option.multiple?option.options.map(sub=>{
      const selected=(labels.q3_details[option.id] || []).includes(sub.id);
      return `<button type="button" class="choice detail-choice ${selected?'selected':''}" data-detail="${sub.id}" data-group="${option.id}" aria-pressed="${selected}" ${disabled?'disabled':''}>${esc(sub.name)}</button>`;
    }).join(''):slotControl('q3',option.options,labels.q3_details[option.id],disabled,null,option.id);
    return `<div class="factor-controls" role="group" aria-label="${esc(option.name)}细分">${controls}</div>`;
  };
  $('#questions').innerHTML=`<section class="question q1-question">
    <div class="question-title"><span class="q-number">Q1</span><h2>图像中存在哪些层面或区域？</h2><small>多选</small></div>
    <p class="question-note">与 SBNP 重叠的区域只计入 SBNP；选择多个层面时填写面积。</p>
    <div class="layer-list">${rules.layers.map(layer=>{const selected=layer.id in labels.q1;return `<div class="layer-row ${selected?'selected':''}"><button type="button" class="choice ${selected?'selected':''}" data-layer="${layer.id}" aria-pressed="${selected}" title="${esc(layer.hint)}">${esc(layer.name)}</button>${slotControl('q1',rules.areas,labels.q1[layer.id],!selected || keys.length<2,layer.id)}</div>`;}).join('')}</div>
  </section>
  <section class="question grade-question q2-question ${disabled?'disabled':''}">
    <div class="question-title"><span class="q-number">Q2</span><h2>SBNP 可追踪性</h2><small>${disabled?'不适用':'单选'}</small></div>
    <div class="grade-box">${slotControl('q2',rules.q2,labels.q2,disabled)}<p class="grade-hint">${disabled?skipped:esc(rules.q2.find(x=>x.id===labels.q2)?.hint || '根据整体对比度、干扰范围及神经能否可靠追踪，选择相应档位。')}</p></div>
  </section>
  <section class="question q3-question ${disabled?'disabled':''}">
    <div class="question-title"><span class="q-number">Q3</span><h2>影响神经追踪的干扰因素</h2><small>${disabled?'不适用':'多选'}</small></div>
    ${disabled?`<p class="skip-note">${skipped}</p>`:''}
    <div class="q3-grid">${rules.q3.map(o=>`<div class="factor-card ${o.options?'has-options':''} ${interference.includes(o.id)?'selected':''}"><button type="button" class="choice ${interference.includes(o.id)?'selected':''}" data-interference="${o.id}" aria-pressed="${interference.includes(o.id)}" title="${esc(o.hint)}" ${disabled?'disabled':''}>${esc(o.name)}</button>${details(o)}</div>`).join('')}</div>
  </section>`;
}
function formProblem() {
  return CCMForm.problem(state.labels) || (!state.imageReady?'等待原图加载成功':'');
}
function updateSubmit() {
  const problem=formProblem(); $('#submit').disabled=state.busy || !!problem;
  $('#validation-hint').textContent=problem || (state.task?.submitted?'修改后将保留历史版本':CCMForm.applicable(state.labels)?'三步已完成，可以提交':'后续问题已跳过，可以提交');
  $('#submit').innerHTML=state.busy?'正在保存…':state.task?.submitted?'保存修改并继续 <span>→</span>':'保存并下一张 <span>→</span>';
}
function changed(focusSelector) {
  CCMForm.reconcile(state.labels);
  state.dirty=true; state.generation++; $('#save-status').textContent='草稿待保存…'; $('#work-error').textContent='';
  renderQuestions(); updateSubmit();
  if(focusSelector) $(focusSelector)?.focus({preventScroll:true});
  clearTimeout(state.timer); state.timer=setTimeout(()=>flushDraft().catch(showSaveError),700);
}
function showSaveError(error) { $('#save-status').textContent='未保存 · 请检查连接后重试'; $('#work-error').textContent=error.message; }
function flushDraft() {
  clearTimeout(state.timer);
  const operation=state.saving.catch(()=>{}).then(async()=>{
    if(!state.dirty || !state.task) return;
    const task=state.task, generation=state.generation, labels=structuredClone(state.labels);
    $('#save-status').textContent='正在保存草稿…';
    const result=await api(`/api/tasks/${task.id}/draft`,{method:'PUT',body:JSON.stringify({labels,revision:task.revision,manual_version:state.rules.version})});
    task.revision=result.revision;
    if(state.task===task && state.generation===generation) { state.dirty=false; $('#save-status').textContent='✓ 草稿已保存'; }
  });
  state.saving=operation;
  return operation;
}
$('#questions').addEventListener('click',event=>{
  if(state.busy) return;
  if(event.target.type==='range' && event.target.closest('.unset') && !event.target.disabled) {
    event.target.dispatchEvent(new Event('change',{bubbles:true})); return;
  }
  const button=event.target.closest('button'); if(!button || button.disabled) return;
  if(button.dataset.layer) {
    const key=button.dataset.layer;
    CCMForm.toggleLayer(state.labels,key);
    changed(`[data-layer="${key}"]`);
  } else if(button.dataset.slot) {
    const {key,slot,area,group}=button.dataset;
    if(group) CCMForm.toggleDetail(state.labels,group,slot);
    else if(area) state.labels.q1[area]=slot; else state.labels[key]=slot;
    changed(`[data-key="${key}"][data-slot="${slot}"]${area?`[data-area="${area}"]`:group?`[data-group="${group}"]`:''}`);
  } else if(button.dataset.interference) {
    const value=button.dataset.interference;
    CCMForm.toggleInterference(state.labels,value);
    changed(`[data-interference="${value}"]`);
  } else if(button.dataset.detail) {
    const {group,detail}=button.dataset;
    CCMForm.toggleDetail(state.labels,group,detail);
    changed(`[data-detail="${detail}"]`);
  }
});
$('#questions').addEventListener('change',event=>{
  const input=event.target;
  if(input.type!=='range' || input.disabled || state.busy) return;
  const {key,area,group}=input.dataset;
  const options=group?state.rules.q3.find(o=>o.id===group).options:area?state.rules.areas:state.rules[key];
  const value=options[Number(input.value)].id;
  if(group) CCMForm.toggleDetail(state.labels,group,value);
  else if(area) state.labels.q1[area]=value; else state.labels[key]=value;
  changed(`input[data-key="${key}"]${area?`[data-area="${area}"]`:group?`[data-group="${group}"]`:''}`);
});
$('#questions').addEventListener('keydown',event=>{
  // Enter/Space explicitly choose the current range position, including an unset first slot.
  if(event.target.type==='range' && ['Enter',' '].includes(event.key)) { event.preventDefault(); event.target.dispatchEvent(new Event('change',{bubbles:true})); }
});
$('#submit').addEventListener('click',async()=>{
  if(state.busy || formProblem()) return;
  state.busy=true; $('#questions').inert=true; $('#navigation').inert=true; $('#account').inert=true; updateSubmit();
  try {
    await flushDraft();
    const task=state.task;
    const result=await api(`/api/tasks/${task.id}/submit`,{method:'POST',body:JSON.stringify({labels:state.labels,revision:task.revision,manual_version:state.rules.version})});
    task.revision=result.revision; state.dirty=false; task.submitted=true;
    $('#save-status').textContent='✓ 正式标注已保存'; toast('标注已保存');
    await nextTask();
  } catch(error) { $('#work-error').textContent=error.message; }
  finally { state.busy=false; $('#questions').inert=false; $('#navigation').inert=false; $('#account').inert=false; updateSubmit(); }
});
function applyTransform() {
  $('#specimen').style.transform=`translate(calc(-50% + ${panX}px),calc(-50% + ${panY}px)) scale(${scale})`;
  $('#zoom-label').textContent=`${Math.round(scale*100)}%`;
}
function fitImage() {
  if(!state.task) return;
  const stage=$('#image-stage');
  scale=Math.min((stage.clientWidth-10)/state.task.width,(stage.clientHeight-10)/state.task.height); panX=panY=0; applyTransform();
}
function zoom(factor) { if(!state.imageReady) return; scale=Math.max(.1,Math.min(12,scale*factor)); applyTransform(); }
$('#specimen').addEventListener('load',()=>{state.imageReady=true; $('#specimen').style.visibility='visible'; $('#image-loading').hidden=true; fitImage(); updateSubmit();});
$('#specimen').addEventListener('error',()=>{state.imageReady=false; $('#image-loading').textContent='原图加载失败，请刷新任务或联系管理员。'; $('#image-loading').hidden=false; updateSubmit();});
$('#zoom-in').onclick=()=>zoom(1.25); $('#zoom-out').onclick=()=>zoom(.8); $('#zoom-fit').onclick=fitImage;
$('#zoom-original').onclick=()=>{scale=1;panX=panY=0;applyTransform();};
$('#fullscreen').onclick=async()=>{try { if(document.fullscreenElement) await document.exitFullscreen(); else await $('#image-stage').requestFullscreen(); } catch {toast('当前浏览器不支持全屏，请使用缩放控件。');}};
document.addEventListener('fullscreenchange',fitImage);
$('#image-stage').addEventListener('wheel',event=>{if(!state.imageReady) return; event.preventDefault();zoom(event.deltaY<0?1.1:1/1.1);},{passive:false});
$('#image-stage').addEventListener('pointerdown',event=>{drag={x:event.clientX-panX,y:event.clientY-panY};$('#image-stage').setPointerCapture(event.pointerId);});
$('#image-stage').addEventListener('pointermove',event=>{if(drag){panX=event.clientX-drag.x;panY=event.clientY-drag.y;applyTransform();}});
$('#image-stage').addEventListener('pointerup',()=>drag=null); $('#image-stage').addEventListener('pointercancel',()=>drag=null);
new ResizeObserver(()=>{if(state.imageReady && state.view==='work') fitImage();}).observe($('#image-stage'));
// Keep the sky below the actual header, including wrapped mobile navigation.
new ResizeObserver(()=>{
  document.documentElement.style.setProperty('--scene-top',`${$('.topbar').getBoundingClientRect().height}px`);
}).observe($('.topbar'));
window.addEventListener('beforeunload',event=>{if(state.dirty || state.busy){event.preventDefault();event.returnValue='';}});

$('#login-form').addEventListener('submit',async(event)=>{
  event.preventDefault(); const form=event.currentTarget, button=form.querySelector('button');button.disabled=true;$('#login-error').textContent='';
  try {await api('/api/login',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(form)))});form.reset();await boot();}
  catch(error){$('#login-error').textContent=error.message;}
  finally{button.disabled=false;}
});
$('#logout').onclick=async()=>{try {await flushDraft(); await api('/api/logout',{method:'POST'});state.user=null;state.task=null;state.labels=null;$('#specimen').removeAttribute('src');showLogin();} catch(error){toast(error.message);}};
async function returnToWork(){try{await flushDraft();setView('work');await nextTask();}catch(error){toast(error.message);}}
$('#work-nav').onclick=returnToWork;$('#back-to-work').onclick=returnToWork;$('#reload-tasks').onclick=returnToWork;
$('#history-nav').onclick=async()=>{
  try {
    await flushDraft(); const rows=await api('/api/history');setView('history');
    $('#history-list').innerHTML=rows.length?rows.map(row=>`<div class="record-row"><div><strong>图像 ${String(row.image_id).padStart(5,'0')}</strong><small>${esc(row.dataset_name)} · ${esc(row.updated_at)} UTC</small></div><button class="button" data-review="${row.id}">查看 / 修改 →</button></div>`).join(''):'<div class="empty">尚无已提交的标注记录。</div>';
  } catch(error){toast(error.message);}
};
$('#history-list').onclick=async(event)=>{
  const button=event.target.closest('[data-review]');if(!button)return;
  try {const task=await api(`/api/tasks/${button.dataset.review}`);setView('work');loadTask(task);window.scrollTo({top:0});}catch(error){toast(error.message);}
};
async function refreshAdmin() {
  const data=await api('/api/admin/overview');$('#image-root').textContent=data.image_root;
  $('#dataset-list').innerHTML=data.datasets.map(ds=>`<div class="record-row"><div><strong>${esc(ds.name)} ${ds.active?'<span class="badge">当前启用</span>':''}</strong><small>${ds.count} 张图像 · ${ds.completed} 份正式标注<br>${ds.mode==='independent'?'每人独立 · 随机排序':'共享任务池'}</small></div><div class="row-actions">${ds.active?'':`<button data-activate="${ds.id}">启用</button>`}<a href="/api/admin/export?dataset_id=${ds.id}&format=csv">CSV</a><a href="/api/admin/export?dataset_id=${ds.id}&format=jsonl">JSONL</a><a href="/api/admin/export?dataset_id=${ds.id}&format=audit">修改记录</a></div></div>`).join('') || '<p class="muted">尚未导入图像集。</p>';
  $('#user-list').innerHTML=data.users.map(user=>`<div class="record-row"><div><strong>${esc(user.display_name)} <span class="badge">${user.role==='admin'?'管理员':user.enabled?'标注员':'已停用'}</span></strong><small>${esc(user.username)} · 已提交 ${user.completed} 张</small></div>${user.role==='annotator'?`<div class="row-actions"><button data-password="${user.id}" data-name="${esc(user.display_name)}">重置密码</button><button data-toggle-user="${user.id}" data-enabled="${user.enabled?'0':'1'}">${user.enabled?'停用':'启用'}</button></div>`:''}</div>`).join('');
}
$('#admin-nav').onclick=async()=>{try{await flushDraft();await refreshAdmin();setView('admin');}catch(error){toast(error.message);}};
$('#dataset-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget,button=form.querySelector('button');button.disabled=true;$('#import-status').textContent='正在扫描文件并校验图像，请稍候…';
  try {const data=Object.fromEntries(new FormData(form));data.mode='independent';const result=await api('/api/admin/datasets',{method:'POST',body:JSON.stringify(data)});$('#import-status').textContent=`已导入 ${result.imported} 张，跳过 ${result.skipped_count} 个文件。请在下方启用图像集。`+(result.skipped.length?` 原因：${result.skipped.map(x=>x.file+'：'+x.reason).join('；')}`:'');form.reset();await refreshAdmin();}
  catch(error){$('#import-status').textContent=error.message;}finally{button.disabled=false;}
});
$('#dataset-list').onclick=async event=>{const button=event.target.closest('[data-activate]');if(!button)return;button.disabled=true;try{await api(`/api/admin/datasets/${button.dataset.activate}/activate`,{method:'POST'});await refreshAdmin();toast('图像集已启用，标注员可开始领取任务。');}catch(error){toast(error.message);button.disabled=false;}};
$('#user-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget,button=form.querySelector('button');button.disabled=true;
  try{await api('/api/admin/users',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(form)))});form.reset();$('#user-status').textContent='标注员已创建，可使用新账号登录。';await refreshAdmin();}catch(error){$('#user-status').textContent=error.message;}finally{button.disabled=false;}
});
$('#user-list').onclick=async event=>{
  const toggle=event.target.closest('[data-toggle-user]'),reset=event.target.closest('[data-password]');
  if(reset){passwordUser=reset.dataset.password;$('#password-target').textContent=reset.dataset.name;$('#password-error').textContent='';$('#password-form').reset();$('#password-dialog').showModal();}
  if(toggle){toggle.disabled=true;try{await api(`/api/admin/users/${toggle.dataset.toggleUser}`,{method:'PATCH',body:JSON.stringify({enabled:toggle.dataset.enabled==='1'})});await refreshAdmin();}catch(error){toast(error.message);toggle.disabled=false;}}
};
$('#cancel-password').onclick=()=>$('#password-dialog').close();
$('#password-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget,button=form.querySelector('button[type="submit"]') || form.querySelector('.primary');button.disabled=true;
  try{await api(`/api/admin/users/${passwordUser}`,{method:'PATCH',body:JSON.stringify(Object.fromEntries(new FormData(form)))});$('#password-dialog').close();form.reset();toast('密码已重置。');}catch(error){$('#password-error').textContent=error.message;}finally{button.disabled=false;}
});
boot().catch(error=>{showLogin();if(!error.message.includes('登录已过期'))$('#login-error').textContent=error.message;});
