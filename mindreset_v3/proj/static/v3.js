/* MindReset v3 · tema, términos, calendario, chequeo profundo, comunidad y extras de psicología */
ICON.cal=svgi('<rect x="3" y="4.5" width="18" height="16" rx="3"/><path d="M3 10h18M8 2.5v4M16 2.5v4"/>');
ICON.group=svgi('<circle cx="12" cy="8" r="3.2"/><path d="M5.5 20a6.5 6.5 0 0 1 13 0"/><circle cx="4.5" cy="10" r="2.2"/><circle cx="19.5" cy="10" r="2.2"/>');

/* ---------- tema claro / oscuro ---------- */
const isDark=()=>{const t=document.documentElement.dataset.theme;return t==='dark'||(t==='auto'&&matchMedia('(prefers-color-scheme: dark)').matches)};
function paintTheme(){const b=$('#themebtn');if(b){b.textContent=isDark()?'☀️':'🌙';b.title=isDark()?'Cambiar a modo claro':'Cambiar a modo oscuro'}
  const m=document.querySelector('meta[name=theme-color]');if(m)m.content=isDark()?'#0C0B10':'#6A3EC8'}
ACT.theme=()=>{const t=isDark()?'light':'dark';document.documentElement.dataset.theme=t;try{localStorage.setItem('mr_theme',t)}catch{}paintTheme()};
matchMedia('(prefers-color-scheme: dark)').addEventListener?.('change',paintTheme);paintTheme();

/* ---------- utilidades ---------- */
const pad=n=>String(n).padStart(2,'0');
const ymd=d=>`${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
const pYmd=s=>{const[y,m,d]=s.split('-').map(Number);return new Date(y,m-1,d)};
const addDays=(d,n)=>{const x=new Date(d);x.setDate(x.getDate()+n);return x};
const mondayOf=d=>addDays(d,-((d.getDay()+6)%7));
const DN=['Lun','Mar','Mié','Jue','Vie','Sáb','Dom'], DL=['L','M','X','J','V','S','D'];
const KIND={class:'Clase',study:'Estudio',work:'Trabajo',transport:'Traslado',meal:'Comida',rest:'Descanso',sleep:'Sueño',deadline:'Entrega',exam:'Examen',other:'Otra'};
const hh=s=>s.slice(11,16), dkey=s=>s.slice(0,10);
const t24=v=>{const m=String(v||'').match(/^(\d{1,2}):(\d{2})/);return m?pad(+m[1])+':'+m[2]:''};
const longDay=d=>d.toLocaleDateString('es-PE',{weekday:'long',day:'numeric',month:'long'});
const sameDay=(a,b)=>ymd(a)===ymd(b);

/* ---------- ventanas (modal) ---------- */
function openModal({title,html,footer='',cls='',onOpen}){
  $('#modalroot').innerHTML=`<div class="modal-bg" data-act="modal-bg"><div class="modal ${cls}" role="dialog" aria-modal="true" aria-label="${esc(title)}">
    <header><h2>${esc(title)}</h2><button class="xbtn" data-act="modal-x" aria-label="Cerrar">×</button></header>
    <div class="mbody" id="mbody">${html}</div>${footer?`<footer>${footer}</footer>`:''}</div></div>`;
  document.body.style.overflow='hidden';
  $('#modalroot .xbtn').focus(); onOpen&&onOpen();
}
function closeModal(){$('#modalroot').innerHTML='';document.body.style.overflow=''}
ACT['modal-x']=closeModal; ACT['modal-close']=closeModal;
document.addEventListener('mousedown',e=>{if(e.target.classList?.contains('modal-bg'))closeModal()});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&$('#modalroot').firstChild)closeModal()});

/* ---------- términos y condiciones ---------- */
let TERMS_HTML='';
function md(src){
  const inl=t=>esc(t).replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>').replace(/\[([^\]]{2,90})\]/g,'<mark class="ph">[$1]</mark>');
  let out='',para=[],list=null,tbl=[];
  const fp=()=>{if(para.length){out+='<p>'+inl(para.join(' '))+'</p>';para=[]}};
  const fl=()=>{if(list){out+=`</${list}>`;list=null}};
  const ft=()=>{if(tbl.length){const rows=tbl.filter(r=>!/^\|?[\s:|-]+\|?$/.test(r)).map(r=>r.replace(/^\||\|$/g,'').split('|').map(c=>c.trim()));
    out+='<div class="tablewrap"><table><thead><tr>'+rows[0].map(c=>`<th>${inl(c)}</th>`).join('')+'</tr></thead><tbody>'+rows.slice(1).map(r=>'<tr>'+r.map(c=>`<td>${inl(c)}</td>`).join('')+'</tr>').join('')+'</tbody></table></div>';tbl=[]}};
  for(const raw of src.split('\n')){
    const ln=raw.trimEnd(); let m;
    if(/^\s*\|/.test(ln)){fp();fl();tbl.push(ln.trim());continue} else ft();
    if(!ln.trim()){fp();fl();continue}
    if(/^---+$/.test(ln.trim())){fp();fl();out+='<hr>';continue}
    if((m=ln.match(/^(#{1,3})\s+(.*)$/))){fp();fl();const t=m[2].replace(/\*\*/g,'');const n=m[1].length===2&&t.match(/^(\d+)\.\s/);
      out+=`<h${m[1].length+(m[1].length===1?0:0)} ${n?`id="sec-${n[1]}"`:''}>${inl(t)}</h${m[1].length}>`;continue}
    if((m=ln.match(/^\s*[-*]\s+(.*)$/))){fp();if(list!=='ul'){fl();out+='<ul>';list='ul'}out+=`<li>${inl(m[1])}</li>`;continue}
    if((m=ln.match(/^\s*\d+[.)]\s+(.*)$/))){fp();if(list!=='ol'){fl();out+='<ol>';list='ol'}out+=`<li>${inl(m[1])}</li>`;continue}
    fl();para.push(ln.trim());
  }
  fp();fl();ft();return out;
}
ACT.terms=async(el)=>{
  const tickBox=el.closest('label')?.querySelector('input[type=checkbox]');
  const sec=el.dataset.sec;
  openModal({title:'Términos y Condiciones · MindReset',cls:'',html:'<p class="muted">Cargando…</p>',
    footer:`<button class="btn ghost" data-act="modal-close">Cerrar</button>${tickBox?'<button class="btn" data-act="terms-accept">He leído y acepto</button>':''}`});
  if(tickBox)$('#modalroot').dataset.tick=tickBox.id;
  try{
    if(!TERMS_HTML){const r=await fetch('/static/terminos.md');if(!r.ok)throw new Error();TERMS_HTML=md(await r.text())}
    const short=t=>{t=t.toLowerCase().replace(/^./,c=>c.toUpperCase());return t.length>34?t.slice(0,34).replace(/\s+\S*$/,'')+'…':t};
    const toc=[...TERMS_HTML.matchAll(/id="sec-(\d+)">\d+\.\s([^<]*)/g)].map(m=>`<button data-act="terms-go" data-sec="${m[1]}">${m[1]}. ${esc(short(m[2]))}</button>`).join('');
    $('#mbody').innerHTML=`<div class="doc"><div class="notice info" style="margin-top:0">Lee con calma. Puedes ir a una sección con los botones de abajo.</div><div class="toc">${toc}</div>${TERMS_HTML}</div>`;
    if(sec)ACT['terms-go']({dataset:{sec}});
  }catch{$('#mbody').innerHTML='<div class="notice err">No se pudo cargar el documento. Revisa tu conexión e inténtalo de nuevo.</div>'}
};
ACT['terms-go']=el=>{const t=$('#sec-'+el.dataset.sec);if(t)t.scrollIntoView({behavior:'smooth',block:'start'})};
ACT['terms-accept']=()=>{const id=$('#modalroot').dataset.tick;closeModal();if(id){const c=$('#'+id);if(c)c.checked=true}};

/* ---------- señales de Mindi ---------- */
async function loadSignals(sel){
  try{const s=await api('/api/signals');const box=$(sel);if(!box)return;
    box.innerHTML=s.length?`<div class="signals" role="status">${s.map(x=>`<div class="sig ${x.level}"><b>${x.level==='alert'?'💗':x.level==='info'?'💡':'🌱'}</b><span>${esc(x.text)}</span></div>`).join('')}</div>`:''}catch{}
}
ACT['offer-yes']=async()=>{CH.msgs=CH.msgs.filter(m=>!m.offer);let t;try{t=(await api('/api/contact-request',{method:'POST'})).message}catch(e){t=e.message}CH.msgs.push({role:'bot',text:t+' Mientras tanto, aquí sigo contigo 💜'});renderMsgs()};
ACT['offer-no']=()=>{CH.msgs=CH.msgs.filter(m=>!m.offer);CH.msgs.push({role:'bot',text:'Está bien, sin presión. Aquí estoy cuando quieras. ¿Seguimos conversando?'});renderMsgs()};

/* =====================================================================
   CALENDARIO
   ===================================================================== */
let CAL={view:(()=>{try{return localStorage.getItem('mr_calview')||'week'}catch{return'week'}})(),cur:new Date(),evs:[],feed:null,mode:'view',confirmDel:false};
let W=null;
const calRange=()=>{
  if(CAL.view==='day')return[CAL.cur,CAL.cur];
  if(CAL.view==='week'){const m=mondayOf(CAL.cur);return[m,addDays(m,6)]}
  const f=new Date(CAL.cur.getFullYear(),CAL.cur.getMonth(),1),s=mondayOf(f);return[s,addDays(s,41)];
};
async function calendarPage(){
  if(CAL.mode==='wizard'&&W)return drawWizard();
  CAL.mode='view';
  const[a,b]=calRange();
  CAL.evs=await api(`/api/calendar/events?start=${ymd(a)}&end=${ymd(b)}`);
  drawCal();
  if(!CAL.feed)api('/api/calendar/feed-info').then(f=>{CAL.feed=f;drawCalSide()}).catch(()=>{});
}
const evChip=e=>`<button class="ev k-${e.kind}" data-act="ev-open" data-id="${e.id}" title="${esc(KIND[e.kind]||'')}"><b>${esc(e.title)}</b><small>${hh(e.start_at)}–${hh(e.end_at)}</small></button>`;
function calTitle(){
  const c=CAL.cur;
  if(CAL.view==='day')return longDay(c);
  if(CAL.view==='month')return c.toLocaleDateString('es-PE',{month:'long',year:'numeric'});
  const m=mondayOf(c),e=addDays(m,6);
  return `${m.getDate()} ${m.toLocaleDateString('es-PE',{month:'short'}).replace('.','')} – ${e.getDate()} ${e.toLocaleDateString('es-PE',{month:'short'}).replace('.','')} ${e.getFullYear()}`;
}
function viewBody(){
  const evs=CAL.evs, today=new Date();
  const by=k=>evs.filter(e=>dkey(e.start_at)===k);
  if(CAL.view==='day'){
    const l=by(ymd(CAL.cur));
    return l.length?`<div class="dayl">${l.map(e=>`<div class="drow"><div class="t">${hh(e.start_at)}</div>${evChip(e)}</div>`).join('')}</div>`
      :`<div class="empty">No tienes actividades este día. Puedes <button class="linkb" data-act="ev-new">añadir una</button> o dejar que Mindi organice tu semana.</div>`;
  }
  if(CAL.view==='week'){
    const m=mondayOf(CAL.cur);
    return `<div class="weekgrid">${Array.from({length:7},(_,i)=>{const d=addDays(m,i),l=by(ymd(d));
      return `<div class="wcol ${sameDay(d,today)?'today':''}"><h4>${DN[i]}<b>${d.getDate()}</b></h4><div>${l.map(evChip).join('')||'<div class="muted small" style="text-align:center;padding:6px 0">—</div>'}</div></div>`}).join('')}</div>`;
  }
  const s=mondayOf(new Date(CAL.cur.getFullYear(),CAL.cur.getMonth(),1));
  const weeks=Math.ceil((((new Date(CAL.cur.getFullYear(),CAL.cur.getMonth()+1,0)).getDate())+((new Date(CAL.cur.getFullYear(),CAL.cur.getMonth(),1).getDay()+6)%7))/7);
  return `<div class="monthgrid">${DN.map(n=>`<div class="mhead">${n}</div>`).join('')}${Array.from({length:weeks*7},(_,i)=>{const d=addDays(s,i),l=by(ymd(d)),out=d.getMonth()!==CAL.cur.getMonth();
    return `<div class="mcell ${out?'out':''} ${sameDay(d,today)?'today':''}" data-act="cal-day" data-d="${ymd(d)}" role="button" tabindex="0" aria-label="${esc(longDay(d))}: ${l.length} actividades"><div class="dn">${d.getDate()}</div>
      ${l.slice(0,3).map(evChip).join('')}${l.length>3?`<div class="more">+${l.length-3} más</div>`:''}<div class="dots">${l.slice(0,6).map(()=>'<i></i>').join('')}</div></div>`}).join('')}</div>`;
}
function drawCal(){
  const has=CAL.evs.length>0;
  $('#main').innerHTML=`<div class="pagehead"><h1>Mi calendario</h1><p>Organiza clases, estudio, descansos, comidas y sueño sin sobrecargarte. Solo tú lo ves.</p></div>
  <div class="cta"><div class="mindi-cta">${mindi(54)}</div><div class="txt"><b>${has?'¿Reorganizamos tu semana?':'Creemos tu calendario juntos'}</b>
    <span>Cuéntale a Mindi tus clases, trabajo, traslados y entregas. Él reparte el estudio en varios días y deja espacio para descansar, comer y dormir.</span></div>
    <div class="inline"><button class="btn" data-act="wiz-new">Crear mi calendario</button><button class="btn mint" data-act="wiz-task">Tengo una entrega</button></div></div>
  <div class="card"><div class="caltool"><button class="navb" data-act="cal-prev" aria-label="Anterior">‹</button><button class="navb" data-act="cal-next" aria-label="Siguiente">›</button>
    <button class="btn ghost sm" data-act="cal-today">Hoy</button><div class="ttl" role="heading" aria-level="2">${esc(calTitle())}</div><div class="spacer"></div>
    <div class="seg3" role="group" aria-label="Vista">${[['day','Día'],['week','Semana'],['month','Mes']].map(([k,l])=>`<button class="${CAL.view===k?'on':''}" data-act="cal-view" data-v="${k}">${l}</button>`).join('')}</div>
    <button class="btn sm" data-act="ev-new">+ Actividad</button></div>
    ${viewBody()}
    <div class="legendk">${['class','study','work','rest','meal','sleep','exam'].map(k=>`<span><i class="k-${k}" style="border:0;background:${{class:'#6A3EC8',study:'#00BFA6',work:'#4B5E7C',rest:'#7BE0D0',meal:'#F6A57C',sleep:'#8F68E8',exam:'#FF7B7B'}[k]}"></i>${KIND[k]}</span>`).join('')}</div></div>
  <div class="two" id="calside"></div>`;
  drawCalSide();
}
function drawCalSide(){
  const box=$('#calside');if(!box)return;const f=CAL.feed,local=f&&/localhost|127\.0\.0\.1/.test(f.feed_url);
  const kinds=['class','study','work','rest','meal','sleep','exam','deadline'];
  box.innerHTML=`<div class="card"><h2>Google Calendar</h2>
    <p class="muted small" style="margin-bottom:12px">Vincula tu calendario para verlo en tu celular y en tu cuenta de Google${me.email?` (<b>${esc(me.email)}</b>)`:''}.</p>
    ${f?`<div class="inline"><a class="btn" target="_blank" rel="noopener" href="${esc(f.google_subscribe)}">Vincular con Google Calendar</a><button class="btn soft" data-act="feed-copy">Copiar enlace iCal</button><a class="btn ghost" data-act="ics-dl" href="#">Descargar .ics</a></div>
      ${local?'<div class="notice">Estás en modo local: Google no puede leer enlaces de tu computadora. Funcionará cuando MindReset esté publicado en internet.</div>':''}
      <p class="muted small" style="margin-top:12px">Se abrirá Google Calendar: elige tu cuenta y confirma «Agregar». Google actualiza los calendarios suscritos cada algunas horas. Cada actividad también tiene su botón «Añadir a Google».</p>`:'<p class="muted">Preparando enlace…</p>'}
    <hr style="border:0;border-top:1px solid var(--line);margin:16px 0">
    <h3 style="font-size:16px">Actividades de Mindi</h3><p class="muted small" style="margin-bottom:10px">Borra solo lo que Mindi generó; tus actividades manuales se quedan.</p>
    <button class="btn danger sm" data-act="plan-del">${CAL.confirmDel?'¿Seguro? Toca otra vez':'Borrar plan de Mindi'}</button></div>
  <div class="card"><h2>Recordatorios por correo</h2>
    <p class="muted small" style="margin-bottom:12px">Te escribimos <b>15 minutos antes</b> de tus descansos y actividades.</p>
    ${!me.mail_enabled?'<div class="notice">El envío de correos aún no está activado en este servidor (ver README, paso «Correos»). Tus ajustes se guardan igual.</div>':''}
    <div class="field" style="margin-top:0"><label for="memail">Correo</label><div class="inline"><input class="input" id="memail" type="email" value="${esc(me.email||'')}" placeholder="tucorreo@gmail.com"><button class="btn soft sm" data-act="mail-save">Guardar</button></div></div>
    ${me.email?(me.email_verified?'<p class="ok-txt">✓ Correo verificado</p>':`<div class="notice info"><b>Verifica tu correo</b> para recibir recordatorios.<div class="inline" style="margin-top:8px"><button class="btn sm" data-act="mail-code">Enviarme un código</button><input class="input" id="mcode" inputmode="numeric" maxlength="6" placeholder="Código de 6 dígitos" style="max-width:170px"><button class="btn sm mint" data-act="mail-verify">Verificar</button></div></div>`):''}
    <label class="check" style="color:var(--ink)"><input type="checkbox" id="mnot" ${me.notify_email?'checked':''} data-act="mail-toggle"><span>Enviar recordatorios por correo</span></label>
    <p class="small" style="font-weight:700;margin-bottom:6px">Avisarme de:</p><div class="kinds">${kinds.map(k=>`<label><input type="checkbox" data-act="mail-kind" data-k="${k}" ${(me.notify_kinds||[]).includes(k)?'checked':''}>${KIND[k]}</label>`).join('')}</div>
    <div style="margin-top:14px"><button class="btn ghost sm" data-act="mail-test" ${me.email_verified?'':'disabled'}>Enviar correo de prueba</button></div></div>`;
}
ACT['cal-prev']=()=>calShift(-1);ACT['cal-next']=()=>calShift(1);
function calShift(n){const c=CAL.cur;CAL.cur=CAL.view==='day'?addDays(c,n):CAL.view==='week'?addDays(c,7*n):new Date(c.getFullYear(),c.getMonth()+n,1);calendarPage().catch(e=>toast(e.message))}
ACT['cal-today']=()=>{CAL.cur=new Date();calendarPage()};
ACT['cal-view']=el=>{CAL.view=el.dataset.v;try{localStorage.setItem('mr_calview',CAL.view)}catch{}calendarPage()};
ACT['cal-day']=el=>{CAL.cur=pYmd(el.dataset.d);CAL.view='day';calendarPage()};
document.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.classList?.contains('mcell')){e.preventDefault();ACT['cal-day'](e.target)}});
ACT['feed-copy']=async()=>{try{await navigator.clipboard.writeText(CAL.feed.feed_url);toast('Enlace copiado')}catch{prompt('Copia este enlace:',CAL.feed.feed_url)}};
ACT['ics-dl']=async()=>{try{const r=await fetch('/api/calendar/export.ics',{headers:{Authorization:'Bearer '+token}});const b=await r.blob();const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='mindreset_calendario.ics';a.click();URL.revokeObjectURL(a.href)}catch(e){toast('No se pudo descargar')}};
ACT['plan-del']=async()=>{if(!CAL.confirmDel){CAL.confirmDel=true;drawCalSide();setTimeout(()=>{CAL.confirmDel=false;drawCalSide()},4000);return}
  CAL.confirmDel=false;try{const r=await api('/api/calendar/plan',{method:'DELETE'});toast(`Se borraron ${r.deleted} actividades de Mindi`);calendarPage()}catch(e){toast(e.message)}};
/* correos */
async function patchProfile(body,msg){try{me=await api('/api/profile',{method:'PATCH',body:JSON.stringify(body)});if(msg)toast(msg);drawCalSide()}catch(e){toast(e.message)}}
ACT['mail-save']=()=>patchProfile({email:$('#memail').value.trim()},'Correo guardado. Verifícalo para recibir recordatorios.');
ACT['mail-toggle']=el=>patchProfile({notify_email:el.checked},el.checked?'Recordatorios activados':'Recordatorios desactivados');
ACT['mail-kind']=()=>patchProfile({notify_kinds:[...document.querySelectorAll('[data-act=mail-kind]:checked')].map(x=>x.dataset.k)},'Preferencias guardadas');
ACT['mail-code']=async el=>{el.disabled=true;try{await api('/api/email/send-code',{method:'POST'});toast('Te enviamos un código. Revisa tu bandeja (y spam).')}catch(e){toast(e.message)}el.disabled=false};
ACT['mail-verify']=async()=>{try{await api('/api/email/verify',{method:'POST',body:JSON.stringify({code:$('#mcode').value.trim()})});me=await api('/api/me');toast('Correo verificado ✓');drawCalSide()}catch(e){toast(e.message)}};
ACT['mail-test']=async el=>{el.disabled=true;try{await api('/api/email/test',{method:'POST'});toast('Correo de prueba enviado')}catch(e){toast(e.message)}el.disabled=false};

/* actividad: crear / editar */
const KIND_OPTS=Object.entries(KIND).map(([k,l])=>`<option value="${k}">${l}</option>`).join('');
function evForm(e){
  const d=e?dkey(e.start_at):ymd(CAL.view==='day'?CAL.cur:(sameDay(CAL.cur,new Date())||CAL.view==='month'?CAL.cur:new Date()));
  return `<form id="evform" data-id="${e?e.id:''}"><div class="field" style="margin-top:0"><label for="evt">Nombre</label><input id="evt" required maxlength="80" value="${esc(e?.title||'')}" placeholder="Ej.: Estudiar cálculo"></div>
   <div class="grid2"><div class="field"><label for="evk">Tipo</label><select id="evk">${KIND_OPTS}</select></div><div class="field"><label for="evd">Fecha</label><input id="evd" type="date" required value="${d}"></div></div>
   <div class="grid2"><div class="field"><label for="evs">Inicio</label><input id="evs" type="time" required value="${e?hh(e.start_at):'16:00'}"></div><div class="field"><label for="eve">Fin</label><input id="eve" type="time" required value="${e?hh(e.end_at):'17:00'}"></div></div>
   <div class="field"><label for="evn">Notas (opcional)</label><input id="evn" maxlength="300" value="${esc(e?.notes||'')}"></div><div id="everr" class="notice err hidden" role="alert"></div></form>`;
}
function openEv(e){
  openModal({title:e?'Editar actividad':'Nueva actividad',cls:'sm',html:evForm(e),
    footer:`${e?`<a class="btn ghost sm" href="${esc(e.gcal)}" target="_blank" rel="noopener">Añadir a Google</a><button class="btn danger sm" data-act="ev-del" data-id="${e.id}">Eliminar</button>`:''}<span class="spacer"></span><button class="btn ghost" data-act="modal-close">Cancelar</button><button class="btn" data-act="ev-save">Guardar</button>`,
    onOpen:()=>{if(e)$('#evk').value=e.kind;else $('#evk').value='study'}});
}
ACT['ev-new']=()=>openEv(null);
ACT['ev-open']=el=>openEv(CAL.evs.find(x=>x.id===+el.dataset.id));
ACT['ev-save']=async el=>{
  const f=$('#evform');if(!f.reportValidity())return;
  const d=$('#evd').value,s=$('#evs').value,e=$('#eve').value,endD=e<=s?ymd(addDays(pYmd(d),1)):d;
  const body={title:$('#evt').value.trim(),kind:$('#evk').value,start_at:`${d}T${s}`,end_at:`${endD}T${e}`,notes:$('#evn').value.trim()};
  const id=f.dataset.id;el.disabled=true;
  try{await api(id?`/api/calendar/events/${id}`:'/api/calendar/events',{method:id?'PUT':'POST',body:JSON.stringify(body)});closeModal();toast('Guardado');CAL.cur=pYmd(d);await calendarPage()}
  catch(err){const b=$('#everr');b.textContent=err.message;b.classList.remove('hidden');el.disabled=false}
};
ACT['ev-del']=async el=>{if(el.dataset.sure!=='1'){el.dataset.sure='1';el.textContent='¿Seguro?';return}
  try{await api('/api/calendar/events/'+el.dataset.id,{method:'DELETE'});closeModal();toast('Actividad eliminada');await calendarPage()}catch(e){toast(e.message)}};

/* ---------- asistente para crear el calendario ---------- */
const newW=mode=>({mode,text:'',fixed:mode==='full'?[{title:'',kind:'class',days:[0,2,4],start:'08:00',end:'12:00'}]:[],tasks:[{title:'',due:ymd(addDays(new Date(),5)),hours:3,kind:'task'}],
  prefs:{wake:'07:00',sleep:'23:00',transport_min:0,breakfast:'07:30',lunch:'13:00',dinner:'20:00',max_study_hours:4},plan:null,busy:false,msg:'',unparsed:[]});
ACT['wiz-new']=()=>{W=newW('full');CAL.mode='wizard';calendarPage()};
ACT['wiz-task']=()=>{W=newW('tasks_only');CAL.mode='wizard';calendarPage()};
ACT['wiz-cancel']=()=>{CAL.mode='view';W=null;calendarPage()};
function fixedRow(f,i){return `<div class="item"><div class="grid3"><div><label>Nombre</label><input class="input" data-p="fixed.${i}.title" value="${esc(f.title)}" placeholder="Ej.: Clases, Trabajo"></div>
  <div><label>Tipo</label><select class="input" data-p="fixed.${i}.kind"><option value="class" ${f.kind==='class'?'selected':''}>Clase</option><option value="work" ${f.kind==='work'?'selected':''}>Trabajo</option><option value="other" ${f.kind==='other'?'selected':''}>Otra actividad</option></select></div>
  <div><label>Horario</label><div class="inline" style="gap:6px"><input class="input" type="time" data-p="fixed.${i}.start" value="${t24(f.start)}"><input class="input" type="time" data-p="fixed.${i}.end" value="${t24(f.end)}"></div></div></div>
  <div class="row"><div class="dayschips" role="group" aria-label="Días">${DL.map((l,d)=>`<button type="button" class="${f.days.includes(d)?'on':''}" data-act="wday" data-i="${i}" data-d="${d}" aria-pressed="${f.days.includes(d)}" aria-label="${DN[d]}">${l}</button>`).join('')}</div>
  <button type="button" class="btn ghost sm" data-act="wdel" data-k="fixed" data-i="${i}">Quitar</button></div></div>`}
function taskRow(t,i){return `<div class="item"><div class="grid3"><div><label>¿Qué debes entregar o rendir?</label><input class="input" data-p="tasks.${i}.title" value="${esc(t.title)}" placeholder="Ej.: Informe de laboratorio"></div>
  <div><label>Fecha límite</label><input class="input" type="date" data-p="tasks.${i}.due" value="${esc(t.due)}"></div>
  <div><label>Horas de esfuerzo</label><input class="input" type="number" min="0.5" max="40" step="0.5" data-p="tasks.${i}.hours" value="${t.hours}"></div></div>
  <div class="row"><select class="input" style="max-width:180px" data-p="tasks.${i}.kind"><option value="task" ${t.kind==='task'?'selected':''}>Tarea / entrega</option><option value="exam" ${t.kind==='exam'?'selected':''}>Examen</option></select>
  <button type="button" class="btn ghost sm" data-act="wdel" data-k="tasks" data-i="${i}">Quitar</button></div></div>`}
function drawWizard(){
  const full=W.mode==='full',p=W.prefs;
  $('#main').innerHTML=`<button class="back" data-act="wiz-cancel">‹ Volver al calendario</button>
  <div class="pagehead"><h1>${full?'Creemos tu calendario':'Repartamos tu entrega'}</h1><p>${full?'Responde lo que sepas; puedes cambiarlo después.':'Mindi repartirá el trabajo en varios días, sin sobrecargarte.'}</p></div>
  ${W.plan?drawPreview():`
  <div class="card"><div class="wiz-step">${mindi(44)}<div class="bub">${full?'Cuéntame con tus palabras: <b>clases, trabajo, tiempo de traslado, tareas y exámenes</b>. Ej.: <i>«Estudio lunes, miércoles y viernes de 8 a 1, trabajo martes y jueves de 3 a 8, el viaje me toma 40 minutos, y tengo examen de cálculo el 4 de diciembre.»</i>':'Dime <b>qué entrega o examen tienes y para cuándo</b>. Ej.: <i>«Informe de física para el viernes 28, unas 5 horas de trabajo.»</i>'}</div></div>
    <textarea class="input" id="wtext" rows="4" maxlength="2000" placeholder="Escribe aquí…">${esc(W.text)}</textarea>
    <div class="inline" style="margin-top:10px"><button class="btn mint" data-act="wparse" ${W.busy?'disabled':''}>${W.busy?'Leyendo…':'Que Mindi lo lea y rellene el cuestionario'}</button><span class="muted small">O completa el cuestionario a mano.</span></div>
    ${W.msg?`<div class="notice ok">${esc(W.msg)}</div>`:''}${W.unparsed.length?`<div class="notice">No pude interpretar: ${W.unparsed.map(esc).join('; ')}. Agrégalo abajo.</div>`:''}</div>
  ${full?`<div class="card"><h2>1 · Tu rutina</h2><div class="grid3 item" style="border:0;padding:0">
    <div><label>Me despierto</label><input class="input" type="time" data-p="prefs.wake" value="${p.wake}"></div><div><label>Me acuesto</label><input class="input" type="time" data-p="prefs.sleep" value="${p.sleep}"></div>
    <div><label>Traslado por trayecto (min)</label><input class="input" type="number" min="0" max="180" step="5" data-p="prefs.transport_min" value="${p.transport_min}"></div>
    <div><label>Desayuno</label><input class="input" type="time" data-p="prefs.breakfast" value="${p.breakfast}"></div><div><label>Almuerzo</label><input class="input" type="time" data-p="prefs.lunch" value="${p.lunch}"></div><div><label>Cena</label><input class="input" type="time" data-p="prefs.dinner" value="${p.dinner}"></div>
    <div><label>Máx. horas de estudio por día</label><input class="input" type="number" min="1" max="10" step="0.5" data-p="prefs.max_study_hours" value="${p.max_study_hours}"></div></div></div>
  <div class="card"><h2>2 · Clases, trabajo y otras actividades fijas</h2><p class="muted small">Lo que se repite cada semana.</p>${W.fixed.map(fixedRow).join('')}<button class="btn soft sm" data-act="wadd" data-k="fixed">+ Añadir otra</button></div>`:''}
  <div class="card"><h2>${full?'3 · ':''}Entregas y exámenes</h2><p class="muted small">Mindi repartirá el estudio en varios días antes de cada fecha, empezando con tiempo.</p>${W.tasks.map(taskRow).join('')}<button class="btn soft sm" data-act="wadd" data-k="tasks">+ Añadir otra</button></div>
  <div id="wizerr" class="notice err hidden" role="alert"></div>
  <div class="row"><button class="btn ghost" data-act="wiz-cancel">Cancelar</button><button class="btn" data-act="wgen" ${W.busy?'disabled':''}>${W.busy?'Armando…':'Armar mi calendario'}</button></div>`}`;
}
function drawPreview(){
  const pl=W.plan,by={};pl.events.forEach(e=>(by[dkey(e.start_at)]??=[]).push(e));
  return `<div class="card"><h2>Así quedaría tu calendario</h2><div class="statline"><span>${pl.stats.days} días</span><span>${pl.stats.study_hours} h de estudio</span><span>${pl.stats.rest_blocks} descansos</span></div>
   ${pl.warnings?.length?`<div class="warns">${pl.warnings.map(w=>`<div class="notice">${esc(w)}</div>`).join('')}</div>`:'<div class="notice ok">Todo cabe sin sobrecargarte. 🌿</div>'}
   <p class="muted small">${W.mode==='full'?'Al guardar, reemplazaremos el plan anterior de Mindi desde '+esc(pl.start)+'. Tus actividades manuales no se tocan.':'Se agregarán a tu calendario sin tocar lo que ya tienes.'}</p></div>
   ${Object.keys(by).sort().map(k=>`<div class="card" style="padding:14px 18px"><div class="prev-day">${esc(longDay(pYmd(k)))}</div>${by[k].map(e=>`<div class="drow" style="margin:4px 0"><div class="t" style="padding-top:6px;font-size:13px">${hh(e.start_at)}</div><div class="ev k-${e.kind}" style="margin:0"><b>${esc(e.title)}</b><small>${hh(e.start_at)}–${hh(e.end_at)} · ${esc(KIND[e.kind]||'')}</small></div></div>`).join('')}</div>`).join('')}
   <div class="row"><button class="btn ghost" data-act="wback">Ajustar datos</button><button class="btn" data-act="wsave">Guardar en mi calendario</button></div>`;
}
document.addEventListener('input',e=>{
  const el=e.target;if(!W||!el.dataset?.p)return;const[a,b,c]=el.dataset.p.split('.');let v=el.value;
  if(c==='hours'||b==='transport_min'||b==='max_study_hours')v=v===''?'':+v;
  if(c===undefined)W[a][b]=v;else W[a][+b][c]=v;
});
document.addEventListener('input',e=>{if(e.target.id==='wtext'&&W)W.text=e.target.value});
ACT.wday=el=>{const f=W.fixed[+el.dataset.i],d=+el.dataset.d;f.days=f.days.includes(d)?f.days.filter(x=>x!==d):[...f.days,d].sort();drawWizard()};
ACT.wadd=el=>{if(el.dataset.k==='fixed')W.fixed.push({title:'',kind:'class',days:[],start:'08:00',end:'12:00'});else W.tasks.push({title:'',due:ymd(addDays(new Date(),5)),hours:3,kind:'task'});drawWizard()};
ACT.wdel=el=>{W[el.dataset.k].splice(+el.dataset.i,1);drawWizard()};
ACT.wback=()=>{W.plan=null;drawWizard()};
const wErr=m=>{const b=$('#wizerr');if(b){b.textContent=m;b.classList.toggle('hidden',!m);b.scrollIntoView({block:'center'})}};
ACT.wparse=async()=>{
  W.text=$('#wtext').value;if(W.text.trim().length<3)return wErr('Escribe algo primero.');W.busy=true;drawWizard();
  try{const r=await api('/api/planner/parse',{method:'POST',body:JSON.stringify({text:W.text})});
    if(W.mode==='full'){if(r.fixed?.length)W.fixed=r.fixed.map(f=>({...f,start:t24(f.start),end:t24(f.end)}));
      for(const k of['wake','sleep','transport_min'])if(r.prefs?.[k]!==undefined&&r.prefs[k]!=='')W.prefs[k]=k==='transport_min'?+r.prefs[k]:t24(r.prefs[k])}
    if(r.tasks?.length)W.tasks=r.tasks;
    W.unparsed=r.unparsed||[];W.msg=`Listo (${r.source==='gemini'?'con Gemini':'lector básico'}). Revisa y corrige abajo lo que haga falta.`}
  catch(e){W.msg='';W.unparsed=[];toast(e.message)}
  W.busy=false;drawWizard();
};
ACT.wgen=async()=>{
  const fixed=W.fixed.filter(f=>f.days.length&&f.start&&f.end).map(f=>({title:(f.title||'Clases').trim(),kind:f.kind,days:f.days,start:t24(f.start),end:t24(f.end)}));
  const tasks=W.tasks.filter(t=>t.title.trim()&&t.due).map(t=>({title:t.title.trim(),due:t.due,hours:+t.hours||3,kind:t.kind}));
  if(!tasks.length&&W.mode==='tasks_only')return wErr('Escribe al menos una entrega o examen con su fecha.');
  if(!tasks.length&&!fixed.length)return wErr('Añade al menos una actividad fija o una entrega.');
  const p={...W.prefs};for(const k of['breakfast','lunch','dinner','wake','sleep'])p[k]=t24(p[k]);
  W.busy=true;drawWizard();
  try{W.plan=await api('/api/planner/generate',{method:'POST',body:JSON.stringify({fixed,tasks,prefs:p,mode:W.mode})})}
  catch(e){W.busy=false;drawWizard();return wErr(e.message)}
  W.busy=false;drawWizard();window.scrollTo({top:0});
};
ACT.wsave=async el=>{el.disabled=true;
  try{const r=await api('/api/planner/apply',{method:'POST',body:JSON.stringify({events:W.plan.events,replace_plan:W.mode==='full',start:W.plan.start})});
    toast(`Guardé ${r.saved} actividades en tu calendario`);CAL.cur=pYmd(W.plan.start);CAL.view='week';CAL.mode='view';W=null;await calendarPage();window.scrollTo({top:0})}
  catch(e){toast(e.message);el.disabled=false}};

/* =====================================================================
   CHEQUEO PROFUNDO (3 preguntas adaptativas + recomendaciones)
   ===================================================================== */
ACT['deep-start']=()=>{DP=null;tab='deep';drawSide();render();window.scrollTo({top:0})};
async function deepPage(){
  if(!DP){
    $('#main').innerHTML=`<div class="wizard"><div class="card intro">${mindi(72)}<h1>Mindi está preparando tus preguntas…</h1><p>Las adapta a tus respuestas, a lo que me contaste y a tu horario.</p></div></div>`;
    const texts=(CH.msgs||[]).filter(m=>m.role==='user').map(m=>m.text);
    try{const r=await api('/api/deep/questions',{method:'POST',body:JSON.stringify({chat:texts})});DP={qs:r.questions,answers:{},i:0,source:r.source,result:null,added:false}}
    catch(e){$('#main').innerHTML=`<div class="wizard"><div class="card"><div class="notice err">${esc(e.message)}</div><button class="btn" data-act="go" data-tab="survey">Hacer la encuesta del día</button></div></div>`;return}
  }
  if(tab!=='deep')return;
  DP.result?drawDeepResult():drawDeepQ();
}
function drawDeepQ(){
  const q=DP.qs[DP.i],n=DP.qs.length,cur=DP.answers[q.id];
  $('#main').innerHTML=`<div class="wizard"><div class="steps" aria-hidden="true">${DP.qs.map((_,k)=>`<span class="seg ${k<DP.i?'done':k===DP.i?'now':''}"></span>`).join('')}</div>
   <div class="card"><p class="qlabel">Pregunta ${DP.i+1} de ${n} · hecha para ti</p><h2 class="qtitle" id="qt">${esc(q.title)}</h2><p class="qhelp">${esc(q.help||'')}</p>
   <div class="opts" role="radiogroup" aria-labelledby="qt">${q.options.map(o=>`<label class="opt ${cur===o.id?'sel':''}"><input type="radio" name="dopt" value="${esc(o.id)}" ${cur===o.id?'checked':''}><span class="dot"></span><span><b>${esc(o.label)}</b>${o.hint?`<small>${esc(o.hint)}</small>`:''}</span></label>`).join('')}</div>
   <div id="derr" class="notice err hidden" role="alert"></div>
   <div class="navrow"><button class="btn ghost" data-act="dprev">${DP.i===0?'Salir':'Atrás'}</button><button class="btn" id="dnext" data-act="dnext" ${cur?'':'disabled'}>${DP.i===n-1?'Ver mis recomendaciones':'Siguiente'}</button></div></div></div>`;
  document.querySelectorAll('.opt input').forEach(r=>r.addEventListener('change',()=>{DP.answers[q.id]=r.value;document.querySelectorAll('.opt').forEach(o=>o.classList.toggle('sel',o.contains(r)&&r.checked));$('#dnext').disabled=false}));
}
ACT.dprev=()=>{if(DP.i===0){DP=null;return go('chat')}DP.i--;drawDeepQ()};
ACT.dnext=async el=>{
  if(DP.i<DP.qs.length-1){DP.i++;return drawDeepQ()}
  el.disabled=true;el.textContent='Preparando…';
  try{DP.result=await api('/api/deep/submit',{method:'POST',body:JSON.stringify({questions:DP.qs,answers:DP.answers})});drawDeepResult();window.scrollTo({top:0})}
  catch(e){const b=$('#derr');b.textContent=e.message;b.classList.remove('hidden');el.disabled=false;el.textContent='Ver mis recomendaciones'}
};
function drawDeepResult(){
  const r=DP.result,withCal=r.recommendations.filter(x=>x.calendar);
  $('#main').innerHTML=`<div class="wizard"><div class="summary"><div class="row" style="justify-content:flex-start;gap:14px">${mindi(48)}<h2 style="margin:0">Lo que veo, ${esc(first())}</h2></div><p style="margin-top:10px">${esc(r.student_summary)}</p></div>
   <h3 style="margin:0 0 4px">Recomendaciones para ti</h3><p class="muted small">Pequeñas y con ejemplos. Marca las que quieras convertir en actividades.</p>
   <div class="recs" id="recs">${r.recommendations.map((x,i)=>`<label class="rec">${x.calendar?`<input type="checkbox" class="rc" data-i="${i}" checked aria-label="Añadir al calendario">`:'<span style="width:20px;flex:none"></span>'}<span><b>${esc(x.title)}</b><span class="t">${esc(x.detail)}</span>${x.calendar?`<small>📅 ${esc(x.calendar.title)} · ${x.calendar.minutes} min</small>`:''}</span></label>`).join('')}</div>
   ${withCal.length?`<div class="askcal" id="askcal"><b>¿Desea añadir estas actividades a su calendario?</b><p style="margin:4px 0 12px">Las pondré en huecos libres de los próximos días, sin chocar con tus clases.</p>
     ${DP.added?'<p class="ok-txt">✓ Listo, ya están en tu calendario.</p>':'<div class="inline"><button class="btn mint" data-act="dadd">Sí, añadir las marcadas</button><button class="btn ghost" data-act="dskip">Ahora no</button></div>'}</div>`:''}
   <div class="notice info">Quedó un <b>informe breve</b> (resumen de tus respuestas y tu progreso, sin tu conversación con Mindi) disponible para el servicio de psicología, como autorizaste al registrarte. También se guarda en la hoja de seguimiento de tu institución.</div>
   <div class="row" style="justify-content:flex-start"><button class="btn" data-act="go" data-tab="calendar">Ver mi calendario</button><button class="btn soft" data-act="go" data-tab="chat">Volver con Mindi</button></div></div>`;
}
ACT.dadd=async el=>{
  const items=[...document.querySelectorAll('.rc:checked')].map(c=>DP.result.recommendations[+c.dataset.i].calendar);
  if(!items.length)return toast('Marca al menos una actividad');
  el.disabled=true;
  try{const r=await api('/api/calendar/add-activities',{method:'POST',body:JSON.stringify({items})});DP.added=true;toast(`Añadí ${r.added} actividad${r.added===1?'':'es'} a tu calendario`);
    const c=$('#askcal');if(c)c.innerHTML=`<b>¡Hecho!</b><p style="margin:6px 0 0" class="ok-txt">✓ Añadí ${r.added} actividad${r.added===1?'':'es'} desde ${esc(fDate(r.from))}${r.skipped?`. ${r.skipped} no encontró hueco libre.`:'.'}</p>`}
  catch(e){toast(e.message);el.disabled=false}};
ACT.dskip=()=>{const c=$('#askcal');if(c)c.innerHTML='<b>Sin problema.</b><p style="margin:6px 0 0">Las recomendaciones quedan guardadas en «Mi bienestar».</p>'};

/* ---------- Mi bienestar: señales + chequeos profundos ---------- */
const _sw=studentWellbeing;
studentWellbeing=async function(){
  await _sw();
  const main=$('#main');if(!main||tab!=='wellbeing')return;
  main.insertAdjacentHTML('afterbegin','<div id="sigw"></div>');loadSignals('#sigw');
  try{const reps=await api('/api/my-reports');
    main.insertAdjacentHTML('beforeend',`<div class="card hist"><h2>Mis chequeos profundos</h2><p class="muted small" style="margin-bottom:6px">Psicología ve un informe breve de cada uno. <button class="linkb" data-act="deep-start">Hacer uno nuevo</button></p>
      ${reps.length?reps.map(r=>`<details><summary>${stressPill(['Sin estrés','Eustrés','Angustia'].indexOf(r.label),r.label)}<span>${esc(fDT(r.created_at))}</span></summary><div class="qa"><div><b>Lo que Mindi vio</b>${esc(r.student_summary)}</div>${r.recommendations.map(x=>`<div><b>${esc(x.title)}</b>${esc(x.detail)}</div>`).join('')}</div></details>`).join(''):'<p class="muted" style="padding:10px 0">Aún no has hecho un chequeo profundo.</p>'}</div>`)}catch{}
};

/* =====================================================================
   COMUNIDAD ANÓNIMA
   ===================================================================== */
const KAV={
 p1:`<svg viewBox="0 0 64 64"><rect width="64" height="64" fill="#E2D6FF"/><path d="M14 27 17 8l13 10zM50 27 47 8 34 18z" fill="#FFE9DC" stroke="#6A3EC8" stroke-width="2" stroke-linejoin="round"/><ellipse cx="32" cy="38" rx="20" ry="16" fill="#FFF6EA" stroke="#6A3EC8" stroke-width="2"/><circle cx="24.5" cy="37" r="2.5" fill="#3B2A66"/><circle cx="39.5" cy="37" r="2.5" fill="#3B2A66"/><ellipse cx="19.5" cy="43" rx="3.6" ry="2.3" fill="#FF7B7B" opacity=".5"/><ellipse cx="44.5" cy="43" rx="3.6" ry="2.3" fill="#FF7B7B" opacity=".5"/><path d="M29 42q3 3 6 0" fill="none" stroke="#3B2A66" stroke-width="2" stroke-linecap="round"/></svg>`,
 p2:`<svg viewBox="0 0 64 64"><rect width="64" height="64" fill="#B2F0E6"/><circle cx="16" cy="20" r="8" fill="#E8C9A6" stroke="#00695C" stroke-width="2"/><circle cx="48" cy="20" r="8" fill="#E8C9A6" stroke="#00695C" stroke-width="2"/><circle cx="32" cy="36" r="21" fill="#F2D9BC" stroke="#00695C" stroke-width="2"/><ellipse cx="32" cy="43" rx="8" ry="6" fill="#FFF3E2"/><circle cx="24" cy="33" r="2.4" fill="#3B2A66"/><circle cx="40" cy="33" r="2.4" fill="#3B2A66"/><ellipse cx="32" cy="40" rx="2.6" ry="1.8" fill="#3B2A66"/><ellipse cx="18.5" cy="40" rx="3.4" ry="2.2" fill="#FF7B7B" opacity=".5"/><ellipse cx="45.5" cy="40" rx="3.4" ry="2.2" fill="#FF7B7B" opacity=".5"/></svg>`,
 p3:`<svg viewBox="0 0 64 64"><rect width="64" height="64" fill="#FFE9DC"/><rect x="18" y="3" width="10" height="26" rx="5" fill="#fff" stroke="#98481F" stroke-width="2"/><rect x="36" y="3" width="10" height="26" rx="5" fill="#fff" stroke="#98481F" stroke-width="2"/><rect x="21" y="8" width="4" height="15" rx="2" fill="#FFB8C8"/><rect x="39" y="8" width="4" height="15" rx="2" fill="#FFB8C8"/><ellipse cx="32" cy="40" rx="19" ry="17" fill="#fff" stroke="#98481F" stroke-width="2"/><circle cx="25" cy="38" r="2.4" fill="#3B2A66"/><circle cx="39" cy="38" r="2.4" fill="#3B2A66"/><ellipse cx="20" cy="44" rx="3.4" ry="2.2" fill="#FF7B7B" opacity=".5"/><ellipse cx="44" cy="44" rx="3.4" ry="2.2" fill="#FF7B7B" opacity=".5"/><path d="M29.5 44q2.5 2.6 5 0" fill="none" stroke="#3B2A66" stroke-width="2" stroke-linecap="round"/></svg>`,
 p4:`<svg viewBox="0 0 64 64"><rect width="64" height="64" fill="#E6ECF7"/><path d="M16 46a10 10 0 0 1 1-19.8A13 13 0 0 1 42 22a11 11 0 0 1 8 22.6c-.6.9-1.8 1.4-3 1.4z" fill="#fff" stroke="#4B5E7C" stroke-width="2" stroke-linejoin="round"/><circle cx="26" cy="35" r="2.3" fill="#3B2A66"/><circle cx="39" cy="35" r="2.3" fill="#3B2A66"/><ellipse cx="21.5" cy="40" rx="3.3" ry="2.1" fill="#FF7B7B" opacity=".5"/><ellipse cx="43.5" cy="40" rx="3.3" ry="2.1" fill="#FF7B7B" opacity=".5"/><path d="M29.5 39.5q3 3 6 0" fill="none" stroke="#3B2A66" stroke-width="2" stroke-linecap="round"/></svg>`,
 p5:`<svg viewBox="0 0 64 64"><rect width="64" height="64" fill="#FFF1CF"/><path d="M32 22c-1-8 4-14 13-14 1 8-4 14-13 14zM32 22c1-6-3-11-10-11-1 6 3 11 10 11z" fill="#00BFA6" stroke="#00695C" stroke-width="2" stroke-linejoin="round"/><path d="M14 52c0-12 8-24 18-24s18 12 18 24z" fill="#F6D8A8" stroke="#98481F" stroke-width="2" stroke-linejoin="round"/><circle cx="26" cy="42" r="2.4" fill="#3B2A66"/><circle cx="38" cy="42" r="2.4" fill="#3B2A66"/><ellipse cx="21.5" cy="47" rx="3.2" ry="2" fill="#FF7B7B" opacity=".5"/><ellipse cx="42.5" cy="47" rx="3.2" ry="2" fill="#FF7B7B" opacity=".5"/><path d="M29 46.5q3 2.8 6 0" fill="none" stroke="#3B2A66" stroke-width="2" stroke-linecap="round"/></svg>`};
const KAV_NAMES={p1:'Gatito',p2:'Osito',p3:'Conejito',p4:'Nubecita',p5:'Brotecito'};
const kav=(a,size=40)=>`<span class="kav" style="width:${size}px;height:${size}px">${a&&a.startsWith('data:image')?`<img alt="" src="${esc(a)}">`:(KAV[a]||KAV.p1)}</span>`;
let CM={profile:undefined,q:'',cat:'',posts:[],cats:[],editing:false,draft:{alias:'',avatar:'p1'},composing:false,timer:null};
const canPost=()=>me.role==='student';
async function communityPage(){
  if(tab==='post')return postPage();
  if(canPost()&&CM.profile===undefined){CM.profile=await api('/api/community/profile');if(CM.profile)CM.draft={...CM.profile}}
  if(canPost()&&(!CM.profile||CM.editing))return drawProfile();
  const r=await api(`/api/community/posts?q=${encodeURIComponent(CM.q)}&category=${encodeURIComponent(CM.cat)}`);
  CM.posts=r.posts;CM.cats=r.categories;drawForum();
}
function drawProfile(){
  const d=CM.draft,custom=d.avatar.startsWith('data:');
  $('#main').innerHTML=`<div class="wizard"><div class="pagehead"><h1>${CM.profile?'Mi perfil anónimo':'Tu perfil anónimo'}</h1><p>En la comunidad nadie verá tu nombre real: solo tu alias y tu avatar.</p></div>
  <div class="card"><div class="notice info" style="margin-top:0">Elige un alias inventado que <b>no</b> se parezca a tu nombre, usuario, carrera ni a datos que te identifiquen.</div>
   <div class="field"><label for="alias">Alias</label><input id="alias" maxlength="24" minlength="3" value="${esc(d.alias)}" placeholder="Ej.: Luna Serena"></div>
   <p style="font-weight:700;margin:6px 0 4px">Tu avatar</p>
   <div class="avpick" role="radiogroup" aria-label="Avatar">${Object.keys(KAV).map(k=>`<button type="button" class="${d.avatar===k?'on':''}" data-act="avpick" data-k="${k}" role="radio" aria-checked="${d.avatar===k}" aria-label="${KAV_NAMES[k]}">${kav(k,64)}</button>`).join('')}
     ${custom?`<button type="button" class="on" aria-label="Tu foto">${kav(d.avatar,64)}</button>`:''}
     <label class="up" tabindex="0">📷<br>Subir foto<input type="file" id="avfile" accept="image/*" hidden></label></div>
   <p class="muted small">Si subes una foto, no uses una donde se te reconozca fácilmente. Se reduce a un tamaño pequeño.</p>
   <div id="perr" class="notice err hidden" role="alert"></div>
   <div class="row" style="margin-top:14px">${CM.profile?'<button class="btn ghost" data-act="prof-cancel">Cancelar</button>':'<span></span>'}<button class="btn" data-act="prof-save">Guardar y entrar a la comunidad</button></div></div></div>`;
  $('#avfile').addEventListener('change',onAvatarFile);$('#alias').addEventListener('input',e=>CM.draft.alias=e.target.value);
}
ACT.avpick=el=>{CM.draft.alias=$('#alias').value;CM.draft.avatar=el.dataset.k;drawProfile()};
ACT['prof-cancel']=()=>{CM.editing=false;CM.draft={...CM.profile};communityPage()};
ACT['prof-save']=async el=>{CM.draft.alias=$('#alias').value.trim();el.disabled=true;
  try{CM.profile=await api('/api/community/profile',{method:'PUT',body:JSON.stringify(CM.draft)});me.alias=CM.profile.alias;me.avatar=CM.profile.avatar;CM.editing=false;toast('Perfil guardado');await communityPage()}
  catch(e){const b=$('#perr');b.textContent=e.message;b.classList.remove('hidden');el.disabled=false}};
function onAvatarFile(e){
  const f=e.target.files[0];if(!f)return;CM.draft.alias=$('#alias').value;
  const img=new Image(),url=URL.createObjectURL(f);
  img.onload=()=>{
    const s=Math.min(img.width,img.height),sx=(img.width-s)/2,sy=(img.height-s)/2;let size=128,q=.82,out='';
    for(let i=0;i<8;i++){const c=document.createElement('canvas');c.width=c.height=size;const x=c.getContext('2d');x.fillStyle='#fff';x.fillRect(0,0,size,size);x.drawImage(img,sx,sy,s,s,0,0,size,size);
      out=c.toDataURL('image/jpeg',q);if(out.length<36000)break;q-=.1;if(q<.4){q=.7;size=Math.round(size*.8)}}
    URL.revokeObjectURL(url);
    if(out.length>=37000){toast('La imagen es muy pesada; prueba con otra');return}
    CM.draft.avatar=out;drawProfile()};
  img.onerror=()=>{URL.revokeObjectURL(url);toast('No pude leer esa imagen')};img.src=url;
}
const crisisCard=()=>`<div class="helpcard"><h3>Estamos contigo 💜</h3><p>Lo que escribiste suena muy duro. No tienes que atravesarlo solo/a: hay personas que pueden escucharte ahora mismo.</p><div class="res">${helpLinks()}</div></div>`;
function drawForum(){
  const p=CM.profile;
  $('#main').innerHTML=`<div class="pagehead"><div class="row"><div><h1>Comunidad</h1><p>Un espacio entre estudiantes para compartir, preguntar y apoyarse. Todo es anónimo.</p></div>
    ${canPost()?`<div class="inline">${kav(p.avatar,40)}<b>${esc(p.alias)}</b><button class="btn ghost sm" data-act="prof-edit">Editar perfil</button></div>`:''}</div></div>
  <div class="rules"><b>Para cuidarnos:</b> sé amable, no compartas datos personales (nombres, teléfonos, direcciones) y no publiques contenido que dañe a otras personas. ${me.role==='student'?'Psicología puede moderar publicaciones.':'Puedes ocultar publicaciones que incumplan las normas.'}</div>
  <div class="card"><div class="inline"><input class="input" id="cq" type="search" value="${esc(CM.q)}" placeholder="Buscar en la comunidad (ej.: dormir, exámenes, ansiedad)" aria-label="Buscar publicaciones">
    ${canPost()?'<button class="btn" data-act="post-new">+ Nueva publicación</button>':''}</div>
    <div class="cats" role="group" aria-label="Categorías"><button class="${CM.cat===''?'on':''}" data-act="cat" data-c="">Todo</button>${CM.cats.map(c=>`<button class="${CM.cat===c?'on':''}" data-act="cat" data-c="${esc(c)}">${esc(c)}</button>`).join('')}</div>
    <div id="plist">${postsHtml()}</div></div>`;
  $('#cq').addEventListener('input',e=>{CM.q=e.target.value;clearTimeout(CM.timer);CM.timer=setTimeout(async()=>{try{const r=await api(`/api/community/posts?q=${encodeURIComponent(CM.q)}&category=${encodeURIComponent(CM.cat)}`);CM.posts=r.posts;$('#plist').innerHTML=postsHtml()}catch{}},300)});
}
const postsHtml=()=>CM.posts.length?CM.posts.map(p=>`<button class="post" data-act="post-open" data-id="${p.id}"><div class="meta">${kav(p.avatar,30)}<b>${esc(p.alias)}</b>${p.mine?'<span class="mineb">tú</span>':''}<span class="pill none">${esc(p.category)}</span><span>${esc(fDate(p.created_at))}</span></div><h3>${esc(p.title)}</h3><p>${esc(p.excerpt)}${p.excerpt.length>=180?'…':''}</p><div class="foot">💬 ${p.comments} ${p.comments===1?'comentario':'comentarios'}</div></button>`).join('')
  :`<div class="empty">${CM.q||CM.cat?'No encontré publicaciones con ese filtro.':'Aún no hay publicaciones. ¡Anímate a escribir la primera!'}</div>`;
ACT['prof-edit']=()=>{CM.editing=true;CM.draft={...CM.profile};communityPage()};
ACT.cat=async el=>{CM.cat=el.dataset.c;await communityPage()};
ACT['post-open']=el=>go('post',+el.dataset.id);
ACT['post-new']=()=>openModal({title:'Nueva publicación',cls:'sm',html:`<form id="pform"><div class="field" style="margin-top:0"><label for="pc">Categoría</label><select id="pc">${CM.cats.map(c=>`<option>${esc(c)}</option>`).join('')}</select></div>
  <div class="field"><label for="pt">Título</label><input id="pt" required minlength="3" maxlength="100" placeholder="Ej.: ¿Cómo organizan sus semanas de parciales?"></div>
  <div class="field"><label for="pb">Cuéntanos</label><textarea id="pb" required minlength="5" maxlength="2000" rows="6" placeholder="Escribe con confianza. Recuerda no incluir datos que te identifiquen."></textarea></div><div id="perr2" class="notice err hidden" role="alert"></div></form>`,
  footer:'<button class="btn ghost" data-act="modal-close">Cancelar</button><button class="btn" data-act="post-save">Publicar</button>'});
ACT['post-save']=async el=>{const f=$('#pform');if(!f.reportValidity())return;el.disabled=true;
  try{const r=await api('/api/community/posts',{method:'POST',body:JSON.stringify({category:$('#pc').value,title:$('#pt').value.trim(),body:$('#pb').value.trim()})});
    closeModal();toast('Publicado');if(r.support){await communityPage();$('#main').insertAdjacentHTML('afterbegin',crisisCard())}else go('post',r.id)}
  catch(e){const b=$('#perr2');b.textContent=e.message;b.classList.remove('hidden');el.disabled=false}};
let PD=null;
async function postPage(){
  PD=await api('/api/community/posts/'+arg);drawPost();
}
function drawPost(extra=''){
  const p=PD,mod=me.role!=='student';
  $('#main').innerHTML=`<button class="back" data-act="go" data-tab="community">‹ Volver a la comunidad</button>${extra}
  <div class="card"><div class="meta" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:8px">${kav(p.avatar,44)}<div><b>${esc(p.alias)}</b>${p.mine?' <span class="mineb">tú</span>':''}<div class="muted small">${esc(fDT(p.created_at))}</div></div><span class="pill none">${esc(p.category)}</span>
    ${(p.mine||mod)?`<button class="btn ghost sm" style="margin-left:auto" data-act="post-del" data-id="${p.id}">${mod&&!p.mine?'Ocultar':'Eliminar'}</button>`:''}</div>
    <h2 style="margin:6px 0 10px">${esc(p.title)}</h2><div class="postbody">${esc(p.body)}</div></div>
  <div class="card"><h3>${p.comments.length} ${p.comments.length===1?'comentario':'comentarios'}</h3>
    ${p.comments.map(c=>`<div class="cmt">${kav(c.avatar,36)}<div class="bub2"><div class="meta"><b>${esc(c.alias)}</b>${c.mine?' <span class="mineb">tú</span>':''} · ${esc(fDT(c.created_at))}${(c.mine||mod)?` · <button class="linkb" style="font-weight:600" data-act="cmt-del" data-id="${c.id}">${mod&&!c.mine?'ocultar':'eliminar'}</button>`:''}</div>${esc(c.body)}</div></div>`).join('')||'<p class="muted">Sé la primera persona en responder con cariño.</p>'}
    ${canPost()?`<div class="field" style="margin-bottom:0"><label for="cb">Tu comentario</label><textarea class="input" id="cb" rows="3" maxlength="1000" placeholder="Escribe algo amable y útil…"></textarea></div><div id="cerr" class="notice err hidden" role="alert"></div><div style="margin-top:10px"><button class="btn" data-act="cmt-save">Comentar</button></div>`:''}</div>`;
}
ACT['cmt-save']=async el=>{const t=$('#cb').value.trim();if(t.length<2)return;el.disabled=true;
  try{const r=await api(`/api/community/posts/${PD.id}/comments`,{method:'POST',body:JSON.stringify({body:t})});PD=await api('/api/community/posts/'+PD.id);drawPost(r.support?crisisCard():'')}
  catch(e){const b=$('#cerr');b.textContent=e.message;b.classList.remove('hidden');el.disabled=false}};
ACT['post-del']=async el=>{if(el.dataset.sure!=='1'){el.dataset.sure='1';el.textContent='¿Seguro?';return}
  try{await api('/api/community/posts/'+el.dataset.id,{method:'DELETE'});toast('Publicación retirada');go('community')}catch(e){toast(e.message)}};
ACT['cmt-del']=async el=>{try{await api('/api/community/comments/'+el.dataset.id,{method:'DELETE'});PD=await api('/api/community/posts/'+PD.id);drawPost()}catch(e){toast(e.message)}};

/* =====================================================================
   PANEL DE PSICOLOGÍA (extras)
   ===================================================================== */
function mindiAlertsCard(d){
  if(!d.mindi_alerts?.length)return '';
  return `<div class="card"><h2>Señales de Mindi</h2><p class="muted small" style="margin-bottom:6px">Mindi detectó posible decaimiento por tendencia, sueño, carga de agenda o fechas cercanas. Son pistas, no diagnósticos.</p>
   ${d.mindi_alerts.map(a=>`<button class="malert ${a.level}" data-act="open" data-id="${a.student_id}"><span>${a.level==='alert'?'💗':'🌱'}</span><span><b>${esc(a.name)}${a.ciclo?' · Ciclo '+a.ciclo:''}</b>${a.texts.map(esc).join(' · ')}</span></button>`).join('')}</div>`;
}
const _dd=drawDetail;
drawDetail=function(){
  _dd();
  const D=P.D;if(!D||tab!=='student')return;const pg=D.progress||{},sc=D.schedule||{};
  const dir={mejora:'Mejora respecto al primer registro',empeora:'Empeora respecto al primer registro',estable:'Se mantiene estable','sin datos':'Aún sin suficientes registros'}[pg.direction]||'';
  const html=`<div class="detail" style="margin-top:0"><div>
   <div class="card"><h2>Progreso</h2><div class="prog"><span>${pg.n||0} encuesta${pg.n===1?'':'s'}</span>${pg.first?`<span class="pill none">${esc(pg.first)}</span><span class="arrow">→</span><span class="pill none">${esc(pg.last)}</span>`:''}</div>
     <p class="muted small" style="margin-top:8px">${esc(dir)}.</p></div>
   <div class="card"><h2>Señales de Mindi</h2>${D.signals?.length?D.signals.map(x=>`<div class="sig ${x.level}" style="margin:6px 0"><b>${x.level==='alert'?'💗':x.level==='info'?'💡':'🌱'}</b><span>${esc(x.text)}</span></div>`).join(''):'<p class="muted">Sin señales relevantes ahora.</p>'}
     ${sc.has_events?`<p class="muted small" style="margin-top:10px">Agenda de la próxima semana (solo cifras): promedio ${sc.busy_avg_h} h/día ocupadas, máximo ${sc.busy_max_h} h, ${sc.days_without_rest} día(s) sin descanso programado.</p>`:'<p class="muted small" style="margin-top:10px">No ha usado el calendario todavía.</p>'}</div>
  </div><div><div class="card"><h2>Informes breves</h2><p class="muted small" style="margin-bottom:6px">Generados por Mindi tras cada chequeo profundo. No incluyen la conversación del chat.</p>
   ${D.reports?.length?D.reports.map(r=>`<div class="rep"><div class="h"><span class="pill ${['Sin estrés','Eustrés','Angustia'].indexOf(r.label)===2?'c2':['Sin estrés','Eustrés','Angustia'].indexOf(r.label)===1?'c1':'c0'}">${esc(r.label)}</span><span>${esc(fDT(r.created_at))}</span><span>${r.source==='gemini'?'Gemini':'Reglas'}</span></div><p>${esc(r.psych_report)}</p>
     <details><summary>Respuestas del chequeo</summary>${r.qa.map(q=>`<div style="margin:6px 0"><span class="muted small">${esc(q.question)}</span><br><b>${esc(q.answer)}</b></div>`).join('')}</details></div>`).join(''):'<p class="muted" style="padding:8px 0">Aún no hay informes breves.</p>'}</div></div></div>`;
  $('#main').insertAdjacentHTML('beforeend',html);
};

/* ---------- arranque ---------- */
fetch('/health').then(r=>r.json()).then(h=>{if(h.show_demo===false){const d=$('#demohint');if(d)d.remove()}}).catch(()=>{});
init();
