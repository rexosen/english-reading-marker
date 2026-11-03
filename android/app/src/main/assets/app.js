/* Offline state and operations are persisted together before network requests. */
'use strict';
const $=id=>document.getElementById(id),esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function uuid(){const bytes=new Uint8Array(16);crypto.getRandomValues(bytes);return Array.from(bytes,x=>x.toString(16).padStart(2,'0')).join('');}
let state;
try{state=JSON.parse(localStorage.getItem('reader-v1')||'null');}catch(error){alert('本地数据无法读取，请保留 App 数据并联系修复。');throw error;}
if(!state)state={client_id:uuid(),instance:null,articles:[],outbox:[],conflicts:[],errors:[],config:{url:'',token:''},translations:{}};
if(!state.study)state.study={};
if(!state.display)state.display={size:21,line:1.75,width:780,margin:18,theme:'paper',image:'',opacity:22};
if(!state.audio)state.audio={accent:'us',speed:0.75,source:'dictionary'};
let page='articles',activeId=null,selected=null,currentDefinition='',lookupSequence=0,busy=false,lastSync='',lastError='',restoring=false;
const callbacks=new Map();
function nativeCall(action,body){return new Promise((resolve,reject)=>{
 const id=uuid(),timer=setTimeout(()=>{callbacks.delete(id);reject(Error('操作超时，修改仍保存在本机'));},90000);
 callbacks.set(id,{resolve,reject,timer});
 if(window.ReaderNative)ReaderNative.send(id,action,JSON.stringify(body));
 else{clearTimeout(timer);callbacks.delete(id);reject(Error('请使用安卓安装包打开'));}
});}
window.nativeReply=(id,result)=>{const cb=callbacks.get(id);if(!cb)return;clearTimeout(cb.timer);callbacks.delete(id);result.error?cb.reject(Error(result.error)):cb.resolve(result);};
let toastTimer;
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,4000);}
window.nativeNotice=toast;
function save(){try{localStorage.setItem('reader-v1',JSON.stringify(state));}catch(error){toast('本机存储空间不足，请先导出生词并释放空间');throw error;}}
function article(){return state.articles.find(a=>a.id===activeId);}
function enqueue(type,fields){
 const before=SyncCore.clone(state),op={id:uuid(),type,...fields};
 // Only coalesce unsent progress. An in-flight request can still acknowledge its own ID.
 if(type==='progress')state.outbox=state.outbox.filter(x=>!(x.type==='progress'&&x.article_id===op.article_id));
 state.outbox.push(op);SyncCore.apply(state.articles,op,state.study);
 try{save();}catch(error){state=before;throw error;}
 updateStatus();return op;
}
function updateStatus(){
 let message=state.config.token?(busy?'正在同步…':lastError?'暂未连接 · 修改已保存在本机':lastSync?'已同步 '+lastSync:'已配对 · 等待同步'):'本机保存 · 尚未连接电脑';
 if(state.outbox.length)message+=' · '+state.outbox.length+' 项待同步';
 if(state.conflicts.length)message+=' · 有名称冲突';
 $('syncStatus').textContent=message;
}
function operationBatch(){let bytes=0;return state.outbox.slice(0,500).filter(op=>{bytes+=new TextEncoder().encode(JSON.stringify(op)).length;return bytes<1400000;});}
async function sync(manual=false){
 if(busy)return;
 if(!state.config.token){if(manual){navigate('connect');toast('先连接电脑，再开始同步');}return;}
 busy=true;updateStatus();
 try{
  const response=await nativeCall('sync',{url:state.config.url,token:state.config.token,body:{client_id:state.client_id,instance:state.instance,operations:SyncCore.clone(operationBatch())}});
  // Merge against the current state, including edits made during the request.
  const previous=state;state=SyncCore.merge(state,response);
  try{save();}catch(error){state=previous;throw error;}
  lastError='';lastSync=new Date().toLocaleTimeString('zh-CN',{hour12:false,hour:'2-digit',minute:'2-digit',second:'2-digit'});
  if(page==='read')updateReader();else if(!['connect','paste','review','noteEdit','settings','backups','notes'].includes(page)&&!document.activeElement?.matches('input,textarea,select'))render();else if(manual&&page==='connect')render();else if(page==='connect')renderConflicts();
  if(manual)toast(state.conflicts.length?'已同步，请在连接页面处理名称冲突':'同步完成');
 }catch(error){lastError=error.message;if(manual)toast(error.message+'；请检查电脑服务、Wi-Fi 和防火墙允许项');}
 finally{busy=false;updateStatus();}
}
function navigate(next,id=null){
 if(page==='noteEdit'&&next!=='noteEdit'&&noteDraft?._dirty&&!confirm('放弃尚未保存的笔记修改？'))return;
 if(page==='read')rememberProgress();
 stopSequence();nativeCall('stop',{}).catch(()=>{});
 page=next;if(id)activeId=id;selected=null;lookupSequence++;
 $('selectionBar').hidden=true;$('lookupOverlay').hidden=true;window.getSelection()?.removeAllRanges();
 render();window.scrollTo(0,0);
 if(page==='read')setTimeout(restoreProgress,100);
}
function render(){
 document.querySelectorAll('.tabs [data-page]').forEach(button=>button.classList.toggle('active',button.dataset.page===page||(page==='read'&&button.dataset.page==='articles')));
 if(page==='articles')renderArticles();
 if(page==='read')renderReader();
 if(page==='vocabulary')renderVocabulary();
 if(page==='connect')renderConnect();
 if(page==='paste')renderPaste();
 if(page==='review')renderReview();
 if(page==='notes')renderNotes();
 if(page==='noteEdit')renderNoteEditor();
 if(page==='settings')renderDisplaySettings();
 if(page==='backups')renderBackups();
 updateStatus();
}
function renderArticles(){renderLearningLibrary();}
function rename(id){
 const a=state.articles.find(a=>a.id===id);const title=prompt('文章新名称',a.title);if(title===null)return;
 if(!title.trim()||title.trim().length>200){toast('名称应为 1–200 个字符');return;}
 enqueue('rename',{article_id:id,title:title.trim(),base_version:a.title_version});render();sync();
}
function renderPaste(){
 $('main').innerHTML='<h2>添加文章</h2><label>文章名称</label><input id="newTitle" maxlength="200" placeholder="输入标题"><label>英文正文</label><textarea id="newBody" placeholder="粘贴 ChatGPT 转换后的文章"></textarea><div class="actions"><button class="primary" id="saveArticle">保存到本机</button><button id="cancelPaste">取消</button></div>';
 $('cancelPaste').onclick=()=>navigate('articles');
 $('saveArticle').onclick=()=>{
  const title=$('newTitle').value.trim(),text=$('newBody').value.replace(/\r\n?/g,'\n').trim();
  if(!title||!text){toast('请填写文章名称和正文');return;}if(text.length>200000){toast('文章过长，请拆分后导入');return;}
  const id='mobile:'+uuid();enqueue('create',{article_id:id,title,text});navigate('read',id);sync();
 };
}
function renderReader(){
 const a=article();if(!a){navigate('articles');return;}
 $('main').innerHTML='<h2 id="readingTitle"></h2><div class="readControls"><div class="actions"><button id="speakAll" class="small">▶ 全文朗读</button><button id="pauseSpeech" class="small">暂停 / 继续</button><button id="stopSpeech" class="small">停止</button></div><div class="muted">点单词查义；长按拖选句段，再点下方“翻译”。</div></div><div id="sentenceControls"></div><article id="readingArea"></article>';
 $('readingTitle').textContent=a.title;
 const pattern=/[A-Za-z]+(?:['’\-][A-Za-z]+)*/g;let html='',last=0,match;
 while((match=pattern.exec(a.text))){
  html+=esc(a.text.slice(last,match.index));const start=Array.from(a.text.slice(0,match.index)).length,end=start+Array.from(match[0]).length;
  html+='<span class="token" data-start="'+start+'" data-end="'+end+'">'+esc(match[0])+'</span>';last=match.index+match[0].length;
 }
 html+=esc(a.text.slice(last));$('readingArea').innerHTML=html;updateReader();installSentenceControls();applyReaderDisplay();
 $('readingArea').onclick=event=>{
  if(window.getSelection()?.toString().trim())return;
  const target=event.target.closest('.token');if(!target)return;
  selected={article_id:a.id,start:+target.dataset.start,end:+target.dataset.end,word:target.textContent};openLookup();
 };
 $('speakAll').onclick=()=>speak(a.text);$('pauseSpeech').onclick=pauseLearningSpeech;$('stopSpeech').onclick=stopLearningSpeech;
}
function updateReader(){
 const a=article();if(!a||!$('readingArea'))return;$('readingTitle').textContent=a.title;
 document.querySelectorAll('#readingArea .token').forEach(token=>{
  token.classList.toggle('marked',a.annotations.some(x=>x.start<+token.dataset.end&&x.end>+token.dataset.start));
 });
}
function selectRange(){
 if(page!=='read'||!$('lookupOverlay').hidden)return;
 const selection=window.getSelection(),body=$('readingArea');
 if(!selection||!selection.rangeCount||selection.isCollapsed||!body.contains(selection.anchorNode)||!body.contains(selection.focusNode)){$('selectionBar').hidden=true;return;}
 const range=selection.getRangeAt(0),prefix=range.cloneRange();prefix.selectNodeContents(body);prefix.setEnd(range.startContainer,range.startOffset);
 let raw=range.toString(),start=Array.from(prefix.toString()).length;
 const leading=raw.match(/^\s*/)[0];start+=Array.from(leading).length;raw=raw.trim();
 if(!raw)return;
 selected={article_id:activeId,start,end:start+Array.from(raw).length,word:raw};currentDefinition='';$('selectionBar').hidden=false;
}
document.addEventListener('selectionchange',()=>setTimeout(selectRange,40));
async function openLookup(){
 if(!selected)return;const selection={...selected},sequence=++lookupSequence;
 currentDefinition='';$('lookupOverlay').hidden=false;$('selectionBar').hidden=true;
 $('lookupTitle').textContent=selection.word.length>120?selection.word.slice(0,120)+'…':selection.word;
 $('lookupDefinition').textContent='正在查询…';
 if(Object.prototype.hasOwnProperty.call(state.translations,selection.word)){
  currentDefinition=state.translations[selection.word];$('lookupDefinition').textContent=currentDefinition;return;
 }
 try{
  const result=await nativeCall('translate',{text:selection.word,url:state.config.url,token:state.config.token});
  if(sequence!==lookupSequence)return;
  currentDefinition=result.text;$('lookupDefinition').textContent=currentDefinition;
  state.translations[selection.word]=currentDefinition;
  const keys=Object.keys(state.translations);if(keys.length>500)delete state.translations[keys[0]];save();
 }catch(error){if(sequence===lookupSequence)$('lookupDefinition').textContent='暂时无法翻译：'+error.message+'。本地生词与划线仍可使用。';}
}
function mark(){
 if(!selected)return;const a=state.articles.find(a=>a.id===selected.article_id);
 const active=!a.annotations.some(x=>x.start===selected.start&&x.end===selected.end);
 enqueue('underline',{...selected,active});if(page==='read')updateReader();toast(active?'已标记这处文字':'已取消此处划线');sync();
}
function saveWord(){
 if(!selected)return;
 if(!/^[A-Za-z]+(?:['’\-][A-Za-z]+)*$/.test(selected.word)){toast('生词本请只选一个单词；句段可以翻译和朗读');return;}
 if(!currentDefinition){openLookup();toast('查询到释义后，再点击加入生词本');return;}
 const a=state.articles.find(a=>a.id===selected.article_id),chars=Array.from(a.text);
 const context=chars.slice(Math.max(0,selected.start-70),Math.min(chars.length,selected.end+120)).join('');
 enqueue('vocabulary',{...selected,definition:currentDefinition,context});toast('已加入生词本');sync();
}
function speak(text){stopSequence();if(text)nativeCall('speak',{text,...state.audio}).catch(error=>toast(error.message));}
function renderVocabulary(){
 const words=state.articles.flatMap(a=>a.vocabulary.map(w=>({...w,article_id:a.id,article_title:a.title})));
 $('main').innerHTML='<div class="row actions"><h2 class="grow">生词本 · '+words.length+'</h2><button id="reviewWords">复习卡片</button><button id="exportWords">导出 CSV</button></div>'+(words.length?words.map((w,i)=>'<section class="card"><div class="row"><div class="title grow">'+esc(w.word)+'</div><button class="small pronounce" data-index="'+i+'">▶ 发音</button></div><div style="white-space:pre-wrap;line-height:1.7">'+esc(w.definition)+'</div><p class="muted">'+esc(w.article_title)+'<br>'+esc(w.context)+'</p></section>').join(''):'<div class="empty">阅读时点单词查义，再加入生词本。</div>');
 document.querySelectorAll('.pronounce').forEach(button=>button.onclick=()=>speak(words[+button.dataset.index].word));
 $('reviewWords').onclick=()=>{reviewSession=null;navigate('review');};
 $('exportWords').onclick=()=>{
  if(!words.length){toast('生词本为空');return;}
  const quote=x=>'"'+String(x??'').replace(/"/g,'""')+'"';
  const rows=[['单词','中文释义','来源文章','原句'],...words.map(w=>[w.word,w.definition,w.article_title,w.context])];
  nativeCall('export',{csv:rows.map(row=>row.map(quote).join(',')).join('\r\n')}).catch(error=>toast(error.message));
 };
}
function renderConnect(){
 $('main').innerHTML='<h2>连接电脑</h2><section class="card"><div class="muted">1. 两台设备连接同一个 Wi-Fi / 路由器。<br>2. 电脑点击“手机同步”，开启服务并生成配对码。<br>3. 填写电脑显示的地址和配对码。</div><label>电脑地址</label><input id="serverUrl" type="url" inputmode="url" autocomplete="off" placeholder="http://192.168.1.10:18765"><label>一次性配对码</label><input id="pairCode" type="text" inputmode="numeric" maxlength="6" autocomplete="off" placeholder="6 位数字"><div class="actions"><button id="pairButton" class="primary">配对并同步</button><button id="retrySync">立即同步</button></div><div id="pairMessage" class="muted"></div></section><section class="card muted">'+(state.config.token?'已保存配对信息。':'尚未配对。')+'联网时每 3 秒尝试同步；电脑关机或离开局域网后，修改先留在手机，恢复连接后补传。<br>此版本使用家庭局域网 HTTP 连接，请在可信任的网络中使用。<br>系统英文朗读取决于已安装的英文语音包。</section><div id="conflicts"></div>';
 $('serverUrl').value=state.config.url;
 $('retrySync').onclick=()=>sync(true);
 $('pairButton').onclick=async()=>{
  const url=$('serverUrl').value.trim().replace(/\/$/,''),code=$('pairCode').value.trim();if(!/^\d{6}$/.test(code)){toast('请填写电脑显示的 6 位配对码');return;}
  $('pairButton').disabled=true;$('pairMessage').textContent='正在连接电脑…';
  try{
   const result=await nativeCall('pair',{url,body:{code}});
   if(state.instance&&result.instance!==state.instance)throw Error('这是另一台电脑的资料库。第一版暂不合并不同电脑，已保留手机原有数据');
   state.config={url,token:result.token};save();$('pairMessage').textContent='配对成功，正在同步文章…';await sync(true);
  }catch(error){$('pairMessage').textContent=error.message+'。请检查电脑地址、配对码及网络访问允许项。';}
  finally{if($('pairButton'))$('pairButton').disabled=false;}
 };
 renderConflicts();
}
function renderConflicts(){
 if(!$('conflicts'))return;
 $('conflicts').innerHTML=state.conflicts.map((c,i)=>'<section class="card conflict"><div class="title">文章名称同时被修改</div><p>电脑：'+esc(c.current_title)+'</p><p>手机：'+esc(c.proposed)+'</p><div class="actions"><button data-index="'+i+'" data-choice="computer">保留电脑名称</button><button data-index="'+i+'" data-choice="mobile">使用手机名称</button></div></section>').join('')+(state.errors.length?'<section class="card conflict"><div class="title">有修改未能同步</div><div class="muted">'+state.errors.map(x=>esc(x.error)).join('<br>')+'<br>修改仍保存在手机，请先检查连接或重新同步。</div></section>':'');
 $('conflicts').querySelectorAll('button[data-choice]').forEach(button=>button.onclick=()=>{
  const c=state.conflicts[+button.dataset.index],a=state.articles.find(a=>a.id===c.article_id);
  enqueue('resolve',{article_id:c.article_id,conflict_id:c.id,choice:button.dataset.choice,base_version:a.title_version});sync(true);
 });
}
let scrollTimer;
window.addEventListener('scroll',()=>{if(page==='read'&&!restoring){clearTimeout(scrollTimer);scrollTimer=setTimeout(rememberProgress,700);}},{passive:true});
function rememberProgress(){
 if(page!=='read'||restoring||!$('readingArea'))return;
 const tokens=Array.from(document.querySelectorAll('#readingArea .token'));
 const first=tokens.find(token=>token.getBoundingClientRect().bottom>160);if(!first)return;
 const a=article(),offset=+first.dataset.start;if(a.progress===offset)return;
 enqueue('progress',{article_id:a.id,offset});
}
function restoreProgress(){
 const a=article();if(!a||page!=='read')return;restoring=true;
 const tokens=Array.from(document.querySelectorAll('#readingArea .token'));
 const token=tokens.find(token=>+token.dataset.end>=a.progress);if(token&&a.progress>0)token.scrollIntoView({block:'start'});
 setTimeout(()=>restoring=false,350);
}
window.handleBack=()=>{if(!$('audioOverlay').hidden){$('audioOverlay').hidden=true;return;}if(!$('lookupOverlay').hidden){$('closeLookup').click();return;}if(page==='read'||page==='paste')navigate('articles');else if(page!=='articles')navigate('articles');else toast('按系统主页键可返回桌面');};
document.querySelectorAll('[data-page]').forEach(button=>button.onclick=()=>navigate(button.dataset.page));
$('syncNow').onclick=()=>sync(true);
$('audioSettings').onclick=()=>{
 $('audioSource').value=state.audio.source;$('audioAccent').value=state.audio.accent;$('audioSpeed').value=String(state.audio.speed);$('audioOverlay').hidden=false;
};
$('saveAudioSettings').onclick=()=>{
 state.audio={source:$('audioSource').value,accent:$('audioAccent').value,speed:Number($('audioSpeed').value)};
 save();nativeCall('stop',{}).catch(()=>{});$('audioOverlay').hidden=true;toast('发音设置已保存');
};
$('cancelAudioSettings').onclick=()=>{$('audioOverlay').hidden=true;};
$('audioOverlay').onclick=event=>{if(event.target===$('audioOverlay'))$('audioOverlay').hidden=true;};
$('selectionTranslate').onclick=openLookup;$('selectionSpeak').onclick=()=>speak(selected?.word);$('selectionMark').onclick=mark;$('selectionSave').onclick=saveWord;
$('lookupSpeak').onclick=()=>speak(selected?.word);$('lookupMark').onclick=mark;$('lookupSave').onclick=saveWord;
$('closeLookup').onclick=()=>{$('lookupOverlay').hidden=true;lookupSequence++;window.getSelection()?.removeAllRanges();};
$('lookupOverlay').onclick=event=>{if(event.target===$('lookupOverlay'))$('closeLookup').click();};
setInterval(()=>{if(document.visibilityState==='visible')sync();},3000);
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')sync();else rememberProgress();});
initLearning();save();render();sync();
