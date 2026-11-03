/* Learning features use the same persisted operation queue as article edits. */
'use strict';
let libraryQuery='',libraryGroup='all',reviewSession=null,noteDraft=null;
let sentenceSession=null,sentenceTimeout=null,sentencePaused=false;
function studySet(key,value,expected=state.study[key]??null){enqueue('study',{key,value,expected:SyncCore.clone(expected)});sync();}
function groups(){return Object.entries(state.study).filter(([key,value])=>key.startsWith('group:')&&value).map(([id,value])=>({id,name:value.name}));}
function metadata(a){return state.study['meta:'+a.id]||{article_id:a.id,group:'',pinned:false,read:false};}
function setMetadata(a,fields){studySet('meta:'+a.id,{...metadata(a),...fields});}
function renderLearningLibrary(){
 $('main').innerHTML='<div class="row actions"><h2 class="grow">我的文章</h2><button id="newArticle">＋ 粘贴</button></div><input id="articleQuery" placeholder="搜索标题或正文"><div class="actions"><select id="libraryGroup" style="flex:1"></select><button id="manageGroups">管理分组</button><button data-local-page="backups">资料备份</button></div><div id="articleCards"></div>';
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
  const m=metadata(a);return '<section class="card"><div class="row"><div class="grow"><div class="title">'+(m.pinned?'★ ':'')+esc(a.title)+(m.read?' ✓':'')+'</div><div class="muted">'+esc(groupMap.get(m.group)||'未分组')+' · '+Array.from(a.text).length+' 字符 · '+a.annotations.length+' 处划线 · '+a.vocabulary.length+' 条生词</div></div><button class="small articleMore" data-id="'+esc(a.id)+'">整理</button></div><p class="muted">'+esc(a.text.slice(0,100))+'…</p><button class="primary openArticle" data-id="'+esc(a.id)+'">继续阅读</button></section>';
 }).join('')||'<div class="empty">没有符合条件的文章。</div>';
 document.querySelectorAll('.openArticle').forEach(b=>b.onclick=()=>navigate('read',b.dataset.id));
 document.querySelectorAll('.articleMore').forEach(b=>b.onclick=()=>articleOptions(b.dataset.id));
}
function articleOptions(id){
 const a=state.articles.find(a=>a.id===id),m=metadata(a);
 const overlay=document.createElement('div');overlay.className='overlay';
 overlay.innerHTML='<section class="sheet"><h3>'+esc(a.title)+'</h3><label>分组</label><select id="articleGroup"><option value="">未分组</option>'+groups().map(g=>'<option value="'+esc(g.id)+'">'+esc(g.name)+'</option>').join('')+'</select><div class="actions"><button id="saveGroup">保存分组</button><button id="togglePin">'+(m.pinned?'取消置顶':'置顶')+'</button><button id="toggleRead">'+(m.read?'标为未读':'标为已读')+'</button><button id="renameArticle">重命名</button><button id="closeOptions">关闭</button></div></section>';
 document.body.appendChild(overlay);$('articleGroup').value=m.group;
 const close=()=>{overlay.remove();renderArticleCards();};
 $('saveGroup').onclick=()=>{setMetadata(a,{group:$('articleGroup').value});close();};
 $('togglePin').onclick=()=>{setMetadata(a,{pinned:!m.pinned});close();};
 $('toggleRead').onclick=()=>{setMetadata(a,{read:!m.read});close();};
 $('renameArticle').onclick=()=>{overlay.remove();rename(id);};$('closeOptions').onclick=close;
 overlay.onclick=e=>{if(e.target===overlay)close();};
}
function manageMobileGroups(){
 const overlay=document.createElement('div');overlay.className='overlay';
 function refresh(){overlay.innerHTML='<section class="sheet"><h3>文章分组</h3><div id="groupsList">'+groups().map(g=>'<div class="row actions"><span class="grow">'+esc(g.name)+'</span><button data-rename-group="'+esc(g.id)+'">改名</button><button data-delete-group="'+esc(g.id)+'">删除</button></div>').join('')+'</div><div class="actions"><button id="addGroup">新建分组</button><button id="closeGroups">完成</button></div></section>';
  $('addGroup').onclick=()=>edit(null);$('closeGroups').onclick=()=>{overlay.remove();renderLearningLibrary();};
  overlay.querySelectorAll('[data-rename-group]').forEach(b=>b.onclick=()=>edit(b.dataset.renameGroup));
  overlay.querySelectorAll('[data-delete-group]').forEach(b=>b.onclick=()=>{if(confirm('删除分组后，文章仍保留并显示为未分组。继续？')){studySet(b.dataset.deleteGroup,null);refresh();}});
 }
 function edit(key){const name=prompt('分组名称（最多60字）',key?state.study[key].name:'');if(name===null)return;if(!name.trim()||name.trim().length>60){toast('请输入1–60字的分组名称');return;}if(groups().some(g=>g.id!==key&&g.name.toLowerCase()===name.trim().toLowerCase())){toast('已存在同名分组');return;}studySet(key||'group:'+uuid(),{name:name.trim()});refresh();}
 document.body.appendChild(overlay);refresh();
}
function allWords(){return state.articles.flatMap(a=>a.vocabulary.map(w=>({...w,article_id:a.id,article_title:a.title,key:'review:'+a.id+':'+w.start+':'+w.end})));}
function renderReview(){
 if(!reviewSession)reviewSession={all:false,queue:allWords().filter(w=>!state.study[w.key]||Date.parse(state.study[w.key].due)<=Date.now()),done:0};
 const card=reviewSession.queue[0];
 $('main').innerHTML='<div class="actions"><button id="reviewBack">返回生词本</button><button id="reviewAll">'+(reviewSession.all?'只复习到期词':'练习全部生词')+'</button></div><div class="muted">剩余 '+reviewSession.queue.length+' 条 · 本轮已复习 '+reviewSession.done+' 条</div>'+(card?'<section class="card"><div class="reviewWord">'+esc(card.word)+'</div><div class="muted">来源：'+esc(card.article_title)+'</div><p class="reviewContext">'+esc(card.context)+'</p><div class="actions"><button id="cardSound">▶ 发音</button><button id="cardOriginal">回原文</button><button id="revealCard" class="primary">显示释义</button></div><div id="cardAnswer" hidden class="noteText">'+esc(card.definition)+'</div><div id="cardGrades" class="actions" hidden><button data-grade="again">不认识 · 10分钟</button><button data-grade="hard">模糊 · 1天</button><button data-grade="known">认识 · 延长间隔</button></div></section>':'<section class="card"><h2>本轮复习完成</h2><p>未到期的词会在到期后出现，也可以练习全部生词。</p></section>')+'<p class="muted">认识：首次3天，再按上次间隔翻倍，最多365天。复习结果可与电脑同步。</p>';
 $('reviewBack').onclick=()=>navigate('vocabulary');$('reviewAll').onclick=()=>{const all=!reviewSession.all;reviewSession={all,queue:allWords().filter(w=>all||!state.study[w.key]||Date.parse(state.study[w.key].due)<=Date.now()),done:0};renderReview();};
 if(!card)return;
 $('cardSound').onclick=()=>speak(card.word);$('cardOriginal').onclick=()=>jumpMobile(card.article_id,card.start,card.end);
 $('revealCard').onclick=()=>{$('cardAnswer').hidden=false;$('cardGrades').hidden=false;};
 document.querySelectorAll('[data-grade]').forEach(b=>b.onclick=()=>{
  const grade=b.dataset.grade,previous=state.study[card.key]||{},interval=grade==='again'?0:grade==='hard'?1:Math.min(365,Math.max(3,(previous.interval||0)*2));
  studySet(card.key,{article_id:card.article_id,start:card.start,end:card.end,grade,interval,due:new Date(Date.now()+(grade==='again'?600000:interval*86400000)).toISOString(),count:(previous.count||0)+1});
  reviewSession.queue.shift();reviewSession.done++;renderReview();
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
 $('main').innerHTML='<h2>句子收藏与笔记</h2><input id="notesSearch" placeholder="搜索原文、译文、笔记或文章"><div id="noteCards" style="margin-top:16px"></div>';
 function refresh(){const query=$('notesSearch').value.toLowerCase(),articles=new Map(state.articles.map(a=>[a.id,a]));
  const notes=Object.entries(state.study).filter(([key,n])=>key.startsWith('note:')&&n&&articles.has(n.article_id)&&(!query||[n.text,n.translation,n.note,articles.get(n.article_id).title].join(' ').toLowerCase().includes(query)));
  $('noteCards').innerHTML=notes.map(([key,n])=>'<section class="card"><div class="muted">'+esc(articles.get(n.article_id).title)+'</div><p class="noteText">'+esc(n.text)+'</p><div class="noteText">'+esc(n.translation)+'</div><p class="muted noteText">笔记：'+esc(n.note)+'</p><div class="actions"><button data-edit-note="'+esc(key)+'">编辑</button><button data-speak-note="'+esc(key)+'">▶ 朗读</button><button data-jump-note="'+esc(key)+'">回原文</button><button data-delete-note="'+esc(key)+'">删除</button></div></section>').join('')||'<div class="empty">阅读时选中句段，点击“收藏句段”。</div>';
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
/* Listening marks and dictation stay in localStorage only; they never enter the sync outbox. */
function listeningLoad(){try{const data=JSON.parse(localStorage.getItem('listening-v1')||'{}');return data&&typeof data==='object'&&!Array.isArray(data)?data:{};}catch(e){return {};}}
function listeningSave(data){try{localStorage.setItem('listening-v1',JSON.stringify(data));}catch(e){toast('本机存储空间不足，这次标记没有保存');}}
function listeningStatus(articleId,start,end,text){const record=(listeningLoad()[articleId]||{})[start+':'+end];return record&&record.text===text?record.status:null;}
function listeningMark(articleId,start,end,text,status){const data=listeningLoad(),records=data[articleId]||{};
 if(status===null)delete records[start+':'+end];else records[start+':'+end]={text,status,updated:new Date().toISOString()};
 data[articleId]=records;listeningSave(data);}
function listeningMissed(articleId,ranges){const marks=listeningLoad()[articleId]||{},result=[];
 ranges.forEach((s,i)=>{const record=marks[s.start+':'+s.end];if(record&&record.status==='missed'&&record.text===s.text)result.push(i);});return result;}
function sentenceOrder(ranges){if(!$('replayMissedOnly')||!$('replayMissedOnly').checked)return ranges.map((_,i)=>i);
 const order=listeningMissed(activeId,ranges);return order.length?order:ranges.map((_,i)=>i);}
function updateMissedCount(){if(!$('missedCount'))return;const a=article();
 $('missedCount').textContent=a?'没听懂 '+listeningMissed(a.id,splitSentences(a.text)).length+' 句':'';}
function currentSentenceRange(){const a=article();if(!a)return null;
 if(sentenceSession&&sentenceSession.ranges[sentenceSession.index])return sentenceSession.ranges[sentenceSession.index];
 const ranges=splitSentences(a.text),position=selected&&selected.article_id===a.id?selected.start:0;
 return ranges.find(s=>s.end>position)||ranges[0]||null;}
function markCurrentSentence(status){const s=currentSentenceRange();if(!s)return;
 const after=listeningStatus(activeId,s.start,s.end,s.text)===status?null:status;
 listeningMark(activeId,s.start,s.end,s.text,after);
 const label={'heard':'已标记听懂','missed':'已标记没听懂',null:'已清除标记'}[after];
 $('sentenceStatus').textContent='当前句 · '+label;updateMissedCount();}
function installSentenceControls(){
 $('sentenceControls').className='sentenceControls';
 $('sentenceControls').innerHTML='<div class="actions"><button id="sentencePrevious" class="small">上一句</button><button id="sentencePlay" class="small">▶ 逐句</button><button id="sentenceNext" class="small">下一句</button><button id="saveCurrentSentence" class="small">收藏当前句</button></div><div class="actions"><select id="sentenceMode"><option value="all">逐句继续</option><option value="one">仅当前句</option></select><input id="sentenceRepeat" type="number" value="1" min="1" max="99" aria-label="每句次数"><span class="muted">遍</span><input id="sentenceGap" type="number" value="1" min="0" max="30" step="0.5" aria-label="句间停顿秒"><span class="muted">秒停顿</span></div><div class="actions"><button id="markHeard" class="small">✓ 听懂</button><button id="markMissed" class="small">✗ 没听懂</button><label class="row" style="gap:6px"><input id="replayMissedOnly" type="checkbox" style="width:auto"><span class="muted">只重听没听懂句</span></label><button id="openDictation" class="small">⌨ 听写</button><span id="missedCount" class="muted"></span></div><div id="sentenceStatus" class="muted">选择句段后可从该句开始，或点“逐句”从开头开始。</div>';
 $('sentencePlay').onclick=()=>beginSentence();$('sentencePrevious').onclick=()=>stepSentence(-1);$('sentenceNext').onclick=()=>stepSentence(1);
 $('markHeard').onclick=()=>markCurrentSentence('heard');$('markMissed').onclick=()=>markCurrentSentence('missed');
 $('replayMissedOnly').onchange=updateMissedCount;$('openDictation').onclick=openDictation;
 updateMissedCount();
 $('saveCurrentSentence').onclick=()=>{const s=sentenceSession?.ranges[sentenceSession.index]||splitSentences(article().text).find(s=>s.end>(selected?.start||0));if(!s)return;selected={article_id:activeId,start:s.start,end:s.end,word:s.text};currentDefinition='';saveSelectedSentence();};
}
function highlightSentence(start,end){document.querySelectorAll('#readingArea .token').forEach(t=>t.classList.toggle('speaking',+t.dataset.start<end&&+t.dataset.end>start));}
function stopSequence(){
 if(sentenceTimeout!==null){clearTimeout(sentenceTimeout);sentenceTimeout=null;}
 sentenceSession=null;sentencePaused=false;document.querySelectorAll('#readingArea .speaking').forEach(t=>t.classList.remove('speaking'));
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
 highlightSentence(s.start,s.end);const first=Array.from(document.querySelectorAll('#readingArea .token')).find(t=>+t.dataset.end>s.start);if(first)first.scrollIntoView({block:'center',behavior:'smooth'});
 $('sentenceStatus').textContent='第 '+(session.index+1)+'/'+session.ranges.length+' 句 · 第 '+(session.round+1)+'/'+repeat+' 遍';
 session.id=uuid();nativeCall('speak',{text:s.text,...state.audio,request_id:session.id}).catch(e=>{stopSequence();toast(e.message);});
}
window.nativeSpeechDone=(id,error)=>{
 const session=sentenceSession;if(!session||session.id!==id)return;
 if(error){stopSequence();toast(error);return;}
 session.round++;const repeat=Math.max(1,Math.min(99,Number($('sentenceRepeat').value)||1));
  if(session.round>=repeat){const pos=session.order.indexOf(session.index);if($('sentenceMode').value==='one'||pos+1>=session.order.length){stopSequence();$('sentenceStatus').textContent='逐句朗读完成';return;}session.index=session.order[pos<0?0:pos+1];session.round=0;}
 const gap=Math.max(0,Math.min(30,Number($('sentenceGap').value)||0));
 sentenceTimeout=setTimeout(()=>{sentenceTimeout=null;playSentence();},gap*1000);
};
function pauseLearningSpeech(){
 if(sentenceTimeout!==null){clearTimeout(sentenceTimeout);sentenceTimeout=null;sentencePaused=true;toast('已暂停句间等待');return;}
 if(sentencePaused){sentencePaused=false;playSentence();return;}
 nativeCall('pause',{}).catch(e=>toast(e.message));
}
function displayStyle(element,options){
 const themes={paper:['#fff9ed','#302b25','255,249,237'],light:['#ffffff','#203044','255,255,255'],green:['#e5efdf','#243829','229,239,223'],dark:['#202733','#dde5f0','32,39,51']},theme=themes[options.theme]||themes.paper;
 element.style.fontSize=options.size+'px';element.style.lineHeight=options.line;element.style.padding=options.margin+'px';element.style.color=theme[1];element.style.backgroundColor=theme[0];
 const opacity=Math.max(0,Math.min(65,Number(options.opacity)))/100;
 element.style.backgroundImage=options.image&&/^data:image\/(jpeg|png);base64,/.test(options.image)?'linear-gradient(rgba('+theme[2]+','+(1-opacity)+'),rgba('+theme[2]+','+(1-opacity)+')),url("'+options.image+'")':'none';element.style.backgroundSize='cover';element.style.backgroundPosition='center';
}
function applyReaderDisplay(){if($('readingArea'))displayStyle($('readingArea'),state.display);$('main').style.maxWidth=state.display.width+'px';}
function renderDisplaySettings(){
 let draft={...state.display};
 $('main').innerHTML='<h2>阅读显示与背景图</h2><section class="card"><label>字号（14–36）</label><input id="displaySize" type="number" min="14" max="36"><label>行距（1.1–2.5）</label><input id="displayLine" type="number" min="1.1" max="2.5" step="0.1"><label>正文最大宽度（320–1100像素）</label><input id="displayWidth" type="number" min="320" max="1100"><label>阅读边距（8–50）</label><input id="displayMargin" type="number" min="8" max="50"><label>配色</label><select id="displayTheme"><option value="paper">暖纸色</option><option value="light">白色</option><option value="green">浅绿色</option><option value="dark">深色</option></select><label>背景图可见度（0–65%）</label><input id="displayOpacity" type="range" min="0" max="65"><div class="actions"><button id="chooseBackground">选自己的背景图</button><button id="clearBackground">移除图片</button></div><div id="displayPreview" class="preview">Reading makes the world a little wider.\n阅读，让世界更宽一点。</div><div class="actions"><button id="saveDisplay" class="primary">保存设置</button><button id="backupPage">资料备份与恢复</button></div><p class="muted">背景图复制到本机，设置各设备独立保存。预览不会修改文章文字和划线位置。</p></section>';
 const controls=[['displaySize','size',14,36],['displayLine','line',1.1,2.5],['displayWidth','width',320,1100],['displayMargin','margin',8,50],['displayOpacity','opacity',0,65]];
 function preview(){for(const[id,key,min,max]of controls)draft[key]=Math.max(min,Math.min(max,Number($(id).value)||min));draft.theme=$('displayTheme').value;displayStyle($('displayPreview'),draft);}
 for(const[id,key]of controls){$(id).value=draft[key];$(id).oninput=preview;}$('displayTheme').value=draft.theme;$('displayTheme').onchange=preview;
 $('chooseBackground').onclick=async()=>{try{const result=await nativeCall('chooseBackground',{});if(!result.cancelled){draft.image=result.image;preview();}}catch(e){toast(e.message);}};
 $('clearBackground').onclick=()=>{draft.image='';preview();};
 $('saveDisplay').onclick=()=>{preview();const previous=state.display;state.display=draft;try{save();toast('阅读设置已保存');}catch(e){state.display=previous;}};
 $('backupPage').onclick=()=>navigate('backups');preview();
}
function backupList(){try{return JSON.parse(localStorage.getItem('reader-backups-v1')||'[]');}catch(e){throw Error('本机备份列表无法读取，已保留原文件');}}
function backupMobile(kind='manual'){
 const backups=backupList(),snapshot={id:uuid(),time:new Date().toISOString(),kind,data:SyncCore.clone(state)};
 backups.unshift(snapshot);
 // Keep local snapshots bounded; the backup screen supports independent file export.
 while(backups.length>7)backups.pop();
 try{localStorage.setItem('reader-backups-v1',JSON.stringify(backups));}catch(e){throw Error('备份空间不足，请先导出备份文件再释放空间；没有替换当前资料');}
 return snapshot;
}
function backupCounts(data){return data.articles.length+'篇文章 · '+data.articles.reduce((sum,a)=>sum+a.annotations.length,0)+'处划线 · '+data.articles.reduce((sum,a)=>sum+a.vocabulary.length,0)+'条生词 · '+Object.entries(data.study||{}).filter(([k,v])=>k.startsWith('note:')&&v).length+'条收藏';}
function validateBackup(data){
 if(!data||!Array.isArray(data.articles)||!Array.isArray(data.outbox)||!data.config||typeof data.client_id!=='string'||data.articles.length>10000||data.outbox.length>50000)throw Error('不是有效的阅读器备份');
 const ids=new Set();for(const a of data.articles){if(!a||typeof a.id!=='string'||ids.has(a.id)||typeof a.title!=='string'||typeof a.text!=='string'||!Array.isArray(a.annotations)||!Array.isArray(a.vocabulary))throw Error('备份文章结构不完整');ids.add(a.id);const text=Array.from(a.text);for(const mark of [...a.annotations,...a.vocabulary])if(!Number.isInteger(mark.start)||!Number.isInteger(mark.end)||mark.start<0||mark.end>text.length||mark.end<=mark.start||text.slice(mark.start,mark.end).join('')!==mark.word)throw Error('备份标记位置与原文不符');}
 if(state.instance&&data.instance&&state.instance!==data.instance)throw Error('备份属于其他电脑的资料库，已阻止覆盖当前手机资料');
 if(data.study&&(typeof data.study!=='object'||Array.isArray(data.study)))throw Error('学习记录格式不正确');
 return data;
}
function restoreMobile(data){
 validateBackup(data);if(busy){toast('正在同步，请同步结束后再恢复');return;}
 if(!confirm('恢复为这份备份？\n'+backupCounts(data)+'\n\n会先保存当前资料副本。恢复后的待同步修改会继续发送给电脑。'))return;
 backupMobile('before-restore');const previous=state,next=SyncCore.clone(data);next.config=previous.config.token?previous.config:next.config;next.study=next.study||{};next.display=next.display||previous.display;next.audio=next.audio||previous.audio;next.translations=next.translations||{};next.errors=[];next.conflicts=next.conflicts||[];
 state=next;try{save();}catch(e){state=previous;throw e;}stopLearningSpeech();lastSync='';navigate('articles');toast('已恢复手机本机资料；联网同步会按电脑当前资料与待传操作合并');
}
function renderBackups(){
 $('main').innerHTML='<h2>手机资料备份与恢复</h2><section class="card"><p>当前：'+esc(backupCounts(state))+'</p><div class="actions"><button id="makeBackup">立即备份到本机</button><button id="exportBackup">导出备份文件</button><button id="importBackup">选择文件恢复</button></div><p class="muted">每天首次打开自动保存快照，最多保留7份本机快照。完整文件可另存到你选择的位置。手机备份格式为JSON，电脑备份为SQLite，请分别使用。\n手机恢复只影响本机；再次联网会与电脑合并，不能用它撤销电脑上的数据。</p></section><div id="backupCards"></div>';
 function refresh(){const backups=backupList();$('backupCards').innerHTML=backups.map((b,i)=>'<section class="card"><div class="title">'+esc(new Date(b.time).toLocaleString())+'</div><p>'+esc(backupCounts(b.data))+'</p><p class="muted">'+esc(b.data.articles.map(a=>a.title).join('、'))+'</p><button data-restore-backup="'+i+'">恢复这份快照</button></section>').join('');document.querySelectorAll('[data-restore-backup]').forEach(b=>b.onclick=()=>{try{restoreMobile(backups[+b.dataset.restoreBackup].data);}catch(e){toast(e.message);}});}
 $('makeBackup').onclick=()=>{try{backupMobile();refresh();toast('备份已保存');}catch(e){toast(e.message);}};
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
 const session={index:Math.max(0,ranges.findIndex(s=>s.end>position)),results:[]};
 const overlay=document.createElement('div');overlay.className='overlay';
 overlay.innerHTML='<section class="sheet"><div class="row"><h3 class="grow">听写练习</h3><button class="small" id="dictationClose">关闭</button></div><div id="dictationInfo" class="muted"></div><textarea id="dictationTyped" placeholder="听一句，敲一句；没听清的词先跳过，对照后再补。" style="min-height:90px"></textarea><div class="actions"><button class="small" id="dictationPrev">上一句</button><button class="small" id="dictationPlay">▶ 播放本句</button><button class="small" id="dictationCheck">对照答案</button><button class="small primary" id="dictationNext">下一句 ▶</button></div><div id="dictationResult" class="muted" style="line-height:2"></div></section>';
 document.body.appendChild(overlay);
 const close=()=>overlay.remove();
 $('dictationClose').onclick=close;
 overlay.onclick=event=>{if(event.target===overlay)close();};
 const info=$('dictationInfo'),typed=$('dictationTyped'),result=$('dictationResult');
 function show(){typed.value='';result.innerHTML='';info.textContent='第 '+(session.index+1)+'/'+ranges.length+' 句 · 原文已隐藏，播放后听写，再对照';}
 function play(){nativeCall('speak',{text:ranges[session.index].text,...state.audio}).catch(e=>toast(e.message));}
 function check(){const cmp=dictationCompare(ranges[session.index].text,typed.value);
  const parts=cmp.expected.map((w,idx)=>cmp.statuses[idx]==='ok'?esc(w):cmp.statuses[idx]==='wrong'?'<b style="color:#c0392b;text-decoration:underline">'+esc(w)+'</b>':'<b style="color:#c0392b">['+esc(w)+']</b>');
  session.results.push(cmp.accuracy);
  const avg=session.results.reduce((x,y)=>x+y,0)/session.results.length;
  result.innerHTML='正确答案：'+parts.join(' ')+(cmp.extra.length?'<br>多写的词：'+esc(cmp.extra.join(' ')):'')+'<br>本句准确率 '+(cmp.accuracy*100).toFixed(0)+'% · 已对照 '+session.results.length+' 句平均 '+(avg*100).toFixed(0)+'%（红=写错，[红]=漏写）';}
 function move(direction){const target=session.index+direction;
  if(target<0)return;
  if(target>=ranges.length){info.textContent='全文听写结束 · 已对照 '+session.results.length+' 句'+(session.results.length?' · 平均准确率 '+(session.results.reduce((x,y)=>x+y,0)/session.results.length*100).toFixed(0)+'%':'');return;}
  session.index=target;show();play();}
 $('dictationPrev').onclick=()=>move(-1);$('dictationNext').onclick=()=>move(1);
 $('dictationPlay').onclick=play;$('dictationCheck').onclick=check;
 show();
}
function initLearning(){
 $('selectionNote').onclick=saveSelectedSentence;$('lookupNote').onclick=saveSelectedSentence;
 try{const today=new Date().toISOString().slice(0,10),backups=backupList();if(!backups.some(b=>b.kind==='daily'&&b.time.startsWith(today)))backupMobile('daily');}catch(e){toast(e.message);}
}
