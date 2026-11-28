/* Learning features use the same persisted operation queue as article edits. */
'use strict';
let libraryQuery='',libraryGroup='all',reviewSession=null,reviewCategory='all',noteDraft=null;
let sentenceSession=null,sentenceTimeout=null,sentencePaused=false,speechMode='none',speechPaused=false,fullSpeechId=null;
function studySet(key,value,expected=state.study[key]??null){enqueue('study',{key,value,expected:SyncCore.clone(expected)});sync();}
function groups(){return Object.entries(state.study).filter(([key,value])=>key.startsWith('group:')&&value).map(([id,value])=>({id,name:value.name}));}
function metadata(a){return state.study['meta:'+a.id]||{article_id:a.id,group:'',pinned:false,read:false};}
function setMetadata(a,fields){studySet('meta:'+a.id,{...metadata(a),...fields});}
function applyGlobalTheme(themeName){
 if(document.documentElement)document.documentElement.dataset.theme=themeName||'paper';
}
function formatDefHtml(text){
 const lines=String(text||'').split(/\r?\n/);
 return lines.map(raw=>{
  const line=raw.trim();
  if(!line)return '<div style="height:6px"></div>';
  const m=/^([a-z]{1,6}\.|\[网络\])\s*(.+)$/i.exec(line);
  if(m)return '<div style="margin:3px 0"><span class="pos-pill">'+esc(m[1])+'</span>'+esc(m[2])+'</div>';
  return '<div style="margin:3px 0">'+esc(line)+'</div>';
 }).join('');
}
function badgeClassFor(key){
 if(key==='vgroup:auto:listening')return 'badge badge-listening';
 if(key==='vgroup:auto:reading')return 'badge badge-reading';
 return 'badge badge-custom';
}
/* ---- 生词分类：与桌面 src/vocabulary.py 同一套规则 ---- */
const VOCAB_AUTO={listening:'vgroup:auto:listening',reading:'vgroup:auto:reading'};
const VOCAB_AUTO_NAMES={'vgroup:auto:listening':'听力','vgroup:auto:reading':'阅读'};
function pyQuote(value){return encodeURIComponent(value).replace(/[!'()*]/g,c=>'%'+c.charCodeAt(0).toString(16).toUpperCase());}
function vocabWordKey(word){return 'vcat:'+pyQuote(SyncCore.normalizeWord(word).toLowerCase());}
function vocabCategories(){
 const custom=Object.entries(state.study)
  .filter(([key,value])=>key.startsWith('vgroup:')&&value&&!VOCAB_AUTO_NAMES[key]&&value.name)
  .map(([key,value])=>({key,name:String(value.name)}));
 return [{key:VOCAB_AUTO.listening,name:'听力'},{key:VOCAB_AUTO.reading,name:'阅读'}].concat(custom);
}
function vocabCategoryName(key){return (vocabCategories().find(g=>g.key===key)||{}).name||'';}
function vocabAutoCategory(title,groupName){
 const match=/^\s*(听力|阅读|listening|reading)\s*[:：]/i.exec(title||'');
 const map={'听力':VOCAB_AUTO.listening,'阅读':VOCAB_AUTO.reading,'listening':VOCAB_AUTO.listening,'reading':VOCAB_AUTO.reading};
 if(match)return map[match[1].toLowerCase()]||'';
 const name=SyncCore.normalizeWord(groupName).toLowerCase().replace(/\s+/g,'');
 return name==='听力'||name==='listening'?VOCAB_AUTO.listening:name==='阅读'||name==='reading'?VOCAB_AUTO.reading:'';
}
function vocabCategoryOf(word,article){
 const assigned=state.study[vocabWordKey(word)];
 const known=assigned&&assigned.group&&vocabCategories().some(g=>g.key===assigned.group);
 if(known)return assigned.group;
 return article?vocabAutoCategory(article.title,article.group_name||''):'';
}
function vocabAssign(word,key){studySet(vocabWordKey(word),key?{word:SyncCore.normalizeWord(word),group:key}:null);}
function vocabCreateCategory(name){
 const clean=SyncCore.normalizeWord(name);
 if(!clean||Array.from(clean).length>60){toast('请输入1–60字的分类名称');return '';}
 const existing=vocabCategories().find(g=>g.name.toLowerCase()===clean.toLowerCase());
 if(existing)return existing.key;
 if(Object.values(VOCAB_AUTO_NAMES).some(label=>label.toLowerCase()===clean.toLowerCase()))return vocabCategories().find(g=>g.name.toLowerCase()===clean.toLowerCase())?.key||'';
 const key='vgroup:'+uuid();studySet(key,{name:clean});return key;
}
function vocabDeleteCategory(key){
 if(VOCAB_AUTO_NAMES[key]){toast('“听力”和“阅读”是内置分类，不能删除');return false;}
 studySet(key,null);
 Object.keys(state.study).filter(k=>k.startsWith('vcat:')&&state.study[k]&&state.study[k].group===key).forEach(k=>studySet(k,null));
 return true;
}
function groupNames(){return new Map(groups().map(g=>[g.id,g.name]));}
function allWords(){
 const names=groupNames();
 const fromArticles=state.articles.flatMap(a=>{
  const article={...a,group_name:names.get(metadata(a).group)||''};
  return a.vocabulary.map(w=>({...w,article_id:a.id,article_title:a.title,manual:false,
   key:'review:'+a.id+':'+w.start+':'+w.end,category:vocabCategoryOf(w.word,article)}));
 });
 const fromManual=(state.vocabulary_manual||[]).map(w=>({word:w.word,definition:w.definition||'',context:w.context||'',
  id:w.id??null,article_id:null,article_title:'',manual:true,start:null,end:null,
  key:w.id?`review:manual:${w.id}`:'review:local:'+pyQuote(SyncCore.normalizeWord(w.word).toLowerCase()),
  category:vocabCategoryOf(w.word,null)}));
 return fromArticles.concat(fromManual);
}

function renderLearningLibrary(){
 $('main').innerHTML='<div class="row actions"><h2 class="grow">我的文章</h2><button id="newArticle" class="primary">＋ 粘贴</button></div><input id="articleQuery" placeholder="搜索标题或正文…"><div class="actions"><select id="libraryGroup" style="flex:1"></select><button id="manageGroups">管理分组</button><button data-local-page="backups">资料备份</button></div><div id="articleCards"></div>';
 $('articleQuery').value=libraryQuery;
 $('articleQuery').oninput=()=>{libraryQuery=$('articleQuery').value;renderArticleCards();};
 $('libraryGroup').innerHTML='<option value="all">全部文章</option><option value="ungrouped">未分组</option>'+groups().map(g=>'<option value="'+esc(g.id)+'">'+esc(g.name)+'</option>').join('');
 if(!['all','ungrouped',...groups().map(g=>g.id)].includes(libraryGroup))libraryGroup='all';
 $('libraryGroup').value=libraryGroup;$('libraryGroup').onchange=()=>{libraryGroup=$('libraryGroup').value;renderArticleCards();};
 $('manageGroups').onclick=manageMobileGroups;$('newArticle').onclick=()=>navigate('paste');
 $('main').querySelector('[data-local-page]').onclick=()=>navigate('backups');renderArticleCards();
}
function renderArticleCards(){
 const groupMap=new Map(groups().map(g=>[g.id,g.name])),query=libraryQuery.trim().toLowerCase();
 const articles=state.articles.filter(a=>{
  const group=groupMap.has(metadata(a).group)?metadata(a).group:'';
  return (!query||(a.title+'\n'+a.text).toLowerCase().includes(query))&&(libraryGroup==='all'||libraryGroup==='ungrouped'&&!group||libraryGroup===group);
 }).sort((a,b)=>Number(metadata(b).pinned)-Number(metadata(a).pinned));
 $('articleCards').innerHTML=articles.map(a=>{
  const m=metadata(a),words=(a.text.match(/[A-Za-z0-9'-]+/g)||[]).length;
  const pct=a.text.length?Math.min(100,Math.round((a.progress||0)*100/a.text.length)):0;
  return '<section class="card"><div class="row"><div class="grow"><div class="title">'+(m.pinned?'★ ':'')+esc(a.title)+(m.read?' ✓':'')+'</div><div class="muted">'+esc(groupMap.get(m.group)||'未分组')+' · '+words+' 词 · 已读 '+pct+'% · '+a.annotations.length+' 处划线 · '+a.vocabulary.length+' 条生词</div></div><button class="small articleMore" data-id="'+esc(a.id)+'">整理</button></div><div class="progress-track"><div class="progress-fill" style="width:'+pct+'%"></div></div><p class="muted">'+esc(a.text.slice(0,100))+'…</p><button class="primary openArticle" data-id="'+esc(a.id)+'">继续阅读</button></section>';
 }).join('')||'<div class="empty">没有符合条件的文章。</div>';
 document.querySelectorAll('.openArticle').forEach(b=>b.onclick=()=>navigate('read',b.dataset.id));
 document.querySelectorAll('.articleMore').forEach(b=>b.onclick=()=>articleOptions(b.dataset.id));
}
function articleOptions(id){
 const a=state.articles.find(a=>a.id===id),m=metadata(a);
 const overlay=document.createElement('div');overlay.className='overlay';
 overlay.innerHTML='<section class="sheet"><h3>'+esc(a.title)+'</h3><label>分组</label><select id="articleGroup"><option value="">未分组</option>'+groups().map(g=>'<option value="'+esc(g.id)+'">'+esc(g.name)+'</option>').join('')+'</select><div class="actions"><button id="saveGroup">保存分组</button><button id="togglePin">'+(m.pinned?'取消置顶':'置顶')+'</button><button id="toggleRead">'+(m.read?'标为未读':'标为已读')+'</button><button id="renameArticle">重命名</button><button id="deleteArticle">删除文章</button><button id="closeOptions">关闭</button></div></section>';
 document.body.appendChild(overlay);$('articleGroup').value=m.group;
 const close=()=>{overlay.remove();renderArticleCards();};
 $('saveGroup').onclick=()=>{setMetadata(a,{group:$('articleGroup').value});close();};
 $('togglePin').onclick=()=>{setMetadata(a,{pinned:!m.pinned});close();};
 $('toggleRead').onclick=()=>{setMetadata(a,{read:!m.read});close();};
 $('renameArticle').onclick=()=>{overlay.remove();rename(id);};
 $('deleteArticle').onclick=()=>{
  if(!confirm('确定删除《'+a.title+'》？\n\n该文章的划线与源自本文的生词会一并删除（自建词条不受影响），同步后电脑上也会删掉。'))return;
  overlay.remove();if(activeId===id)activeId=null;enqueue('delete',{article_id:id});sync();renderLearningLibrary();toast('文章已删除');
 };
 $('closeOptions').onclick=close;
 overlay.onclick=e=>{if(e.target===overlay)close();};
}
function manageMobileGroups(){
 const overlay=document.createElement('div');overlay.className='overlay';
 function refresh(){overlay.innerHTML='<section class="sheet"><h3>文章分组</h3><div id="groupsList">'+groups().map(g=>'<div class="row actions"><span class="grow">'+esc(g.name)+'</span><button data-rename-group="'+esc(g.id)+'">改名</button><button data-delete-group="'+esc(g.id)+'">删除</button></div>').join('')+'</div><div class="actions"><button id="addGroup" class="primary">新建分组</button><button id="closeGroups">完成</button></div></section>';
  $('addGroup').onclick=()=>edit(null);$('closeGroups').onclick=()=>{overlay.remove();renderLearningLibrary();};
  overlay.querySelectorAll('[data-rename-group]').forEach(b=>b.onclick=()=>edit(b.dataset.renameGroup));
  overlay.querySelectorAll('[data-delete-group]').forEach(b=>b.onclick=()=>{if(confirm('删除分组后，文章仍保留并显示为未分组。继续？')){studySet(b.dataset.deleteGroup,null);refresh();}});
 }
 function edit(key){const name=prompt('分组名称（最多60字）',key?state.study[key].name:'');if(name===null)return;if(!name.trim()||name.trim().length>60){toast('请输入1–60字的分组名称');return;}if(groups().some(g=>g.id!==key&&g.name.toLowerCase()===name.trim().toLowerCase())){toast('已存在同名分组');return;}studySet(key||'group:'+uuid(),{name:name.trim()});refresh();}
 document.body.appendChild(overlay);refresh();
}
function reviewContextHtml(word,context,reveal){
 const safe=esc(context||'（无例句）');
 if(!word)return safe;
 const escapedWord=esc(word).replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
 const re=new RegExp(escapedWord,'ig');
 if(reveal)return safe.replace(re,m=>'<span style="background:var(--blue-soft);color:var(--blue);font-weight:700;padding:1px 4px;border-radius:4px">'+m+'</span>');
 const blank='_'.repeat(Math.max(5,Math.min(12,word.length)));
 return safe.replace(re,'<span style="color:var(--blue);font-weight:700;letter-spacing:1px">'+blank+'</span>');
}
function buildReviewQueue(all,category){
 return allWords().filter(w=>{
  if(category!=='all'&&w.category!==category)return false;
  return all||!state.study[w.key]||Date.parse(state.study[w.key].due)<=Date.now();
 });
}
function renderReview(){
 if(!reviewSession){
  const q=buildReviewQueue(false,reviewCategory);
  reviewSession={all:false,category:reviewCategory,queue:q,done:0,total:q.length};
 }
 const card=reviewSession.queue[0];
 const pct=reviewSession.total?Math.min(100,Math.round(reviewSession.done*100/reviewSession.total)):100;
 const catOptions='<option value="all">全部分类</option>'+vocabCategories().map(g=>'<option value="'+esc(g.key)+'">'+esc(g.name)+'</option>').join('')+'<option value="">未分类</option>';
 $('main').innerHTML='<div class="actions"><button id="reviewBack">返回生词本</button><button id="reviewAll">'+(reviewSession.all?'只复习到期词':'练习全部生词')+'</button><select id="reviewCat" style="flex:1;min-width:120px">'+catOptions+'</select></div>'
  +'<div class="progress-track"><div class="progress-fill" style="width:'+pct+'%"></div></div>'
  +'<div class="muted" style="margin-bottom:10px">剩余 '+reviewSession.queue.length+' 条 · 本轮已复习 '+reviewSession.done+' 条</div>'
  +(card?'<section class="card"><div class="reviewWord">'+esc(card.word)+'</div><div class="muted">来源：'+esc(card.article_title||'自建词条')+(card.category?' · <span class="'+badgeClassFor(card.category)+'">'+esc(vocabCategoryName(card.category))+'</span>':'')+'</div><p id="reviewCtx" class="reviewContext">'+reviewContextHtml(card.word,card.context,false)+'</p><div class="actions"><button id="cardSound">▶ 发音</button>'+(card.manual?'':'<button id="cardOriginal">回原文</button>')+'<button id="revealCard" class="primary">显示释义</button></div><div id="cardAnswer" hidden class="definition" style="margin-top:10px;padding-top:10px;border-top:1px solid var(--border)">'+formatDefHtml(card.definition||'暂无释义')+'</div><div id="cardGrades" class="actions" hidden><button data-grade="again">不认识 · 本轮回炉</button><button data-grade="hard">模糊 · 1天</button><button data-grade="known" class="primary">认识 · 延长间隔</button></div></section>'
   :'<section class="card"><h2>本轮复习完成</h2><p class="muted">未到期的词会在到期后出现，也可以切换分类或练习全部生词。</p></section>')
  +'<p class="muted">认识：首次3天，再按上次间隔翻倍，最多365天。复习结果可与电脑同步。</p>';
 $('reviewCat').value=reviewSession.category;
 $('reviewBack').onclick=()=>navigate('vocabulary');
 $('reviewAll').onclick=()=>{
  const all=!reviewSession.all,q=buildReviewQueue(all,reviewSession.category);
  reviewSession={all,category:reviewSession.category,queue:q,done:0,total:q.length};renderReview();
 };
 $('reviewCat').onchange=()=>{
  reviewCategory=$('reviewCat').value;
  const q=buildReviewQueue(reviewSession.all,reviewCategory);
  reviewSession={all:reviewSession.all,category:reviewCategory,queue:q,done:0,total:q.length};renderReview();
 };
 if(!card)return;
 $('cardSound').onclick=()=>speak(card.word);
 if(!card.manual)$('cardOriginal').onclick=()=>jumpMobile(card.article_id,card.start,card.end);
 $('revealCard').onclick=()=>{$('reviewCtx').innerHTML=reviewContextHtml(card.word,card.context,true);$('cardAnswer').hidden=false;$('cardGrades').hidden=false;};
 document.querySelectorAll('[data-grade]').forEach(b=>b.onclick=()=>{
  const grade=b.dataset.grade,previous=state.study[card.key]||{},interval=grade==='again'?0:grade==='hard'?1:Math.min(365,Math.max(3,(previous.interval||0)*2));
  const due=new Date(Date.now()+(grade==='again'?600000:interval*86400000)).toISOString(),count=(previous.count||0)+1;
  if(card.manual){
   const record=card.id?{manual:true,vocabulary_id:card.id,grade,interval,due,count}:{grade,interval,due,count};
   if(card.id)studySet(card.key,record);else{state.study[card.key]=record;save();toast('该词条尚未同步编号，复习结果先记在本机');}
  }else studySet(card.key,{article_id:card.article_id,start:card.start,end:card.end,grade,interval,due,count});
  reviewSession.queue.shift();
  if(grade==='again')reviewSession.queue.push(card);
  else reviewSession.done++;
  renderReview();
 });
}
function saveSelectedSentence(){
 if(!selected){toast('请先选中句子或段落');return;}
 const a=state.articles.find(a=>a.id===selected.article_id);if(!a)return;
 noteDraft={key:'note:'+uuid(),article_id:a.id,start:selected.start,end:selected.end,text:Array.from(a.text).slice(selected.start,selected.end).join(''),translation:currentDefinition||'',note:''};
 navigate('noteEdit');
}
function renderNoteEditor(){
 if(!noteDraft){navigate('notes');return;}
 $('main').innerHTML='<h2>句子收藏与笔记</h2><section class="card noteText">'+esc(noteDraft.text)+'</section><label>中文译文（可编辑）</label><textarea id="noteTranslation" style="min-height:130px"></textarea><label>我的笔记</label><textarea id="noteBody" style="min-height:160px"></textarea><div class="actions"><button id="saveNote" class="primary">保存收藏</button><button id="cancelNote">取消</button></div>';
 $('noteTranslation').value=noteDraft.translation;$('noteBody').value=noteDraft.note;
 $('noteTranslation').oninput=()=>{noteDraft._dirty=true;};$('noteBody').oninput=()=>{noteDraft._dirty=true;};
 $('cancelNote').onclick=()=>{if(confirm('放弃本次尚未保存的修改？')){noteDraft._dirty=false;navigate('notes');}};
 $('saveNote').onclick=()=>{
  const value={...noteDraft,translation:$('noteTranslation').value.trim(),note:$('noteBody').value.trim()},key=value.key,expected=value._base??null;delete value.key;delete value._base;delete value._dirty;
  if(value.translation.length>20000||value.note.length>10000){toast('译文最多20000字，笔记最多10000字');return;}
  studySet(key,value,expected);noteDraft=null;navigate('notes');toast('收藏已保存');
 };
}
function renderNotes(){
 $('main').innerHTML='<h2>句子收藏与笔记</h2><input id="notesSearch" placeholder="搜索原文、译文、笔记或文章…"><div id="noteCards" style="margin-top:14px"></div>';
 function refresh(){const query=$('notesSearch').value.toLowerCase(),articles=new Map(state.articles.map(a=>[a.id,a]));
  const notes=Object.entries(state.study).filter(([key,n])=>key.startsWith('note:')&&n&&articles.has(n.article_id)&&(!query||[n.text,n.translation,n.note,articles.get(n.article_id).title].join(' ').toLowerCase().includes(query)));
  $('noteCards').innerHTML=notes.map(([key,n])=>'<section class="card"><div class="muted">'+esc(articles.get(n.article_id).title)+'</div><p class="noteText">'+esc(n.text)+'</p><div class="noteText">'+esc(n.translation)+'</div><p class="muted noteText">笔记：'+esc(n.note)+'</p><div class="actions"><button class="small" data-edit-note="'+esc(key)+'">编辑</button><button class="small" data-speak-note="'+esc(key)+'">▶ 朗读</button><button class="small" data-jump-note="'+esc(key)+'">回原文</button><button class="small" data-delete-note="'+esc(key)+'">删除</button></div></section>').join('')||'<div class="empty">阅读时选中句段，点击“收藏句段”。</div>';
  document.querySelectorAll('[data-edit-note]').forEach(b=>b.onclick=()=>{noteDraft={key:b.dataset.editNote,...state.study[b.dataset.editNote],_base:SyncCore.clone(state.study[b.dataset.editNote])};navigate('noteEdit');});
  document.querySelectorAll('[data-speak-note]').forEach(b=>b.onclick=()=>speak(state.study[b.dataset.speakNote].text));
  document.querySelectorAll('[data-jump-note]').forEach(b=>b.onclick=()=>{const n=state.study[b.dataset.jumpNote];jumpMobile(n.article_id,n.start,n.end);});
  document.querySelectorAll('[data-delete-note]').forEach(b=>b.onclick=()=>{if(confirm('删除此句子收藏及笔记？')){studySet(b.dataset.deleteNote,null);refresh();}});
 }
 $('notesSearch').oninput=refresh;refresh();
}
function jumpMobile(id,start,end){navigate('read',id);setTimeout(()=>{const token=Array.from(document.querySelectorAll('#readingArea .token')).find(t=>+t.dataset.end>start);if(token)token.scrollIntoView({block:'center'});highlightSentence(start,end);},180);}
function splitSentences(text){
 const ranges=[];let start=0;const re=/[.!?。！？]+[”’"']*|\n+/g;let match;
 while((match=re.exec(text))){let end=re.lastIndex;
  if(match[0].startsWith('.')){const token=text.slice(start,match.index).match(/([A-Za-z.]+)$/);if(token&&(['mr','mrs','ms','dr','prof','st','vs','etc','e.g','i.e'].includes(token[1].toLowerCase())||token[1].length===1)||/\d/.test(text[match.index-1]||'')&&/\d/.test(text[end]||''))continue;}
  if(end<text.length&&!/\s|[。！？]/.test(text[end]))continue;
  const raw=text.slice(start,end),leading=raw.match(/^\s*/)[0].length,trimmed=raw.trim();if(trimmed)ranges.push({start:Array.from(text.slice(0,start+leading)).length,end:Array.from(text.slice(0,start+leading+trimmed.length)).length,text:trimmed});start=end;
 }
 const rest=text.slice(start),leading=rest.match(/^\s*/)[0].length;if(rest.trim())ranges.push({start:Array.from(text.slice(0,start+leading)).length,end:Array.from(text.trimEnd()).length,text:rest.trim()});return ranges;
}
/* Listening marks merge localStorage with synced state.study['listen:<id>']. */
function listeningLoad(){
 let data={};
 try{const raw=JSON.parse(localStorage.getItem('listening-v1')||'{}');if(raw&&typeof raw==='object'&&!Array.isArray(raw))data=raw;}catch(e){}
 if(state&&state.study){
  for(const [k,v] of Object.entries(state.study)){
   if(!k.startsWith('listen:')||!v||typeof v!=='object')continue;
   const aid=k.slice(7),local=data[aid]||(data[aid]={});
   for(const [span,rec] of Object.entries(v)){
    if(!rec||typeof rec!=='object')continue;
    if(!local[span]||String(rec.updated||'')>String(local[span].updated||''))local[span]=rec;
   }
  }
 }
 return data;
}
function listeningSave(data){try{localStorage.setItem('listening-v1',JSON.stringify(data));}catch(e){toast('本机存储空间不足，这次标记没有保存');}}
function listeningStatus(articleId,start,end,text){const record=(listeningLoad()[articleId]||{})[start+':'+end];return record&&record.text===text?record.status:null;}
function listeningMark(articleId,start,end,text,status){
 const data=listeningLoad(),records=data[articleId]||{};
 if(status===null)delete records[start+':'+end];else records[start+':'+end]={start,end,text,status,updated:new Date().toISOString()};
 data[articleId]=records;listeningSave(data);
 if(state&&state.articles&&state.articles.some(a=>a.id===articleId)){
  studySet('listen:'+articleId,Object.keys(records).length?records:null);
 }
}
function listeningMissed(articleId,ranges){const marks=listeningLoad()[articleId]||{},result=[];
 ranges.forEach((s,i)=>{const record=marks[s.start+':'+s.end];if(record&&record.status==='missed'&&record.text===s.text)result.push(i);});return result;}
function recordDictationStat(articleId,count,avg){
 if(!count)return;
 const data=listeningLoad();
 const list=Array.isArray(data.__dictation_history__)?data.__dictation_history__:[];
 list.push({article_id:articleId,sentences:count,accuracy:avg,at:new Date().toISOString()});
 if(list.length>200)list.splice(0,list.length-200);
 data.__dictation_history__=list;listeningSave(data);
}
function formatSpeedLabel(speed){
 const n=Number(speed)||0.75;
 return (Number.isInteger(n)?n.toFixed(1):String(n))+'×';
}
function refreshSpeedUI(){
 const cur=Number(state.audio?.speed)||0.75;
 if($('quickSpeed'))$('quickSpeed').textContent=formatSpeedLabel(cur);
 document.querySelectorAll('[data-speed-pick]').forEach(b=>b.classList.toggle('active',Math.abs(Number(b.dataset.speedPick)-cur)<1e-6));
}
function setSpeechSpeed(next,showToast=true){
 const speed=Math.max(0.6,Math.min(1.25,Number(next)||0.75));
 state.audio={...state.audio,speed};save();refreshSpeedUI();
 if(showToast)toast('已切至 '+formatSpeedLabel(speed)+' 倍速');
}
function setPlayerDrawer(open){
 const drawer=$('playerDrawer'),backdrop=$('playerBackdrop'),toggle=$('playerMoreToggle');
 if(drawer)drawer.hidden=!open;
 if(backdrop)backdrop.hidden=!open;
 document.body.classList.toggle('drawer-open',!!open);
 if(toggle){toggle.classList.toggle('open',!!open);toggle.setAttribute('aria-expanded',open?'true':'false');}
}
function hidePlayerDock(){
 setPlayerDrawer(false);
 if($('playerDock'))$('playerDock').hidden=true;
}
function updatePlayButton(){
 const btn=$('sentencePlay');if(!btn)return;
 if(speechMode!=='none'&&!speechPaused)btn.textContent='⏸ 暂停';
 else if(speechMode!=='none'&&speechPaused)btn.textContent='▶ 继续';
 else btn.textContent='▶ 逐句';
}
function updateDrawerBadge(){
 const btn=$('playerMoreToggle');if(!btn)return;
 const custom=Boolean($('replayMissedOnly')?.checked||$('sentenceMode')?.value==='one'||(Number($('sentenceRepeat')?.value)||1)>1);
 btn.classList.toggle('has-badge',custom);
}
function updateIdleSentenceStatus(){
 const el=$('sentenceStatus');if(!el||sentenceSession||speechMode==='full')return;
 const a=article();if(!a){el.textContent='';return;}
 const ranges=splitSentences(a.text),missed=listeningMissed(a.id,ranges).length;
 const onlyMissed=$('replayMissedOnly')?.checked;
 el.textContent='共 '+ranges.length+' 句'+(onlyMissed?' · 仅重听没听懂('+missed+')':missed?' · 没听懂 '+missed+' 句':' · 点 ▶ 开始逐句');
}
function updateSentenceMarkButtons(){
 const heardBtn=$('markHeard'),missedBtn=$('markMissed');
 if(!heardBtn||!missedBtn)return;
 const s=currentSentenceRange();
 const st=s&&activeId?listeningStatus(activeId,s.start,s.end,s.text):null;
 heardBtn.classList.toggle('is-heard',st==='heard');
 missedBtn.classList.toggle('is-missed',st==='missed');
}
function sentenceOrder(ranges){if(!$('replayMissedOnly')||!$('replayMissedOnly').checked)return ranges.map((_,i)=>i);
 const order=listeningMissed(activeId,ranges);return order.length?order:ranges.map((_,i)=>i);}
function updateMissedCount(){
 const a=article(),count=a?listeningMissed(a.id,splitSentences(a.text)).length:0;
 if($('missedCount'))$('missedCount').textContent=a?'没听懂 '+count+' 句':'';
 updateDrawerBadge();updateIdleSentenceStatus();
}
function currentSentenceRange(){const a=article();if(!a)return null;
 if(sentenceSession&&sentenceSession.ranges[sentenceSession.index])return sentenceSession.ranges[sentenceSession.index];
 const ranges=splitSentences(a.text),position=selected&&selected.article_id===a.id?selected.start:0;
 return ranges.find(s=>s.end>position)||ranges[0]||null;}
function markCurrentSentence(status){const s=currentSentenceRange();if(!s)return;
 const after=listeningStatus(activeId,s.start,s.end,s.text)===status?null:status;
 listeningMark(activeId,s.start,s.end,s.text,after);
 const label={'heard':'已标记听懂','missed':'已标记没听懂',null:'已清除标记'}[after];
 if($('sentenceStatus'))$('sentenceStatus').textContent=(sentenceSession?'第 '+(sentenceSession.index+1)+'/'+sentenceSession.ranges.length+' 句':'当前句')+' · '+label;
 updateMissedCount();updateSentenceMarkButtons();
 if(typeof updateReader==='function')updateReader();
}
function startFullReading(){
 const a=article();if(!a)return;
 setPlayerDrawer(false);stopSequence();
 speechMode='full';speechPaused=false;fullSpeechId=uuid();updatePlayButton();
 if($('sentenceStatus'))$('sentenceStatus').textContent='正在全文朗读…';
 nativeCall('speak',{text:a.text,...state.audio,request_id:fullSpeechId}).catch(e=>{stopSequence();toast(e.message);});
}
function repeatCurrentSentence(){
 if(sentenceSession){
  const ranges=sentenceSession.ranges,idx=sentenceSession.index;
  stopSequence();
  sentenceSession={ranges,order:sentenceOrder(ranges),index:idx,round:0,id:null};
  playSentence();
 }else{
  beginSentence();
 }
}
function togglePrimaryPlay(){
 if(speechMode==='none')beginSentence();
 else pauseLearningSpeech();
}
function installSentenceControls(){
 const dock=$('playerDock');if(!dock)return;
 dock.hidden=false;
 dock.innerHTML='<div class="player-dock-inner">'
  +'<div id="playerDrawer" class="dock-drawer" hidden>'
  +'<div class="dock-drawer-head"><span class="dock-drawer-title">精听与朗读设置</span><button id="playerDrawerClose" class="small" style="padding:4px 10px;font-size:12px">收起</button></div>'
  +'<div class="dock-quick-grid"><button id="speakAll">▶ 全文</button><button id="stopSpeech">⏹ 停止</button><button id="openDictation">⌨ 听写</button><button id="saveCurrentSentence">☆ 收藏句</button></div>'
  +'<div class="dock-speed-strip"><span class="dock-speed-label">倍速</span><div class="dock-speed-pills"><button data-speed-pick="0.6">0.6×</button><button data-speed-pick="0.75">0.75×</button><button data-speed-pick="0.9">0.9×</button><button data-speed-pick="1">1.0×</button><button data-speed-pick="1.25">1.25×</button></div></div>'
  +'<div class="dock-setting-row"><select id="sentenceMode"><option value="all">逐句继续</option><option value="one">仅当前句</option></select><input id="sentenceRepeat" type="number" value="1" min="1" max="99" aria-label="每句次数"><span class="muted">遍</span><input id="sentenceGap" type="number" value="1" min="0" max="30" step="0.5" aria-label="句间停顿秒"><span class="muted">秒停顿</span></div>'
  +'<div class="dock-check-row"><label class="dock-check-label"><input id="replayMissedOnly" type="checkbox"><span>只重听没听懂句</span></label><span id="missedCount" class="muted"></span></div>'
  +'</div>'
  +'<div class="dock-status-row"><div id="sentenceStatus" class="dock-status-text"></div><div class="dock-mini-actions"><button id="sentenceRepeatNow" class="dock-mini-btn icon-only" title="重听当前句" aria-label="重听当前句">↻</button><button id="markHeard" class="dock-mini-btn">✓ 听懂</button><button id="markMissed" class="dock-mini-btn">✗ 没听懂</button></div></div>'
  +'<div class="dock-transport"><button id="quickSpeed" class="speed-pill dock-speed-btn" title="切换 0.75× / 1.0× 倍速"></button><button id="sentencePrevious" class="dock-step-btn">‹ 上句</button><button id="sentencePlay" class="primary dock-play-btn">▶ 逐句</button><button id="sentenceNext" class="dock-step-btn">下句 ›</button><button id="playerMoreToggle" class="dock-more-btn" title="更多精听设置" aria-label="更多精听设置" aria-expanded="false">⚙</button></div>'
  +'</div>';
 $('quickSpeed').onclick=()=>{
  const next=Math.abs(Number(state.audio.speed)-0.75)<1e-6?1:0.75;
  setSpeechSpeed(next,true);
 };
 dock.querySelectorAll('[data-speed-pick]').forEach(b=>b.onclick=()=>setSpeechSpeed(Number(b.dataset.speedPick),true));
 $('sentencePlay').onclick=togglePrimaryPlay;
 $('sentencePrevious').onclick=()=>stepSentence(-1);
 $('sentenceNext').onclick=()=>stepSentence(1);
 $('sentenceRepeatNow').onclick=repeatCurrentSentence;
 $('markHeard').onclick=()=>markCurrentSentence('heard');
 $('markMissed').onclick=()=>markCurrentSentence('missed');
 $('speakAll').onclick=startFullReading;
 $('stopSpeech').onclick=()=>{setPlayerDrawer(false);stopLearningSpeech();};
 $('openDictation').onclick=()=>{setPlayerDrawer(false);openDictation();};
 $('replayMissedOnly').onchange=updateMissedCount;
 $('sentenceMode').onchange=updateDrawerBadge;
 $('sentenceRepeat').oninput=updateDrawerBadge;
 $('playerMoreToggle').onclick=()=>setPlayerDrawer($('playerDrawer').hidden);
 $('playerDrawerClose').onclick=()=>setPlayerDrawer(false);
 if($('playerBackdrop'))$('playerBackdrop').onclick=()=>setPlayerDrawer(false);
 $('saveCurrentSentence').onclick=()=>{setPlayerDrawer(false);const s=sentenceSession?.ranges[sentenceSession.index]||splitSentences(article().text).find(s=>s.end>(selected?.start||0));if(!s)return;selected={article_id:activeId,start:s.start,end:s.end,word:s.text};currentDefinition='';saveSelectedSentence();};
 refreshSpeedUI();updatePlayButton();updateMissedCount();updateSentenceMarkButtons();
}
function highlightSentence(start,end){document.querySelectorAll('#readingArea .token').forEach(t=>t.classList.toggle('speaking',+t.dataset.start<end&&+t.dataset.end>start));}
function stopSequence(){
 if(sentenceTimeout!==null){clearTimeout(sentenceTimeout);sentenceTimeout=null;}
 sentenceSession=null;sentencePaused=false;fullSpeechId=null;speechMode='none';speechPaused=false;
 document.querySelectorAll('#readingArea .speaking').forEach(t=>t.classList.remove('speaking'));
 updatePlayButton();
}
function stopLearningSpeech(){stopSequence();nativeCall('stop',{}).catch(e=>toast(e.message));if($('sentenceStatus'))$('sentenceStatus').textContent='已停止';}
function beginSentence(index=null){
 const a=article();if(!a)return;const ranges=splitSentences(a.text);if(!ranges.length)return;
 const order=sentenceOrder(ranges);
 const position=selected?.article_id===a.id?selected.start:0;
 let current;
 if(index===null)current=order.find(i=>ranges[i].end>position)??order[0];
 else current=order.includes(index)?index:(order.find(i=>i>=index)??order[order.length-1]);
 stopSequence();
 sentenceSession={ranges,order,index:current,round:0,id:null};playSentence();
}
function stepSentence(direction){
 if(!sentenceSession){beginSentence(direction>0?0:null);return;}
 const pos=sentenceSession.order.indexOf(sentenceSession.index),target=pos+direction;
 if(pos<0||target<0||target>=sentenceSession.order.length)return;
 const ranges=sentenceSession.ranges;
 stopSequence();
 sentenceSession={ranges,order:sentenceOrder(ranges),index:0,round:0,id:null};
 sentenceSession.index=sentenceSession.order[Math.min(target,sentenceSession.order.length-1)];
 playSentence();
}
function playSentence(){
 if(!sentenceSession||page!=='read')return;
 const session=sentenceSession,s=session.ranges[session.index],repeat=Math.max(1,Math.min(99,Number($('sentenceRepeat').value)||1));
 speechMode='sentence';speechPaused=false;sentencePaused=false;updatePlayButton();
 highlightSentence(s.start,s.end);const first=Array.from(document.querySelectorAll('#readingArea .token')).find(t=>+t.dataset.end>s.start);if(first)first.scrollIntoView({block:'center',behavior:'smooth'});
 $('sentenceStatus').textContent='第 '+(session.index+1)+'/'+session.ranges.length+' 句 · 第 '+(session.round+1)+'/'+repeat+' 遍';
 updateSentenceMarkButtons();
 session.id=uuid();nativeCall('speak',{text:s.text,...state.audio,request_id:session.id}).catch(e=>{stopSequence();toast(e.message);});
}
window.nativeSpeechDone=(id,error)=>{
 if(fullSpeechId&&id===fullSpeechId){
  stopSequence();
  if(error)toast(error);else{updateIdleSentenceStatus();toast('全文朗读完成');}
  return;
 }
 const session=sentenceSession;if(!session||session.id!==id)return;
 if(error){stopSequence();toast(error);return;}
 session.round++;const repeat=Math.max(1,Math.min(99,Number($('sentenceRepeat').value)||1));
 if(session.round>=repeat){const pos=session.order.indexOf(session.index);if($('sentenceMode').value==='one'||pos+1>=session.order.length){stopSequence();if($('sentenceStatus'))$('sentenceStatus').textContent='逐句朗读完成';return;}session.index=session.order[pos<0?0:pos+1];session.round=0;}
 const gap=Math.max(0,Math.min(30,Number($('sentenceGap').value)||0));
 sentenceTimeout=setTimeout(()=>{sentenceTimeout=null;playSentence();},gap*1000);
};
function pauseLearningSpeech(){
 if(sentenceTimeout!==null){clearTimeout(sentenceTimeout);sentenceTimeout=null;sentencePaused=true;speechPaused=true;updatePlayButton();toast('已暂停句间等待');return;}
 if(sentencePaused){sentencePaused=false;speechPaused=false;updatePlayButton();playSentence();return;}
 if(speechMode!=='none'){speechPaused=!speechPaused;updatePlayButton();}
 nativeCall('pause',{}).catch(e=>toast(e.message));
}
function displayStyle(element,options){
 const themes={paper:['#fffaf0','#2c2721','255,250,240'],light:['#ffffff','#203044','255,255,255'],green:['#e8f2e2','#223627','232,242,226'],dark:['#1b222e','#dde6f2','27,34,46']},theme=themes[options.theme]||themes.paper;
 element.style.fontSize=options.size+'px';element.style.lineHeight=options.line;element.style.padding=options.margin+'px';element.style.color=theme[1];element.style.backgroundColor=theme[0];
 const opacity=Math.max(0,Math.min(65,Number(options.opacity)))/100;
 element.style.backgroundImage=options.image&&/^data:image\/(jpeg|png);base64,/.test(options.image)?'linear-gradient(rgba('+theme[2]+','+(1-opacity)+'),rgba('+theme[2]+','+(1-opacity)+')),url("'+options.image+'")':'none';element.style.backgroundSize='cover';element.style.backgroundPosition='center';
}
function applyReaderDisplay(){
 applyGlobalTheme(state.display.theme);
 if($('readingArea'))displayStyle($('readingArea'),state.display);
 $('main').style.maxWidth=state.display.width+'px';
}
function renderDisplaySettings(){
 let draft={...state.display};
 $('main').innerHTML='<h2>阅读显示与背景图</h2><section class="card"><label>字号（14–36）</label><input id="displaySize" type="number" min="14" max="36"><label>行距（1.1–2.5）</label><input id="displayLine" type="number" min="1.1" max="2.5" step="0.1"><label>正文最大宽度（320–1100像素）</label><input id="displayWidth" type="number" min="320" max="1100"><label>阅读边距（8–50）</label><input id="displayMargin" type="number" min="8" max="50"><label>全局主题配色</label><select id="displayTheme"><option value="paper">暖纸色</option><option value="light">明亮白</option><option value="green">护眼浅绿</option><option value="dark">深色夜间模式</option></select><label>背景图可见度（0–65%）</label><input id="displayOpacity" type="range" min="0" max="65"><div class="actions"><button id="chooseBackground">选自己的背景图</button><button id="clearBackground">移除图片</button></div><div id="displayPreview" class="preview">Reading makes the world a little wider.\n阅读，让世界更宽一点。</div><div class="actions"><button id="saveDisplay" class="primary">保存设置</button><button id="backupPage">资料备份与恢复</button></div><p class="muted">切换主题会同步应用到整个 App 界面。背景图复制到本机，设置各设备独立保存。</p></section>';
 const controls=[['displaySize','size',14,36],['displayLine','line',1.1,2.5],['displayWidth','width',320,1100],['displayMargin','margin',8,50],['displayOpacity','opacity',0,65]];
 function preview(){for(const[id,key,min,max]of controls)draft[key]=Math.max(min,Math.min(max,Number($(id).value)||min));draft.theme=$('displayTheme').value;displayStyle($('displayPreview'),draft);applyGlobalTheme(draft.theme);}
 for(const[id,key]of controls){$(id).value=draft[key];$(id).oninput=preview;}$('displayTheme').value=draft.theme;$('displayTheme').onchange=preview;
 $('chooseBackground').onclick=async()=>{try{const result=await nativeCall('chooseBackground',{});if(!result.cancelled){draft.image=result.image;preview();}}catch(e){toast(e.message);}};
 $('clearBackground').onclick=()=>{draft.image='';preview();};
 $('saveDisplay').onclick=()=>{preview();const previous=state.display;state.display=draft;try{save();applyGlobalTheme(draft.theme);toast('阅读设置已保存');}catch(e){state.display=previous;applyGlobalTheme(previous.theme);}};
 $('backupPage').onclick=()=>navigate('backups');preview();
}
function renderStats(){
 const articles=state.articles,words=allWords(),now=Date.now();
 const readCount=articles.filter(a=>metadata(a).read).length;
 const totalWords=articles.reduce((s,a)=>s+(a.text.match(/[A-Za-z0-9'-]+/g)||[]).length,0);
 const totalAnn=articles.reduce((s,a)=>s+a.annotations.length,0);
 const totalNotes=Object.entries(state.study).filter(([k,v])=>k.startsWith('note:')&&v).length;
 let due=0,mastered=0,reviews=0;
 words.forEach(w=>{
  const rec=state.study[w.key];
  if(!rec||Date.parse(rec.due)<=now)due++;
  if(rec){reviews+=Number(rec.count||0);if(Number(rec.interval||0)>=7)mastered++;}
 });
 const hist=(listeningLoad().__dictation_history__)||[];
 const avgDict=hist.length?Math.round(hist.reduce((s,x)=>s+Number(x.accuracy||0),0)/hist.length*100):0;
 const tally=new Map();
 words.forEach(w=>{const name=vocabCategoryName(w.category)||'未分类';tally.set(name,(tally.get(name)||0)+1);});
 const cats=Array.from(tally.entries()).sort((a,b)=>b[1]-a[1]);
 const maxV=Math.max(1,words.length);
 $('main').innerHTML='<h2>学习统计</h2>'
  +'<div class="stat-grid">'
  +'<div class="stat-card"><div class="muted">文章阅读</div><div class="stat-num">'+readCount+' / '+articles.length+'</div><div class="muted">累计约 '+totalWords.toLocaleString()+' 词</div></div>'
  +'<div class="stat-card"><div class="muted">生词积累</div><div class="stat-num">'+words.length+' 条</div><div class="muted">已掌握 '+mastered+' 条（间隔≥7天）</div></div>'
  +'<div class="stat-card"><div class="muted">待复习生词</div><div class="stat-num">'+due+' 条</div><div class="muted">累计复习 '+reviews+' 次</div></div>'
  +'<div class="stat-card"><div class="muted">精读与听写</div><div class="stat-num">'+totalAnn+' 划线</div><div class="muted">笔记 '+totalNotes+' 条 · 听写 '+(hist.length?hist.length+'次 ('+avgDict+'%)':'0次')+'</div></div>'
  +'</div>'
  +'<section class="card"><div class="title">生词分类分布</div>'
  +(cats.length?cats.map(([name,cnt])=>'<div style="margin:10px 0"><div class="row"><span class="grow">'+esc(name)+'</span><span class="muted">'+cnt+' 条</span></div><div class="progress-track"><div class="progress-fill" style="width:'+Math.round(cnt*100/maxV)+'%"></div></div></div>').join(''):'<p class="muted">暂无生词记录。</p>')
  +'<div class="actions"><button id="statsReview" class="primary">去复习到期生词</button></div></section>';
 $('statsReview').onclick=()=>{reviewSession=null;navigate('review');};
}
function backupList(){try{return JSON.parse(localStorage.getItem('reader-backups-v1')||'[]');}catch(e){throw Error('本机备份列表无法读取，已保留原文件');}}
function backupMobile(kind='manual'){
 const backups=backupList(),snapshot={id:uuid(),time:new Date().toISOString(),kind,data:SyncCore.clone(state)};
 backups.unshift(snapshot);
 while(backups.length>7)backups.pop();
 try{localStorage.setItem('reader-backups-v1',JSON.stringify(backups));}catch(e){throw Error('备份空间不足，请先导出备份文件再释放空间；没有替换当前资料');}
 return snapshot;
}
function backupCounts(data){return data.articles.length+'篇文章 · '+data.articles.reduce((sum,a)=>sum+a.annotations.length,0)+'处划线 · '+allWordsIn(data).length+'条生词 · '+Object.entries(data.study||{}).filter(([k,v])=>k.startsWith('note:')&&v).length+'条收藏';}
function allWordsIn(data){return (data.articles||[]).reduce((sum,a)=>sum+(a.vocabulary||[]).length,0)+(data.vocabulary_manual||[]).length;}
function validateBackup(data){
 if(!data||!Array.isArray(data.articles)||!Array.isArray(data.outbox)||!data.config||typeof data.client_id!=='string'||data.articles.length>10000||data.outbox.length>50000)throw Error('不是有效的阅读器备份');
 if(data.vocabulary_manual&&!Array.isArray(data.vocabulary_manual))throw Error('自建词条格式不正确');
 const ids=new Set();for(const a of data.articles){if(!a||typeof a.id!=='string'||ids.has(a.id)||typeof a.title!=='string'||typeof a.text!=='string'||!Array.isArray(a.annotations)||!Array.isArray(a.vocabulary))throw Error('备份文章结构不完整');ids.add(a.id);const text=Array.from(a.text);for(const mark of [...a.annotations,...a.vocabulary])if(!Number.isInteger(mark.start)||!Number.isInteger(mark.end)||mark.start<0||mark.end>text.length||mark.end<=mark.start||text.slice(mark.start,mark.end).join('')!==mark.word)throw Error('备份标记位置与原文不符');}
 if(state.instance&&data.instance&&state.instance!==data.instance)throw Error('备份属于其他电脑的资料库，已阻止覆盖当前手机资料');
 if(data.study&&(typeof data.study!=='object'||Array.isArray(data.study)))throw Error('学习记录格式不正确');
 return data;
}
function restoreMobile(data){
 validateBackup(data);if(busy){toast('正在同步，请同步结束后再恢复');return;}
 if(!confirm('恢复为这份备份？\n'+backupCounts(data)+'\n\n会先保存当前资料副本。恢复后的待同步修改会继续发送给电脑。'))return;
 backupMobile('before-restore');const previous=state,next=SyncCore.clone(data);next.config=previous.config.token?previous.config:next.config;next.study=next.study||{};next.vocabulary_manual=Array.isArray(next.vocabulary_manual)?next.vocabulary_manual:[];next.display=next.display||previous.display;next.audio=next.audio||previous.audio;next.translations=next.translations||{};next.errors=[];next.conflicts=next.conflicts||[];
 state=next;try{save();}catch(e){state=previous;throw e;}stopLearningSpeech();applyGlobalTheme(state.display.theme);lastSync='';navigate('articles');toast('已恢复手机本机资料；联网同步会按电脑当前资料与待传操作合并');
}
function renderBackups(){
 $('main').innerHTML='<h2>手机资料备份与恢复</h2><section class="card"><p>当前：'+esc(backupCounts(state))+'</p><div class="actions"><button id="makeBackup">立即备份到本机</button><button id="exportBackup">导出备份文件</button><button id="importBackup">选择文件恢复</button><button id="clearAudioCache">清理语音缓存</button></div><p class="muted">每天首次打开自动保存快照，最多保留7份本机快照。完整文件可另存到你选择的位置。手机备份格式为JSON，电脑备份为SQLite，请分别使用。\n手机恢复只影响本机；再次联网会与电脑合并，不能用它撤销电脑上的数据。</p></section><div id="backupCards"></div>';
 function refresh(){const backups=backupList();$('backupCards').innerHTML=backups.map((b,i)=>'<section class="card"><div class="title">'+esc(new Date(b.time).toLocaleString())+'</div><p>'+esc(backupCounts(b.data))+'</p><p class="muted">'+esc(b.data.articles.map(a=>a.title).join('、'))+'</p><button data-restore-backup="'+i+'">恢复这份快照</button></section>').join('');document.querySelectorAll('[data-restore-backup]').forEach(b=>b.onclick=()=>{try{restoreMobile(backups[+b.dataset.restoreBackup].data);}catch(e){toast(e.message);}});}
 $('makeBackup').onclick=()=>{try{backupMobile();refresh();toast('备份已保存');}catch(e){toast(e.message);}};
 $('clearAudioCache').onclick=async()=>{if(!confirm('清理本机缓存的词典发音与整句语音文件？不影响文章与生词。'))return;try{const res=await nativeCall('clearAudioCache',{});toast('已清理 '+(res.removed||0)+' 个语音缓存文件');}catch(e){toast(e.message);}};
 $('exportBackup').onclick=async()=>{try{const data=SyncCore.clone(state);data.config={url:data.config.url,token:''};await nativeCall('exportBackup',{data:JSON.stringify({format:'readingdesk-mobile',version:2,created_at:new Date().toISOString(),data})});toast('请选择文件保存位置');}catch(e){toast(e.message);}};
 $('importBackup').onclick=async()=>{try{const result=await nativeCall('importBackup',{});if(result.cancelled)return;const payload=JSON.parse(result.data);if(payload.format!=='readingdesk-mobile'||payload.version!==2)throw Error('不是此版本的手机备份文件');restoreMobile(payload.data);}catch(e){toast(e.message);}};refresh();
}
/* Dictation hides the original, plays one sentence, then diffs typed words; mirrors src/dictation.py. */
function dictationTokens(text){return (text.toLowerCase().replace(/[\u2019]/g,"'").match(/[a-z][a-z'-]*|\d+(?:[.,]\d+)*/g)||[]).map(w=>w.replace(/'/g,''));}
function dictationCompare(expected,typed){
 const exp=dictationTokens(expected),typ=dictationTokens(typed),n=exp.length,m=typ.length;
 const dp=Array.from({length:n+1},()=>new Array(m+1).fill(0));
 for(let i=n-1;i>=0;i--)for(let j=m-1;j>=0;j--)dp[i][j]=exp[i]===typ[j]?dp[i+1][j+1]+1:Math.max(dp[i+1][j],dp[i][j+1]);
 const statuses=new Array(n).fill('missing'),extra=[];
 let i=0,j=0;
 while(i<n&&j<m){
  if(exp[i]===typ[j]){statuses[i]='ok';i++;j++;continue;}
  const skipExp=dp[i+1][j],skipTyp=dp[i][j+1];
  if(skipExp>skipTyp){statuses[i]='missing';i++;}
  else if(skipTyp>skipExp){extra.push(typ[j]);j++;}
  else{statuses[i]='wrong';extra.push(typ[j]);i++;j++;}
 }
 while(i<n){statuses[i]='missing';i++;}
 while(j<m){extra.push(typ[j++]);}
 const ok=statuses.filter(s=>s==='ok').length;
 return {expected:exp,statuses,extra,accuracy:n?ok/n:1};
}
function openDictation(){
 const a=article();if(!a){toast('请先打开一篇文章');return;}
 const ranges=splitSentences(a.text);if(!ranges.length){toast('这篇文章没有可用于听写的句子');return;}
 stopSequence();
 const position=selected&&selected.article_id===a.id?selected.start:0;
 const session={index:Math.max(0,ranges.findIndex(s=>s.end>position)),results:{}};
 const overlay=document.createElement('div');overlay.className='overlay';
 overlay.innerHTML='<section class="sheet"><div class="row"><h3 class="grow">听写练习</h3><button class="small" id="dictationClose">关闭</button></div><div id="dictationInfo" class="muted"></div><textarea id="dictationTyped" placeholder="听一句，敲一句；没听清的词先跳过，对照后再补。" style="min-height:90px"></textarea><div class="actions"><button class="small" id="dictationPrev">上一句</button><button class="small" id="dictationPlay">▶ 播放本句</button><button class="small primary" id="dictationCheck">对照答案</button><button class="small" id="dictationTrans">参考译文</button><button class="small" id="dictationNext">下一句 ▶</button></div><div id="dictationResult" class="muted" style="line-height:2"></div></section>';
 document.body.appendChild(overlay);
 const close=()=>{
  nativeCall('stop',{}).catch(()=>{});
  const scores=Object.values(session.results);
  if(scores.length)recordDictationStat(a.id,scores.length,scores.reduce((x,y)=>x+y,0)/scores.length);
  overlay.remove();
 };
 $('dictationClose').onclick=close;
 overlay.onclick=event=>{if(event.target===overlay)close();};
 const info=$('dictationInfo'),typed=$('dictationTyped'),result=$('dictationResult');
 function show(){typed.value='';result.innerHTML='';info.textContent='第 '+(session.index+1)+'/'+ranges.length+' 句 · 原文已隐藏，播放后听写，再对照';}
 function play(){nativeCall('speak',{text:ranges[session.index].text,...state.audio}).catch(e=>toast(e.message));}
 async function addMissedWord(word){
  const clean=SyncCore.normalizeWord(word);if(!clean)return;
  if(allWords().some(existing=>SyncCore.sameWord(existing.word,clean))){toast('“'+clean+'”已经在生词本里了');return;}
  let def=state.translations[clean]||'';
  if(!def){try{const r=await nativeCall('translate',{text:clean,url:state.config.url,token:state.config.token});def=r.text||'';}catch(e){}}
  enqueue('vocabulary_manual',{word:clean,definition:def,context:ranges[session.index].text});sync();
  toast('已将错词 “'+clean+'” 加入生词本');
 }
 function check(){const cmp=dictationCompare(ranges[session.index].text,typed.value);
  const parts=cmp.expected.map((w,idx)=>cmp.statuses[idx]==='ok'?esc(w):cmp.statuses[idx]==='wrong'?'<a href="#" data-add-word="'+esc(w)+'" style="color:#d93829;font-weight:700;text-decoration:underline">'+esc(w)+'</a>':'<a href="#" data-add-word="'+esc(w)+'" style="color:#d93829;font-weight:700;text-decoration:none">['+esc(w)+']</a>');
  session.results[session.index]=cmp.accuracy;
  const scores=Object.values(session.results);
  const avg=scores.reduce((x,y)=>x+y,0)/scores.length;
  result.innerHTML='正确答案：'+parts.join(' ')+(cmp.extra.length?'<br>多写的词：'+esc(cmp.extra.join(' ')):'')+'<br>本句准确率 <b>'+(cmp.accuracy*100).toFixed(0)+'%</b> · 已对照 '+scores.length+' 句平均 '+(avg*100).toFixed(0)+'%（点击红色词可直接加生词）';
  result.querySelectorAll('[data-add-word]').forEach(el=>el.onclick=e=>{e.preventDefault();addMissedWord(el.dataset.addWord);});
 }
 $('dictationTrans').onclick=async()=>{
  const s=ranges[session.index].text;
  let tr=state.translations[s]||'';
  if(!tr){try{const r=await nativeCall('translate',{text:s,url:state.config.url,token:state.config.token});tr=r.text||'';}catch(e){tr='翻译失败：'+e.message;}}
  result.innerHTML+='<div style="margin-top:6px">中文参考：'+esc(tr)+'</div>';
 };
 function move(direction){const target=session.index+direction;
  if(target<0)return;
  if(target>=ranges.length){const scores=Object.values(session.results);info.textContent='全文听写结束 · 已对照 '+scores.length+' 句'+(scores.length?' · 平均准确率 '+(scores.reduce((x,y)=>x+y,0)/scores.length*100).toFixed(0)+'%':'');return;}
  session.index=target;show();play();}
 $('dictationPrev').onclick=()=>move(-1);$('dictationNext').onclick=()=>move(1);
 $('dictationPlay').onclick=play;$('dictationCheck').onclick=check;
 show();
}
function initLearning(){
 applyGlobalTheme(state.display?.theme||'paper');
 $('selectionNote').onclick=saveSelectedSentence;$('lookupNote').onclick=saveSelectedSentence;
 try{const today=new Date().toISOString().slice(0,10),backups=backupList();if(!backups.some(b=>b.kind==='daily'&&b.time.startsWith(today)))backupMobile('daily');}catch(e){toast(e.message);}
}
