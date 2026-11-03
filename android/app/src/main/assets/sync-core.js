(function(root){
'use strict';
function clone(value){return JSON.parse(JSON.stringify(value));}
function apply(articles,op,study){
 if(op.type==='study'){if(study)study[op.key]=clone(op.value);return;}
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
 if(op.type==='vocabulary'&&!a.vocabulary.some(x=>x.start===op.start&&x.end===op.end))
  a.vocabulary.push({start:op.start,end:op.end,word:op.word,definition:op.definition,context:op.context||''});
}
function merge(state,response){
 if(state.instance&&state.instance!==response.instance)throw Error('电脑身份不同，已阻止覆盖本地数据');
 const acknowledgements=new Map(response.acknowledgements.map(x=>[x.id,x]));
 const next=clone(state);
 next.outbox=state.outbox.filter(x=>!acknowledgements.get(x.id)?.ok);
 next.errors=response.acknowledgements.filter(x=>x.error);
 next.instance=response.instance;
 next.articles=clone(response.articles);
 next.study=clone(response.study||state.study||{});
 next.conflicts=clone(response.conflicts);
 for(const op of next.outbox)apply(next.articles,op,next.study);
 return next;
}
const api={apply,merge,clone};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
else root.SyncCore=api;
})(typeof globalThis!=='undefined'?globalThis:this);
