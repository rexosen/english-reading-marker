/* Offline state and operations are persisted together before network requests. */
'use strict';
const $=id=>document.getElementById(id),esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function uuid(){const bytes=new Uint8Array(16);crypto.getRandomValues(bytes);return Array.from(bytes,x=>x.toString(16).padStart(2,'0')).join('');}
let state;
try{state=JSON.parse(localStorage.getItem('reader-v1')||'null');}catch(error){alert('本地数据无法读取，请保留 App 数据并联系修复。');throw error;}
if(!state)state={client_id:uuid(),instance:null,articles:[],outbox:[],conflicts:[],errors:[],config:{url:'',token:''},translations:{}};
if(!state.study)state.study={};
if(!Array.isArray(state.vocabulary_manual))state.vocabulary_manual=[];
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
 state.outbox.push(op);SyncCore.apply(state.articles,op,state.study,state.vocabulary_manual);
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
  const batch=operationBatch();
  const response=await nativeCall('sync',{url:state.config.url,token:state.config.token,body:{client_id:state.client_id,instance:state.instance,revision:batch.length?null:(state.revision??null),operations:SyncCore.clone(batch)}});
  if(response.unchanged){
   if(typeof response.revision==='number')state.revision=response.revision;
   lastError='';lastSync=new Date().toLocaleTimeString('zh-CN',{hour12:false,hour:'2-digit',minute:'2-digit',second:'2-digit'});
   if(manual)toast(state.conflicts.length?'已同步，请在连接页面处理名称冲突':'已是最新');
   return;
  }
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
 $('main').innerHTML='<h2 id="readingTitle"></h2><div class="readControls"><div class="actions"><button id="speakAll" class="small">▶ 全文朗读</button><button id="pauseSpeech" class="small">暂停 / 继续</button><button id="stopSpeech" class="small">停止</button><button id="quickSpeed" class="small"></button></div><div class="muted">点单词查义；长按拖选句段，再点下方“翻译”。</div></div><div id="sentenceControls"></div><article id="readingArea"></article>';
 const refreshQuickSpeed=()=>{if($('quickSpeed'))$('quickSpeed').textContent='🔊 '+state.audio.speed+' 倍速';};
 refreshQuickSpeed();
 $('quickSpeed').onclick=()=>{
  const next=Math.abs(Number(state.audio.speed)-0.75)<1e-6?1:0.75;
  state.audio={...state.audio,speed:next};save();refreshQuickSpeed();toast('已切换 '+next+' 倍速（点顶部“发音”可改口音与其他倍速）');
 };
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
 const phrase=selected.word.trim();
 // 与桌面端一致：单词和短词组都能记，长句留给翻译与朗读。
 if(!/^[A-Za-z][A-Za-z'’.\- ]*$/.test(phrase)||phrase.split(/\s+/).length>6){toast('生词本可记单词或最多 6 个词的词组；更长的句段请翻译或朗读');return;}
 if(!currentDefinition){openLookup();toast('查询到释义后，再点击加入生词本');return;}
 const a=state.articles.find(a=>a.id===selected.article_id),chars=Array.from(a.text);
 const context=chars.slice(Math.max(0,selected.start-70),Math.min(chars.length,selected.end+120)).join('');
 enqueue('vocabulary',{...selected,definition:currentDefinition,context});toast('已加入生词本');sync();
}
function speak(text){stopSequence();if(text)nativeCall('speak',{text,...state.audio}).catch(error=>toast(error.message));}
let vocabularyGroup='all',vocabularyQuery='';
function vocabularyCounts(){
 const words=allWords(),tally=new Map();
 words.forEach(w=>tally.set(w.category,(tally.get(w.category)||0)+1));
 return tally;
}
function filteredVocabularyWords(){
 const words=allWords(),q=vocabularyQuery.trim().toLowerCase();
 return words.filter(w=>{
  if(vocabularyGroup!=='all'&&w.category!==vocabularyGroup)return false;
  if(!q)return true;
  return [w.word,w.definition,w.context,w.article_title].join(' ').toLowerCase().includes(q);
 });
}
function renderVocabulary(){
 const words=allWords(),tally=vocabularyCounts();
 if(vocabularyGroup!=='all'&&vocabularyGroup!==''&&!vocabCategories().some(g=>g.key===vocabularyGroup))vocabularyGroup='all';
 const chips=[{key:'all',name:'全部'}].concat(vocabCategories()).concat([{key:'',name:'未分类'}])
  .map(g=>({key:g.key,name:g.name||'未分类',count:g.key==='all'?words.length:(g.key===''?words.filter(w=>!w.category).length:(tally.get(g.key)||0))}));
 $('main').innerHTML='<div class="row actions"><h2 class="grow">生词本 · '+words.length+'</h2><button id="reviewWords">复习卡片</button><button id="exportWords">导出 CSV</button></div>'
  +'<div class="actions"><button id="addPhrase" class="primary">＋ 加入词组</button><button id="manageVocabGroups">分类管理</button></div>'
  +'<input id="vocabSearch" placeholder="搜索单词、释义、例句或文章">'
  +'<div class="tabs">'+chips.map(g=>'<button data-vocab-group="'+esc(g.key)+'"'+(String(vocabularyGroup)===String(g.key)?' class="active"':'')+'>'+esc(g.name)+' '+g.count+'</button>').join('')+'</div>'
  +'<div id="vocabCards"></div>'
  +'<p class="muted">点卡片任意位置就朗读；✎ 是自己录入的词组，可编辑。标题以“听力:/阅读:”开头的文章里的生词自动进这两类，手动分类优先。删除会与电脑同步。</p>';
 $('vocabSearch').value=vocabularyQuery;
 function renderCards(){
  const visible=filteredVocabularyWords();
  const card=(w,index)=>'<section class="card" data-speak-row="'+index+'"><div class="row"><div class="title grow">'+(w.manual?'✎ ':'')+esc(w.word)+'</div>'+(w.category?'<span class="muted">'+esc(vocabCategoryName(w.category))+'</span>':'')+'</div>'
   +'<div style="white-space:pre-wrap;line-height:1.7">'+esc(w.definition||'暂无释义')+'</div>'
   +'<p class="muted">'+esc(w.article_title||'自建词条（自己录入的单词或词组）')+(w.context?'<br>'+esc(w.context):'')+'</p>'
   +'<div class="actions"><button class="small" data-speak="'+index+'">▶ 朗读</button><button class="small" data-group="'+index+'">分类</button>'
   +(w.manual?'<button class="small" data-edit="'+index+'">编辑</button>':'')+'<button class="small" data-delete="'+index+'">删除</button></div></section>';
  $('vocabCards').innerHTML=visible.length?visible.map((w,index)=>card(w,index)).join(''):'<div class="empty">'+(words.length?'当前筛选或搜索下没有生词，试试清空搜索或点“全部”。':'阅读时点单词查义即可加入生词本，也可以点“＋ 加入词组”自己写词组、释义和例句。')+'</div>';
  document.querySelectorAll('[data-speak-row]').forEach(row=>row.onclick=event=>{
   if(event.target.closest('button'))return;
   speak(visible[+row.dataset.speakRow].word);
  });
  document.querySelectorAll('[data-speak]').forEach(button=>button.onclick=()=>speak(visible[+button.dataset.speak].word));
  document.querySelectorAll('[data-group]').forEach(button=>button.onclick=()=>vocabularyGroupPicker(visible[+button.dataset.group]));
  document.querySelectorAll('[data-edit]').forEach(button=>button.onclick=()=>vocabularyEntryEditor(visible[+button.dataset.edit]));
  document.querySelectorAll('[data-delete]').forEach(button=>button.onclick=()=>deleteVocabularyWord(visible[+button.dataset.delete]));
 }
 $('vocabSearch').oninput=()=>{vocabularyQuery=$('vocabSearch').value;renderCards();};
 document.querySelectorAll('[data-vocab-group]').forEach(button=>button.onclick=()=>{vocabularyGroup=button.dataset.vocabGroup;renderVocabulary();});
 $('addPhrase').onclick=()=>vocabularyEntryEditor(null);
 $('manageVocabGroups').onclick=manageVocabularyGroups;
 $('reviewWords').onclick=()=>{reviewSession=null;navigate('review');};
 $('exportWords').onclick=()=>{
  const visible=filteredVocabularyWords();
  if(!visible.length){toast('当前筛选下没有可导出的生词');return;}
  const quote=x=>'"'+String(x??'').replace(/"/g,'""')+'"';
  const rows=[['单词','中文释义','分类','来源文章','原句'],...visible.map(w=>[w.word,w.definition,vocabCategoryName(w.category),w.article_title||'自建词条',w.context])];
  nativeCall('export',{csv:rows.map(row=>row.map(quote).join(',')).join('\r\n')}).catch(error=>toast(error.message));
 };
 renderCards();
}
function deleteVocabularyWord(word){
 const label=SyncCore.normalizeWord(word.word);
 if(!confirm('从生词本删除“'+label+'”？\n\n只删生词记录，文章里的划线保留；同步后电脑上也会删掉。'))return;
 if(word.manual)enqueue('vocabulary_manual_remove',{word:label});
 else enqueue('vocabulary_remove',{article_id:word.article_id,start:word.start,end:word.end,word:label});
 sync();renderVocabulary();toast('已删除，联网后与电脑同步');
}
function vocabularyGroupPicker(word){
 const overlay=document.createElement('div');overlay.className='overlay';
 const current=vocabCategoryOf(word.word,word.manual?null:state.articles.find(a=>a.id===word.article_id));
 overlay.innerHTML='<section class="sheet"><h3>'+esc(word.word)+'</h3><label>分类</label><select id="vocabPick"><option value="">自动（按文章标题）</option>'
  +vocabCategories().map(g=>'<option value="'+esc(g.key)+'">'+esc(g.name)+'</option>').join('')
  +'<option value="__new">＋ 新建分类…</option></select><div class="actions"><button id="vocabPickSave" class="primary">保存</button><button id="vocabPickClose">关闭</button></div></section>';
 document.body.appendChild(overlay);$('vocabPick').value=current||'';
 $('vocabPickSave').onclick=()=>{
  let key=$('vocabPick').value;
  if(key==='__new'){overlay.remove();key=vocabCreateCategory(prompt('新分类名称（最多60字）')||'');if(!key){renderVocabulary();return;}}
  vocabAssign(word.word,key);overlay.remove();renderVocabulary();toast(key?'已归入“'+vocabCategoryName(key)+'”':'已恢复按文章自动分类');
 };
 $('vocabPickClose').onclick=()=>{overlay.remove();renderVocabulary();};
 overlay.onclick=event=>{if(event.target===overlay)$('vocabPickClose').onclick();};
}
function vocabularyEntryEditor(word){
 const editing=!!word;
 const overlay=document.createElement('div');overlay.className='overlay';
 overlay.innerHTML='<section class="sheet"><h3>'+(editing?'编辑词条':'加入单词或词组')+'</h3><label>单词或词组</label><input id="entryWord" placeholder="例如：in demand、take over" value="'+esc(word?word.word:'')+'">'
  +'<label>中文释义</label><textarea id="entryDefinition" placeholder="写你自己记得住的说法">'+esc(word?word.definition:'')+'</textarea>'
  +'<label>例句或用法（可选）</label><textarea id="entryContext">'+esc(word?word.context:'')+'</textarea>'
  +'<label>分类</label><select id="entryGroup"><option value="">自动（按文章标题）</option>'+vocabCategories().map(g=>'<option value="'+esc(g.key)+'">'+esc(g.name)+'</option>').join('')+'</select>'
  +'<div class="actions"><button id="entrySave" class="primary">保存</button><button id="entryClose">取消</button></div>'
  +'<p class="muted">词组可以写多个单词；保存后点卡片即可朗读，同步后电脑生词本里也会出现（前面带 ✎）。</p></section>';
 document.body.appendChild(overlay);
 if(editing&&word.category)$('entryGroup').value=word.category;
 $('entrySave').onclick=()=>{
  const clean=SyncCore.normalizeWord($('entryWord').value);
  if(!clean){toast('请先写单词或词组');return;}
  if(Array.from(clean).length>200){toast('词条太长（最多200字）');return;}
  const definition=$('entryDefinition').value.trim(),context=$('entryContext').value.trim(),group=$('entryGroup').value;
  if(editing){
   const renamed=!SyncCore.sameWord(word.word,clean);
   if(renamed&&allWords().some(existing=>existing.manual&&!SyncCore.sameWord(existing.word,word.word)&&SyncCore.sameWord(existing.word,clean))){toast('“'+clean+'”已经在生词本里了');return;}
   enqueue('vocabulary_manual',renamed?{word:clean,old_word:word.word,definition,context}:{word:clean,definition,context});
   // 分类记录按写法编号，改名时要一起搬过去
   if(renamed){vocabAssign(word.word,'');if(group)vocabAssign(clean,group);}
   else if(group!==(word.category||''))vocabAssign(clean,group);
  }else{
   if(allWords().some(existing=>SyncCore.sameWord(existing.word,clean))){toast('“'+clean+'”已经在生词本里了');return;}
   enqueue('vocabulary_manual',{word:clean,definition,context});
   if(group)vocabAssign(clean,group);
  }
  overlay.remove();sync();renderVocabulary();toast('已保存，点词条即可朗读');
 };
 $('entryClose').onclick=()=>{overlay.remove();renderVocabulary();};
 overlay.onclick=event=>{if(event.target===overlay)$('entryClose').onclick();};
}
function manageVocabularyGroups(){
 const overlay=document.createElement('div');overlay.className='overlay';
 function refresh(){
  overlay.innerHTML='<section class="sheet"><h3>生词分类</h3><div class="muted">“听力”“阅读”按文章标题自动生成，不能改名或删除。</div><div id="vocabGroupList">'
   +vocabCategories().map(g=>'<div class="row actions"><span class="grow">'+esc(g.name)+(VOCAB_AUTO_NAMES[g.key]?'（内置）':'')+'</span>'
    +(VOCAB_AUTO_NAMES[g.key]?'':'<button data-rename-vgroup="'+esc(g.key)+'">改名</button><button data-delete-vgroup="'+esc(g.key)+'">删除</button>')+'</div>').join('')
   +'</div><div class="actions"><button id="addVocabGroup" class="primary">新建分类</button><button id="closeVocabGroups">完成</button></div></section>';
  $('addVocabGroup').onclick=()=>{const name=prompt('分类名称（最多60字）');if(name===null)return;const key=vocabCreateCategory(name);if(key)refresh();};
  $('closeVocabGroups').onclick=()=>{overlay.remove();renderVocabulary();};
  overlay.querySelectorAll('[data-rename-vgroup]').forEach(button=>button.onclick=()=>{
   const key=button.dataset.renameVgroup,name=prompt('分类名称',vocabCategoryName(key));
   if(name===null)return;const clean=SyncCore.normalizeWord(name);
   if(!clean||Array.from(clean).length>60){toast('请输入1–60字的分类名称');return;}
   const clash=vocabCategories().find(g=>g.key!==key&&g.name.toLowerCase()===clean.toLowerCase());
   if(clash){toast('已存在同名分类');return;}
   studySet(key,{name:clean});refresh();
  });
  overlay.querySelectorAll('[data-delete-vgroup]').forEach(button=>button.onclick=()=>{
   if(confirm('删除分类后，里面的生词按文章标题重新自动归类。继续？')){if(vocabDeleteCategory(button.dataset.deleteVgroup))refresh();}
  });
 }
 document.body.appendChild(overlay);refresh();
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
window.handleBack=()=>{
 const dynamicOverlays=Array.from(document.querySelectorAll('.overlay')).filter(el=>el.id!=='audioOverlay'&&el.id!=='lookupOverlay'&&!el.hidden);
 if(dynamicOverlays.length){
  const top=dynamicOverlays[dynamicOverlays.length-1];
  const closer=top.querySelector('#dictationClose,#closeOptions,#closeGroups,#closeVocabGroups,#vocabPickClose,#entryClose');
  if(closer)closer.click();else top.remove();
  return;
 }
 if(!$('audioOverlay').hidden){$('audioOverlay').hidden=true;return;}
 if(!$('lookupOverlay').hidden){$('closeLookup').click();return;}
 if(page==='read'||page==='paste')navigate('articles');else if(page!=='articles')navigate('articles');else toast('按系统主页键可返回桌面');
};
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
