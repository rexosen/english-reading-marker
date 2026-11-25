/* Node-only checks for the Android vocabulary book (no browser needed).
   Run: node tests/mobile_vocabulary.test.cjs */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const SyncCore=require('../android/app/src/main/assets/sync-core.js');
const assets=path.resolve(__dirname,'../android/app/src/main/assets');

function makeWorld(initial){
 const context={console,SyncCore,Math,Date,Number,String,Object,Array,JSON,RegExp,Uint8Array,encodeURIComponent,isNaN,parseInt,
  window:{},document:{addEventListener(){},querySelectorAll:()=>[],getElementById:()=>null,createElement:()=>({style:{},classList:{toggle(){}}}),body:{appendChild(){}}},
  localStorage:{getItem:()=>null,setItem(){}},setTimeout:()=>0,alert(){},navigator:{}},
  ops=[],syncCalls=[];
 context.uuid=(()=>{let n=0;return()=>'g'+(++n);})();
 context.state=initial;
 context.enqueue=(type,fields)=>{const op={id:'op'+(ops.length+1),type,...fields};ops.push(op);SyncCore.apply(context.state.articles,op,context.state.study,context.state.vocabulary_manual);return op;};
 context.sync=()=>{syncCalls.push(true);};
 context.toast=()=>{};
 context.save=()=>{};
 context.prompt=()=>null;
 context.confirm=()=>true;
 context.ops=ops;context.syncCalls=syncCalls;
 const sandbox=vm.createContext(context);
 vm.runInContext(fs.readFileSync(path.join(assets,'learning.js'),'utf8'),sandbox);
 return sandbox;
}

const world=()=>makeWorld({client_id:'c',instance:'test',articles:[
 {id:'a1',title:'阅读:在线课程的局限',title_version:1,text:'Online classes are compatible.',progress:0,annotations:[],
  vocabulary:[{start:20,end:31,word:'compatible',definition:'能共处的',context:'Online classes are compatible.'}]},
 {id:'a2',title:'听力:非洲简界智能手机',title_version:1,text:'These devices are genuinely cheap.',annotations:[],progress:0,
  vocabulary:[{start:18,end:28,word:'genuinely',definition:'真正地',context:'These devices are genuinely cheap.'}]},
 {id:'a3',title:'无前缀文章',text:'Students learn.',annotations:[],vocabulary:[],progress:0}],
 outbox:[],conflicts:[],errors:[],study:{},vocabulary_manual:[],config:{},translations:{},display:{},audio:{}});

let passed=0;
// vm 里创建的对象带着沙箱原型，比较前先转成宿主结构
const plain=value=>JSON.parse(JSON.stringify(value));
function check(name,body){body();passed++;console.log('ok   '+name);}

check('pyQuote matches Python quote(safe="") on awkward wording',()=>{
 // 这些期望值由桌面 .venv 的 urllib.parse.quote(word.casefold(), safe='') 实算得到
 const expect={'don’t':"don%E2%80%99t",'don\'t':'don%27t','in demand':'in%20demand','e.g.':'e.g.','a-b~c':'a-b~c',
  'what (really)!':'what%20%28really%29%21','take over*':'take%20over%2A','x_y.z~1':'x_y.z~1','50%':'50%25','A+B':'a%2Bb'};
 const context=makeWorld({study:{},articles:[],vocabulary_manual:[]});
 for(const [word,key]of Object.entries(expect))assert.equal(vm.runInContext(`vocabWordKey(${JSON.stringify(word)})`,context),`vcat:${key}`,word);
});

check('built-in categories come first and custom ones follow',()=>{
 const w=world();
 assert.deepEqual(plain(vm.runInContext('vocabCategories()',w)),[{key:'vgroup:auto:listening',name:'听力'},{key:'vgroup:auto:reading',name:'阅读'}]);
 vm.runInContext('studySet("vgroup:x1",{name:"必背"})',w);
 assert.equal(w.state.study['vgroup:x1'].name,'必背');
 assert.deepEqual(plain(vm.runInContext('vocabCategories().map(g=>g.name)',w)),['听力','阅读','必背']);
 assert.equal(vm.runInContext('vocabCategoryName("vgroup:auto:reading")',w),'阅读');
});

check('titles and group names decide the automatic category',()=>{
 const w=world();
 const auto=(title,group)=>vm.runInContext(`vocabAutoCategory(${JSON.stringify(title)},${JSON.stringify(group||'')})`,w);
 assert.equal(auto('听力:Section C'),'vgroup:auto:listening');
 assert.equal(auto('阅读：课程局限'),'vgroup:auto:reading');
 assert.equal(auto('Listening:  Short News'),'vgroup:auto:listening');
 assert.equal(auto('Reading Section B'),'');
 assert.equal(auto('无前缀文章'),'');
 assert.equal(auto('无前缀文章','听力'),'vgroup:auto:listening');
 assert.equal(auto('无前缀文章',' 阅 读 '),'vgroup:auto:reading');
 assert.equal(auto('无前缀文章','必背'),'');
});

check('manual assignment wins over the article rule',()=>{
 const w=world();
 assert.equal(vm.runInContext('vocabCategoryOf("compatible",state.articles[0])',w),'vgroup:auto:reading');
 vm.runInContext('studySet("vgroup:x1",{name:"必背"})',w);
 vm.runInContext('vocabAssign("Compatible","vgroup:x1")',w);
 assert.equal(w.state.study['vcat:compatible'].group,'vgroup:x1');
 assert.equal(vm.runInContext('vocabCategoryOf("compatible",state.articles[0])',w),'vgroup:x1');
 // a record pointing at a category that no longer exists falls back to the article rule
 const stale=makeWorld({study:{'vcat:compatible':{word:'compatible',group:'vgroup:gone'}},articles:[],vocabulary_manual:[]});
 assert.equal(vm.runInContext('vocabCategoryOf("compatible",{title:"阅读:课程局限",group_name:""})',stale),'vgroup:auto:reading');
});

check('allWords merges article words with hand-written phrases',()=>{
 const w=world();
 w.state.vocabulary_manual=[{id:77,word:'in demand',definition:'有需求的',context:'Jobs are in demand.'},
  {word:'take over',definition:'接管',context:''}];
 vm.runInContext('studySet("vgroup:x1",{name:"必背"});studySet(vocabWordKey("take over"),{word:"take over",group:"vgroup:x1"})',w);
 const words=vm.runInContext('allWords()',w);
 const byWord=new Map(words.map(w2=>[w2.word,w2]));
 assert.equal(words.length,4);
 assert.equal(byWord.get('compatible').category,'vgroup:auto:reading');
 assert.equal(byWord.get('genuinely').category,'vgroup:auto:listening');
 assert.equal(byWord.get('in demand').manual,true);
 assert.equal(byWord.get('in demand').key,'review:manual:77');
 assert.equal(byWord.get('in demand').category,'');
 assert.equal(byWord.get('take over').category,'vgroup:x1');
 assert.match(byWord.get('take over').key,/^review:local:/);
});

check('category management protects the built-ins',()=>{
 const w=world();
 assert.equal(vm.runInContext('vocabCreateCategory(" 必  背 ")',w),'vgroup:g1');
 assert.equal(w.state.study['vgroup:g1'].name,'必 背','与桌面 display_name 一致：折叠重复空格');
 assert.equal(vm.runInContext('vocabCreateCategory("听力")',w),'vgroup:auto:listening');
 assert.equal(vm.runInContext('vocabDeleteCategory("vgroup:auto:reading")',w),false);
 vm.runInContext('vocabAssign("compatible","vgroup:g1")',w);
 assert.equal(vm.runInContext('vocabDeleteCategory("vgroup:g1")',w),true);
 assert.equal(w.state.study['vgroup:g1'],null);
 assert.equal(w.state.study[vm.runInContext('vocabWordKey("compatible")',w)],null);
});

check('sync core applies manual vocabulary operations',()=>{
 const articles=[],study={},manual=[];
 SyncCore.apply(articles,{type:'vocabulary_manual',word:'  in   demand ',definition:'有需求的',context:'Jobs are in demand.'},study,manual);
 // Editing an existing manual entry (same word case-insensitively) updates it in-place without duplicating.
 SyncCore.apply(articles,{type:'vocabulary_manual',word:'IN DEMAND',definition:'非常抢手',context:'Updated.'},study,manual);
 assert.deepEqual(manual,[{word:'IN DEMAND',definition:'非常抢手',context:'Updated.'}]);
 // Renaming via old_word updates in-place and preserves entry identity.
 manual[0].id=42;
 SyncCore.apply(articles,{type:'vocabulary_manual',old_word:'IN DEMAND',word:'in high demand',definition:'极其抢手',context:'New.'},study,manual);
 assert.deepEqual(manual,[{id:42,word:'in high demand',definition:'极其抢手',context:'New.'}]);
 const local={id:'a1',title:'T',text:'Online',annotations:[],vocabulary:[{start:0,end:6,word:'Online',definition:'在线的',context:''}]};
 SyncCore.apply([local],{type:'vocabulary_remove',article_id:'a1',start:0,end:6,word:'Online'},study,manual);
 assert.deepEqual(local.vocabulary,[]);
 SyncCore.apply([local],{type:'vocabulary',article_id:'a1',start:0,end:6,word:'Online',definition:'在线的',context:'Online'},study,manual);
 assert.equal(local.vocabulary.length,1);
 SyncCore.apply([local],{type:'vocabulary_manual_remove',word:'In  High  Demand'},study,manual);
 assert.deepEqual(manual,[]);
 // Deleting an article removes it and its study metadata.
 const list=[local];study['meta:a1']={article_id:'a1',group:'',pinned:true,read:false};
 SyncCore.apply(list,{type:'delete',article_id:'a1'},study,manual);
 assert.deepEqual(list,[]);
 assert.equal(study['meta:a1'],undefined);
});

check('merge keeps manual words from the desktop and replays unsent ones',()=>{
 const base={instance:'test',articles:[],study:{},outbox:[],conflicts:[],errors:[],vocabulary_manual:[{word:'stale'}],config:{}};
 const merged=SyncCore.merge(base,{instance:'test',acknowledgements:[],articles:[],study:{},conflicts:[],
  vocabulary_manual:[{id:5,word:'in demand',definition:'有需求的',context:''}]});
 assert.deepEqual(merged.vocabulary_manual,[{id:5,word:'in demand',definition:'有需求的',context:''}]);
 const pending=SyncCore.clone(base);
 pending.vocabulary_manual=[];
 pending.outbox=[{id:'late',type:'vocabulary_manual',word:'take over',definition:'接管'}];
 const replayed=SyncCore.merge(pending,{instance:'test',acknowledgements:[],articles:[],study:{},conflicts:[],
  vocabulary_manual:[{id:5,word:'in demand',definition:'有需求的',context:''}]});
 assert.deepEqual(replayed.vocabulary_manual.map(x=>x.word),['in demand','take over']);
 const older=makeOlderDesktopCase();
 assert.deepEqual(older.vocabulary_manual.map(x=>x.word).sort(),['stale','take over'].sort());
 function makeOlderDesktopCase(){
  // 电脑还是旧版（快照里没有 vocabulary_manual）：手机本机的自建词条必须留着
  const phone=SyncCore.clone(base);
  phone.vocabulary_manual=[{word:'stale'}];
  phone.outbox=[{id:'late',type:'vocabulary_manual',word:'take over',definition:'接管'}];
  return SyncCore.merge(phone,{instance:'test',acknowledgements:[],articles:[],study:{},conflicts:[]});
 }
});

console.log(`\n${passed} Android vocabulary checks passed.`);
