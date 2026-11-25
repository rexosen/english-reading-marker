(function(root){
'use strict';
function clone(value){return JSON.parse(JSON.stringify(value));}
// Same wording normalisation the desktop uses, so "in   demand" and "in demand" are one entry.
function normalizeWord(value){return String(value??'').replace(/\s+/g,' ').trim();}
function sameWord(left,right){return normalizeWord(left).toLowerCase()===normalizeWord(right).toLowerCase();}
function apply(articles,op,study,manual){
 if(op.type==='study'){if(study)study[op.key]=clone(op.value);return;}
 if(op.type==='vocabulary_manual'||op.type==='vocabulary_manual_remove'){
  if(!manual)return;
  if(op.type==='vocabulary_manual'){
   const clean=normalizeWord(op.word),oldClean=op.old_word?normalizeWord(op.old_word):'';
   const existing=manual.find(x=>sameWord(x.word,clean));
   const oldEntry=oldClean&&!sameWord(oldClean,clean)?manual.find(x=>sameWord(x.word,oldClean)):null;
   if(oldEntry&&!existing){
    oldEntry.word=clean;oldEntry.definition=op.definition||'';oldEntry.context=op.context||'';
   }else if(existing){
    existing.word=clean;existing.definition=op.definition||'';existing.context=op.context||'';
    if(oldEntry){const idx=manual.indexOf(oldEntry);if(idx>=0)manual.splice(idx,1);}
   }else{
    manual.push({word:clean,definition:op.definition||'',context:op.context||''});
   }
  }else{
   for(let index=manual.length-1;index>=0;index--)if(sameWord(manual[index].word,op.word))manual.splice(index,1);
  }
  return;
 }
 if(op.type==='delete'){
  const idx=articles.findIndex(a=>a.id===op.article_id);
  if(idx>=0)articles.splice(idx,1);
  if(study){
   delete study['meta:'+op.article_id];
   const prefix='review:'+op.article_id+':';
   for(const key of Object.keys(study))if(key.startsWith(prefix))delete study[key];
  }
  return;
 }
 let a=articles.find(a=>a.id===op.article_id);
 if(op.type==='create'){
  if(!a)articles.unshift({id:op.article_id,title:op.title,text:op.text,title_version:1,annotations:[],vocabulary:[],progress:0});
  return;
 }
 if(!a)return;
 if(op.type==='rename'&&a.title!==op.title){a.title=op.title;a.title_version++;}
 if(op.type==='progress')a.progress=op.offset;
 if(op.type==='underline'){
  a.annotations=a.annotations.filter(x=>!(x.start===op.start&&x.end===op.end));
  if(op.active)a.annotations.push({start:op.start,end:op.end,word:op.word});
 }
 if(op.type==='vocabulary_remove')a.vocabulary=a.vocabulary.filter(x=>!(x.start===op.start&&x.end===op.end));
 if(op.type==='vocabulary'&&!a.vocabulary.some(x=>x.start===op.start&&x.end===op.end))
  a.vocabulary.push({start:op.start,end:op.end,word:op.word,definition:op.definition,context:op.context||''});
}
function merge(state,response){
 if(state.instance&&state.instance!==response.instance)throw Error('电脑身份不同，已阻止覆盖本地数据');
 const next=clone(state);
 if(typeof response.revision==='number')next.revision=response.revision;
 if(response.unchanged){next.instance=response.instance;return next;}
 const acknowledgements=new Map((response.acknowledgements||[]).map(x=>[x.id,x]));
 next.outbox=state.outbox.filter(x=>!acknowledgements.get(x.id)?.ok);
 next.errors=(response.acknowledgements||[]).filter(x=>x.error);
 next.instance=response.instance;
 next.articles=clone(response.articles);
 next.study=clone(response.study||state.study||{});
 // Hand-written words and phrases live outside articles; older desktops simply omit the key.
 next.vocabulary_manual=clone(response.vocabulary_manual||state.vocabulary_manual||[]);
 next.conflicts=clone(response.conflicts);
 for(const op of next.outbox)apply(next.articles,op,next.study,next.vocabulary_manual);
 return next;
}
const api={apply,merge,clone,normalizeWord,sameWord};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
else root.SyncCore=api;
})(typeof globalThis!=='undefined'?globalThis:this);
