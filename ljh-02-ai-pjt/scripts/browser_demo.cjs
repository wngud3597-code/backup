/* Real local Chrome/Streamlit demo. Uses built-in Node/CDP only, no packages.
 * No API result is mocked. Two chat submissions maximum; never resubmit.
 * --inspect opens the current app without submitting discovery/chat requests.
 */
const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
const ROOT = path.resolve(__dirname, '..');
const OUT = path.join(ROOT, 'artifacts', 'review_browser_demo');
const INSPECT = process.argv.includes('--inspect');
const CONTINUE_MOON = process.argv.includes('--continue-moon');
const REPLAY = process.argv.includes('--replay-status');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const A = '157336', B = '753091';
const Q1 = '이 영화의 감독과 상영 시간을 알려줘.';
const Q2 = '이 영화는 크리스토퍼 놀란이 감독했고, 실제 달은 지구의 자연위성이라는 말이 맞나요?';
const QUERY = '2014년 SF 영화 중 우주 탐험을 다룬 영화';
const assistantNodes = `Array.from(document.querySelectorAll('[data-testid="stChatMessage"]')).filter(e => e.querySelector('[data-testid="stChatMessageAvatarAssistant"]'))`;
const chatNodes = `Array.from(document.querySelectorAll('[data-testid="stChatMessage"]'))`;

function events() {
  const p = path.join(OUT, 'api_events.jsonl');
  return fs.existsSync(p) ? fs.readFileSync(p, 'utf8').trim().split('\n').filter(Boolean).map(x=>JSON.parse(x)) : [];
}
async function main() {
  console.log('Browser demo start: '+(REPLAY?'saved-result UI replay; API blocked':INSPECT?'inspect only':'two authorized questions'));
  fs.mkdirSync(OUT, {recursive: true});
  const previous=CONTINUE_MOON?JSON.parse(fs.readFileSync(path.join(OUT,'browser_results.json'),'utf8')):null;
  const priorStarts=events().filter(e=>e.event==='answer_start');
  if(CONTINUE_MOON && (priorStarts.length!==1 || priorStarts[0].movie_id!==A))
    throw new Error('Continuation requires exactly one completed Interstellar submission');
  if (!INSPECT && !CONTINUE_MOON && !REPLAY && priorStarts.length)
    throw new Error('An actual question was already submitted; automatic rerun blocked');
  const chromePath = path.join(process.env.ProgramFiles || 'C:\\Program Files', 'Google', 'Chrome', 'Application', 'chrome.exe');
  const browser = spawn(chromePath, ['--headless=new','--remote-debugging-port=9224',
    '--remote-debugging-address=127.0.0.1','--user-data-dir='+path.join(OUT, INSPECT?'profile-inspect':'profile-demo'),
    '--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-sync',
    '--disable-component-update','--disable-default-apps','--disable-features=Translate,OptimizationHints,MediaRouter',
    'about:blank'], {windowsHide:true,stdio:'ignore'});
  browser.on('error', ()=>{});
  let socket;
  const report = previous || {verified:false,kind:'actual Chrome CDP against latest app.py',mock_responses:false,
    question_budget:2,submitted_questions:[],steps:[],screenshots:[],runtime_errors:[],external_browser_requests_blocked:[]};
  if(CONTINUE_MOON){report.tool_failures=[...(report.tool_failures||[]),{stage:'source mode selector',reason:report.failure,question_submissions_at_failure:1}];
    delete report.failure;report.continued_in_new_browser_session=true;}
  if(REPLAY){report.kind='saved actual result replay against latest app.py';report.mock_responses=true;report.actual_api_calls=0;report.question_budget=0;}
  try {
    let ready=false;
    for(let n=0;n<50;n++) {try{if((await fetch('http://127.0.0.1:9224/json/version')).ok){ready=true;break;}}catch{} await delay(200);}
    if(!ready) throw new Error('Local Chrome debugging endpoint unavailable');
    console.log('Local Chrome debugging endpoint ready');
    const target = await fetch('http://127.0.0.1:9224/json/new?about:blank',{method:'PUT'}).then(r=>r.json());
    socket = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('CDP connection timeout')),10000);
      socket.addEventListener('open',()=>{clearTimeout(timer);resolve();});socket.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('CDP connection failed'));});});
    console.log('CDP session connected');
    let next=0; const pending = new Map();
    const send=(method,params={})=>new Promise((resolve,reject)=>{
      const id=++next;const timer=setTimeout(()=>{pending.delete(id);reject(new Error('CDP timeout: '+method));},15000);
      pending.set(id,{resolve:v=>{clearTimeout(timer);resolve(v);},reject:e=>{clearTimeout(timer);reject(e);}});socket.send(JSON.stringify({id,method,params}));
    });
    socket.addEventListener('message',e=>{
      const m=JSON.parse(e.data);
      if(m.id){const p=pending.get(m.id);if(p){pending.delete(m.id);m.error?p.reject(new Error('CDP command failed '+m.error.code)):p.resolve(m.result);}}
      if(m.method==='Runtime.exceptionThrown') report.runtime_errors.push('Browser runtime exception');
      if(m.method==='Fetch.requestPaused'){
        let local=false;
        try{const u=new URL(m.params.request.url);local=['127.0.0.1','localhost'].includes(u.hostname);
          if(!local)report.external_browser_requests_blocked.push(u.origin+u.pathname);}catch{}
        send(local?'Fetch.continueRequest':'Fetch.failRequest', {requestId:m.params.requestId,...(local?{}:{errorReason:'BlockedByClient'})}).catch(()=>{});
      }
    });
    const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
      if(r.exceptionDetails) throw new Error('Browser DOM operation failed');return r.result.value;};
    async function waitFor(expression,description,attempts=160){
      for(let n=0;n<attempts;n++){if(await evaluate(expression))return;await delay(250);}throw new Error('Timed out: '+description);
    }
    async function fill(selector,text,blur=true){
      const s=JSON.stringify(selector);await waitFor(`!!document.querySelector(${s}) && !document.querySelector(${s}).disabled`,'enabled input');
      await evaluate(`(()=>{const e=document.querySelector(${s});e.focus();e.click();e.select();})()`);
      await send('Input.insertText',{text});if(blur)await evaluate('document.activeElement.blur()');await delay(250);
    }
    async function expander(label,open=true){
      await evaluate(`(()=>{const s=Array.from(document.querySelectorAll('[data-testid="stExpander"] summary')).find(e=>e.innerText.includes(${JSON.stringify(label)}));if(s && s.parentElement.open!==${open})s.click();})()`);await delay(150);
    }
    async function click(selector){const s=JSON.stringify(selector);await waitFor(`!!document.querySelector(${s}) && !document.querySelector(${s}).disabled`,'clickable control');await evaluate(`document.querySelector(${s}).click()`);}
    async function movie(id,title){
      await fill('.st-key-selected_movie_id input',title,false);
      await waitFor(`Array.from(document.querySelectorAll('[role="option"]')).some(e=>e.innerText.includes(${JSON.stringify(id)}))`,'movie option');
      await evaluate(`Array.from(document.querySelectorAll('[role="option"]')).find(e=>e.innerText.includes(${JSON.stringify(id)})).click()`);
      await selected(id);await delay(350);
    }
    async function selected(id){await waitFor(`Array.from(document.querySelectorAll('[data-testid="stHeading"]')).some(e=>e.innerText.includes(${JSON.stringify(id)}))`,'selected movie heading');}
    async function readAssistant(){
      await evaluate(`(${assistantNodes}).at(-1)?.querySelectorAll('[data-testid="stExpander"] summary').forEach(s=>{if(!s.parentElement.open)s.click();})`);await delay(200);
      return evaluate(`(()=>{const e=(${assistantNodes}).at(-1);return e?{text:e.innerText,
        links:Array.from(e.querySelectorAll('a')).map(a=>({title:a.innerText,url:a.href})),
        captions:Array.from(e.querySelectorAll('[data-testid="stCaptionContainer"]')).map(c=>c.innerText),
        sourceText:Array.from(e.querySelectorAll('[data-testid="stExpander"]')).map(s=>s.innerText)}:null;})()`);
    }
    async function ask(id,question){
      if(report.submitted_questions.length>=2)throw new Error('Question budget exceeded');
      const before=await evaluate(`${assistantNodes}.length`);const started=Date.now();
      await fill('.st-key-question textarea',question,false);
      report.submitted_questions.push({movie_id:id,question,at:new Date().toISOString()});
      await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,nativeVirtualKeyCode:13});
      await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,nativeVirtualKeyCode:13});
      await waitFor(`((${assistantNodes}.length>${before} || document.body.innerText.includes('답변 생성 실패')) && !document.querySelector('.st-key-question textarea').disabled)`,'answer or failure',480);
      await delay(300);
      return {movie_id:id,question,browser_elapsed_seconds:(Date.now()-started)/1000,
        assistant:await readAssistant(),screenText:await evaluate('document.body.innerText'),
        userCount:await evaluate(`${chatNodes}.filter(e=>!e.querySelector('[data-testid="stChatMessageAvatarAssistant"]')).length`),
        assistantCount:await evaluate(`${assistantNodes}.length`)};
    }
    function check(step,condition,detail){report.steps.push({step,status:condition?'passed':'failed',detail});}
    async function capture(name){
      await evaluate(`(()=>{const h=Array.from(document.querySelectorAll('[data-testid="stHeading"]')).find(e=>e.innerText.includes('157336')||e.innerText.includes('753091'));h?.scrollIntoView({block:'start'});})()`);
      await delay(300);const p=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      fs.writeFileSync(path.join(OUT,name),Buffer.from(p.data,'base64'));report.screenshots.push(name);
    }
    await send('Page.enable');await send('Runtime.enable');await send('Network.enable');
    await send('Fetch.enable',{patterns:[{urlPattern:'*',requestStage:'Request'}]});
    await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1600,deviceScaleFactor:1,mobile:false});
    await send('Page.navigate',{url:'http://127.0.0.1:'+(REPLAY?'8504':'8503')});
    await waitFor(`!!document.querySelector('.st-key-selected_movie_id input') && document.body.innerText.includes('964')`,'initial app');
    const initial={text:await evaluate('document.body.innerText'),chatCount:await evaluate(`${chatNodes}.length`)};
    if(CONTINUE_MOON)report.continuation_initial=initial;else report.initial=initial;
    if(INSPECT){console.log(JSON.stringify({inspectOnly:true,...initial},null,2));return;}
    if(REPLAY){
      const beforeApis=events().filter(e=>e.event==='api_start').length;
      await movie(B,'더 문');
      await evaluate(`Array.from(document.querySelectorAll('.st-key-answer_mode label')).find(e=>e.innerText.includes('작품·현실 배경 확인')).click()`);
      await waitFor(`document.body.innerText.includes('현재 질문 방식: 작품·현실 배경 확인')`,'replay verify mode');
      report.replay=await ask(B,Q2);
      check('latest_partial_insufficient_status',report.replay.screenText.includes('일부 확인 · 근거 부족 포함'),'Offline replay of the captured mixed insufficient result');
      check('latest_search_failure_notice',report.replay.screenText.includes('근거 검색 연결에 실패해 저장된 자료로 답했습니다.'),'Saved 502 is visibly distinguished from a successful search');
      check('replay_has_no_new_api',events().filter(e=>e.event==='api_start').length===beforeApis,'Actual API event count remains unchanged');
      await evaluate('window.scrollTo(0,0)');await delay(300);
      await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1800,deviceScaleFactor:1,mobile:false});
      const image=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      fs.writeFileSync(path.join(OUT,'03-status-replay.png'),Buffer.from(image.data,'base64'));
      report.screenshots=['03-status-replay.png'];report.verified=report.steps.every(s=>s.status==='passed');
      console.log(JSON.stringify({kind:report.kind,verified:report.verified,steps:report.steps,actual_api_calls:0}));return;
    }

    if(!CONTINUE_MOON){
    await fill('.st-key-discovery_query input',QUERY);
    await click('.st-key-run_discovery button');
    await waitFor(`!!document.querySelector('.st-key-choose_discovery_${A} button')`,'Interstellar discovery result');
    report.discovery={query:QUERY,text:await evaluate('document.body.innerText')};
    await click(`.st-key-choose_discovery_${A} button`);await selected(A);await delay(300);
    report.selection={heading:await evaluate(`Array.from(document.querySelectorAll('[data-testid="stHeading"]')).filter(e=>e.innerText.includes('${A}')).map(e=>e.innerText)`),
      text:await evaluate('document.body.innerText')};
    check('discovery_to_selection',report.selection.text.includes('인터스텔라')&&report.selection.text.includes('2014')&&report.selection.text.includes('크리스토퍼 놀란')&&report.selection.heading.some(x=>x.includes(A)),'Title/year/director/ID checked in search result and selected heading');
    await expander('자연어로 영화 찾기',false);
    report.interstellar=await ask(A,Q1);
    const first=report.interstellar.assistant;
    check('interstellar_answer',!!first&&first.text.includes('169')&&first.text.includes('놀란')&&first.text.includes('[근거 1]'),'Actual browser answer has director/runtime and source 1');
    const firstBackend=events().find(e=>e.event==='answer_result'&&e.movie_id===A);
    const firstSource=firstBackend?.result.sources?.[0];
    const multipleQuotes=firstSource?.quotes || (firstSource?.quote?[firstSource.quote]:[]);
    const compact=s=>s.replace(/\s+/g,'');
    check('same_source_multiple_quotes',!!first&&multipleQuotes.length>=2&&multipleQuotes.every(q=>compact(first.text).includes(compact(q))),'All actual source-1 quote snapshots are visible, not just the first quote');
    await capture('01-interstellar.png');
    }

    await movie(B,'더 문');
    await evaluate(`Array.from(document.querySelectorAll('.st-key-answer_mode label')).find(e=>e.innerText.includes('작품·현실 배경 확인')).click()`);
    await waitFor(`document.body.innerText.includes('현재 질문 방식: 작품·현실 배경 확인')`,'verify mode');
    await expander('고급 설정 · 자료 미리 준비');
    await expander('자료 경로와 갱신 설정');
    await fill('.st-key-snapshot_path input','C:\\Users\\SSAFY\\Downloads\\영화도메인_데이터_배포용.zip');
    await delay(1500);
    await evaluate(`document.querySelector('.st-key-document_source_mode input').focus()`);
    for(const [key,code,vk] of [['ArrowDown','ArrowDown',40],['End','End',35],['Enter','Enter',13]]){
      await send('Input.dispatchKeyEvent',{type:'keyDown',key,code,windowsVirtualKeyCode:vk,nativeVirtualKeyCode:vk});
      await send('Input.dispatchKeyEvent',{type:'keyUp',key,code,windowsVirtualKeyCode:vk,nativeVirtualKeyCode:vk});
      await delay(100);
    }
    await waitFor(`document.querySelector('.st-key-document_source_mode input')?.value==='제공 스냅샷'`,'snapshot mode selected');
    await delay(350);await expander('고급 설정 · 자료 미리 준비',false);
    report.moon=await ask(B,Q2);
    const moon=report.moon.assistant;
    const moonBackend=events().find(e=>e.event==='answer_result'&&e.movie_id===B);
    const verdicts=Object.fromEntries((moonBackend?.result.checks||[]).map(c=>[c.scope,c.verdict]));
    check('moon_item_verdicts',!!moon&&moon.text.includes('근거와 상충')&&moon.text.includes('확인됨')&&moon.text.includes('김용화')&&moon.text.includes('자연위성')&&verdicts['작품 속 묘사']==='근거와 상충'&&verdicts['현실 사실']==='확인됨'&&moonBackend?.result.validation?.semantic_check==='item_review_passed','Actual browser mixed verification answer and per-item acceptance');
    check('source_provenance',!!moon&&moon.text.includes('제공 스냅샷')&&moon.text.includes('2026-09-10')&&moon.text.includes('메타데이터')&&moon.text.includes('배경 문서'),'Stored source classifications, collection mode/date visible');
    await capture('02-moon-verification.png');

    await movie(A,'인터스텔라');
    let restored=await readAssistant();
    report.restoration={assistant:restored,chatCount:await evaluate(`${chatNodes}.length`),screenText:await evaluate('document.body.innerText')};
    let reference=report.interstellar.assistant;
    if(CONTINUE_MOON){
      report.steps.push({step:'requested_interstellar_restoration',status:'unverified',detail:'First browser session ended at harness selector timeout. Full-refresh persistence is outside scope; old answer was not injected or resubmitted.'});
      report.restoration.original_interstellar_history_not_replayed=true;
      await movie(B,'더 문');restored=await readAssistant();reference=report.moon.assistant;
      check('moon_B_A_B_restoration',!!reference&&!!restored&&reference.text===restored.text&&JSON.stringify(reference.links)===JSON.stringify(restored.links)&&await evaluate(`${chatNodes}.length`)===2,'Actual second-session B→A→B restores Moon answer and original source snapshot; does not prove original Interstellar restoration');
    }else{
    const first=reference;
    check('movie_switch_restoration',!!first&&!!restored&&first.text===restored.text&&JSON.stringify(first.links)===JSON.stringify(restored.links)&&report.restoration.chatCount===2&&!report.restoration.screenText.includes(Q2),'A→B→A restores answer, quotes and links without B question');
    }

    const beforeInteraction=events();
    await evaluate(`Array.from(document.querySelectorAll('.st-key-answer_mode label')).find(e=>e.innerText.includes('근거 기반 질문')).click()`);
    await delay(800);
    const modeAfter=await evaluate(`document.querySelector('.st-key-answer_mode input:checked')?.value`);
    const beforeRerunEvents=events();
    await evaluate('document.activeElement?.blur()');
    await send('Input.dispatchKeyEvent',{type:'keyDown',key:'r',code:'KeyR',windowsVirtualKeyCode:82,nativeVirtualKeyCode:82});
    await send('Input.dispatchKeyEvent',{type:'keyUp',key:'r',code:'KeyR',windowsVirtualKeyCode:82,nativeVirtualKeyCode:82});
    await delay(1500);await selected(CONTINUE_MOON?B:A);
    const afterRerun=await readAssistant();
    const afterInteraction=events();
    const count=(rows,event)=>rows.filter(e=>e.event===event).length;
    report.rerun={modeAfter,questionStartsBefore:count(beforeInteraction,'answer_start'),questionStartsAfter:count(afterInteraction,'answer_start'),
      apiStartsBefore:count(beforeInteraction,'api_start'),apiStartsAfter:count(afterInteraction,'api_start'),
      threadReadsBefore:count(beforeInteraction,'thread_observation'),threadReadsAfter:count(afterInteraction,'thread_observation'),
      threadReadsAfterModeChange:count(beforeRerunEvents,'thread_observation'),
      chatCount:await evaluate(`${chatNodes}.length`),assistant:afterRerun};
    check('rerun_no_duplicate_or_api',!!reference&&!!afterRerun&&reference.text===afterRerun.text&&report.rerun.chatCount===2&&report.rerun.apiStartsBefore===report.rerun.apiStartsAfter&&report.rerun.questionStartsAfter===2&&report.rerun.threadReadsAfter>report.rerun.threadReadsAfterModeChange,'Mode change and normal r shortcut rerun preserve current-session record and issue zero API calls');
    if(!CONTINUE_MOON)await capture('03-interstellar-restored.png');
    const allEvents=events();
    report.api_summary={starts:allEvents.filter(e=>e.event==='api_start'),ends:allEvents.filter(e=>e.event==='api_end'),
      answers:allEvents.filter(e=>e.event==='answer_result').map(e=>({movie_id:e.movie_id,seconds:e.seconds,content:e.result.content,
        timings:e.result.timings,stage_calls:e.result.stage_calls,cache:e.result.cache,validation:e.result.validation,error:e.result.error}))};
    check('browser_runtime',report.runtime_errors.length===0,'No observed runtime exceptions');
    report.verified=report.steps.every(s=>s.status==='passed');
    console.log(JSON.stringify({verified:report.verified,steps:report.steps,screenshots:report.screenshots,submitted:report.submitted_questions.length},null,2));
  } catch(error) {
    report.failure=String(error.message).slice(0,180);
    console.error(report.failure);process.exitCode=1;
  } finally {
    if(!INSPECT)fs.writeFileSync(path.join(OUT,REPLAY?'browser_replay.json':'browser_results.json'),JSON.stringify(report,null,2));
    socket?.close();browser.kill();
  }
}
main().catch(()=>{console.error('Browser validation failed before session initialization');process.exitCode=1;});
