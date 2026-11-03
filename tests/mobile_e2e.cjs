const {chromium}=require('playwright');
const {spawn}=require('node:child_process');const path=require('node:path');const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');const core=require('../android/app/src/main/assets/sync-core.js');
const fixture={instance:'test',articles:[{id:'one',title:'Old',title_version:1,annotations:[],vocabulary:[],text:'Online',progress:0}],outbox:[],conflicts:[],errors:[]};
const local=core.clone(fixture);local.outbox=[{id:'late',type:'underline',article_id:'one',start:0,end:6,word:'Online',active:true}];
let merged=core.merge(local,{...fixture,acknowledgements:[]});assert.equal(merged.articles[0].annotations.length,1);assert.equal(merged.outbox.length,1);
assert.throws(()=>core.merge(local,{...fixture,instance:'other',acknowledgements:[]}));assert.equal(local.instance,'test');
const renamed=core.clone(fixture.articles);core.apply(renamed,{type:'rename',article_id:'one',title:'One'});core.apply(renamed,{type:'rename',article_id:'one',title:'Two'});assert.equal(renamed[0].title_version,3);
(async()=>{
 const harness=spawn(path.join(root,'.venv/Scripts/python.exe'),['tests/mobile_harness.py'],{cwd:root,env:{...process.env,PYTHONPATH:root}});
 let browser;
 try{
  const info=await new Promise((resolve,reject)=>{let data='';harness.stdout.on('data',chunk=>{data+=chunk.toString();const line=data.split('\n')[0];try{resolve(JSON.parse(line));}catch{}});harness.on('exit',code=>reject(Error('Harness exit '+code)));harness.stderr.on('data',c=>process.stderr.write(c));setTimeout(()=>reject(Error('Harness startup timeout')),10000).unref();});
  browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
  const context=await browser.newContext({viewport:{width:393,height:852},isMobile:true,hasTouch:true});
  const page=await context.newPage();let network=true,spoken='',speechConfig=null,csv='',errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.exposeFunction('bridgeSend',async(id,action,raw)=>{
   let result={};try{const p=JSON.parse(raw);
    if(action==='pair'||action==='sync'){
     if(!network)throw Error('模拟离线');
     const response=await fetch(p.url+'/'+action,{method:'POST',headers:{'Content-Type':'application/json',...(p.token?{Authorization:'Bearer '+p.token}:{})},body:JSON.stringify(p.body)});
     result=await response.json();
    }else if(action==='translate')result={text:'在线的；测试译文'};
    else if(action==='speak'){spoken=p.text;speechConfig=p;result={ok:true};}
    else if(action==='export'){csv=p.csv;result={ok:true};}else result={ok:true};
   }catch(error){result={error:error.message};}
   await page.evaluate(({id,result})=>window.nativeReply(id,result),{id,result});
  });
  await page.addInitScript(()=>{window.ReaderNative={send:(id,action,raw)=>window.bridgeSend(id,action,raw)};});
  const appUrl='http://127.0.0.1:'+info.staticPort+'/index.html';
  await page.goto(appUrl);
  assert.deepEqual(await page.evaluate(()=>JSON.parse(localStorage.getItem('reader-v1')).audio),{accent:'us',speed:0.75,source:'dictionary'});
  await page.locator('#audioSettings').click();await page.locator('#audioAccent').selectOption('uk');await page.locator('#audioSpeed').selectOption('0.6');await page.locator('#saveAudioSettings').click();
  await page.locator('[data-page="connect"]').click();
  const serverUrl='http://127.0.0.1:'+info.port;
  await page.locator('#serverUrl').fill(serverUrl);await page.locator('#pairCode').fill(info.code);await page.locator('#pairButton').click();
  await page.waitForFunction(()=>JSON.parse(localStorage.getItem('reader-v1')).articles.length===1);
  await page.locator('[data-page="articles"]').click();await page.locator('.openArticle').click();
  await page.locator('.token').first().click();await page.locator('#lookupDefinition').filter({hasText:'在线的'}).waitFor();
  await page.locator('#lookupMark').click();await page.locator('#lookupSave').click();
  await page.waitForFunction(()=>JSON.parse(localStorage.getItem('reader-v1')).outbox.length===0);
  assert.equal(await page.locator('.token.marked').count(),1);
  await page.locator('#closeLookup').click();
  network=false;await page.locator('.token').filter({hasText:/^Students$/}).first().click();await page.locator('#lookupDefinition').filter({hasText:'在线的'}).waitFor();await page.locator('#lookupMark').click();await page.locator('#closeLookup').click();await page.locator('[data-page="articles"]').click();
  page.once('dialog',dialog=>dialog.accept('Phone title'));await page.locator('.articleMore').click();await page.locator('#renameArticle').click();
  assert.ok(await page.evaluate(()=>JSON.parse(localStorage.getItem('reader-v1')).outbox.some(x=>x.type==='rename')));
  await page.reload();await page.locator('.title').filter({hasText:'Phone title'}).waitFor();
  const stored=await page.evaluate(()=>JSON.parse(localStorage.getItem('reader-v1'))),a=stored.articles[0];
  const remote=await fetch(serverUrl+'/sync',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+stored.config.token},body:JSON.stringify({client_id:'desktop-fixture',instance:stored.instance,operations:[{id:'desktop-rename',type:'rename',article_id:a.id,title:'Desktop title',base_version:1}]})});assert.equal(remote.status,200);
  network=true;await page.locator('#syncNow').click();
  await page.waitForFunction(()=>JSON.parse(localStorage.getItem('reader-v1')).conflicts.length===1);
  const synced=await page.evaluate(()=>JSON.parse(localStorage.getItem('reader-v1')));assert.equal(synced.articles[0].annotations.length,2);assert.equal(synced.articles[0].annotations.find(x=>x.word==='Students').start,Array.from(synced.articles[0].text.slice(0,synced.articles[0].text.indexOf('Students'))).length);
  await page.locator('[data-page="connect"]').click();await page.locator('[data-choice="mobile"]').click();
  await page.waitForFunction(()=>JSON.parse(localStorage.getItem('reader-v1')).conflicts.length===0&&JSON.parse(localStorage.getItem('reader-v1')).articles[0].title==='Phone title');
  await page.locator('[data-page="vocabulary"]').click();await page.locator('#exportWords').click();assert.ok(csv.includes('Online')&&csv.includes('Phone title'));
  await page.locator('[data-page="articles"]').click();await page.locator('.openArticle').click();
  await page.evaluate(()=>{const body=document.getElementById('readingArea'),r=document.createRange();r.selectNodeContents(body);const s=window.getSelection();s.removeAllRanges();s.addRange(r);});
  await page.locator('#selectionBar').waitFor({state:'visible'});await page.locator('#selectionTranslate').click();await page.locator('#lookupDefinition').filter({hasText:'测试译文'}).waitFor();await page.locator('#lookupSpeak').click();assert.ok(spoken.includes('Students learn'));assert.equal(speechConfig.accent,'uk');assert.equal(speechConfig.speed,0.6);assert.equal(speechConfig.source,'dictionary');
  // Listening training: per-sentence self-assessment, missed-only replay, dictation diff.
  await page.locator('#closeLookup').click();
  const outboxBefore=await page.evaluate(()=>JSON.parse(localStorage.getItem('reader-v1')).outbox.length);
  await page.locator('#markHeard').click();
  await page.locator('#markMissed').click();
  const firstSentence=await page.evaluate(()=>splitSentences(article().text)[0].text);
  const articleMarks=await page.evaluate(()=>{const s=JSON.parse(localStorage.getItem('reader-v1'));return (JSON.parse(localStorage.getItem('listening-v1')||'{}')[s.articles[0].id]||{});});
  assert.ok(Object.values(articleMarks).some(x=>x.status==='missed'),'没听懂标记已保存');
  const outboxAfter=await page.evaluate(()=>JSON.parse(localStorage.getItem('reader-v1')).outbox.length);
  assert.equal(outboxAfter,outboxBefore,'听力标记不进同步队列');
  await page.locator('#replayMissedOnly').check();
  await page.locator('#sentencePlay').click();
  await page.waitForFunction(()=>document.getElementById('sentenceStatus').textContent.includes('第 1/'));
  assert.equal(spoken,firstSentence,'只重听从没听懂句开始');
  await page.locator('#openDictation').click();
  await page.locator('#dictationTyped').fill(firstSentence);
  await page.locator('#dictationCheck').click();
  assert.ok((await page.locator('#dictationResult').textContent()).includes('100%'),'听写满分判定');
  await page.locator('#dictationTyped').fill('students learnt');
  await page.locator('#dictationCheck').click();
  assert.ok((await page.locator('#dictationResult').textContent()).includes('多写的词'),'错词与多写识别');
  await page.locator('#dictationClose').click();
  for(const width of [360,393]){await page.setViewportSize({width,height:852});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));}
  await page.screenshot({path:path.join(root,'work/mobile_e2e.png'),fullPage:false});
  assert.deepEqual(errors,[]);console.log('PASS: offline merge, pairing, sync, exact underline, vocabulary, offline reload, rename conflict, CSV, paragraph selection, speech bridge, audio settings persistence, 360/393px layout.');
 }finally{if(browser)await browser.close();harness.kill();}
})().catch(error=>{console.error(error);process.exitCode=1;});
