import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { webcrypto } from 'node:crypto';
import { test } from 'node:test';

const prismRuntime=vm.createContext({});
vm.runInContext(readFileSync(new URL('../public/vendor/prism/prism-python-1.30.0.min.js',import.meta.url),'utf8'),prismRuntime);
const workspaceContexts = new WeakMap();
const sampleProfileIds={"central_gov": "1dd02d79-f43e-49ef-a1f1-7a2ddfab1e8d", "consultation": "41bbe1dc-85cb-4ab0-ab79-cd7c4e6f8e72", "application": "617706a3-c4ee-426f-81cf-7f5d80ecf67a", "general": "4e6d5417-611e-49e0-8e23-2444a0f49ee4", "local_gov": "efb7c8ca-61c1-4785-b38d-0a86764ca758", "authentication": "702ecfa5-01fb-4321-9692-996134a10802", "network": "0181af82-c1ed-41c8-8cd3-22a385746b32", "http_access": "2e44ae00-7a3a-492d-8806-9177a8973582"};
function readProfileTemplate(name) {const {id,...profile}=JSON.parse(readFileSync(new URL(`../profiles/${name}.json`,import.meta.url),'utf8'));return profile;}
const systemProfile=readProfileTemplate('general');
function profileFixture(label,instructions,criteria=systemProfile.questions.category.criteria) {
  return {...structuredClone(systemProfile),label,instructions,questions:{...structuredClone(systemProfile.questions),category:{...structuredClone(systemProfile.questions.category),criteria}}};
}
function systemResult(log,overrides={}) {
  return {log,elapsedMs:1,criteriaGroup:'system',profileId:'4e6d5417-611e-49e0-8e23-2444a0f49ee4',defaultDecision:'category',decisionDefinitions:structuredClone(systemProfile.questions),decisions:{category:{type:'choice',choice:'normal',confidence:.9,probabilities:{normal:1,warning:0,error:0,security:0,other:0}},urgency:{type:'score',score:undefined,probabilities:{},legend:Object.fromEntries(systemProfile.questions.urgency.criteria.map((text,i)=>[i,text]))},ticket:{type:'noul',noul:undefined}},...overrides};
}
function setDecisions(item,{choice,confidence,probabilities,score,scoreProbabilities,legend,noul,uncertain,reasons,candidates,...metadata}) {
  Object.assign(item,metadata);
  const answer=item.decisions.category;
  if(choice!==undefined){answer.choice=choice;answer.probabilities=Object.fromEntries(Object.keys(answer.probabilities).map(key=>[key,Number(key===choice)]));}
  if(confidence!==undefined)answer.confidence=confidence;
  if(probabilities!==undefined)answer.probabilities=probabilities;
  if(score!==undefined)item.decisions.urgency.score=score;
  if(scoreProbabilities!==undefined)item.decisions.urgency.probabilities=scoreProbabilities;
  if(legend!==undefined)item.decisions.urgency.legend=legend;
  if(noul!==undefined)item.decisions.ticket.noul=noul;
  if(uncertain!==undefined || reasons || candidates)item.decisionAssessments={category:{uncertain:uncertain ?? false,reviewReasons:reasons || [],candidates:candidates || [],answerProbability:answer.probabilities[answer.choice]}};
}

function showDecisions(context,keys) {
  const inputs=vm.runInContext('[...decisionDisplayInputs]',context);
  for(const [key,input] of inputs){
    const checked=keys.includes(key);
    if(input.checked!==checked){input.checked=checked;input.onchange();}
  }
}

function runTask(nodes) {
  return vm.runInContext('handleRunTask(selectedTaskId)', workspaceContexts.get(nodes));
}

function workspace(events, status, storage = { getItem: () => null, setItem() {} }, criteria = null, navigation = null, session = undefined) {
  const nodes = new Map();
  const requests = [];
  const listeners = new Map();
  const node = () => ({
    children: [], value: '', checked: false, attributes: {},
    showModal() { this.returnValue='delete'; this.onclose(); },
    append(...children) { for(const child of children){if(child?.parentNode)child.parentNode.removeChild(child);this.children.push(child);if(child && typeof child==='object')child.parentNode=this;} },
    remove() { this.parentNode?.removeChild(this); },
    get parentElement() { return this.parentNode; },
    get options() { return this.children.flatMap(child=>child.tagName==='optgroup'?child.children:[child]); },
    prepend(...children) { for(const child of children.toReversed())this.insertBefore(child,this.children[0] || null); },
    get nextSibling() { return this.parentNode?.children[this.parentNode.children.indexOf(this)+1] || null; },
    replaceChildren(...children) { this.children = []; this.append(...children); },
    insertBefore(child, reference) {
      const previous=this.children.indexOf(child);
      if(previous!==-1)this.children.splice(previous,1);
      const index=reference===null?this.children.length:this.children.indexOf(reference);
      if(child.parentNode && child.parentNode!==this)child.parentNode.removeChild(child);
      this.children.splice(index,0,child);child.parentNode=this;
    },
    removeChild(child) { const index=this.children.indexOf(child);if(index>=0)this.children.splice(index,1);child.parentNode=null; },
    setAttribute(name, value) { this.attributes[name] = value; },
  });
  const context = vm.createContext({
    Prism:prismRuntime.Prism, crypto: webcrypto, structuredClone, systemProfile, profileFixture, systemResult, sampleProfileIds,
    ...(navigation ? { location: navigation, addEventListener: (name, handler) => listeners.set(name, handler) } : {}),
    document: {
      getElementById(id) {
        if (!nodes.has(id)) nodes.set(id, node());
        return nodes.get(id);
      },
      createElement: tagName => Object.assign(node(),{tagName}),
    },
    Option: function(text, value) { return { text, value }; },
    localStorage: storage,
    ...(session ? {sessionStorage:session} : {}),
    AbortController,
    setTimeout: () => 1,
    clearTimeout() {},
    fetch: async (path, options) => {
      if (path === '/api/delete-check') return {ok:true,json:async()=>({references:[],details:[]})};
      if (path === '/api/settings') return {ok:true,json:async()=>options.method==='PUT'?JSON.parse(options.body):({resultsPerPage:50})};
      if (path === '/api/criteria') {
        if (!criteria) return { ok: false, json: async () => ({ error: 'Unavailable' }) };
        return { ok: true, json: async () => ({ profiles: options.method === 'PUT' ? JSON.parse(options.body) : criteria }) };
      }
      if (path === '/api/tasks') return {ok:true,json:async()=>({tasks:vm.runInContext('registeredTasks.map(task=>({...task}))',context)})};
      if (path === '/api/tasks/test-task/run') {
        const sources=vm.runInContext('sourceRows.map(({path,profile,size,action})=>({sourceId:path,profile:profile.value,chunkEvents:Number(size.value),actionId:action.value}))',context);
        const mode=nodes.get('source-mode').value || 'batch';
        const error=vm.runInContext('!sourcesLoaded',context)?'Sources are not loaded.':sources.some(source=>!vm.runInContext('registeredSources.map(s=>s.id)',context).includes(source.sourceId))?'Select a registered source.':sources.some(source=>!Number.isInteger(source.chunkEvents)||source.chunkEvents<1)?'Events per chunk must be a positive integer.':null;
        if(error)return {ok:false,json:async()=>({error})};
        requests.push({mode,sources,persist:true});
        return {ok:true,status:202,json:async()=>({jobId:'test-job',state:'running',settings:{mode,sources,taskId:'test-task'}})};
      }
      if (path === '/api/jobs/test-job/events')return {ok:true,body:{}};
      if (path === '/api/ssh-hosts') return {ok:true,json:async()=>({hosts:[]})};
      if (path === '/api/ssh-keys') return { ok: true, json: async () => ({ keys: [] }) };
      if (path === '/api/sources') return { ok: true, json: async () => ({ sources: options.method === 'PUT' ? JSON.parse(options.body).map((source,index)=>({...source,id:source.id || String(index+4).padStart(32,'0')})) : vm.runInContext('sampleSources.map(source=>({...source}))',context) }) };
      if (path === '/api/actions') return { ok: true, json: async () => ({ actions: [] }) };
      if (path === '/api/engine-health') return {ok:true,json:async()=>({engine:status?.engine || 'laya',connection:'connected'})};
      if (path === '/api/status') return status ? { ok: true, json: async () => status } : new Promise(() => {});
      requests.push(JSON.parse(options.body));
      return { ok: true, body: {} };
    },
    readEvents: async (_, receive) => events.forEach(receive),
  });
  context.document.getElementById('review-filter').value = 'all';
  context.document.getElementById('processing-filter').value = 'all';
  const source = readFileSync(new URL('../public/app.js', import.meta.url), 'utf8');
  vm.runInContext(source.replace(/^import .*;\n/, ''), context);
  vm.runInContext("sourcesLoaded = true; registeredTasks=[{id:'test-task',name:'Test Task',mode:'batch',sources:[],timezone:'UTC',cron:'',enabled:true}];selectedTaskId='test-task';renderTaskMonitor()", context);
  workspaceContexts.set(nodes, context);
  return { nodes, context, requests, listeners };
}

function processingValues(nodes) {
  return Object.fromEntries(nodes.get('summary').children[5].children[0].children.map(item=>[
    item.children[0].textContent,item.children[1].children[0].textContent,
  ]));
}

function result(index, review = true) {
  return {
    type: 'result', index, elapsedMs: index,
    result: systemResult(`log-${index}`,{review}),
  };
}

function decisionCards(row) {
  return row.children[0].children[0].children;
}

function logs(nodes) {
  return nodes.get('results').children.map(row => row.children[1].children[1].textContent);
}

test('arrival order, filtering, corrections, pagination and restart', async () => {
  const events = [{ type: 'start', engine: 'laya', total: 105 },
    result(2), result(0, false), result(1),
    ...Array.from({ length: 102 }, (_, i) => result(i + 3)),
    { type: 'done', elapsedMs: 100 }];
  const { nodes, context } = workspace(events);
  await runTask(nodes);
  assert.equal(logs(nodes)[0], 'log-104');
  assert.equal(logs(nodes).length, 100);
  nodes.get('next').onclick();
  assert.deepEqual(logs(nodes), ['log-4', 'log-3', 'log-1', 'log-0', 'log-2']);
  nodes.get('review-filter').value = 'needs-review';
  nodes.get('review-filter').onchange();
  nodes.get('next').onclick();
  assert.deepEqual(logs(nodes), ['log-4', 'log-3', 'log-1', 'log-2']);
  const select = nodes.get('results').children[0].children.at(-2).children[1].children[0].children[0];
  select.value = 'warning';
  select.onchange();
  vm.runInContext('render()', context);
  assert.equal(nodes.get('results').children[0].children.at(-2).children[1].children[0].children[0].value,
    'warning');
  events.splice(0, events.length, { type: 'start', engine: 'jev', total: 1 }, result(0));
  await runTask(nodes);
  assert.deepEqual(logs(nodes), ['log-0']);
});

test('average request duration includes failures, ignores filters, and resets', async () => {
  const first = result(0, false);
  first.result.elapsedMs = 100;
  const failed = result(1);
  failed.result = { log: 'failed-log', error: 'timeout', review: true, elapsedMs: 300 };
  const events = [{ type: 'start', engine: 'laya', total: 2 }, first, failed,
    { type: 'done', elapsedMs: 5000 }];
  const { nodes, context } = workspace(events);
  const average = () => processingValues(nodes).Avg;
  vm.runInContext('render()', context);
  assert.equal(average(), '0 ms');
  await runTask(nodes);
  assert.equal(average(), '200 ms');
  nodes.get('review-filter').value = 'needs-review';
  nodes.get('review-filter').onchange();
  assert.equal(average(), '200 ms');
  assert.equal(nodes.get('results').children[0].textContent, 'No results to display.');
  events.splice(0, events.length, { type: 'start', engine: 'jev', total: 1 }, result(0));
  await runTask(nodes);
  assert.equal(average(), '1 ms');
});

test('review filters exclude failures without changing success and failure totals', async () => {
  const events = [{ type: 'start', engine: 'laya', total: 3 },
    result(0, false), result(1),
    { type: 'result', index: 2, elapsedMs: 2,
      result: { log: 'failed-log', error: 'timeout', elapsedMs: 2, review: true } }];
  const { nodes } = workspace(events);
  await runTask(nodes);
  assert.deepEqual(logs(nodes), ['failed-log', 'log-1', 'log-0']);
  for (const [filter, expected] of [
    ['needs-review', ['log-1']],
    ['no-review', ['log-0']],
    ['all', ['failed-log', 'log-1', 'log-0']],
  ]) {
    nodes.get('review-filter').value = filter;
    nodes.get('review-filter').onchange();
    assert.deepEqual(logs(nodes), expected);
    assert.equal(nodes.get('summary').children[0].children[0].children.map(node => node.textContent).join(''), '2 / 1 / 3');
    assert.equal(nodes.get('needs-review-count').textContent, 'Needs Review: 1');
  }
  nodes.get('review-filter').value = 'no-review';
  events.splice(0, events.length, { type: 'start', engine: 'jev', total: 1 }, result(0));
  await runTask(nodes);
  assert.equal(nodes.get('results').children[0].textContent, 'No results to display.');
});

test('Tasks expose Manual Batch, Cron Batch and Realtime without Paste', async () => {
  const {nodes,context}=workspace([]);await vm.runInContext('handleEditTask()',context);
  assert.equal(nodes.get('source-mode').value,'batch');
  nodes.get('task-trigger').value='cron';nodes.get('task-trigger').onchange();
  assert.equal(nodes.get('task-cron-field').hidden,false);
  assert.match(nodes.get('task-mode-note').textContent,/repeat Actions/);
  nodes.get('source-mode').value='realtime';nodes.get('source-mode').onchange();
  assert.equal(nodes.get('task-cron-field').hidden,true);
  assert.equal(nodes.get('task-resume-field').hidden,false);
});

test('Task saves registered Source settings without starting a run', async () => {
  const {nodes,context}=workspace([]);await vm.runInContext('handleEditTask()',context);
  nodes.get('task-name').value='Nightly logs';nodes.get('task-trigger').value='cron';nodes.get('task-cron').value='0 2 * * *';nodes.get('task-timezone').value='Asia/Seoul';
  let payload;context.fetch=async(path,options)=>{assert.equal(path,'/api/tasks');payload=JSON.parse(options.body);return {ok:true,json:async()=>({tasks:[{...payload,id:'saved'}]})};};
  await nodes.get('task-form').onsubmit({preventDefault(){}});
  assert.equal(payload.cron,'0 2 * * *');assert.equal(payload.timezone,'Asia/Seoul');
  assert.ok(payload.sources[0].sourceId);assert.equal(payload.resumeOnRestart,false);
  assert.equal(nodes.get('task-editor').hidden,true);
});

test('active time uses server intervals, updates while idle, and resets', async () => {
  const first = result(0, false);
  first.result.elapsedMs = 100;
  const failed = result(1);
  failed.result = { log: 'failed-log', error: 'timeout', review: true, elapsedMs: 300 };
  const events = [{ type: 'start', engine: 'laya', total: 2 }, first, failed,
    { type: 'timing', elapsedMs: 200, activeProcessingMs: 150 },
    { type: 'done', elapsedMs: 1000, activeProcessingMs: 150 }];
  const { nodes, context } = workspace(events);
  const active = () => elapsedValues(nodes)[1];
  vm.runInContext('render()', context);
  assert.equal(active(), '0 ms (N/A)');
  await runTask(nodes);
  assert.equal(active(), '150 ms (15.0%)');
  assert.ok(nodes.get('summary').children[4].title.includes('not CPU utilization'));
  nodes.get('review-filter').value = 'no-review';
  nodes.get('review-filter').onchange();
  assert.equal(active(), '150 ms (15.0%)');
  events.at(-1).elapsedMs = 200;
  await runTask(nodes);
  assert.equal(active(), '150 ms (75.0%)');
  events.splice(0, events.length, { type: 'start', engine: 'jev', total: 1 }, result(0));
  await runTask(nodes);
  assert.equal(active(), '0 ms (N/A)');
});

test('connection status shares the title row without a breadcrumb header', () => {
  const html = readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');
  assert.ok(!html.includes('Workspace / Log classification'));
  assert.ok(!html.includes('<header>'));
  const title = html.match(/<div class="intro-title">(.*?)<\/div>/s)[1];
  assert.ok(title.includes('<h1>Main</h1>'));
  assert.ok(!html.includes('LOG INTELLIGENCE'));
  assert.ok(!html.includes('LOG COLLECTION'));
  assert.ok(title.includes('id="status"'));
  assert.equal((html.match(/id="status"/g) || []).length, 1);
});

test('New Tasks default to Disabled one-time Batch and do not auto-resume', async () => {
  const {nodes,context}=workspace([]);await vm.runInContext('handleEditTask()',context);
  assert.equal(nodes.get('source-mode').value,'batch');assert.equal(nodes.get('task-trigger').value,'manual');
  assert.equal(nodes.get('task-enabled').checked,false);
  assert.equal(nodes.get('task-resume').checked,false);assert.equal(nodes.get('task-cron-field').hidden,true);
});

test('Changing Task modes retains the Source configuration draft', async () => {
  const {nodes,context}=workspace([]);await vm.runInContext('handleEditTask()',context);
  vm.runInContext("sourceRows[0].profile.value='2e44ae00-7a3a-492d-8806-9177a8973582';sourceRows[0].size.value='5';sourceRows[0].action.value='Notify'",context);
  nodes.get('source-mode').value='realtime';nodes.get('source-mode').onchange();nodes.get('source-mode').value='batch';nodes.get('source-mode').onchange();
  assert.equal(vm.runInContext('sourceRows[0].profile.value',context),'2e44ae00-7a3a-492d-8806-9177a8973582');assert.equal(vm.runInContext('sourceRows[0].size.value',context),'5');
});

test('Main monitors Tasks and Source configuration lives only in Tasks', () => {
  const html=readFileSync(new URL('../public/index.html',import.meta.url),'utf8');
  const main=html.slice(html.indexOf('id="main-page"'),html.indexOf('id="tasks-page"'));
  assert.ok(main.includes('id="running-tasks"'));assert.ok(!main.includes('id="source-settings"'));
  assert.ok(!html.includes('id="paste-input"'));assert.ok(!html.includes('<option value="paste">Paste</option>'));
});

 test('sidebar identifies the DeciFlow reader host', async () => {
  const { nodes } = workspace([], {
    host: { hostname: 'log-node', addresses: ['192.168.35.10', '10.0.0.2'], os: 'Rocky Linux 8.10' },
    engine: 'laya', configured: true, model: 'multilingual',
    workingDirectory: '/logs', limits: { context_tokens: 8192 },
  });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(nodes.get('host-name').textContent, 'log-node');
  assert.equal(nodes.get('host-os').textContent, 'Rocky Linux 8.10');
  assert.equal(nodes.get('host-addresses').textContent, '192.168.35.10\n10.0.0.2');
});

test('Editing an existing Task restores saved per-Source criteria, chunk size and Action', async () => {
  const {context}=workspace([]);await vm.runInContext("handleEditTask({id:'saved',name:'Logs',mode:'batch',timezone:'UTC',cron:'',sources:[{sourceId:sampleSources[0].id,profile:'2e44ae00-7a3a-492d-8806-9177a8973582',chunkEvents:3,actionId:'notify'}]})",context);
  assert.equal(vm.runInContext('sourceRows[0].profile.value',context),'2e44ae00-7a3a-492d-8806-9177a8973582');assert.equal(vm.runInContext('sourceRows[0].size.value',context),'3');assert.equal(vm.runInContext('sourceRows[0].action.value',context),'notify');
});

test('individual JSON reflects review changes and stays open after rendering', async () => {
  const event = result(0);
  Object.assign(event.result, { profile: '2e44ae00-7a3a-492d-8806-9177a8973582', chunkEvents: 3, eventCount: 2, source: '/logs/access.log', line: 10, lineEnd: 11, log: '<script>example</script>' });
  const failed = result(1);
  failed.result = { log: 'bad input', error: 'request failed', review: true, elapsedMs: 1, profile: '0181af82-c1ed-41c8-8cd3-22a385746b32' };
  const { nodes, context } = workspace([{ type: 'start', total: 2, engine: 'laya' }, event, failed]);
  await runTask(nodes);
  const row = nodes.get('results').children[1];
  const details = row.children.at(-1);
  assert.equal(details.children[0].textContent, 'View Result JSON');
  assert.equal(details.children[1].children[1].textContent, '');
  details.open = true; details.ontoggle();
  assert.equal(JSON.parse(details.children[1].children[1].textContent).lineEnd, 11);
  assert.equal(JSON.parse(details.children[1].children[1].textContent).log, '<script>example</script>');
  const select = row.children.at(-2).children[1].children[0].children[0];
  select.value = 'warning'; select.onchange();
  assert.equal(JSON.parse(details.children[1].children[1].textContent).reviewerDecisions.category, 'warning');
  vm.runInContext('render()', context);
  const reopened = nodes.get('results').children[1].children.at(-1);
  assert.equal(reopened.open, true);
  reopened.open = false; reopened.ontoggle();
  vm.runInContext('render()', context);
  assert.equal(nodes.get('results').children[1].children.at(-1).open, false);
  const failureView = nodes.get('results').children[0].children.at(-1);
  failureView.open = true; failureView.ontoggle();
  assert.equal(JSON.parse(failureView.children[1].children[1].textContent).error, 'request failed');
});

test('pause freezes rows while analysis continues; resume includes pending results', async () => {
  const { nodes, context } = workspace([]);
  let receive, finish;
  context.readEvents = async (_, callback) => {
    receive = callback;
    await new Promise(resolve => { finish = resolve; });
  };
  const run = runTask(nodes);
  await new Promise(resolve => setImmediate(resolve));
  receive({ type: 'start', engine: 'laya', total: null });
  receive(result(0, false));
  vm.runInContext('render()', context);
  const original = nodes.get('results').children[0];
  const details = original.children.at(-1);
  details.open = true; details.ontoggle();
  nodes.get('pause-updates').onclick();
  receive(result(1));
  receive(result(2, false));
  vm.runInContext('render(false)', context);
  assert.equal(nodes.get('results').children[0], original);
  assert.equal(details.open, true);
  assert.equal(nodes.get('summary').children[0].children[0].children.map(node => node.textContent).join(''), '3 / 0 / 3');
  assert.equal(nodes.get('pause-updates').textContent, 'Resume Display Updates (2 new)');
  nodes.get('review-filter').value = 'needs-review';
  nodes.get('review-filter').onchange();
  assert.equal(nodes.get('results').children[0].textContent, 'No results to display.');
  nodes.get('review-filter').value = 'all'; nodes.get('review-filter').onchange();
  assert.deepEqual(logs(nodes), ['log-0']);
  nodes.get('processing-filter').value='failed';nodes.get('processing-filter').onchange();
  assert.equal(nodes.get('results').children[0].textContent, 'No results to display.');
  nodes.get('processing-filter').value = 'all'; nodes.get('processing-filter').onchange();
  nodes.get('log-search').value = 'LOG-1'; nodes.get('log-search').oninput();
  assert.equal(nodes.get('results').children[0].textContent, 'No results to display.');
  nodes.get('log-search').value = ''; nodes.get('log-search').oninput();
  assert.deepEqual(logs(nodes), ['log-0']);
  finish(); await run;
  assert.deepEqual(logs(nodes), ['log-0']);
  assert.equal(nodes.get('pause-updates').textContent, 'Resume Display Updates (2 new)');
  nodes.get('pause-updates').onclick();
  assert.deepEqual(logs(nodes), ['log-2', 'log-1', 'log-0']);
  assert.equal(nodes.get('pause-updates').textContent, 'Pause Display Updates');
  nodes.get('pause-updates').onclick();
  context.readEvents = async (_, callback) => {
    callback({ type: 'start', engine: 'laya', total: 1 }); callback(result(0));
  };
  await runTask(nodes);
  assert.equal(nodes.get('pause-updates').textContent, 'Pause Display Updates');
  assert.deepEqual(logs(nodes), ['log-0']);
});

test('pause excludes received results that have not yet been displayed', async () => {
  const { nodes, context } = workspace([{ type: 'start', total: null, engine: 'laya' }, result(0)]);
  await runTask(nodes);
  vm.runInContext("results[1] = { log: 'queued', elapsedMs: 1, review: true }; completionOrder.push(1); completed++;", context);
  nodes.get('pause-updates').onclick();
  nodes.get('review-filter').onchange();
  assert.deepEqual(logs(nodes), ['log-0']);
  assert.equal(nodes.get('pause-updates').textContent, 'Resume Display Updates (1 new)');
});

test('file line labels distinguish batch from observed realtime sequences', async () => {
  for (const mode of ['batch', 'realtime']) {
    const first = result(0);
    Object.assign(first.result, { source: '/var/log/secure', line: 1, lineEnd: 1, profile: '4e6d5417-611e-49e0-8e23-2444a0f49ee4', eventCount: 1, chunkEvents: 1 });
    const second = result(1);
    Object.assign(second.result, { source: '/var/log/secure', line: 10, lineEnd: 12, lineCount: 3, profile: '702ecfa5-01fb-4321-9692-996134a10802', eventCount: 1, chunkEvents: 5 });
    const { nodes, context } = workspace([{ type: 'start', engine: 'laya', total: null, mode }, first, second]);
    await runTask(nodes);
    const rows = nodes.get('results').children;
    const detailValues=row=>Object.fromEntries(row.children.find(node=>node.children[0]?.textContent==='Details').children[1].children.map(field=>[field.children[0].textContent,field.children[1]]));
    const prefix = mode === 'realtime' ? 'Observed' : 'File';
    assert.equal(detailValues(rows[1]).Source.textContent, `/var/log/secure · ${prefix} line 1`);
    assert.equal(detailValues(rows[0]).Source.textContent, `/var/log/secure · ${prefix} lines 10–12`);
    assert.equal(detailValues(rows[1]).Criteria.textContent, 'Sample General System · Chunk: 1 event (max 1)');
    assert.equal(detailValues(rows[0]).Criteria.textContent, 'Sample Authentication · Chunk: 1 event (max 5)');
    if (mode === 'realtime') assert.ok(detailValues(rows[1]).Source.title.includes('not an absolute'));
    nodes.get('source-mode').value = mode === 'realtime' ? 'batch' : 'realtime';
    nodes.get('source-mode').onchange();
    vm.runInContext('render()', context);
    assert.equal(detailValues(nodes.get('results').children[1]).Source.textContent, `/var/log/secure · ${prefix} line 1`);
  }
});

test('realtime can pause before receiving its first result', async () => {
  const { nodes, context } = workspace([]);
  let receive, finish;
  context.readEvents = async (_, callback) => {
    receive = callback;
    await new Promise(resolve => { finish = resolve; });
  };
  const run = runTask(nodes);
  await new Promise(resolve => setImmediate(resolve));
  receive({ type: 'start', engine: 'laya', mode: 'realtime', total: null });
  assert.equal(nodes.get('pause-updates').disabled, false);
  nodes.get('pause-updates').onclick();
  const original = nodes.get('results').children[0];
  receive(result(0));
  vm.runInContext('render(false)', context);
  assert.equal(nodes.get('results').children[0], original);
  assert.equal(nodes.get('pause-updates').textContent, 'Resume Display Updates (1 new)');
  nodes.get('pause-updates').onclick();
  assert.deepEqual(logs(nodes), ['log-0']);
  finish(); await run;
});

test('profile selectors have visible Criteria labels', () => {
  const { nodes } = workspace([]);
  for (const row of nodes.get('source-settings').children) {
    assert.equal(row.children[1].textContent, 'Criteria ');
    assert.equal(row.children[1].children.length, 1);
  }
  const html = readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');
  assert.ok(html.includes('Sources and Decisions'));
});

test('category chart applies result filters and preserves original AI counts after edits', async () => {
  const events = [{ type: 'start', engine: 'laya', total: null }];
  for (const [index, category] of ['normal', 'normal', 'warning', 'error', 'security', 'other'].entries()) {
    const event = result(index, index % 2 === 0);
    setDecisions(event.result, { choice:category, source: index % 2 ? '/logs/http' : '/logs/system', eventCount: 10, chunkEvents: 10 });
    events.push(event);
  }
  const failure = result(6);
  failure.result = { log: 'failed', error: 'timeout', review: true, elapsedMs: 1, category: 'error' };
  events.push(failure);
  const { nodes, context } = workspace(events);
  const values = () => nodes.get('category-chart').children.map(row => row.children[2].textContent);
  assert.deepEqual(values(), Array(5).fill('0 (0.0%)'));
  await runTask(nodes);
  assert.deepEqual(values(), ['2 (33.3%)', '1 (16.7%)', '1 (16.7%)', '1 (16.7%)', '1 (16.7%)']);
  assert.equal(nodes.get('category-chart').children[0].children[1].children[0].attributes.style, 'width:100%');
  assert.equal(nodes.get('category-chart').children[1].children[1].children[0].attributes.style, 'width:50%');
  assert.equal(nodes.get('chart-totals').textContent, '6 classified chunks · 1 failed request');
  nodes.get('review-filter').value = 'needs-review'; nodes.get('review-filter').onchange();
  vm.runInContext("results[0].reviewerDecisions = {category:'security'}; render();", context);
  assert.equal(values()[0], '1 (25.0%)');
  assert.match(nodes.get('chart-totals').textContent,/Filtered Results/);
  nodes.get('review-filter').value='all';nodes.get('review-filter').onchange();
  nodes.get('pause-updates').onclick();
  vm.runInContext("results[7] = systemResult('new');results[7].decisions.category.choice='security'; completionOrder.push(7); completed++; render(false);", context);
  assert.equal(values()[3], '2 (28.6%)');
  events.splice(0, events.length, { type: 'start', engine: 'laya', total: 0 });
  await runTask(nodes);
  assert.deepEqual(values(), Array(5).fill('0 (0.0%)'));
});

test('category overview precedes Log input and Classification Results', () => {
  const html = readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');
  assert.ok(html.indexOf('Classification Overview') < html.indexOf('Task Monitor'));
  assert.ok(html.indexOf('Classification Overview') < html.indexOf('Classification Results'));
});

test('uncertain category is explicitly provisional without changing the model choice', async () => {
  const event = result(0);
  setDecisions(event.result, { choice: 'error', confidence: .26, uncertain: true,
    candidates: ['error', 'other'], reasons: ['low_answer_probability', 'close_probabilities'],
    probabilities: { normal: .01, warning: .18, error: .41, security: 0, other: .4 } });
  const { nodes } = workspace([{ type: 'start', engine: 'jev', total: 1 }, event]);
  await runTask(nodes);
  const row = nodes.get('results').children[0];
  assert.equal(decisionCards(row)[0].children[1].textContent, 'Error');
  assert.ok(decisionCards(row)[0].children.at(-1).textContent.includes('Error 41.0% vs Other 40.0%'));
  assert.ok(decisionCards(row)[0].children.at(-1).textContent.includes('top two probabilities differ'));
  const details = row.children.at(-1); details.open = true; details.ontoggle();
  assert.equal(JSON.parse(details.children[1].children[1].textContent).decisions.category.choice, 'error');
  assert.equal(nodes.get('category-chart').children[2].children[2].textContent, '1 (100.0%)');
});

test('workspace places input and overview in the 40% column beside 60% results', () => {
  const html = readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');
  const css = readFileSync(new URL('../public/style.css', import.meta.url), 'utf8').replace(/\s*([{}:;])\s*/g, '$1');
  const leftStart = html.indexOf('<div class="input-column">');
  const leftEnd = html.indexOf('</div>\n      <section id="classification-results" class="card output">', leftStart);
  assert.ok(leftStart >= 0 && leftEnd > leftStart);
  const left = html.slice(leftStart, leftEnd);
  assert.ok(left.includes('Task Monitor'));
  assert.ok(left.includes('Classification Overview'));
  assert.ok(!left.includes('Classification Results'));
  assert.ok(css.includes('grid-template-columns:minmax(0,2fr) minmax(0,3fr)'));
  assert.ok(css.includes('.workspace{grid-template-columns:1fr}'));
});

test('category, review and literal log search combine and retain full aggregates', async () => {
  const normal = result(0, false);
  normal.result.log = 'Service Started [OK]';
  const warning = result(1);
  warning.result.decisions.category.choice = 'warning';
  warning.result.log = 'Service retry [pending]';
  const failed = { type: 'result', index: 2, elapsedMs: 3,
    result: { log: 'Service request failed', error: 'timeout', review: true, elapsedMs: 2 } };
  const { nodes } = workspace([{ type: 'start', engine: 'laya', total: 3 }, normal, warning, failed]);
  await runTask(nodes);
  nodes.get('log-search').value = 'SERVICE'; nodes.get('log-search').oninput();
  assert.equal(logs(nodes).length, 3);
  nodes.get('processing-filter').value='successful';nodes.get('processing-filter').onchange();
  assert.deepEqual(logs(nodes), ['Service retry [pending]','Service Started [OK]']);
  nodes.get('review-filter').value = 'needs-review'; nodes.get('review-filter').onchange();
  assert.deepEqual(logs(nodes), ['Service retry [pending]']);
  nodes.get('processing-filter').value = 'successful'; nodes.get('processing-filter').onchange();
  nodes.get('log-search').value = '[PENDING]'; nodes.get('log-search').oninput();
  assert.deepEqual(logs(nodes), ['Service retry [pending]']);
  nodes.get('log-search').value = '.*'; nodes.get('log-search').oninput();
  assert.equal(nodes.get('results').children[0].textContent, 'No results to display.');
  nodes.get('log-search').value = ''; nodes.get('log-search').oninput();
  nodes.get('processing-filter').value='failed';nodes.get('processing-filter').onchange();
  assert.equal(nodes.get('results').children[0].textContent, 'No results to display.');
  nodes.get('review-filter').value = 'all'; nodes.get('review-filter').onchange();
  assert.deepEqual(logs(nodes), ['Service request failed']);
  assert.equal(nodes.get('summary').children[0].children[0].children.map(node => node.textContent).join(''), '2 / 1 / 3');
  nodes.get('processing-filter').value = 'all'; nodes.get('processing-filter').onchange();
  nodes.get('review-filter').value = 'all'; nodes.get('review-filter').onchange();
  assert.equal(logs(nodes).length, 3);
});

test('chart certainty groups partition classified results without treating failures as uncertain', async () => {
  const events = [{ type: 'start', engine: 'laya', total: 4 }];
  for (const [index, category, uncertain, review] of [
    [0, 'normal', false, false], [1, 'error', true, true], [2, 'other', false, true],
  ]) {
    const event = result(index, review);
    setDecisions(event.result, { choice:category, uncertain });
    events.push(event);
  }
  events.push({ type: 'result', index: 3, result: { log: 'failed', error: 'timeout', review: true, elapsedMs: 1 } });
  const { nodes } = workspace(events);
  await runTask(nodes);
  const values = () => nodes.get('category-chart').children.map(row => row.children[2].textContent);
  const options = () => ['all', 'certain', 'uncertain'].map(key => nodes.get(`chart-${key}`).textContent);
  assert.deepEqual(options(), ['All · 3', 'Certain · 2 (66.7%)', 'Uncertain · 1 (33.3%)']);
  nodes.get('pause-updates').onclick();
  nodes.get('chart-uncertain').onclick();
  assert.deepEqual(values(), ['0 (0.0%)', '0 (0.0%)', '1 (100.0%)', '0 (0.0%)', '0 (0.0%)']);
  assert.equal(nodes.get('chart-totals').textContent, '1 classified chunk · 1 failed request');
  assert.equal(nodes.get('chart-uncertain').attributes['aria-pressed'], 'true');
  assert.equal(nodes.get('chart-all').attributes['aria-pressed'], 'false');
  assert.deepEqual(options(), ['All · 3', 'Certain · 2 (66.7%)', 'Uncertain · 1 (33.3%)']);
  nodes.get('chart-certain').onclick();
  assert.deepEqual(values(), ['1 (50.0%)', '0 (0.0%)', '0 (0.0%)', '0 (0.0%)', '1 (50.0%)']);
  assert.equal(nodes.get('summary').children[0].children[0].children.map(node => node.textContent).join(''), '3 / 1 / 4');
  assert.equal(nodes.get('results').children.length, 4);
  nodes.get('chart-all').onclick();
  assert.equal(nodes.get('chart-totals').textContent, '3 classified chunks · 1 failed request');
});

test('chart certainty buttons show zero counts before results arrive', () => {
  const { nodes } = workspace([]);
  assert.deepEqual(['all', 'certain', 'uncertain'].map(key => nodes.get(`chart-${key}`).textContent),
    ['All · 0', 'Certain · 0 (0.0%)', 'Uncertain · 0 (0.0%)']);
});

test('truncated count includes rejected responses across chart filters and paused updates', async () => {
  const events = [{ type: 'start', engine: 'laya', total: 3 }, result(0, false),
    { type: 'result', index: 1, result: { log: 'too long', error: 'truncated', review: true, elapsedMs: 1, providerResponse: { usage: { truncated: true } } } },
    { type: 'result', index: 2, result: { log: 'timeout', error: 'timeout', review: true, elapsedMs: 1 } }];
  const { nodes, context } = workspace(events);
  await runTask(nodes);
  assert.equal(nodes.get('chart-truncated').textContent, 'Truncated: 1');
  nodes.get('chart-certain').onclick();
  assert.equal(nodes.get('chart-truncated').textContent, 'Truncated: 1');
  nodes.get('pause-updates').onclick();
  vm.runInContext("results.push({log:'more', error:'truncated', review:true, elapsedMs:1, providerResponse:{usage:{truncated:true}}}); render(false);", context);
  assert.equal(nodes.get('chart-truncated').textContent, 'Truncated: 2');
  assert.equal(nodes.get('chart-totals').textContent, '1 classified chunk · 3 failed requests');
});

test('result label uses selected category probability rather than provider confidence', async () => {
  const event = result(0, false);
  setDecisions(event.result, { confidence: .16, probabilities:{normal:.9,warning:.1,error:0,security:0,other:0} });
  const { nodes } = workspace([{ type: 'start', engine: 'laya', total: 1 }, event]);
  await runTask(nodes);
  assert.equal(decisionCards(nodes.get('results').children[0])[0].children[2].textContent, '90.0% selected probability');
});

test('collapsed options show the rendering integrity warning', async () => {
  const event = result(0);
  setDecisions(event.result, {
    uncertain: true, candidates: ['normal'], reasons: ['collapsed_options'],
  });
  const { nodes } = workspace([{ type: 'start', engine: 'laya', total: 1 }, event]);
  await runTask(nodes);
  const texts = decisionCards(nodes.get('results').children[0])[0].children.map(child => child.textContent || '');
  assert.ok(texts.some(text => text.includes('option descriptions lost distinction')));
});

test('Copy JSON copies current reviewer edits and reports success or failure', async () => {
  const { nodes, context } = workspace([
    { type: 'start', engine: 'laya', total: 1 }, result(0),
  ]);
  let copied;
  context.navigator = { clipboard: { writeText: async text => { copied = text; } } };
  await runTask(nodes);
  const row = nodes.get('results').children[0];
  const reviewer = row.children.at(-2).children[1].children[0].children[0];
  reviewer.value = 'warning';
  reviewer.onchange();
  const actions = row.children.at(-1).children[1].children[0];
  assert.equal(actions.children[0].textContent, 'Copy');
  assert.equal(actions.children[0].className, 'json-copy');
  await actions.children[0].onclick();
  assert.equal(JSON.parse(copied).reviewerDecisions.category, 'warning');
  assert.equal(JSON.parse(copied).log, 'log-0');
  assert.equal(actions.children[1].textContent, 'Copied');
  context.navigator.clipboard.writeText = async () => { throw new Error('Denied'); };
  await actions.children[0].onclick();
  assert.match(actions.children[1].textContent, /Copy failed/);
  assert.equal(actions.children[0].disabled, false);
});

test('clipboard fallback copies on HTTP and cleans up on failure', async () => {
  const { context } = workspace([]);
  let removed = 0;
  let restored = 0;
  let selected;
  context.document.activeElement = { focus() { restored++; } };
  context.document.body = { append(buffer) {
    buffer.select = () => { selected = buffer.value; };
    buffer.remove = () => { removed++; };
  } };
  context.document.execCommand = command => command === 'copy';
  await vm.runInContext('copyText("example JSON")', context);
  assert.equal(selected, 'example JSON');
  assert.equal(removed, 1);
  assert.equal(restored, 1);
  context.document.execCommand = () => false;
  await assert.rejects(vm.runInContext('copyText("example JSON")', context));
  assert.equal(removed, 2);
  assert.equal(restored, 2);
});

test('quiet actions and JSON disclosure have visible button borders', () => {
  const css = readFileSync(new URL('../public/style.css', import.meta.url), 'utf8').replace(/\s*([{}:;])\s*/g, '$1');
  assert.match(css, /\.quiet\{[^}]*border:1px solid/);
  assert.match(css, /\.result-json summary\{[^}]*border:1px solid/);
});

test('stream errors are red and a new successful run clears the error style', async () => {
  const events = [{ type: 'error', error: 'File access denied' }];
  const { nodes } = workspace(events);
  await runTask(nodes);
  assert.equal(nodes.get('message').className, 'error-message');
  events.splice(0, events.length, { type: 'start', engine: 'laya', total: 1 }, result(0));
  await runTask(nodes);
  assert.equal(nodes.get('message').className.includes('error-message'), false);
});

test('selected engine is explicitly named and emphasized for both engines', async () => {
  for (const engine of ['laya', 'jev']) {
    for (const configured of [true, false]) {
      const { nodes } = workspace([], {
        host: { hostname: 'host', addresses: [], os: 'Linux' },
        engine, configured, model: 'test', workingDirectory: '/app',
        limits: { context_tokens: 8192, max_jev_input_bytes: 30000 },
      });
      nodes.get('source-mode').value = 'realtime';
      await new Promise(resolve => setImmediate(resolve));
      const status = nodes.get('status');
      assert.equal(status.textContent, 'Decision Engine: ');
      assert.equal(status.children[0].textContent, engine === 'laya' ? 'Laya' : 'Jev');
      assert.equal(status.children[0].className, 'selected-engine');
      assert.equal(status.children[2].textContent, ' · Model: ');
      assert.equal(status.children[3].textContent, 'test');
      assert.equal(status.children[3].className, 'selected-model');
      assert.equal(status.children.length, configured ? 4 : 5);
      assert.equal(status.children[1].textContent, ' (Reachable)');
      if (!configured) assert.equal(status.children[4].textContent, ' · API key required');
    }
  }
  const css = readFileSync(new URL('../public/style.css', import.meta.url), 'utf8').replace(/\s*([{}:;])\s*/g, '$1');
  assert.ok(css.includes('.selected-engine{color:#7c3aed;font-weight:700}'));
  assert.ok(css.includes('.selected-model{color:#7c3aed;font-weight:700;}'));
});


test('uncertain results retain their category color class', async () => {
  const categories = ['normal', 'warning', 'error', 'security', 'other'];
  for (const uncertain of [false, true]) {
    const events = categories.map((category, index) => {
      const event = result(index);
      setDecisions(event.result, { choice:category, uncertain });
      return event;
    });
    const { nodes } = workspace(events);
    await runTask(nodes);
    for (const [index, row] of nodes.get('results').children.entries()) {
      const category = categories[categories.length - 1 - index];
      const badge = decisionCards(row)[0].children[1];
      assert.equal(badge.className, `badge ${category}${uncertain ? ' uncertain' : ''}`);
      assert.equal(badge.textContent.startsWith('Uncertain · '), false);
      assert.equal(decisionCards(row)[0].children[2].children.some(node=>node.className==='decision-uncertainty' && node.textContent==='Uncertain'),uncertain);
    }
  }
  const css = readFileSync(new URL('../public/style.css', import.meta.url), 'utf8').replace(/\s*([{}:;])\s*/g, '$1');
  assert.doesNotMatch(css, /\.badge\.uncertain\{[^}]*background/);
});


test('chart bars and result badges share the same category colors', () => {
  const css = readFileSync(new URL('../public/style.css', import.meta.url), 'utf8').replace(/\s*([{}:;])\s*/g, '$1');
  for (const [category, color] of Object.entries({
    normal: '#498568', warning: '#c29b43', error: '#c86b60',
    security: '#8c649d', other: '#84938c',
  })) {
    assert.ok(css.includes(`.category-bar.${category},.badge.${category}{background:${color}}`));
  }
});


test('throughput uses active time, excludes failures, ignores idle time and resets', async () => {
  const success = (index, elapsedMs) => ({ ...result(index), elapsedMs });
  const failed = success(3, 5600);
  failed.result.error = 'timeout';
  const events = [{ type: 'start', engine: 'laya', total: null },
    success(0, 1000), success(1, 2000), success(2, 5500), failed,
    { type: 'timing', elapsedMs: 7000, activeProcessingMs: 3000 }];
  const { nodes } = workspace(events);
  const rate = () => nodes.get('summary').children[2].children[0].textContent;
  await runTask(nodes);
  assert.equal(rate(), '1.000 chunks/s');
  nodes.get('review-filter').value = 'no-review';
  nodes.get('review-filter').onchange();
  assert.equal(rate(), '1.000 chunks/s');
  events.push({ type: 'timing', elapsedMs: 11000, activeProcessingMs: 3000 });
  await runTask(nodes);
  assert.equal(rate(), '1.000 chunks/s');
  events.push({ type: 'timing', elapsedMs: 12000, activeProcessingMs: 4000 });
  await runTask(nodes);
  assert.equal(rate(), '0.750 chunks/s');
  events.splice(0, events.length, { type: 'start', engine: 'jev', total: 1 },
    success(0, 1000), {type:'timing',elapsedMs:2000,activeProcessingMs:500});
  await runTask(nodes);
  assert.equal(rate(), '2.000 chunks/s');
  events.splice(0,events.length,{type:'start',engine:'laya',total:0},{type:'timing',elapsedMs:5000,activeProcessingMs:0});
  await runTask(nodes);
  assert.equal(rate(),'0.000 chunks/s');
});


test('source filtering uses input patterns with counts and combines with other filters', async () => {
  const first = result(0, false);
  Object.assign(first.result, { source: '/logs/access-1.log', sourcePatterns: ['/logs/access*.log'], log: 'request ok' });
  const second = result(1);
  setDecisions(second.result, { source: '/logs/messages', sourcePatterns: ['/logs/*', '/logs/messages'], log: 'service failed', choice: 'error' });
  const events = [{ type: 'start', engine: 'jev', total: null,
    sourcePatterns: ['/logs/access*.log', '/logs/*', '/logs/messages', '/logs/empty.log'] },
    first, second];
  const { nodes } = workspace(events);
  await runTask(nodes);
  const select = nodes.get('source-filter');
  assert.ok(select.children.some(option => option.text === '/logs/messages (1)'));
  assert.ok(select.children.some(option => option.text === '/logs/empty.log (0)'));
  select.value = '/logs/messages'; select.onchange();
  assert.deepEqual(logs(nodes), ['service failed']);
  nodes.get('processing-filter').value='failed';nodes.get('processing-filter').onchange();
  assert.equal(nodes.get('results').children[0].textContent, 'No results to display.');
  nodes.get('processing-filter').value = 'all';
  nodes.get('log-search').value = 'failed'; nodes.get('log-search').oninput();
  assert.deepEqual(logs(nodes), ['service failed']);
  assert.equal(nodes.get('summary').children[0].children[0].children.map(node => node.textContent).join(''), '2 / 0 / 2');
  select.value = '/logs/*'; select.onchange();
  assert.deepEqual(logs(nodes), ['service failed']);
  events.splice(0, events.length, { type: 'start', engine: 'laya', total: null,
    sourcePatterns: ['/logs/new.log'] });
  await runTask(nodes);
  assert.equal(select.value, 'all');
  assert.ok(!select.children.some(option => option.value === '/logs/messages'));
});

test('file Actions are assigned in requests and execution failures are visible', async () => {
  const event = result(0, false);
  event.result.actionExecution = { name: 'notify', status: 'failed', exitCode: 7, elapsedMs: 12 };
  const { nodes, context, requests } = workspace([
    { type: 'start', engine: 'laya', total: 1 }, event,
  ]);
  await new Promise(resolve => setImmediate(resolve));
  vm.runInContext("registeredActions = [{id:'notify',name:'notify', python: '/venv/bin/python', script: '/actions/notify.py'}]; renderActions(); updateSourceSettings();", context);
  const selector = nodes.get('source-settings').children[0].children[3].children[0];
  assert.match(selector.attributes['aria-label'], /^Action for /);
  assert.deepEqual(selector.children.map(option => option.text), ['None', 'notify']);
  selector.value = 'notify'; selector.onchange();
  await runTask(nodes);
  assert.equal(requests[0].sources[0].actionId, 'notify');
  assert.ok(nodes.get('results').children[0].children.some(node => node.textContent?.includes('Action execution: notify · failed · 12ms · exit 7')));
  assert.equal(selector.disabled, false);
});

test('Action editor sends Python Versions and module lists and recovers from preparation errors', async () => {
  const { nodes, context } = workspace([]);
  await new Promise(resolve => setImmediate(resolve));
  nodes.get('add-action').onclick();
  const row = nodes.get('action-editor').children[0];
  const inputs = row.children.slice(0, 4).map(label => label.children[0]);
  assert.equal(inputs[0].readOnly, false);
  assert.equal(row.children[0].children.length, 1);
  assert.equal(inputs[1].value, '3.12');
  inputs[0].value = 'notify'; inputs[3].value = 'import json, sys\nresult = json.load(sys.stdin)\n';
  inputs[2].value = 'httpx==0.28.1\nrequests';
  let sent, complete;
  context.fetch = async (path, options) => {
    assert.equal(path, '/api/actions');
    sent = JSON.parse(options.body);
    await new Promise(resolve => { complete = resolve; });
    return { ok: false, json: async () => ({ error: 'Could not prepare action notify.' }) };
  };
  const saving = nodes.get('save-actions').onclick();
  assert.equal(nodes.get('save-actions').disabled, true);
  assert.equal(inputs[2].disabled, true);
  assert.equal(sent[0].pythonVersion, '3.12');
  assert.equal(sent[0].modules, 'httpx==0.28.1\nrequests');
  assert.ok(sent[0].code.includes('json.load(sys.stdin)'));
  assert.equal(Object.hasOwn(sent[0], 'script'), false);
  complete(); await saving;
  assert.equal(nodes.get('save-actions').disabled, false);
  assert.equal(inputs[2].disabled, false);
  assert.equal(inputs[2].value, 'httpx==0.28.1\nrequests');
  assert.equal(nodes.get('action-message').textContent, 'Could not prepare action notify.');
  context.fetch = async (path, options) => ({ ok: true, json: async () => ({ actions: JSON.parse(options.body) }) });
  await nodes.get('save-actions').onclick();
  assert.ok(nodes.get('action-message').textContent.includes('environments ready'));
});


test('sidebar returns to the Actions list and discards an unsaved editor', async () => {
  const { nodes } = workspace([]);
  await new Promise(resolve => setImmediate(resolve));
  nodes.get('nav-actions').onclick();
  assert.equal(nodes.get('main-page').hidden, true);
  assert.equal(nodes.get('actions-page').hidden, false);
  assert.equal(nodes.get('nav-actions').attributes['aria-current'], 'page');
  nodes.get('add-action').onclick();
  const code = nodes.get('action-editor').children[0].children[3].children[0];
  code.value = 'print("editor draft")';
  nodes.get('nav-main').onclick();
  nodes.get('nav-actions').onclick();
  assert.equal(nodes.get('action-editor').hidden,true);
  assert.equal(nodes.get('action-editor').children.length,0);
  assert.equal(nodes.get('action-list').hidden,false);
  const html = readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');
  assert.ok(html.indexOf('id="action-registry"') > html.indexOf('id="actions-page"'));
  assert.ok(!html.includes('Python script path'));
});


test('Action list edits one handler, cancels drafts, and saves deletion without losing others', async () => {
  const { nodes, context } = workspace([]);
  await new Promise(resolve => setImmediate(resolve));
  vm.runInContext("registeredActions = [{id:'first', name:'First', pythonVersion:'3.12', modules:[], code:'pass'}, {id:'second', name:'Second', pythonVersion:'3.13', modules:['httpx'], code:'pass'}]; renderActions();", context);
  const table = () => nodes.get('action-registry').children[0];
  assert.equal(table().children.length, 3);
  assert.equal(table().children[2].children[0].textContent, 'Second');
  table().children[2].children.at(-1).children[1].onclick();
  assert.equal(nodes.get('action-editor').children.length, 1);
  nodes.get('action-editor').children[0].children[0].children[0].value = 'Discard';
  nodes.get('cancel-action').onclick();
  assert.equal(table().children[2].children[0].textContent, 'Second');
  table().children[2].children.at(-1).children[1].onclick();
  assert.equal(nodes.get('action-editor').children[0].children[0].children[0].readOnly, false);
  nodes.get('action-editor').children[0].children[0].children[0].value = 'Edited';
  let sent;
  context.fetch = async (path, options) => {
    if(path==='/api/delete-check')return {ok:true,json:async()=>({references:[],details:[]})};
    sent = JSON.parse(options.body);
    return {ok:true, json:async () => ({actions:sent})};
  };
  await nodes.get('save-actions').onclick();
  assert.equal(sent.length, 2);
  assert.equal(sent[0].name, 'First');
  assert.equal(sent[1].name, 'Edited');
  assert.equal(nodes.get('action-editor').hidden, true);
  await table().children.find(row=>row.children[0].textContent==='First').children.at(-1).children[3].onclick();
  await nodes.get('save-actions').onclick();
  assert.equal(sent.length, 1);
  assert.equal(sent[0].name, 'Edited');
  nodes.get('add-action').onclick();
  nodes.get('cancel-action').onclick();
  assert.equal(table().children.length, 2);
});


test('Action name search ignores case and retains original edit and delete targets', async () => {
  const { nodes, context } = workspace([]);
  await new Promise(resolve => setImmediate(resolve));
  vm.runInContext("registeredActions = [{id:'First',name:'First', code:'pass'}, {id:'Notify admin',name:'Notify admin', code:'pass'}, {id:'Last',name:'Last', code:'pass'}]; renderActions();", context);
  const search = nodes.get('action-search');
  search.value = '  NOTIFY  '; search.oninput();
  const table = nodes.get('action-registry').children[0];
  assert.equal(table.children.length, 2);
  assert.equal(table.children[1].children[0].textContent, 'Notify admin');
  table.children[1].children.at(-1).children[1].onclick();
  assert.equal(nodes.get('action-editor').children[0].children[0].children[0].value, 'Notify admin');
  nodes.get('cancel-action').onclick();
  await nodes.get('action-registry').children[0].children[1].children.at(-1).children[3].onclick();
  assert.equal(nodes.get('action-registry').children[0].textContent, 'No Actions match your search.');
  search.value = ''; search.oninput();
  assert.equal(nodes.get('action-registry').children[0].children.length, 3);
  assert.equal(nodes.get('action-registry').children[0].children[2].children[0].textContent, 'Last');
});


test('source rows select registered sources, reject unknown text, and retain settings across modes', async () => {
  const { nodes, context, requests } = workspace([]);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(nodes.get('source-settings').children.length, 3);
  const first = nodes.get('source-settings').children[0];
  const path = first.children[0].children[0];
  assert.equal(path.value, '1'.padStart(32,'0'));
  path.value = '/custom/access*.log'; path.onchange();
  const profile = first.children[1].children[0];
  profile.value = '2e44ae00-7a3a-492d-8806-9177a8973582'; profile.onchange();
  first.children.at(-1).onclick();
  assert.equal(nodes.get('source-settings').children.length, 2);
  nodes.get('add-source').onclick();
  const added = nodes.get('source-settings').children[2].children[0].children[0];
  assert.equal(added.value, '');
  await runTask(nodes);
  assert.equal(requests.length, 0);
  assert.match(nodes.get('message').textContent, /Select a registered source/);
  added.value = '1'.padStart(32,'0'); added.onchange();
  vm.runInContext("sourceRows[2].profile.value = '2e44ae00-7a3a-492d-8806-9177a8973582'; sourceRows[2].profile.onchange();", context);
  assert.equal(vm.runInContext('sourceRows[2].path', context), '1'.padStart(32,'0'));
  nodes.get('source-mode').value = 'realtime'; nodes.get('source-mode').onchange();
  nodes.get('source-mode').value = 'batch'; nodes.get('source-mode').onchange();
  assert.equal(nodes.get('source-settings').children[2].children[0].children[0].value, '1'.padStart(32,'0'));
  assert.equal(vm.runInContext('sourceRows[2].profile.value', context), '2e44ae00-7a3a-492d-8806-9177a8973582');
  await runTask(nodes);
  assert.equal(requests[0].sources.length, 3);
  assert.equal(requests[0].sources[2].sourceId, '1'.padStart(32,'0'));
  assert.equal(Object.hasOwn(requests[0].sources[2], 'path'), false);
  const html = readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');
  assert.ok(!html.includes('Server-side file paths or patterns'));
});


test('result JSON puts metadata first and preserves UTC ISO 8601 timestamps and values', () => {
  const { context } = workspace([]);
  const value = vm.runInContext("orderedResult({log:'original', category:'normal', source:'/logs/test', elapsedMs:12, requestedAt:'2026-10-12T03:00:00.123456+00:00', engine:'laya'})", context);
  assert.deepEqual(Object.keys(value), ['requestedAt', 'engine', 'source', 'elapsedMs', 'log', 'category']);
  assert.equal(value.requestedAt, '2026-10-12T03:00:00.123456+00:00');
  assert.equal(value.log, 'original');
  assert.equal(value.category, 'normal');
});


test('stored Action assignments never run by default; explicit selections last only for this page', async () => {
  let saved;
  const storage = {
    getItem: () => JSON.stringify([['/host-logs/var/log/messages', {profile:'2e44ae00-7a3a-492d-8806-9177a8973582', chunkEvents:3, actionId:'notify'}]]),
    setItem: (_, value) => { saved = JSON.parse(value); },
  };
  const {nodes, context, requests} = workspace([], undefined, storage);
  await new Promise(resolve => setImmediate(resolve));
  vm.runInContext("registeredActions = [{id:'notify',name:'notify'}]; updateSourceSettings();", context);
  const selector = () => nodes.get('source-settings').children[0].children[3].children[0];
  assert.equal(selector().value, '');
  assert.equal(vm.runInContext('sourceRows[0].profile.value', context), '2e44ae00-7a3a-492d-8806-9177a8973582');
  assert.equal(vm.runInContext('sourceRows[0].size.value', context), '3');
  await runTask(nodes);
  assert.ok(requests[0].sources.every(source => source.actionId === ''));
  selector().value = 'notify'; selector().onchange();
  assert.ok(saved.every(([, preference]) => !Object.hasOwn(preference, 'action')));
  nodes.get('source-mode').value = 'realtime'; nodes.get('source-mode').onchange();
  nodes.get('source-mode').value = 'batch'; nodes.get('source-mode').onchange();
  assert.equal(selector().value, 'notify');
  const reloaded = workspace([], undefined, {getItem:() => JSON.stringify(saved), setItem() {}});
  await new Promise(resolve => setImmediate(resolve));
  vm.runInContext("registeredActions = [{id:'notify',name:'notify'}]; updateSourceSettings();", reloaded.context);
  assert.equal(reloaded.nodes.get('source-settings').children[0].children[3].children[0].value, '');
});


test('new jobs persist their ID and reload replays results without submitting another run', async () => {
  const stored = new Map();
  const storage = {getItem:key => stored.get(key) || null, setItem:(key,value) => stored.set(key,value), removeItem:key => stored.delete(key)};
  const events = [{type:'start', engine:'laya', mode:'batch', total:1, sourcePatterns:['/custom/log']}, result(0), {type:'done', state:'completed', elapsedMs:100}];
  const first = workspace(events, undefined, storage);
  await new Promise(resolve => setImmediate(resolve));
  let submissions = 0;
  const settings = {mode:'batch', sources:[{path:'/custom/log', profile:'2e44ae00-7a3a-492d-8806-9177a8973582', chunkEvents:2, actionId:'notify'}]};
  first.context.fetch = async (path, options) => {
    if (path === '/api/tasks/test-task/run') {
      submissions++;
      return {ok:true, status:202, json:async () => ({jobId:'job1',state:'running',settings})};
    }
    if(path==='/api/tasks')return {ok:true,json:async()=>({tasks:vm.runInContext('registeredTasks',first.context)})};
    assert.equal(path, '/api/jobs/job1/events');
    return {ok:true, body:{}};
  };
  await runTask(first.nodes);
  assert.equal(stored.get('deciflow-job-id'), 'job1');
  const reloaded = workspace(events, undefined, storage);
  await new Promise(resolve => setImmediate(resolve));
  reloaded.context.fetch = async path => {
    if(path==='/api/tasks')return {ok:true,json:async()=>({tasks:vm.runInContext('registeredTasks',reloaded.context)})};
    if (path === '/api/jobs/job1') return {ok:true,json:async () => ({jobId:'job1', state:'completed', settings})};
    assert.equal(path, '/api/jobs/job1/events');
    return {ok:true,body:{}};
  };
  await vm.runInContext('handleRestoreJob()', reloaded.context);
  assert.equal(submissions, 1);
  assert.equal(vm.runInContext('completed', reloaded.context), 1);
  assert.equal(vm.runInContext('sourceRows[0].path', reloaded.context), '1'.padStart(32,'0'));
  assert.equal(vm.runInContext('sourceRows[0].profile.value', reloaded.context), '4e6d5417-611e-49e0-8e23-2444a0f49ee4');
  assert.equal(vm.runInContext('sourceRows[0].action.value', reloaded.context), '');
  reloaded.context.fetch = async () => ({ok:false,status:404});
  await vm.runInContext('handleRestoreJob()', reloaded.context);
  assert.equal(stored.has('deciflow-job-id'), false);
  assert.match(reloaded.nodes.get('message').textContent, /server may have restarted/);
});


test('Tasks Stop calls the server endpoint instead of aborting the browser stream', async () => {
  const {nodes, context} = workspace([]);
  await new Promise(resolve => setImmediate(resolve));
  let finish;
  context.fetch = async path => {
    if (path === '/api/tasks/test-task/run') return {ok:true,status:202,json:async () => ({jobId:'running',state:'running',settings:{mode:'batch',sources:[]}})};
    if(path==='/api/tasks')return {ok:true,json:async()=>({tasks:vm.runInContext('registeredTasks',context)})};
    if (path.endsWith('/events')) return {ok:true,body:{}};
    assert.equal(path, '/api/tasks/test-task/stop');
    assert.equal(vm.runInContext('activeRequest.signal.aborted', context), false);
    finish();
    return {ok:true,json:async()=>({state:'stopped'})};
  };
  context.readEvents = async (body, receive) => {
    receive({type:'start',engine:'laya',mode:'batch',total:null});
    await new Promise(resolve => {finish=resolve;});
    receive({type:'done',state:'stopped',elapsedMs:100});
  };
  const running = runTask(nodes);
  await new Promise(resolve => setImmediate(resolve));
  await vm.runInContext("handleStopTask('test-task')",context);
  await running;
  assert.equal(nodes.get('run-state').textContent,'Stopped');
});


test('status initialization automatically restores the remembered job after refresh', async () => {
  const status = {host:{hostname:'node',os:'Linux',addresses:[]},engine:'laya',model:'english',configured:true,workingDirectory:'/app',limits:{context_tokens:512}};
  const storage = {getItem:key => key === 'deciflow-job-id' ? 'remembered' : null, setItem() {}, removeItem() {}};
  const events = [{type:'start',engine:'laya',total:1}, result(0), {type:'done',state:'completed',elapsedMs:100}];
  const {nodes,context,requests} = workspace(events, status, storage);
  nodes.get('source-mode').value = 'batch';
  const paths = [];
  context.fetch = async path => {
    if(path==='/api/tasks')return {ok:true,json:async()=>({tasks:vm.runInContext('registeredTasks',context)})};
    paths.push(path);
    if (path === '/api/engine-health') return {ok:true,json:async()=>({engine:'laya',connection:'connected'})};
    if (path === '/api/jobs/remembered') return {ok:true,json:async () => ({jobId:'remembered',state:'completed',settings:{mode:'batch',sources:[]}})};
    assert.equal(path, '/api/jobs/remembered/events');
    return {ok:true,body:{}};
  };
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(paths, ['/api/engine-health', '/api/jobs/remembered', '/api/jobs/remembered/events']);
  assert.equal(requests.length, 0);
  assert.equal(logs(nodes)[0],'log-0');
  assert.equal(vm.runInContext('completed', context), 1);
});


test('Export stays visibly disabled during processing and enables only with downloadable results', () => {
  const { nodes, context } = workspace([]);
  vm.runInContext("results=[{log:'one', category:'normal', probabilities:{normal:1}, elapsedMs:1}]; completionOrder=[0]; completed=1; busy=true; render();", context);
  assert.equal(nodes.get('export').disabled, true);
  nodes.get('export').onclick();
  vm.runInContext("busy=false; activeJobState='running'; render();", context);
  assert.equal(nodes.get('export').disabled, true);
  nodes.get('export').onclick();
  for (const state of ['completed', 'stopped']) {
    vm.runInContext(`activeJobState='${state}'; render();`, context);
    assert.equal(nodes.get('export').disabled, false);
  }
  vm.runInContext('completed=0; render();', context);
  assert.equal(nodes.get('export').disabled, true);
  assert.equal(nodes.get('export-reviewed').disabled,true);
  const css = readFileSync(new URL('../public/style.css', import.meta.url), 'utf8');
  assert.match(css, /button:disabled\s*\{\s*opacity:\s*\.5;/);
});


test('Criteria management resets drafts on menu entry, saves edits, and clears deleted source selections', async () => {
  const definitions = Object.fromEntries(['normal', 'warning', 'error', 'security', 'other'].map(key => [key, `${key} evidence`]));
  const profiles = {
    [sampleProfileIds.general]: profileFixture('Sample General System','General instructions',definitions),
    custom: profileFixture('Custom','Custom instructions',definitions),
  };
  const { nodes, context } = workspace([], undefined, undefined, profiles);
  await nodes.get('nav-criteria').onclick();
  assert.equal(nodes.get('criteria-page').hidden, false);
  assert.equal(nodes.get('main-page').hidden, true);
  assert.equal(nodes.get('save-criteria').disabled, false);
  assert.equal(criteriaRow(nodes, 'Sample General System').children.at(-1).children[0].textContent, 'View');
  assert.equal(nodes.get('criteria-registry').children[0].children[1].children[0].textContent, 'Custom');
  nodes.get('add-criteria').onclick();
  vm.runInContext("criteriaFields.label.value='New profile'; criteriaFields.instructions.value='New instructions';", context);
  nodes.get('nav-main').onclick();
  await nodes.get('nav-criteria').onclick();
  assert.equal(nodes.get('criteria-editor').hidden,true);
  assert.equal(vm.runInContext('editingCriteria', context),null);
  nodes.get('add-criteria').onclick();
  vm.runInContext("criteriaFields.label.value='New profile'; criteriaFields.instructions.value='New instructions';", context);
  await nodes.get('save-criteria').onclick();
  assert.equal(vm.runInContext("Object.values(profileLabels).find(name=>name==='New profile')", context), 'New profile');
  vm.runInContext("handleEditCriteria('custom'); criteriaFields.instructions.value='Edited custom';", context);
  assert.equal(vm.runInContext('criteriaFields.id', context), undefined);
  await nodes.get('save-criteria').onclick();
  assert.equal(vm.runInContext('criteriaProfiles.custom.instructions', context), 'Edited custom');
  vm.runInContext("sourceRows[0].profile.value='custom';", context);
  vm.runInContext("delete criteriaProfiles.custom; renderCriteria();", context);
  await nodes.get('save-criteria').onclick();
  assert.equal(vm.runInContext('sourceRows[0].profile.value', context), '');
  assert.match(nodes.get('criteria-message').textContent, /Select replacements/);
  assert.equal(nodes.get('criteria-editor').hidden, true);
});

test('Criteria search, cancel, and duplicate IDs leave saved profiles unchanged', async () => {
  const definitions = Object.fromEntries(['normal', 'warning', 'error', 'security', 'other'].map(key => [key, key]));
  const profiles = { [sampleProfileIds.general]: profileFixture('Sample General System','Original',definitions), custom: profileFixture('Custom','Original',definitions) };
  const { nodes, context } = workspace([], undefined, undefined, profiles);
  await nodes.get('nav-criteria').onclick();
  nodes.get('criteria-search').value = 'missing';
  nodes.get('criteria-search').oninput();
  assert.match(nodes.get('criteria-registry').children[0].textContent, /No profiles/);
  nodes.get('criteria-search').value = '';
  vm.runInContext("handleEditCriteria('custom'); criteriaFields.instructions.value='Unsaved';", context);
  nodes.get('cancel-criteria').onclick();
  assert.equal(vm.runInContext('criteriaProfiles.custom.instructions', context), 'Original');
  nodes.get('add-criteria').onclick();
  vm.runInContext("criteriaFields.label.value='Sample General System'; criteriaFields.label.oninput();", context);
  await nodes.get('save-criteria').onclick();
  assert.match(nodes.get('criteria-message').textContent, /already exists/);
  assert.equal(nodes.get('save-criteria').disabled, true);
});


test('View shows read-only Action configuration without editing or losing drafts', async () => {
  const { nodes, context, requests } = workspace([]);
  await new Promise(resolve => setImmediate(resolve));
  vm.runInContext("registeredActions=[{id:'notify', name:'Notify', pythonVersion:'3.12', modules:['httpx'], code:'print(1)'}]; renderActions();", context);
  const controls = () => nodes.get('action-registry').children[0].children[1].children.at(-1).children;
  assert.deepEqual(controls().map(button => button.textContent), ['View', 'Edit', 'Reset venv', 'Delete', 'Ref.']);
  controls()[0].onclick();
  const values = () => nodes.get('action-view').children.find(node=>node.className?.includes('view-details')).children.map(field => field.children[1]);
  assert.equal(nodes.get('action-view').hidden, false);
  assert.ok(values().every(value => value.className !== 'action-code'));
  assert.equal(values().at(-1).textContent, 'print(1)');
  assert.equal(vm.runInContext('editingAction', context), null);
  assert.equal(vm.runInContext('actionRows.length', context), 0);
  assert.equal(requests.length, 0);
  controls()[1].onclick();
  assert.equal(nodes.get('action-view').hidden, true);
  assert.equal(nodes.get('action-view').children.length, 0);
  assert.equal(nodes.get('action-editor').hidden, false);
  vm.runInContext("actionRows[0].code.value='Unsaved draft';", context);
  controls()[0].onclick();
  assert.equal(values().at(-1).textContent, 'print(1)');
  assert.equal(nodes.get('action-editor').hidden, true);
  assert.equal(nodes.get('save-actions').disabled, true);
  assert.equal(vm.runInContext('actionRows[0].code.value', context), 'Unsaved draft');
  assert.equal(nodes.get('action-view').children[0].children.length, 1);
  vm.runInContext("handleCloseConfiguration('action-view')",context);
  assert.equal(nodes.get('action-view').hidden, true);
  assert.equal(nodes.get('action-editor').hidden, false);
  assert.equal(nodes.get('save-actions').disabled, false);
  assert.equal(vm.runInContext('editingAction', context), 0);
});

test('View shows all Criteria definitions and preserves the edit draft', async () => {
  const definitions = Object.fromEntries(['normal', 'warning', 'error', 'security', 'other'].map(key => [key, `${key} evidence`]));
  const profiles = { [sampleProfileIds.general]: profileFixture('Sample General System','Saved instructions',definitions), custom: profileFixture('Custom','Saved instructions',definitions) };
  const { nodes, context } = workspace([], undefined, undefined, profiles);
  await nodes.get('nav-criteria').onclick();
  const controls = () => nodes.get('criteria-registry').children[0].children[1].children.at(-1).children;
  assert.deepEqual(controls().map(button => button.textContent), ['View', 'Edit', 'Clone', 'Delete', 'Ref.']);
  controls()[0].onclick();
  const values = () => nodes.get('criteria-view').children.find(node=>node.className?.includes('view-details')).children.map(field => field.children[1]);
  assert.ok(values().every(value => value.className !== 'action-code'));
  assert.equal(values()[3].textContent,'Category');assert.ok(values()[4].textContent.includes('normal: normal evidence'));
  assert.equal(vm.runInContext('editingCriteria', context), null);
  controls()[1].onclick();
  assert.equal(nodes.get('criteria-view').hidden, true);
  assert.equal(nodes.get('criteria-view').children.length, 0);
  assert.equal(nodes.get('criteria-editor').hidden, false);
  vm.runInContext("criteriaFields.instructions.value='Draft instructions';", context);
  controls()[0].onclick();
  assert.equal(values()[2].textContent, 'Saved instructions');
  assert.equal(nodes.get('criteria-editor').hidden, true);
  assert.equal(nodes.get('save-criteria').disabled, true);
  assert.equal(nodes.get('criteria-view').children[0].children.length, 1);
  vm.runInContext("handleCloseConfiguration('criteria-view')",context);
  assert.equal(nodes.get('criteria-view').hidden, true);
  assert.equal(nodes.get('criteria-editor').hidden, false);
  assert.equal(nodes.get('save-criteria').disabled, false);
  assert.equal(vm.runInContext('criteriaFields.instructions.value', context), 'Draft instructions');
});


test('Add closes View in both managers and enables the new editor', async () => {
  const definitions = Object.fromEntries(['normal', 'warning', 'error', 'security', 'other'].map(key => [key, key]));
  const profiles = { [sampleProfileIds.general]: profileFixture('General','Instructions',definitions) };
  const { nodes, context } = workspace([], undefined, undefined, profiles);
  await new Promise(resolve => setImmediate(resolve));
  vm.runInContext("registeredActions=[{id:'Notify',name:'Notify', code:'pass'}]; renderActions();", context);
  nodes.get('action-registry').children[0].children[1].children[4].children[0].onclick();
  nodes.get('add-action').onclick();
  assert.equal(nodes.get('action-view').hidden, true);
  assert.equal(nodes.get('action-editor').hidden, false);
  assert.equal(nodes.get('save-actions').disabled, false);
  await nodes.get('nav-criteria').onclick();
  criteriaRow(nodes, 'General').children.at(-1).children[0].onclick();
  nodes.get('add-criteria').onclick();
  assert.equal(nodes.get('criteria-view').hidden, true);
  assert.equal(nodes.get('criteria-editor').hidden, false);
  assert.equal(nodes.get('save-criteria').disabled, true);
});


test('URL routes restore Actions and Criteria on reload and support browser history', async () => {
  const definitions = Object.fromEntries(['normal', 'warning', 'error', 'security', 'other'].map(key => [key, key]));
  const profiles = { [sampleProfileIds.general]: profileFixture('General','Instructions',definitions) };
  for (const view of ['actions', 'criteria']) {
    const navigation = { hash: `#${view}` };
    const { nodes, context, listeners } = workspace([], undefined, undefined, profiles, navigation);
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(nodes.get(`${view}-page`).hidden, false);
    assert.equal(nodes.get('main-page').hidden, true);
    assert.equal(nodes.get(`nav-${view}`).attributes['aria-current'], 'page');
    if (view === 'criteria') assert.equal(vm.runInContext('criteriaLoaded', context), true);
    nodes.get('nav-main').onclick();
    assert.equal(navigation.hash, '');
    assert.equal(nodes.get('main-page').hidden, false);
    navigation.hash = `#${view}`;
    await listeners.get('hashchange')();
    assert.equal(nodes.get(`${view}-page`).hidden, false);
    navigation.hash = '#unknown';
    await listeners.get('hashchange')();
    assert.equal(nodes.get('main-page').hidden, false);
    assert.equal(navigation.hash, '');
    nodes.get('nav-actions').onclick();
    assert.equal(navigation.hash, '#actions');
    await nodes.get('nav-criteria').onclick();
    assert.equal(navigation.hash, '#criteria');
  }
});


test('engine connection follows actual requests for both providers without local rejection changes', async () => {
  for (const engine of ['laya', 'jev']) {
    const status = { host: { hostname: 'host', addresses: [], os: 'Linux' }, engine, configured: true, model: 'test', workingDirectory: '/app', limits: { context_tokens: 8192, max_jev_input_bytes: 30000 } };
    const events = [{ type: 'start', engine, total: 6 }];
    const { nodes, context } = workspace(events, status);
    await new Promise(resolve => setImmediate(resolve));
    const connection = nodes.get('status').children[1];
    assert.equal(connection.textContent, ' (Reachable)');
    const states = [
      ['connected', 'Operational'], ['disconnected', 'Unreachable'],
      [undefined, 'Unreachable'], ['timeout', 'Timed Out'],
      ['api_error', 'API Error'], ['connected', 'Operational'],
    ];
    context.readEvents = async (_, receive) => {
      receive(events[0]);
      states.forEach(([state, caption], index) => {
        receive({ type: 'result', index, elapsedMs: index + 1, result: { log: `event-${index}`, elapsedMs: 1, ...(index === 0 || index === 5 ? { category: 'normal', review: true, probabilities: { normal: 1 } } : { error: 'failed', review: true }), ...(state ? { engineConnection: state } : {}) } });
        assert.equal(connection.textContent, ` (${caption})`);
      });
      receive({ type: 'done', elapsedMs: 100 });
    };
    await runTask(nodes);
    assert.equal(nodes.get('summary').children[0].textContent, 'Success / Failed / Total');
    assert.equal(nodes.get('summary').children[0].children[0].children.map(node => node.textContent).join(''), '2 / 4 / 6');
    assert.equal(nodes.get('needs-review-count').textContent, 'Needs Review: 2');
    nodes.get('review-filter').value = 'needs-review'; nodes.get('review-filter').onchange();
    assert.deepEqual(logs(nodes), ['event-5', 'event-0']);
    assert.equal(connection.className, 'engine-connection connected');
  }
});


test('All Criteria share one searchable editable list without a required default', async () => {
  const definitions = Object.fromEntries(['normal', 'warning', 'error', 'security', 'other'].map(key => [key, key]));
  const profiles = { [sampleProfileIds.general]: profileFixture('Sample General System','Default instructions',definitions), custom: profileFixture('Custom','Custom instructions',definitions) };
  const { nodes, context } = workspace([], undefined, undefined, profiles);
  await nodes.get('nav-criteria').onclick();
  assert.equal(nodes.get('criteria-registry').children[0].children.length, 3);
  const row = criteriaRow(nodes, 'Sample General System');
  assert.deepEqual(row.children.at(-1).children.map(button => button.textContent), ['View', 'Edit', 'Clone', 'Delete', 'Ref.']);
  row.children.at(-1).children[0].onclick();
  assert.equal(nodes.get('criteria-view').children.find(node=>node.className?.includes('view-details')).children[0].children[1].textContent, 'Sample General System');
  nodes.get('criteria-search').value = 'missing'; nodes.get('criteria-search').oninput();
  assert.equal(nodes.get('criteria-registry').children[0].textContent, 'No profiles match your search.');
  nodes.get('criteria-search').value = 'general'; nodes.get('criteria-search').oninput();
  assert.equal(criteriaRow(nodes, 'Sample General System').children[0].textContent, 'Sample General System');
  criteriaRow(nodes, 'Sample General System').children.at(-1).children[1].onclick();
  assert.equal(vm.runInContext('editingCriteria', context), '4e6d5417-611e-49e0-8e23-2444a0f49ee4');
  nodes.get('cancel-criteria').onclick();
  const html = readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');
  assert.ok(!html.includes('criteria-default'));
  assert.ok(!html.includes('Default Criteria'));
  assert.ok(!html.includes('Registered Criteria'));
});

function criteriaRow(nodes, name) {
  return nodes.get('criteria-registry').children[0].children.find(row => row.children[0]?.textContent === name);
}


test('Add and Edit show only the form and restore each manager list on cancel or save', async () => {
  const definitions = Object.fromEntries(['normal', 'warning', 'error', 'security', 'other'].map(key => [key, key]));
  const profiles = { [sampleProfileIds.general]: profileFixture('General','Default',definitions), custom: profileFixture('Custom','Custom',definitions) };
  const { nodes, context } = workspace([], undefined, undefined, profiles);
  await new Promise(resolve => setImmediate(resolve));
  vm.runInContext("registeredActions=[{id:'Notify',name:'Notify', code:'pass'}]; renderActions();", context);
  nodes.get('add-action').onclick();
  assert.equal(nodes.get('action-list').hidden, true);
  assert.equal(nodes.get('action-editor').hidden, false);
  nodes.get('cancel-action').onclick();
  assert.equal(nodes.get('action-list').hidden, false);
  vm.runInContext('handleEditAction(0)', context);
  assert.equal(nodes.get('action-list').hidden, true);
  context.fetch = async (path, options) => ({ ok: true, json: async () => path === '/api/actions' ? { actions: JSON.parse(options.body) } : { profiles: options.method === 'PUT' ? JSON.parse(options.body) : profiles } });
  await nodes.get('save-actions').onclick();
  assert.equal(nodes.get('action-list').hidden, false);
  assert.equal(nodes.get('action-editor').hidden, true);
  await nodes.get('nav-criteria').onclick();
  criteriaRow(nodes, 'General').children.at(-1).children[0].onclick();
  nodes.get('add-criteria').onclick();
  assert.equal(nodes.get('criteria-list').hidden, true);
  assert.equal(nodes.get('criteria-view').hidden, true);
  assert.equal(nodes.get('criteria-editor').hidden, false);
  nodes.get('cancel-criteria').onclick();
  assert.equal(nodes.get('criteria-list').hidden, false);
  vm.runInContext("handleEditCriteria('custom')", context);
  assert.equal(nodes.get('criteria-list').hidden, true);
  await nodes.get('save-criteria').onclick();
  assert.equal(nodes.get('criteria-list').hidden, false);
  assert.equal(nodes.get('criteria-editor').hidden, true);
});


test('edit cancel buttons precede the forms in both managers', () => {
  const html = readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');
  for (const kind of ['action', 'criteria']) {
    assert.ok(html.indexOf(`id="cancel-${kind}"`) < html.indexOf(`id="${kind}-editor"`));
  }
});


test('Reset venv rebuilds a saved managed Action and reports maintenance errors', async () => {
  const { nodes, context } = workspace([]);
  await new Promise(resolve => setImmediate(resolve));
  vm.runInContext("registeredActions=[{id:'a'.repeat(32), name:'Notify', pythonVersion:'3.12', modules:[], code:'pass'}]; renderActions();", context);
  const controls = () => nodes.get('action-registry').children[0].children[1].children.at(-1).children;
  let finish;
  let requested;
  context.fetch = (path, options) => {
    requested = { path, options };
    return new Promise(resolve => { finish = resolve; });
  };
  const resetting = controls()[2].onclick();
  assert.equal(requested.path, `/api/actions/${'a'.repeat(32)}/reset`);
  assert.equal(requested.options.method, 'POST');
  assert.ok(controls().filter(button => button.textContent !== 'Ref.').every(button => button.disabled));
  assert.equal(nodes.get('save-actions').disabled, true);
  finish({ ok: true, json: async () => ({ action: { id:'a'.repeat(32), name:'Notify', pythonVersion:'3.12', modules:[], code:'pass' } }) });
  await resetting;
  assert.match(nodes.get('action-message').textContent, /rebuilt with pip/);
  context.fetch = async () => ({ ok: false, json: async () => ({ error: 'Stop runs using this Action' }) });
  await controls()[2].onclick();
  assert.match(nodes.get('action-message').textContent, /Stop runs/);
  assert.equal(controls()[2].disabled, false);
  vm.runInContext("registeredActions=[{id:'External',name:'External', python:'/usr/bin/python', script:'/tmp/script.py'}]; renderActions();", context);
  assert.equal(controls()[2].disabled, true);
});


test('Action status distinguishes saved readiness, reset progress, and other Actions', async () => {
  const { nodes, context } = workspace([]);
  await new Promise(resolve => setImmediate(resolve));
  vm.runInContext("registeredActions=[{id:'a'.repeat(32), name:'Ready action', pythonVersion:'3.12', environmentStatus:'ready'}, {id:'b'.repeat(32), name:'Missing action', pythonVersion:'3.12', environmentStatus:'not_ready'}, {id:'External',name:'External'}]; renderActions();", context);
  const statuses = () => nodes.get('action-registry').children[0].children.slice(1).map(row => row.children[3].children[0].textContent);
  assert.deepEqual(statuses(), ['External', 'Not ready', 'Ready']);
  let finish;
  context.fetch = () => new Promise(resolve => { finish = resolve; });
  const resetting = nodes.get('action-registry').children[0].children[3].children.at(-1).children[2].onclick();
  assert.deepEqual(statuses(), ['External', 'Not ready', 'Preparing...']);
  finish({ok:true, json:async () => ({action:{id:'a'.repeat(32), name:'Ready action', pythonVersion:'3.12', environmentStatus:'ready'}})});
  await resetting;
  assert.deepEqual(statuses(), ['External', 'Not ready', 'Ready']);
  context.fetch = async () => ({ok:true, json:async () => ({actions:[{id:'a'.repeat(32), environmentStatus:'ready'},{id:'b'.repeat(32), environmentStatus:'ready'}]})});
  await vm.runInContext('handleRefreshActionStatus()', context);
  assert.deepEqual(statuses(), ['External', 'Ready', 'Ready']);
  nodes.get('add-action').onclick();
  assert.equal(nodes.get('action-environment-status').hidden, false);
  assert.equal(nodes.get('action-environment-status').textContent, 'Not ready');
  vm.runInContext('preparingActions=true; renderActions()', context);
  assert.equal(nodes.get('action-environment-status').textContent, 'Preparing...');
});


test('success failure and total counts use green red and blue respectively', () => {
  const { nodes, context } = workspace([]);
  vm.runInContext('render()', context);
  const counts = nodes.get('summary').children[0].children[0].children;
  assert.deepEqual([counts[0].className, counts[2].className, counts[4].className], ['count-success', 'count-failed', 'count-total']);
  const css = readFileSync(new URL('../public/style.css', import.meta.url), 'utf8').replace(/\s*([{}:;])\s*/g, '$1');
  for (const [name, color] of [['success', '#429665'], ['failed', '#9a443c'], ['total', '#0057ff']]) assert.ok(css.includes(`.count-${name}{color:${color};}`));
});


test('duration metrics use readable units without changing millisecond data', () => {
  const { nodes, context } = workspace([]);
  for (const [milliseconds, expected] of [
    [0, '0 ms'], [0.5, '0.5 ms'], [999, '999 ms'], [1000, '1 sec'],
    [1500, '1.5 sec'], [59000, '59 sec'], [60000, '1 min'],
    [65000, '1 min 5 sec'], [3599000, '59 min 59 sec'],
    [3600000, '1 hour'], [3720000, '1 hour 2 min'],
    [86400000, '1 day'], [176400000, '2 days 1 hour'],
  ]) assert.equal(vm.runInContext(`formatDuration(${milliseconds})`, context), expected);
  vm.runInContext("elapsedMs=3720000; activeProcessingMs=65000; results=[{elapsedMs:1500, log:'event', category:'normal', probabilities:{normal:1}}]; completionOrder=[0]; completed=1; render();", context);
  assert.equal(elapsedValues(nodes)[0], '1 hour 2 min');
  assert.equal(elapsedValues(nodes)[1], '1 min 5 sec (1.7%)');
  assert.equal(processingValues(nodes).Avg, '1.5 sec');
  assert.equal(vm.runInContext('elapsedMs', context), 3720000);
  assert.equal(vm.runInContext('activeProcessingMs', context), 65000);
  assert.equal(vm.runInContext('orderedResult(results[0]).elapsedMs', context), 1500);
});


test('Reset Selections restores registered samples and clears Action assignments', () => {
  const values = new Map();
  const storage = { getItem: key => values.get(key) || null, setItem: (key, value) => values.set(key, value) };
  const { nodes, context } = workspace([], undefined, storage);
  vm.runInContext("sourcePreferences.set('/host-logs/var/log/messages', {profile:'0181af82-c1ed-41c8-8cd3-22a385746b32', chunkEvents:9, actionId:'Notify'}); filePaths.realtime='/my/live.log';", context);
  nodes.get('file-path').value = '/custom.log'; nodes.get('file-path').oninput();
  nodes.get('reset-sources').onclick();
  assert.equal(nodes.get('file-path').value, vm.runInContext('defaultFilePaths.batch', context));
  assert.equal(nodes.get('source-settings').children.length, 3);
  assert.equal(vm.runInContext('filePaths.realtime', context), '/my/live.log');
  assert.equal(vm.runInContext("sourceRows.every(row => row.profile.value===defaultSourceProfiles[registeredSources.find(source=>source.id===row.path)?.path] && row.size.value==='1' && row.action.value==='')", context), true);
  const stored = new Map(JSON.parse(values.get('deciflow-source-preferences')));
  assert.deepEqual(stored.get('1'.padStart(32,'0')), { profile:'4e6d5417-611e-49e0-8e23-2444a0f49ee4', chunkEvents:1 });
  nodes.get('source-mode').value = 'realtime'; nodes.get('source-mode').onchange();
  assert.equal(nodes.get('file-path').value, vm.runInContext('defaultFilePaths.batch',context));
  nodes.get('reset-sources').onclick();
  assert.equal(nodes.get('file-path').value, vm.runInContext('defaultFilePaths.realtime', context));
  vm.runInContext('busy=true', context);
  nodes.get('file-path').value = '/keep.log';
  nodes.get('reset-sources').onclick();
  assert.equal(nodes.get('file-path').value, vm.runInContext('defaultFilePaths.batch',context));
  const html = readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');
  assert.ok(html.includes('Add Source</button><button id="reset-sources"'));
});


test('Action metrics count completed executions separately from decision outcomes', async () => {
  const success = result(0, false);
  success.result.actionExecution = {name:'Notify', status:'success', elapsedMs:1};
  const failure = result(1, false);
  failure.result.actionExecution = {name:'Notify', status:'failed', exitCode:1, elapsedMs:1};
  const decisionFailure = {type:'result', index:3, elapsedMs:4, result:{log:'failed decision', error:'Could not connect', review:false, elapsedMs:1}};
  const events = [{type:'start', engine:'laya', total:4}, success, failure, result(2, false), decisionFailure];
  const { nodes, context } = workspace(events);
  const counts = index => nodes.get('summary').children[index].children[0].children.map(node => node.textContent).join('');
  vm.runInContext('render()', context);
  assert.equal(counts(1), '0 / 0 / 0');
  await runTask(nodes);
  assert.equal(nodes.get('summary').children[1].textContent, 'Action Success / Failed / Total');
  assert.equal(counts(0), '3 / 1 / 4');
  assert.equal(counts(1), '1 / 1 / 2');
  assert.equal(nodes.get('needs-review-count').textContent, 'Needs Review: 0');
  nodes.get('review-filter').value='needs-review'; nodes.get('review-filter').onchange();
  assert.equal(counts(1), '1 / 1 / 2');
  nodes.get('pause-updates').onclick();
  vm.runInContext("results.push({log:'timeout', category:'normal', review:false, elapsedMs:1, actionExecution:{name:'Notify',status:'failed',error:'timeout',elapsedMs:30000}}); completionOrder.push(4); completed++; render(false);", context);
  assert.equal(counts(0), '4 / 1 / 5');
  assert.equal(counts(1), '1 / 2 / 3');
  const colors = nodes.get('summary').children[1].children[0].children;
  assert.deepEqual([colors[0].className,colors[2].className,colors[4].className], ['count-success','count-failed','count-total']);
});


test('Throughput occupies the third metric and Processing Time appears last', () => {
  const { nodes, context } = workspace([]);
  vm.runInContext('render()', context);
  assert.equal(nodes.get('summary').children[2].textContent, 'Throughput');
  assert.equal(nodes.get('summary').children.at(-1).textContent, 'Processing Time');
});


test('Action edit explains environment replacement and reset behavior', () => {
  const {nodes, context} = workspace([]);
  vm.runInContext("registeredActions=[{id:'a'.repeat(32), name:'Notify', pythonVersion:'3.12', modules:[], code:'pass'}]; handleEditAction(0);", context);
  const row = nodes.get('action-editor').children[0];
  for (const index of [1, 2]) {
    assert.equal(row.children[index].children[0].readOnly, undefined);
    assert.equal(row.children[index].children[1].textContent, 'Changing Python version or modules replaces the environment after preparation succeeds. Stop runs using this Action before editing.');
  }
  const html = readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');
  assert.ok(html.includes('Reset venv deletes the current virtual environment and rebuilds it using saved settings and locked dependencies.'));
});

test('results display urgency and ticket need probability', async () => {
  const event = result(0, false);
  event.result.decisions.urgency.score = 2.37;
  event.result.decisions.ticket.noul = 0.91;
  const { nodes } = workspace([
    { type: 'start', engine: 'laya', total: 1 }, event,
    { type: 'done', elapsedMs: 10 },
  ]);
  await runTask(nodes);
  const row = nodes.get('results').children[0];
  const cards = decisionCards(row);
  assert.deepEqual(cards.map(card => card.children[0].textContent), ['Category (Choice)', 'Urgency (Score)', 'Work Ticket (Noul)']);
  assert.equal(cards[1].children[1].textContent, '2.37 / 3');
  assert.equal(cards[2].children[1].textContent, '91.0%');
});

test('Sources navigation and SSH registration feed searchable Main choices by ID', async () => {
  const navigation = { hash: '' };
  const {nodes,context,requests} = workspace([], undefined, undefined, null, navigation);
  await new Promise(resolve => setImmediate(resolve));
  nodes.get('nav-sources').onclick();
  assert.equal(nodes.get('main-page').hidden, true);
  assert.equal(nodes.get('sources-page').hidden, false);
  assert.equal(navigation.hash, '#sources');
  nodes.get('add-registered-source').onclick();
  vm.runInContext(`sourceFields.name.value='Production logs'; sourceFields.type.value='ssh'; sourceFields.type.onchange(); sourceFields.path.value='/var/log/app/*.log';`, context);
  assert.equal(vm.runInContext('Object.keys(sourceFields).join(",")',context),'name,type,endpoint,path,format,contentField,username,ticketCache,tokenFile,caFile');
  let saved;
  context.fetch = async (path,options) => {
    if (path === '/api/sources') {
      saved=JSON.parse(options.body);
      return {ok:true,json:async()=>({sources:saved.map((source,i)=>({...source,id:source.id || String(i+1).padStart(32,'0'),...(source.type==='ssh'?{host:'logs.example',username:'reader',port:2222}:{} )}))})};
    }
    if(path==='/api/tasks')return {ok:true,json:async()=>({tasks:vm.runInContext('registeredTasks',context)})};
    if(path==='/api/tasks/test-task/run'){const sources=vm.runInContext('sourceRows.map(row=>({sourceId:row.path}))',context);requests.push({sources});return {ok:true,status:202,json:async()=>({jobId:'test-job',state:'running',settings:{mode:'batch',sources}})};}
    return {ok:true,body:{}};
  };
  await nodes.get('save-sources').onclick();
  assert.equal(Object.hasOwn(saved[3], 'hostId'), false);
  assert.equal(Object.hasOwn(saved[3], 'keyPath'), false);
  assert.equal(Object.hasOwn(saved[3], 'password'), false);
  vm.runInContext("registeredActions=[{id:'Notify',name:'Notify'}]; updateSourceSettings([registeredSources[3].id]);",context);
  const picker=nodes.get('source-settings').children[0].children[0];
  assert.equal(picker.children[0].attributes['aria-label'], 'Registered source');
  assert.equal(picker.children[0].value, '4'.padStart(32,'0'));
  assert.match(picker.children[0].children.find(option=>option.value==='4'.padStart(32,'0')).title,/Remote File.*app/);
  nodes.get('nav-main').onclick();
  await runTask(nodes);
  assert.equal(requests[0].sources[0].sourceId,'4'.padStart(32,'0'));
  assert.equal(Object.hasOwn(requests[0].sources[0], 'keyPath'),false);
  assert.equal(Object.hasOwn(requests[0].sources[0], 'host'),false);
});

test('Source loading failure blocks Source saving and Task editing', async () => {
  const {nodes,context}=workspace([]);await new Promise(resolve=>setImmediate(resolve));
  context.fetch=async()=>({ok:false,json:async()=>({error:'Source storage unavailable'})});vm.runInContext('sourcesLoaded=false',context);
  await nodes.get('save-sources').onclick();assert.equal(nodes.get('source-message').textContent,'Load Sources before saving.');
  await vm.runInContext('handleEditTask()',context);assert.match(nodes.get('task-message').textContent,/Load Sources/);
});

test('Saved source edits keep identity, and source search filters host and path', async () => {
  const {nodes,context}=workspace([]);
  await new Promise(resolve=>setImmediate(resolve));
  nodes.get('source-search').value='access-1k'; nodes.get('source-search').oninput();
  assert.equal(nodes.get('source-registry').children[0].children.length,2);
  const controls=nodes.get('source-registry').children[0].children[1].children.at(-1);
  controls.children[1].onclick();
  vm.runInContext("sourceFields.name.value='Renamed HTTP'; sourceFields.path.value='/new/access*.log';",context);
  await nodes.get('save-sources').onclick();
  assert.equal(vm.runInContext('registeredSources[1].name',context),'Renamed HTTP');
  assert.equal(vm.runInContext('registeredSources[1].id',context),'2'.padStart(32,'0'));
  assert.equal(vm.runInContext('sourceRows[1].name.value',context),'2'.padStart(32,'0'));
  assert.equal(vm.runInContext('sourceRows[1].profile.value',context),'2e44ae00-7a3a-492d-8806-9177a8973582');
});

test('Running jobs can show deleted source snapshots but new runs require a saved source', async () => {
  const events=[{type:'start',engine:'laya',total:1},result(0),{type:'done',state:'completed',elapsedMs:1}];
  const {nodes,context}=workspace(events);
  await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext("registeredSources=[];sourceSnapshots=[{id:'a'.repeat(32),name:'Deleted source',type:'local',path:'/old/app.log'}]; updateSourceSettings(['a'.repeat(32)]);",context);
  const originalFetch=context.fetch;context.fetch=async()=>({ok:true,body:{}});
  await vm.runInContext("handleProcessing({jobId:'existing',state:'running',settings:{mode:'batch',sources:[]}})",context);
  assert.equal(logs(nodes)[0],'log-0');
  context.fetch=originalFetch;
  await runTask(nodes);
  assert.match(nodes.get('message').textContent,/Select a registered source/);
});


test('Settings uses a compact key list, opens details and confirms deletion', async () => {
  const { nodes, context } = workspace([], null, undefined, null, { hash: '#settings' });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(nodes.get('settings-page').hidden, false);
  vm.runInContext(`sshKeys = [{id:'key-production',name:'production',privatePath:'/data/private_key',publicPath:'/data/public_key.pub',publicKey:'ssh-ed25519 PUBLIC'}]; renderSSHKeys();`, context);
  const row = nodes.get('ssh-key-list').children[0].children[1].children[0];
  assert.equal(row.children[0].textContent, 'production');
  assert.equal(row.children[1].textContent, '/data/private_key');
  assert.equal(row.children[2].children.length, 3);
  row.children[2].children[0].onclick();
  const card = nodes.get('ssh-key-view').children[1];
  assert.equal(card.children[2].children[1].textContent, 'ssh-ed25519 PUBLIC');
  assert.equal(card.children[3].children[1].textContent, '****');
  assert.equal(nodes.get('ssh-key-registry').hidden, false);
  const calls = [];
  context.fetch = async (path, options) => {
    calls.push({path, options});
    return {ok:true, json:async()=>({keys:[]})};
  };
  context.handleConfirmDelete = async () => false;
  await row.children[2].children[2].onclick();
  assert.equal(calls.length, 0);
  context.handleConfirmDelete = async () => true;
  await row.children[2].children[2].onclick();
  assert.equal(calls[0].options.method, 'DELETE');
});

test('SSH Key import clears file and Sources select managed keys', async () => {
  const { nodes, context } = workspace([], null);
  const key = {id:'key-production',name:'production',privatePath:'/data/ssh-keys/production/private_key',publicPath:'/data/ssh-keys/production/public_key.pub',publicKey:'ssh-ed25519 PUBLIC'};
  context.fetch = async (path, options) => {
    assert.equal(path, '/api/ssh-keys');
    assert.equal(JSON.parse(options.body).privateKey, 'PRIVATE test input');
    return {ok:true,json:async()=>({keys:[key]})};
  };
  context.document.getElementById('ssh-key-method').value = 'upload';
  context.document.getElementById('ssh-key-name').value = 'production';
  context.document.getElementById('ssh-key-file').files = [{size:18,text:async()=> 'PRIVATE test input'}];
  await nodes.get('ssh-key-form').onsubmit({preventDefault(){}});
  assert.equal(nodes.get('ssh-key-file').value, '');
  assert.equal(nodes.get('ssh-key-name').value, '');
  vm.runInContext('handleEditHost()', context);
  assert.equal(nodes.get('ssh-host-key').children[0].value, key.id);
});


test('SSH Key methods mask pasted multiline keys and send paths without contents', async () => {
  const {nodes, context} = workspace([], null);
  const get = id => context.document.getElementById(id);
  const bodies = [];
  context.fetch = async (path, options) => {
    bodies.push(JSON.parse(options.body));
    return {ok:true,json:async()=>({keys:[]})};
  };
  get('ssh-key-method').value = 'paste';
  get('ssh-key-method').onchange();
  const privateKey = '-----BEGIN OPENSSH PRIVATE KEY-----\nSECRET\n-----END OPENSSH PRIVATE KEY-----';
  get('ssh-key-paste').onpaste({preventDefault(){},clipboardData:{getData:()=>privateKey}});
  assert.equal(get('ssh-key-paste').value, '****');
  assert.equal(get('ssh-key-paste-field').hidden, false);
  assert.equal(get('ssh-key-upload-field').hidden, true);
  get('ssh-key-name').value = 'pasted';
  await get('ssh-key-form').onsubmit({preventDefault(){}});
  assert.equal(bodies[0].privateKey, privateKey);
  assert.equal(bodies[0].inputMethod, 'paste');
  assert.equal(get('ssh-key-paste').value, '');
  get('ssh-key-method').value = 'path'; get('ssh-key-method').onchange();
  assert.equal(get('ssh-key-paste').required, false);
  assert.equal(get('ssh-key-path').required, true);
  get('ssh-key-name').value = 'path'; get('ssh-key-path').value = '/run/keys/existing';
  await get('ssh-key-form').onsubmit({preventDefault(){}});
  assert.equal(bodies[1].privateKeyPath, '/run/keys/existing');
  assert.equal(Object.hasOwn(bodies[1], 'privateKey'), false);
  vm.runInContext("sshKeys=[{id:'key-test',name:'test',privatePath:'/keys/private',publicPath:'/keys/public',publicKey:'PUBLIC'}];renderSSHKeys()",context);
  vm.runInContext('handleViewKey(sshKeys[0])', context);
  const card = nodes.get('ssh-key-view').children[1];
  assert.equal(card.children[3].children[1].textContent, '****');
  assert.equal(card.children[2].children[1].textContent, 'PUBLIC');
});


test('SSH Key form accepts spaced names and reports input and unavailable API errors', async () => {
  const {nodes, context} = workspace([], null);
  const get = id => context.document.getElementById(id);
  const requests = [];
  context.fetch = async (path, options) => {
    if (options.body) requests.push(JSON.parse(options.body));
    return {ok:false,status:405,json:async()=>{throw new SyntaxError('Method Not Allowed')}};
  };
  get('ssh-key-method').value = 'path';
  get('ssh-key-name').value = 'DeciFlow SSH Key';
  get('ssh-key-path').value = '/root/.ssh/id_ed25519';
  await get('ssh-key-form').onsubmit({preventDefault(){}});
  assert.equal(requests[0].name, 'DeciFlow SSH Key');
  assert.match(get('ssh-key-message').textContent, /Restart the DeciFlow UI/);
  assert.equal(get('add-ssh-key').disabled, false);
  get('ssh-key-name').value = '../bad';
  await get('ssh-key-form').onsubmit({preventDefault(){}});
  assert.equal(requests.length, 1);
  assert.match(get('ssh-key-message').textContent, /Enter a name/);
  await vm.runInContext('handleLoadKeys()', context);
  assert.match(get('ssh-key-message').textContent, /Restart the DeciFlow UI/);
  const markup = readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');
  assert.match(markup, /<form id="ssh-key-form"[^>]*novalidate/);
});


test('SSH Key Add, cancel and search keep the default screen compact', async () => {
  const { nodes, context } = workspace([], null);
  const get = id => context.document.getElementById(id);
  get('open-add-ssh-key').onclick();
  assert.equal(get('ssh-key-editor').hidden, false);
  assert.equal(get('ssh-key-registry').hidden, true);
  get('cancel-ssh-key').onclick();
  assert.equal(get('ssh-key-editor').hidden, true);
  vm.runInContext("sshKeys=[{id:'key-one',name:'one',privatePath:'/one'},{id:'key-two',name:'two',privatePath:'/two'}];renderSSHKeys()",context);
  get('ssh-key-search').value = 'two'; get('ssh-key-search').oninput();
  const rows = get('ssh-key-list').children[0].children[1].children;
  assert.equal(rows.length, 1); assert.equal(rows[0].children[0].textContent, 'two');
});


test('SSH Hosts CRUD and Remote File selection share saved connection settings', async () => {
  const {nodes,context} = workspace([], null);
  await new Promise(resolve=>setImmediate(resolve));
  const get = id => context.document.getElementById(id);
  vm.runInContext("sshKeys=[{id:'key-logs',name:'logs',privatePath:'/keys/logs/private_key'}]",context);
  get('open-add-ssh-host').onclick();
  assert.equal(get('ssh-host-editor').hidden, false);
  assert.equal(get('ssh-host-key').children[0].value, 'key-logs');
  get('ssh-host-name').value='Production'; get('ssh-host-address').value='logs.example';
  get('ssh-host-port').value='2222'; get('ssh-host-user').value='reader';
  get('ssh-host-key').value='key-logs';
  const requests=[];
  context.fetch=async(path,options)=>{
    if(path==='/api/delete-check')return {ok:true,json:async()=>({references:[],details:[]})};
    requests.push({path,options});
    if(options.method==='DELETE')return {ok:true,json:async()=>({hosts:[]})};
    return {ok:true,json:async()=>({hosts:[{...JSON.parse(options.body),id:'host-1'}]})};
  };
  await get('ssh-host-form').onsubmit({preventDefault(){}});
  assert.equal(JSON.parse(requests[0].options.body).port,2222);
  assert.equal(get('ssh-host-registry').hidden,false);
  const row=get('ssh-host-list').children[0].children[1].children[0];
  assert.equal(row.children[1].textContent,'reader@logs.example:2222');
  row.children[4].children[0].onclick();
  assert.equal(get('ssh-host-view').hidden,false);
  row.children[4].children[1].onclick();
  assert.equal(get('ssh-host-name').value,'Production');
  get('ssh-host-port').value='22';
  await get('ssh-host-form').onsubmit({preventDefault(){}});
  assert.equal(JSON.parse(requests[1].options.body).id,'host-1');
  vm.runInContext('handleEditSource(registeredSources.length)',context);
  assert.equal(vm.runInContext('Object.keys(sourceFields).join(",")',context),'name,type,endpoint,path,format,contentField,username,ticketCache,tokenFile,caFile');
  context.handleConfirmDelete=async()=>false;
  await row.children[4].children[2].onclick(); assert.equal(requests.length,2);
  context.handleConfirmDelete=async()=>true;
  await row.children[4].children[2].onclick(); assert.equal(requests[2].options.method,'DELETE');
  assert.equal(get('ssh-host-message').textContent,'SSH Host deleted.');
});


test('Selected Source shows its path or pattern and updates without stale text', () => {
  const {nodes,context} = workspace([], null);
  vm.runInContext("registeredSources=[{id:'one',name:'Local logs',type:'local',path:'/var/log/app/*.log'},{id:'two',name:'Remote logs',type:'ssh',path:'/srv/logs/**/*.json'}];updateSourceSettings(['one'])",context);
  const label=nodes.get('source-settings').children[0].children[0];
  const input=label.children[0]; const path=label.children[1];
  assert.equal(path.textContent,'/var/log/app/*.log');
  assert.equal(path.hidden,false);
  input.value='two'; input.onchange();
  assert.equal(path.textContent,'/srv/logs/**/*.json');
  input.value='Unregistered'; input.onchange();
  assert.equal(path.textContent,''); assert.equal(path.hidden,true);
});


for (const engine of ['laya', 'jev']) {
  test(`${engine} presents three equal core decisions including zero and endpoint probabilities`, async () => {
    const event = result(0, false);
    event.result.decisions.urgency.score = 0; event.result.decisions.ticket.noul = 0;
    const {nodes,context} = workspace([{type:'start',engine,total:1},event,{type:'done',elapsedMs:1}]);
    await runTask(nodes);
    let cards=decisionCards(nodes.get('results').children[0]);
    assert.equal(cards.length,3);
    assert.ok(cards.every(card=>card.className==='decision-card'));
    assert.equal(cards[1].children[1].textContent,'0.00 / 3');
    assert.equal(cards[2].children[1].textContent,'0.0%');
    assert.equal(cards[2].children[2].textContent,'Yes probability · 0% No → 100% Yes');
    vm.runInContext('results[0].decisions.urgency.score=3;results[0].decisions.ticket.noul=1;render(false)',context);
    cards=decisionCards(nodes.get('results').children[0]);
    assert.equal(cards[1].children[1].textContent,'3.00 / 3');
    assert.equal(cards[2].children[1].textContent,'100.0%');
  });
}

test('Missing legacy scores remain unavailable and failed requests show no predictions', async () => {
  const {nodes,context} = workspace([result(0,false)]);
  await runTask(nodes);
  const cards=decisionCards(nodes.get('results').children[0]);
  assert.equal(cards[1].children[1].textContent,'Not available');
  assert.equal(cards[2].children[1].textContent,'Not available');
  vm.runInContext("results[0].error='request failed';render(false)",context);
  const header=nodes.get('results').children[0].children[0];
  assert.equal(header.className,'result-top');
  assert.equal(header.children[0].textContent,'Processing Failed');
});


for (const engine of ['laya', 'jev']) {
  test(`${engine} scopes probability distributions and review notes to each decision`, async () => {
    const event=result(0);
    setDecisions(event.result,{
      choice:'normal',uncertain:true,candidates:['normal','error'],reasons:['low_answer_probability','close_probabilities'],
      probabilities:{normal:.275,warning:.2,error:.251,security:.11,other:.164},
      score:2,scoreProbabilities:{0:.1,1:.2,2:.3,3:.4},
      legend:{0:'Low: routine',1:'Medium: scheduled',2:'High: prompt',3:'Critical: immediate'},
      noul:.275,
    });
    const {nodes}=workspace([{type:'start',engine,total:1},event]);
    await runTask(nodes);
    const header=nodes.get('results').children[0].children[0];
    const cards=header.children[0].children;
    const distribution=card=>card.children.find(child=>child.className==='decision-distribution').children[1];
    const entries=card=>distribution(card).children.map(entry=>entry.children.map(value=>value.textContent).join(': '));
    assert.deepEqual(entries(cards[0]),['Normal: 27.5%','Warning: 20.0%','Error: 25.1%','Security: 11.0%','Other: 16.4%']);
    assert.deepEqual(entries(cards[1]),['0 · Low: 10.0%','1 · Medium: 20.0%','2 · High: 30.0%','3 · Critical: 40.0%']);
    assert.deepEqual(entries(cards[2]),['Yes: 27.5%','No: 72.5%']);
    assert.match(cards[0].children.at(-1).textContent,/Provisional:/);
    assert.equal(cards[1].children.some(child=>child.className==='uncertainty-note'),false);
    assert.equal(cards[2].children.some(child=>child.className==='uncertainty-note'),false);
    assert.equal(header.children.at(-1).children.find(child=>child.className==='review').textContent,'Needs Review');
  });
}


test('Three decisions show details by default without duplicate badges or toggles', async () => {
  const event=result(0,false);
  event.result.decisions.urgency.score=1.41; event.result.decisions.ticket.noul=.299;
  const {nodes,context}=workspace([event]);
  await runTask(nodes);
  const header=()=>nodes.get('results').children[0].children[0];
  const badges=()=>decisionCards(nodes.get('results').children[0]).map(card=>card.children[1]);
  assert.equal(header().children[0].className,'decision-grid');
  assert.deepEqual(badges().map(badge=>badge.textContent),['Normal','1.41 / 3','29.9%']);
  assert.match(badges()[1].title,/Urgency \(Score\)/);
  assert.match(badges()[2].title,/Work Ticket \(Noul\)/);
  assert.equal(header().children.some(child=>child.className==='decision-details'),false);
  vm.runInContext('render(false)',context);
  assert.equal(decisionCards(nodes.get('results').children[0]).length,3);
});

test('Main follows a selected Task new scheduled run but keeps explicit history selection', async () => {
  const {context}=workspace([]);
  vm.runInContext(`
    currentView='main'; monitoringReady=true; activeJobId='previous';
    registeredTasks[0].latestRun={jobId:'scheduled-run',state:'completed'};
    globalThis.watched=[]; handleWatchRun=async job=>{watched.push(job.jobId);activeJobId=job.jobId;};
  `,context);
  await vm.runInContext('handleLoadTasks()',context);
  assert.equal(vm.runInContext('watched.join()',context),'scheduled-run');
  vm.runInContext('followLatestTask=false;watched=[]',context);
  await vm.runInContext('handleLoadTasks()',context);
  assert.equal(vm.runInContext('watched.length',context),0);
});

test('Task navigation lists registered Tasks and exposes their run history', async () => {
  const {nodes,context}=workspace([]);
  vm.runInContext('handleNavigation("tasks");renderTasks()',context);
  assert.equal(nodes.get('tasks-page').hidden,false);
  assert.equal(nodes.get('main-page').hidden,true);
  const controls=nodes.get('task-list').children[0].children[1].children.at(-1);
  assert.deepEqual(controls.children.map(button=>button.textContent),['Run','Stop','Pause','View','Edit','History','Delete']);
  assert.equal(controls.children[1].disabled,true);
});

test('Source and Action dropdowns retain every sorted option with an existing selection', async () => {
  const {nodes,context}=workspace([]);
  await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext(`
    registeredTasks=['Zulu','가나다','Alpha','나다라'].map((name,index)=>({id:String(index),name,mode:'batch',sources:[]}));
    selectedTaskId='0'; renderTaskMonitor();
    registeredSources=['Zulu','가나다','Alpha','나다라'].map((name,index)=>({id:String(index),name,type:'local',path:'/logs/'+index}));
    registeredActions=[{id:'Zulu',name:'Zulu'},{id:'Alpha',name:'Alpha'}];
    sourcePreferences.set('0',{profile:'4e6d5417-611e-49e0-8e23-2444a0f49ee4',chunkEvents:1,actionId:'Zulu'});
    updateSourceSettings(['0']);
  `,context);
  const row=nodes.get('source-settings').children[0];
  const source=row.children[0].children[0]; const action=row.children[3].children[0];
  const expected=['가나다','나다라','Alpha','Zulu'];
  assert.deepEqual(source.children.map(option=>option.text),['None',...expected]);
  assert.deepEqual(source.children.map(option=>option.value),['','1','3','2','0']);
  assert.equal(source.value,'0');
  assert.deepEqual(action.children.map(option=>option.value),['','Alpha','Zulu']);
  assert.equal(action.value,'Zulu');
  const html=readFileSync(new URL('../public/index.html',import.meta.url),'utf8');
  assert.ok(html.includes('id="running-tasks"'));
  assert.equal(html.includes('Select a Task…'),false);
  assert.equal(html.includes('monitor-task-options'),false);
});

test('Main lists all saved Tasks in name order and opens current or latest runs', async () => {
  const {nodes,context}=workspace([]);
  await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext(`
    selectedTaskId='';
    registeredTasks=[
      {id:'z',name:'Zulu',mode:'realtime',sources:[],activeRun:{jobId:'run-z'}},
      {id:'idle',name:'Idle Task',mode:'batch',sources:[],latestRun:{jobId:'old'}},
      {id:'a',name:'Alpha',mode:'batch',sources:[],activeRun:{jobId:'run-a'}}
    ];
    globalThis.watched=[]; handleWatchRun=async job=>watched.push(job.jobId);
    renderTaskMonitor();
  `,context);
  const buttons=nodes.get('running-tasks').children;
  assert.deepEqual(buttons.map(button=>button.children[0].textContent),['Alpha','Zulu','Idle Task']);
  assert.ok(buttons.every(button=>button.attributes['aria-pressed']==='false'));
  await buttons[1].onclick();
  assert.equal(vm.runInContext('selectedTaskId',context),'z');
  assert.equal(vm.runInContext('watched.join()',context),'run-z');
  assert.equal(nodes.get('running-tasks').children[1].attributes['aria-pressed'],'true');
  await nodes.get('running-tasks').children[2].onclick();
  assert.equal(vm.runInContext('watched.join()',context),'run-z,old');
  vm.runInContext('registeredTasks=[];renderTaskMonitor()',context);
  assert.match(nodes.get('running-tasks').children[0].textContent,/No Enabled Tasks/);
});

test('Wide Main panels scroll independently and narrow layouts retain page scrolling', () => {
  const css=readFileSync(new URL('../public/style.css',import.meta.url),'utf8');
  assert.match(css,/@media \(min-width: 1051px\)[\s\S]*#main-page \.input-column, #main-page \.output[^}]*overflow-y: auto/);
  assert.match(css,/overscroll-behavior-y: contain/);
});

test('Required selectors omit Select placeholders without silently choosing a default', async () => {
  const {nodes,context}=workspace([]);
  await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext(`
    sshKeys=[{id:'key-Key',name:'Key',privatePath:'/keys/private_key'}];handleEditHost();
    registeredSources=[{id:'source',name:'Logs',type:'local',path:'/logs/app.log'}];
    updateSourceSettings(['']);
  `,context);
  const key=nodes.get('ssh-host-key');
  assert.deepEqual(key.children.map(option=>option.text),['Key']);
  assert.equal(key.value,'');
  const source=nodes.get('source-settings').children[0].children[0].children[0];
  assert.deepEqual(source.children.map(option=>option.text),['None','Logs']);
  assert.equal(source.value,'');
  const script=readFileSync(new URL('../public/app.js',import.meta.url),'utf8');
  assert.doesNotMatch(script,/new Option\('Select /);
  assert.equal(script.includes('Select a Source…'),false);
});

test('Main uses Task row clicks for viewing and has no duplicate Run button', () => {
  const html=readFileSync(new URL('../public/index.html',import.meta.url),'utf8');
  assert.equal(html.includes('id="classify"'),false);
  const script=readFileSync(new URL('../public/app.js',import.meta.url),'utf8');
  assert.equal(script.includes('View running'),false);
  assert.match(script,/return handleSelectTask\(task.id\)/);
  assert.match(script,/Click its Task in the running list to reconnect/);
});

test('Sidebar places DeciFlow host information above Main and keeps SSH management in Settings', () => {
  const html=readFileSync(new URL('../public/index.html',import.meta.url),'utf8');
  assert.ok(html.indexOf('class="host-info"')<html.indexOf('id="nav-main"'));
  assert.ok(html.indexOf('id="nav-settings"')<html.indexOf('id="settings-page"'));
  assert.ok(html.indexOf('id="settings-ssh-keys"')>html.indexOf('id="settings-page"'));
});

test('SSH connection tests work from unsaved editor and saved rows with status feedback', async () => {
  const {nodes,context}=workspace([]);
  await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext("sshKeys=[{id:'key-Key',name:'Key',privatePath:'/keys/private'}];handleEditHost()",context);
  nodes.get('ssh-host-name').value='Draft';nodes.get('ssh-host-address').value='logs.example';
  nodes.get('ssh-host-port').value='2222';nodes.get('ssh-host-user').value='reader';nodes.get('ssh-host-key').value='/keys/private';
  const calls=[];
  context.fetch=async(path,options)=>{calls.push({path,body:JSON.parse(options.body)});return {ok:true,json:async()=>({connected:true,checkedAt:'2026-10-16T00:00:00Z',elapsedMs:12})};};
  await nodes.get('test-ssh-host').onclick();
  assert.equal(calls[0].path,'/api/ssh-hosts/test');
  assert.equal(calls[0].body.port,2222);
  assert.match(nodes.get('ssh-host-test-result').textContent,/Connected \(SSH \+ SFTP\)/);
  assert.match(nodes.get('ssh-host-test-result').className,/connection-ok/);
  assert.equal(vm.runInContext('sshHosts.length',context),0);
  vm.runInContext("sshHosts=[{...hostDraft(),id:'saved'}];renderSSHHosts()",context);
  let row=nodes.get('ssh-host-list').children[0].children[1].children[0];
  assert.match(row.children[3].textContent,/Connected/);
  context.fetch=async(path,options)=>{calls.push({path,body:JSON.parse(options.body)});return {ok:true,json:async()=>({connected:false,error:'Permission denied',checkedAt:'2026-10-16T00:01:00Z',elapsedMs:5})};};
  await row.children[4].children[3].onclick();
  assert.deepEqual(calls[1].body,{id:'saved'});
  row=nodes.get('ssh-host-list').children[0].children[1].children[0];
  assert.match(row.children[3].textContent,/Failed.*Permission denied/);
  assert.equal(row.children[3].className,'connection-failed');
  vm.runInContext("sshHosts[0].port=22;renderSSHHosts()",context);
  assert.equal(nodes.get('ssh-host-list').children[0].children[1].children[0].children[3].textContent,'Not checked');
});

for(const approve of [false,true]) {
  test(`SSH unknown fingerprint requires approval before trusting (${approve})`, async () => {
    const {nodes,context}=workspace([]);await new Promise(resolve=>setImmediate(resolve));
    vm.runInContext("handleEditHost();",context);
    nodes.get('ssh-host-name').value='Draft';nodes.get('ssh-host-address').value='logs.example';
    nodes.get('ssh-host-port').value='22';nodes.get('ssh-host-user').value='reader';nodes.get('ssh-host-key').value='/keys/private';
    const calls=[]; const dialog=context.document.getElementById('ssh-trust-dialog');
    dialog.showModal=()=>{};context.confirm=()=>{throw new Error('Native confirmation must not be used');};
    context.fetch=async(path,options)=>{const payload=JSON.parse(options.body);calls.push(payload);return {ok:true,json:async()=>payload.trustedHostKey ? {connected:true} : {connected:false,error:'Host key is not trusted',hostKey:{host:'logs.example',port:22,fingerprint:'SHA256:expected',publicKey:'ssh-ed25519 PUBLIC'}}};};
    const pending=nodes.get('test-ssh-host').onclick();
    await new Promise(resolve=>setImmediate(resolve));
    assert.equal(nodes.get('ssh-trust-fingerprint').textContent,'SHA256:expected');
    assert.equal(nodes.get('ssh-trust-host').textContent,'logs.example:22');
    assert.equal(nodes.get('ssh-trust-algorithm').textContent,'ssh-ed25519');
    dialog.returnValue=approve?'approve':'cancel';dialog.onclose();
    await pending;
    assert.equal(calls.length,approve?2:1);
    if(approve)assert.equal(calls[1].trustedHostKey,'ssh-ed25519 PUBLIC');
    else assert.match(nodes.get('ssh-host-test-result').textContent,/not approved/);
  });
}

test('SSH approval modal queues simultaneous hosts and dismisses without approval', async () => {
  const {nodes,context}=workspace([]);
  const dialog=context.document.getElementById('ssh-trust-dialog');let opened=0;
  dialog.showModal=()=>{opened++;};
  const first=vm.runInContext("handleApproveHostKey({host:'first',port:22,publicKey:'ssh-ed25519 A',fingerprint:'SHA256:first'})",context);
  const second=vm.runInContext("handleApproveHostKey({host:'second',port:2222,publicKey:'ssh-rsa B',fingerprint:'SHA256:second'})",context);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(opened,1);assert.equal(nodes.get('ssh-trust-host').textContent,'first:22');
  assert.equal(dialog.returnValue,'cancel');dialog.onclose();assert.equal(await first,false);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(opened,2);assert.equal(nodes.get('ssh-trust-host').textContent,'second:2222');
  dialog.returnValue='approve';dialog.onclose();assert.equal(await second,true);
  const html=readFileSync(new URL('../public/index.html',import.meta.url),'utf8');
  assert.match(html,/<dialog id="ssh-trust-dialog"[^>]*aria-labelledby="ssh-trust-title"/);
  assert.match(html,/<form method="dialog">/);
  assert.match(html,/id="ssh-trust-cancel"[^>]*autofocus/);
});

test('Visible SSH Hosts auto-check sequentially once per visit without periodic repeats', async () => {
  const {nodes,context}=workspace([]);await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext("currentView='settings';sshHosts=[{id:'b',name:'Beta',host:'b',port:22,username:'u',keyPath:'/key'},{id:'a',name:'Alpha',host:'a',port:22,username:'u',keyPath:'/key'}]",context);
  context.document.getElementById('ssh-host-registry').hidden=false;
  let release;const gate=new Promise(resolve=>release=resolve);const calls=[];const delays=[];let active=0,maxActive=0;
  context.setTimeout=(handler,delay)=>{delays.push(delay);return 1;};
  context.fetch=async(path,options)=>{const body=JSON.parse(options.body);calls.push(body.id);active++;maxActive=Math.max(active,maxActive);if(body.id==='a')await gate;active--;return {ok:true,json:async()=>({connected:true})};};
  const pass=vm.runInContext('handleAutoCheckHosts()',context);
  await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(calls,['a']);
  await vm.runInContext('handleAutoCheckHosts()',context);assert.deepEqual(calls,['a']);
  release();await pass;
  assert.deepEqual(calls,['a','b']);assert.equal(maxActive,1);assert.ok(!delays.includes(30000));
  await vm.runInContext('handleAutoCheckHosts()',context);assert.equal(calls.length,2);
  context.document.hidden=true;
  await vm.runInContext('handleAutoCheckHosts()',context);assert.equal(calls.length,2);
  context.document.hidden=false;nodes.get('ssh-host-registry').hidden=true;
  await vm.runInContext('handleAutoCheckHosts()',context);assert.equal(calls.length,2);
});

test('Automatic host checks leave unknown keys unapproved and stop after leaving Settings', async () => {
  const {nodes,context}=workspace([]);await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext("currentView='settings';sshHosts=[{id:'a',name:'Alpha',host:'a',port:22,username:'u',keyPath:'/key'},{id:'b',name:'Beta',host:'b',port:22,username:'u',keyPath:'/key'}]",context);
  context.document.getElementById('ssh-host-registry').hidden=false;
  const calls=[];let prompts=0;
  context.document.getElementById('ssh-trust-dialog').showModal=()=>{prompts++;};
  context.fetch=async(path,options)=>{calls.push(JSON.parse(options.body));vm.runInContext("currentView='main'",context);return {ok:true,json:async()=>({connected:false,hostKey:{host:'a',port:22,fingerprint:'SHA256:test',publicKey:'ssh-ed25519 TEST'}})};};
  await vm.runInContext('handleAutoCheckHosts()',context);
  assert.equal(calls.length,1);assert.equal(prompts,0);assert.equal(calls[0].trustedHostKey,undefined);
  assert.match(vm.runInContext('sshHostChecks.values().next().value.error',context),/Use Test Connection/);
});

test('Nested Settings navigation opens individual sections and restores deep links', async () => {
  const location={hash:''};const {nodes,context,listeners}=workspace([],null,undefined,null,location);
  await new Promise(resolve=>setImmediate(resolve));
  nodes.get('nav-ssh-keys').onclick();
  assert.equal(location.hash,'#settings/ssh-keys');
  assert.equal(nodes.get('settings-title').textContent,'SSH Keys');
  assert.equal(nodes.get('settings-overview').hidden,true);
  assert.equal(nodes.get('settings-page').hidden,false);
  assert.equal(nodes.get('settings-ssh-keys').hidden,false);
  assert.equal(nodes.get('settings-ssh-hosts').hidden,true);
  assert.equal(nodes.get('nav-ssh-keys').attributes['aria-current'],'page');
  assert.equal(vm.runInContext('hostChecksVisible()',context),false);
  location.hash='#settings/ssh-hosts';listeners.get('hashchange')();
  assert.equal(nodes.get('settings-ssh-keys').hidden,true);
  assert.equal(nodes.get('settings-ssh-hosts').hidden,false);
  assert.equal(nodes.get('nav-ssh-hosts').attributes['aria-current'],'page');
  assert.equal(nodes.get('settings-title').textContent,'SSH Hosts');
  nodes.get('nav-settings').onclick();
  assert.equal(location.hash,'#settings');
  assert.equal(nodes.get('settings-ssh-keys').hidden,true);
  assert.equal(nodes.get('settings-ssh-hosts').hidden,true);
  assert.equal(nodes.get('settings-overview').hidden,false);
  assert.equal(nodes.get('settings-title').textContent,'Settings');
  assert.equal(vm.runInContext('hostChecksVisible()',context),false);
  nodes.get('nav-main').onclick();
  assert.equal(location.hash,'');assert.equal(nodes.get('main-page').hidden,false);
});

test('Source Action and Criteria menu entries close both editor and View without changing saved data', async () => {
  const definitions=Object.fromEntries(['normal','warning','error','security','other'].map(key=>[key,key]));
  const profiles={[sampleProfileIds.general]:profileFixture('General','Instructions',definitions),custom:profileFixture('Custom','Instructions',definitions)};
  const {nodes,context}=workspace([],undefined,undefined,profiles);
  await new Promise(resolve=>setImmediate(resolve));await nodes.get('nav-criteria').onclick();
  const original=vm.runInContext('JSON.stringify([registeredSources,registeredActions,criteriaProfiles])',context);
  for(const [nav,edit,kind,list] of [
    ['nav-sources','handleEditSource(0)','source','source-list'],
    ['nav-actions','handleEditAction(registeredActions.length)','action','action-list'],
    ['nav-criteria',"handleEditCriteria('custom')",'criteria','criteria-list'],
  ]) {
    vm.runInContext(edit,context);
    vm.runInContext(`handleViewConfiguration('${kind}-view','Details',[['Name','Saved item']])`,context);
    nodes.get('nav-main').onclick();await nodes.get(nav).onclick();
    assert.equal(nodes.get(`${kind}-view`).hidden,true);
    assert.equal(nodes.get(`${kind}-editor`).hidden,true);
    assert.equal(nodes.get(list).hidden,false);
  }
  assert.equal(vm.runInContext('JSON.stringify([registeredSources,registeredActions,criteriaProfiles])',context),original);
});

test('Tasks and Settings menus reopen their lists instead of editor detail or history', async () => {
  const {nodes,context}=workspace([]);await new Promise(resolve=>setImmediate(resolve));
  await vm.runInContext('handleEditTask(registeredTasks[0])',context);
  vm.runInContext('handleViewTask(registeredTasks[0])',context);
  context.document.getElementById('task-history').hidden=false;
  nodes.get('nav-main').onclick();nodes.get('nav-tasks').onclick();
  assert.equal(nodes.get('task-registry').hidden,false);
  for(const id of ['task-editor','task-view','task-history'])assert.equal(nodes.get(id).hidden,true);
  vm.runInContext("handleAddKey();pastedPrivateKey='unsaved private key';",context);
  nodes.get('nav-main').onclick();nodes.get('nav-ssh-keys').onclick();
  assert.equal(nodes.get('ssh-key-registry').hidden,false);
  assert.equal(nodes.get('ssh-key-editor').hidden,true);
  assert.equal(nodes.get('ssh-key-view').hidden,true);
  assert.equal(vm.runInContext('pastedPrivateKey',context),'');
  vm.runInContext('handleEditHost()',context);
  nodes.get('nav-main').onclick();nodes.get('nav-ssh-hosts').onclick();
  assert.equal(nodes.get('ssh-host-registry').hidden,false);
  assert.equal(nodes.get('ssh-host-editor').hidden,true);
  assert.equal(nodes.get('ssh-host-view').hidden,true);
});

test('Task assigns multiple Hosts per remote Source and submits only selected IDs', async () => {
  const {nodes,context}=workspace([]);await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext("registeredSources=[{id:'remote',name:'Common logs',type:'ssh',path:'/var/log/*.log'}]",context);
  let submitted;
  context.fetch=async(path,options)=>{
    if(path==='/api/ssh-hosts')return {ok:true,json:async()=>({hosts:[{id:'a',name:'Alpha',host:'a',port:22,username:'u'},{id:'b',name:'Beta',host:'b',port:22,username:'u'}]})};
    if(path==='/api/tasks' && options.method==='PUT')submitted=JSON.parse(options.body);
    return {ok:true,json:async()=>({tasks:[]})};
  };
  await vm.runInContext("handleEditTask({id:'test-task',name:'Fleet',mode:'batch',sources:[{sourceId:'remote',profile:'4e6d5417-611e-49e0-8e23-2444a0f49ee4',chunkEvents:1,hostIds:['a']}]})",context);
  const row=nodes.get('source-settings').children[0];const picker=row.children[4];
  assert.equal(picker.hidden,false);assert.equal(picker.children[0].textContent,'Source Hosts · 1 selected');
  picker.children[1].value='Beta';picker.children[1].oninput();
  assert.equal(picker.children[3].children.length,1);
  picker.children[2].children[0].onclick();
  assert.equal(picker.children[0].textContent,'Source Hosts · 2 selected');
  await nodes.get('task-form').onsubmit({preventDefault(){}});
  assert.deepEqual(submitted.sources[0].hostIds,['a','b']);
  assert.equal(Object.hasOwn(submitted.sources[0],'host'),false);
  assert.equal(vm.runInContext('registeredSources[0].hostId',context),undefined);
});

test('Host filter combines with Source filters and retains host failure diagnostics', async () => {
  const a=result(0,false),b=result(1,false),failed=result(2,false);
  a.result.hostId='a';a.result.hostName='Alpha';a.result.hostAddress='a';a.result.hostPort=22;a.result.source='/same';
  b.result.hostId='b';b.result.hostName='Beta';b.result.hostAddress='b';b.result.hostPort=22;b.result.source='/same';
  failed.result={log:'',error:'Host unavailable',sourceFailure:true,hostId:'b',hostName:'Beta',hostAddress:'b',hostPort:22,source:'ssh://b/logs'};
  const {nodes}=workspace([{type:'start',engine:'laya',total:null,hosts:[{hostId:'a',hostName:'Alpha',hostAddress:'a',hostPort:22},{hostId:'b',hostName:'Beta',hostAddress:'b',hostPort:22}]},a,b,failed,{type:'host-status',hosts:[{hostId:'b',hostName:'Beta',hostAddress:'b',hostPort:22,collectionState:'failed',error:'Host unavailable'}]},{type:'done',state:'failed',elapsedMs:4}]);
  await runTask(nodes);
  nodes.get('host-filter').value='b';nodes.get('host-filter').onchange();
  assert.deepEqual(logs(nodes),['','log-1']);
  assert.equal((nodes.get('source-hosts-rows')?.children.length || 0),0);
  const dialog=nodes.get('source-hosts-dialog');
  dialog.showModal=()=>{dialog.open=true;};
  nodes.get('source-hosts-detail').onclick();
  const row=nodes.get('source-hosts-rows').children.find(row=>row.children[0].children[0].textContent==='Beta');
  assert.equal(row.children[1].textContent,'Failed');
  assert.equal(row.children[1].children[0].textContent,'Host unavailable');
  assert.deepEqual(row.children[2].children.map(node=>node.textContent),['1',' / ','1',' / ','2']);
  dialog.open=false;dialog.onclose();
  assert.equal((nodes.get('source-hosts-rows')?.children.length || 0),0);
  assert.equal(nodes.get('results').children[0].children[0].children[0].textContent,'Source failed');
  nodes.get('source-filter').value='/same';nodes.get('source-filter').onchange();
  assert.deepEqual(logs(nodes),['log-1']);
});

test('Timing updates reuse visible cards and never rescan the result history', () => {
  const {nodes,context}=workspace([]);
  vm.runInContext(`
    results=Array.from({length:20000},(_,index)=>({log:'record '+index,category:'normal',elapsedMs:2,probabilities:{normal:1},hostId:'host-'+index%3,source:'/data/input.txt'}));
    completionOrder=results.map((_,index)=>index);completed=results.length;
    render();
    globalThis.historyReads=0;
    results=new Proxy(results,{get(target,key){if(/^\\d+$/.test(String(key)))historyReads++;return Reflect.get(target,key);}});
    render(false,true);
    historyReads=0;
  `,context);
  const rows=[...nodes.get('results').children];
  let created=0;const create=context.document.createElement;
  context.document.createElement=(...args)=>{created++;return create(...args);};
  vm.runInContext('elapsedMs+=1000;render(false,true)',context);
  assert.ok(vm.runInContext('historyReads',context)<=100);
  assert.ok(created<100,`Timing tick created ${created} nodes`);
  assert.ok(rows.every((row,index)=>nodes.get('results').children[index]===row));
});

for (const engine of ['laya','jev']) test(`${engine} incremental results preserve cards, JSON and exact aggregate/filter counts`, async () => {
  const {nodes,context}=workspace([{type:'start',engine,total:null},...Array.from({length:150},(_,index)=>result(index,index%2===0))]);
  await runTask(nodes);
  const retained=nodes.get('results').children[0];
  const details=retained.children.at(-1);details.open=true;details.ontoggle();
  const json=details.children[1].children[1].textContent;
  vm.runInContext(`
    results[150]={log:'new',category:'error',error:'failed',elapsedMs:3,source:'/data/input.txt',hostId:'host-1',sourceFailure:true};
    completionOrder.push(150);completed++;render(false,true);
  `,context);
  assert.equal(nodes.get('results').children[1],retained);
  assert.equal(details.open,true);assert.equal(details.children[1].children[1].textContent,json);
  assert.equal(vm.runInContext('resultStatistics.failed',context),1);
  assert.equal(vm.runInContext('resultStatistics.total',context),151);
  nodes.get('processing-filter').value='failed';nodes.get('processing-filter').onchange();
  assert.deepEqual(logs(nodes),['new']);
  vm.runInContext(`
    results[151]={log:'another',error:'timeout',elapsedMs:5};completionOrder.push(151);completed++;
    render(false,true);
  `,context);
  assert.deepEqual(logs(nodes),['another','new']);
  const incremental=vm.runInContext('JSON.stringify(resultStatistics,(_,value)=>value instanceof Map?[...value]:value)',context);
  vm.runInContext('render()',context);
  assert.equal(vm.runInContext('JSON.stringify(resultStatistics,(_,value)=>value instanceof Map?[...value]:value)',context),incremental);
  assert.ok(vm.runInContext('renderedRows.size',context)<=100);
});

test('Hidden dashboards defer scheduled DOM work and catch up on return', async () => {
  const {nodes,context}=workspace([{type:'start',engine:'laya',total:null},result(0)]);
  await runTask(nodes);
  const first=nodes.get('results').children[0];
  let flush;context.setTimeout=handler=>{flush=handler;return 1;};
  vm.runInContext("currentView='main';document.hidden=true;renderTimer=undefined;scheduleRender()",context);
  flush();assert.equal(nodes.get('results').children[0],first);
  vm.runInContext("results[1]={log:'next',category:'normal',elapsedMs:1};completionOrder.push(1);completed++;document.hidden=false;scheduleRender()",context);
  flush();assert.deepEqual(logs(nodes),['next','log-0']);
  assert.equal(nodes.get('results').children[1],first);
});

test('Task Monitor only lists selectable Tasks without management controls or duplicated details', () => {
  const html=readFileSync(new URL('../public/index.html',import.meta.url),'utf8');
  const section=html.slice(html.indexOf('<section class="card task-monitor">'),html.indexOf('</section>',html.indexOf('<section class="card task-monitor">')));
  assert.ok(section.includes('<h2>Task Monitor</h2>'));
  assert.ok(section.includes('id="running-tasks"'));
  for(const id of ['stop','manage-tasks','monitor-task-info','monitor-task-status','input-limits','data-notice'])assert.ok(!section.includes(`id="${id}"`));
});

// Extract text from static heading fixtures; this is not an HTML sanitizer.
function headingText(markup) {
  return Array.from(markup.matchAll(/(?:^|>)([^<>]+)(?=<|$)/g), match => match[1]).join('');
}

test('Static heading text extraction preserves text and excludes tag attributes', () => {
  assert.equal(headingText('Classification Results'), 'Classification Results');
  assert.equal(headingText('<span class="lowercase">Running</span> Task Monitor'), 'Running Task Monitor');
  assert.equal(headingText('Sources <strong>and <em>Decisions</em></strong>'), 'Sources and Decisions');
  assert.equal(headingText('Classifi<strong>cation</strong> Results'), 'Classification Results');
  assert.equal(headingText('<span id="status"></span>'), '');
});

test('Static page, section and dialog headings consistently use Title Case', () => {
  const html=readFileSync(new URL('../public/index.html',import.meta.url),'utf8');
  const minorWords=new Set(['a','an','and','as','at','but','by','for','in','of','on','or','the','to']);
  for(const [,markup] of html.matchAll(/<h[1-6][^>]*>([\s\S]*?)<\/h[1-6]>/g)) {
    const title=headingText(markup);
    const words=title.match(/[A-Za-z]+/g) || [];
    words.forEach((word,index)=>{
      if(index>0 && index<words.length-1 && minorWords.has(word))return;
      assert.match(word,/^[A-Z]/,`Heading must use Title Case: ${title}`);
    });
  }
});

function pagedWorkspace(count=1000) {
  const state=workspace([]);
  let records=Array.from({length:count},(_,index)=>({sequence:index+1,result:{log:`record-${index+1}`,category:'normal',elapsedMs:1,review:false,hostId:'host-1'}}));
  let limit=50;
  const original=state.context.fetch;const queries=[];
  state.context.fetch=async(path,options)=>{
    if(path==='/api/settings'){
      if(options.method==='PUT')limit=JSON.parse(options.body).resultsPerPage;
      return {ok:true,json:async()=>({resultsPerPage:limit})};
    }
    if(path.endsWith('/results')){
      const query=JSON.parse(options.body);queries.push(query);
      let items=records.filter(item=>(query.before==null || item.sequence<query.before) && (query.after==null || item.sequence>query.after) && (query.through==null || item.sequence<=query.through));
      if(query.search)items=items.filter(item=>item.result.log.includes(query.search));
      items=items.toReversed();
      const summary={total:records.length,failed:0,review:0,truncated:0,processingMs:records.length,actionSuccess:0,actionFailed:0,groups:{all:records.length,certain:records.length,uncertain:0},categories:Object.fromEntries(['all','certain','uncertain'].map(group=>[group,{normal:group==='uncertain'?0:records.length,warning:0,error:0,security:0,other:0}])),hosts:{'host-1':{name:'Host',count:records.length,failed:0}},sources:{},processingPercentiles:{medianMs:1,p95Ms:1,p99Ms:1}};
      return {ok:true,json:async()=>JSON.parse(JSON.stringify({snapshot:{jobId:'paged',state:'completed',settings:{mode:'batch',taskName:'Paged Task'},hosts:[],elapsedMs:1000},summary,sequence:records.length,...(query.onlySummary?{}:{items:items.slice(0,limit),hasNext:items.length>limit,limit})}))};
    }
    if(path.endsWith('/review'))return {ok:true,json:async()=>({saved:true})};
    return original(path,options);
  };
  return {...state,queries,append(){const sequence=records.length+1;records.push({sequence,result:{log:`record-${sequence}`,category:'normal',elapsedMs:1,review:false,hostId:'host-1'}});}};
}

test('SQLite-backed UI keeps only its 50-result page while showing whole-run aggregates', async()=>{
  const {nodes,context,queries}=pagedWorkspace();
  await vm.runInContext("handlePagedProcessing({jobId:'paged',state:'completed',settings:{mode:'batch'},pagedResults:true})",context);
  assert.equal(nodes.get('results').children.length,50);
  assert.equal(logs(nodes)[0],'record-1000');
  assert.equal(vm.runInContext('completed',context),1000);
  assert.equal(vm.runInContext('results.length',context),50);
  assert.equal(vm.runInContext('resultStatistics?.total || pagedView.summary.total',context),1000);
  assert.equal(nodes.get('page-info').textContent,'Page 1 · 50 results shown');
  await nodes.get('next').onclick();
  assert.equal(logs(nodes)[0],'record-950');
  assert.equal(queries.at(-1).before,951);
  assert.equal(queries.at(-1).through,1000);
  assert.equal(vm.runInContext('results.length',context),50);
  await nodes.get('previous').onclick();assert.equal(logs(nodes)[0],'record-1000');
});

test('Paged polling only requests new rows and freezes historical or paused pages', async()=>{
  const {nodes,context,queries,append}=pagedWorkspace();
  await vm.runInContext("handlePagedProcessing({jobId:'paged',state:'completed',settings:{mode:'batch'},pagedResults:true})",context);
  const retained=nodes.get('results').children[0];
  append();await vm.runInContext('handleRefreshResults(false,true)',context);
  assert.equal(queries.at(-1).after,1000);
  assert.equal(logs(nodes)[0],'record-1001');
  assert.equal(nodes.get('results').children[1],retained);
  assert.equal(vm.runInContext('results.length',context),50);
  await nodes.get('next').onclick();const frozen=logs(nodes);
  append();await vm.runInContext('handleRefreshResults(false,true)',context);
  assert.equal(queries.at(-1).onlySummary,true);assert.deepEqual(logs(nodes),frozen);
  assert.equal(nodes.get('pause-updates').textContent,'Latest Results (1 new)');
  await nodes.get('pause-updates').onclick();assert.equal(logs(nodes)[0],'record-1002');
  nodes.get('pause-updates').onclick();append();await vm.runInContext('handleRefreshResults(false,true)',context);
  assert.equal(logs(nodes)[0],'record-1002');
  assert.equal(nodes.get('pause-updates').textContent,'Resume Display Updates (1 new)');
  await nodes.get('pause-updates').onclick();assert.equal(logs(nodes)[0],'record-1003');
});

test('Results settings persist the page size and apply it to the selected run', async()=>{
  const {nodes,context}=pagedWorkspace();
  await vm.runInContext("handlePagedProcessing({jobId:'paged',state:'completed',settings:{mode:'batch'},pagedResults:true})",context);
  nodes.get('nav-configuration').onclick();
  assert.equal(nodes.get('settings-title').textContent,'Configurations');
  assert.equal(nodes.get('settings-configuration').hidden,false);
  nodes.get('results-per-page').value='10';
  await nodes.get('results-settings-form').onsubmit({preventDefault(){}});
  assert.equal(vm.runInContext('results.length',context),10);
  assert.equal(nodes.get('results').children.length,10);
  assert.equal(nodes.get('results-settings-message').textContent,'Settings saved.');
});

test('Delete confirmation uses the shared modal and defaults to cancellation', async()=>{
  const {context,nodes}=workspace([]);
  const dialog=context.document.getElementById('delete-dialog');
  let opened=0;dialog.showModal=()=>{opened++;};
  context.confirm=()=>{throw new Error('Native confirmation must not be used');};
  const pending=vm.runInContext("handleConfirmDelete('Task','Example','All results will be permanently deleted.')",context);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(opened,1);assert.equal(dialog.returnValue,'cancel');
  assert.equal(nodes.get('delete-name').textContent,'Example');
  dialog.onclose();assert.equal(await pending,false);
  const approved=vm.runInContext("handleConfirmDelete('Source','Input','Original files are kept.')",context);
  await new Promise(resolve=>setImmediate(resolve));dialog.returnValue='delete';dialog.onclose();assert.equal(await approved,true);
  const html=readFileSync(new URL('../public/index.html',import.meta.url),'utf8');
  assert.match(html,/<dialog id="delete-dialog"[^>]*aria-labelledby="delete-title"/);
  assert.match(html,/value="cancel" class="quiet" autofocus/);
  const code=readFileSync(new URL('../public/app.js',import.meta.url),'utf8');
  assert.ok(!code.includes('globalThis.confirm('));
  for(const kind of ['Task','Source','Criteria','Action','SSH Key','SSH Host'])assert.ok(code.includes(`handleConfirmDelete('${kind}'`));
});

test('Dependency blockers show references with Close only and never approve deletion', async()=>{
  const {context,nodes}=workspace([]);
  const dialog=context.document.getElementById('delete-dialog');dialog.showModal=()=>{};
  context.fetch=async()=>({ok:true,json:async()=>({references:['Task: Analysis','Running task: Analysis']})});
  const pending=vm.runInContext("handleConfirmDelete('Source','Input','Delete input.','source-1')",context);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(nodes.get('delete-title').textContent,'Cannot Delete Source');
  assert.equal(nodes.get('delete-approve').hidden,true);
  assert.equal(nodes.get('delete-cancel').textContent,'Close');
  assert.equal(nodes.get('delete-references').children[0].textContent,'Task: Analysis');
  dialog.returnValue='delete';dialog.onclose();assert.equal(await pending,false);
  context.fetch=async()=>{throw new Error('Offline');};
  const failed=vm.runInContext("handleConfirmDelete('Task','Example','Delete results.','task-1')",context);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(nodes.get('delete-approve').hidden,true);
  assert.match(nodes.get('delete-description').textContent,/Could not verify dependencies/);
  dialog.onclose();assert.equal(await failed,false);
});

test('Task View groups source fields and host names in structured cards',()=>{
  const {nodes,context}=workspace([]);
  vm.runInContext(`
    registeredSources=[{id:'remote',name:'System Logs',type:'ssh',path:'/var/log/*'},{id:'local',name:'Local Input',type:'local',path:'/input/data.txt'}];
    sshHosts=[{id:'host-a',name:'Oracle'},{id:'host-b',name:'Raspberry Pi'}];
    registeredActions=[{id:'Notify',name:'Notify'}];
    handleViewTask({name:'Monitor',mode:'realtime',resumeOnRestart:true,sources:[
      {sourceId:'remote',profile:'4e6d5417-611e-49e0-8e23-2444a0f49ee4',chunkEvents:5,actionId:'Notify',hostIds:['host-a','host-b']},
      {sourceId:'local',profile:'4e6d5417-611e-49e0-8e23-2444a0f49ee4',chunkEvents:1,actionId:''}
    ]});
  `,context);
  const container=nodes.get('task-view').children[0];
  assert.equal(container.children[0].children[0].children[0].textContent,'Monitor');
  const cards=container.children[1].children;
  assert.equal(cards.length,2);
  const fields=cards[0].children[0].children;
  assert.equal(fields[0].children[0].textContent,'Source Name');
  assert.equal(fields[0].children[1].textContent,'System Logs');
  assert.equal(fields[1].children[0].textContent,'File Path / Pattern');
  assert.equal(fields[1].children[1].textContent,'/var/log/*');
  assert.equal(fields[2].children[1].textContent,'Remote File (SSH)');
  assert.equal(fields.find(field=>field.children[0].textContent==='Input Format').children[1].textContent,'TEXT (Chunk)');
  assert.equal(fields.find(field=>field.children[0].textContent==='Events per Chunk').children[1].textContent,'5');
  assert.equal(fields.find(field=>field.children[0].textContent==='Action').children[1].textContent,'Notify');
  assert.equal(fields[3].children[0].textContent,'Source Hosts (2)');
  assert.deepEqual(fields[3].children[1].children.map(host=>host.textContent),['Oracle','Raspberry Pi']);
  const local=cards[1].children[0].children;
  assert.equal(local.find(field=>field.children[0].textContent==='Action').children[1].textContent,'None');
  assert.equal(local[3].children[1].children[0].textContent,'DeciFlow (Local)');
});


test('Task list keeps its summary columns while Source names appear in View',()=>{
  const {nodes,context}=workspace([]);
  vm.runInContext('renderTasks()',context);
  const header=nodes.get('task-list').children[0].children[0];
  assert.deepEqual(header.children.map(item=>item.textContent),['Name','Enabled','Execution','Status','Next Run','Manage']);
});


test('View keeps Task and SSH lists visible without a Back to List button',()=>{
  const {nodes,context}=workspace([]);
  vm.runInContext("handleViewTask({name:'Example',mode:'batch',sources:[]})",context);
  assert.equal(nodes.get('task-registry').hidden,false);
  assert.equal(nodes.get('task-view').children[0].children[0].children.length,1);
  vm.runInContext("handleViewKey({id:'key-Key',name:'Key',privatePath:'/private',publicPath:'/public',publicKey:'public'})",context);
  assert.equal(nodes.get('ssh-key-registry').hidden,false);
  assert.equal(nodes.get('ssh-key-view').children[0].children.length,1);
  vm.runInContext("handleViewHost({name:'Host',host:'example',port:22,username:'reader',keyPath:'/private'})",context);
  assert.equal(nodes.get('ssh-host-registry').hidden,false);
  assert.equal(nodes.get('ssh-host-view').children[0].children.length,1);
});

test('Second SSH Host expands directly below its own row and stays there after status rendering',async()=>{
  const {nodes,context}=workspace([]);await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext(`sshHosts=[{id:'a',name:'Alpha',host:'a',port:22,username:'reader',keyPath:'/key'},{id:'b',name:'Oracle',host:'b',port:22,username:'reader',keyPath:'/key'},{id:'c',name:'Third',host:'c',port:22,username:'reader',keyPath:'/key'}];renderSSHHosts();`,context);
  const body=()=>nodes.get('ssh-host-list').children[0].children[1];
  const view=()=>nodes.get('ssh-host-view');
  body().children[1].children[4].children[0].onclick();
  assert.equal(body().children.length,4);
  assert.equal(body().children[2].children[0].children[0],view());
  assert.equal(body().children[2].children[0].colSpan,5);
  assert.equal(view().children[0].children[0].textContent,'Oracle');
  vm.runInContext('renderSSHHosts()',context);
  assert.equal(body().children[2].children[0].children[0],view());
  body().children[1].children[4].children[0].onclick();assert.equal(view().hidden,true);
  assert.equal(body().children.length,3);
  body().children[0].children[4].children[0].onclick();
  body().children[2].children[4].children[0].onclick();
  assert.equal(body().children.length,4);
  assert.equal(body().children[2].children[0].children[0],view());
  assert.equal(view().children[0].children[0].textContent,'Oracle');
});

test('Host View and redraw do not repeat automatic checks within one visit',async()=>{
  const {nodes,context}=workspace([]);await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext(`currentView='settings';currentSettingsSection='ssh-hosts';sshHosts=[{id:'a',name:'Alpha',host:'a',port:22,username:'reader',keyPath:'/key'}];`,context);
  context.document.getElementById('ssh-host-registry').hidden=false;let count=0;
  context.fetch=async()=>{count++;return {ok:true,json:async()=>({connected:true})};};
  await vm.runInContext('handleAutoCheckHosts()',context);assert.equal(count,1);
  const body=()=>nodes.get('ssh-host-list').children[0].children[1];
  body().children[0].children[4].children[0].onclick();
  await vm.runInContext('handleAutoCheckHosts()',context);assert.equal(count,1);
  body().children[0].children[4].children[3].onclick();
  await new Promise(resolve=>setImmediate(resolve));assert.equal(count,2);
  vm.runInContext('autoCheckedHosts.clear()',context);
  await vm.runInContext('handleAutoCheckHosts()',context);assert.equal(count,3);
});

test('Source Action Criteria Task and SSH Key View buttons insert a detail row immediately after selection',async()=>{
  const {context,nodes}=workspace([]);await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext(`registeredSources=[{id:'source',name:'Input',type:'local',path:'/input'}];renderSources();registeredActions=[{id:'action',name:'Notify',code:'pass'}];renderActions();registeredTasks=[{id:'task',name:'Analysis',mode:'batch',sources:[]}];renderTasks();sshKeys=[{id:'key-Key',name:'Key',privatePath:'/key',publicPath:'/pub',publicKey:'public'}];renderSSHKeys();criteriaProfiles={[sampleProfileIds.general]:profileFixture('General','Default',{normal:'Normal'})};renderCriteria();`,context);
  for(const [list,id,body] of [['source-registry','source-view',false],['action-registry','action-view',false],['task-list','task-view',false],['ssh-key-list','ssh-key-view',true],['criteria-registry','criteria-view',false]]){
    const table=nodes.get(list).children[0];const parent=body?table.children[1]:table;
    const row=parent.children[body?0:1];const button=row.children.at(-1).children.find(item=>item.textContent==='View');
    button.onclick();assert.ok(row.nextSibling,id);assert.equal(row.nextSibling.children[0].children[0],nodes.get(id),id);
    button.onclick();assert.equal(nodes.get(id).hidden,true,id);
  }
});


test('SSH Host View uses compact label-value fields instead of multiline inputs',()=>{
  const {nodes,context}=workspace([]);
  vm.runInContext("handleViewHost({name:'Oracle',host:'132.145.80.109',port:22,username:'root',keyPath:'/data/ssh-keys/My Key/private_key'})",context);
  const fields=nodes.get('ssh-host-view').children[1];
  assert.equal(fields.className,'view-details ssh-host-details');
  assert.deepEqual(fields.children.map(field=>field.children[0].textContent),['Host','Port','SSH User','SSH Key Path']);
  assert.deepEqual(fields.children.map(field=>field.children[1].textContent),['132.145.80.109','22','root','/data/ssh-keys/My Key/private_key']);
  assert.ok(fields.children.every(field=>field.children[1].value===''));
  const html=readFileSync(new URL('../public/index.html',import.meta.url),'utf8');
  assert.ok(!html.includes('repeating 30 seconds after each pass'));
});

test('Source Criteria Action SSH Key SSH Host and Task Views share compact detail styling',()=>{
  const {nodes,context}=workspace([]);
  vm.runInContext(`
    handleViewConfiguration('source-view','Input',[['Name','Input'],['Path / Pattern','/input']]);
    handleViewConfiguration('criteria-view','General',[['Name','General'],['Decision Instructions','Use observed evidence.']]);
    handleViewConfiguration('action-view','Notify',[['Name','Notify'],['Python Code','print(1)\\nprint(2)']]);
    handleViewKey({id:'key-Key',name:'Key',privatePath:'/private',publicPath:'/public',publicKey:'ssh-ed25519 PUBLIC'});
    handleViewHost({name:'Host',host:'example',port:22,username:'reader',keyPath:'/private'});
    registeredSources=[{id:'input',name:'Input',type:'local',path:'/input'}];
    handleViewTask({name:'Task',mode:'batch',sources:[{sourceId:'input',profile:'4e6d5417-611e-49e0-8e23-2444a0f49ee4',chunkEvents:1}]});
  `,context);
  for(const id of ['source-view','criteria-view','action-view','ssh-key-view','ssh-host-view']){
    const fields=nodes.get(id).children[1];assert.ok(fields.className.includes('view-details'),id);
    assert.ok(fields.children.every(field=>field.children.length===2),id);
  }
  assert.equal(nodes.get('action-view').children.find(node=>node.className?.includes('view-details')).children[1].children[1].textContent,'print(1)\nprint(2)');
  assert.equal(nodes.get('action-view').children.find(node=>node.className?.includes('view-details')).children[1].children[1].className,'view-value-code');
  assert.equal(nodes.get('ssh-key-view').children[1].children[3].children[1].textContent,'****');
  assert.ok(nodes.get('task-view').children[0].children[1].children[0].children[0].className.includes('view-details'));
});

test('Python coloring preserves source text and treats code as inert text',()=>{
  const {context}=workspace([]);
  const source='@decorator\nasync def notify(value):\n    # import is a comment\n    text = "<script>alert(1)</script>"\n    block = """class text\nline two"""\n    return print(0xFF, 3.14, True)\n';
  context.pythonSource=source;
  const tokens=vm.runInContext("(()=>{const node=element('code','');highlightPython(node,pythonSource);return node.children.map(span=>({text:span.textContent,kind:span.className}));})()",context);
  assert.equal(tokens.map(token=>token.text).join(''),source);
  for(const [text,kind] of [['async','keyword'],['notify','function'],['# import is a comment','comment'],['"<script>alert(1)</script>"','string'],['0xFF','number'],['print','keyword']]){
    assert.ok(tokens.some(token=>token.text===text && token.kind.split(' ').includes(kind)),text);
  }
});

test('Python editor recolors without changing input text or selection and synchronizes scrolling',()=>{
  const {context,nodes}=workspace([]);
  vm.runInContext("registeredActions=[{id:'Notify',name:'Notify',code:'print(1)'}];handleEditAction(0)",context);
  const label=nodes.get('action-editor').children[0].children[3];
  const input=label.children[0],backdrop=label.children[1],code=backdrop.children[0];
  input.value='if True:\n    print("updated")';input.selectionStart=4;input.selectionEnd=4;input.oninput();
  assert.equal(code.children.map(token=>token.textContent).join(''),input.value);
  assert.equal(input.selectionStart,4);assert.equal(input.selectionEnd,4);
  assert.equal(backdrop.attributes['aria-hidden'],'true');
  code.style={};input.scrollLeft=24;input.scrollTop=48;input.onscroll();
  assert.equal(code.style.transform,'translate(-24px, -48px)');
  assert.equal(vm.runInContext('actionRows[0].code.value',context),input.value);
});

test('Vendored Prism handles nested Python f-string tokens without changing source',()=>{
  const {context}=workspace([]);
  context.pythonSource='result = f"value: {len(items) + 1!r}"\n';
  const result=vm.runInContext("(()=>{const node=element('code','');highlightPython(node,pythonSource);const classes=[];const walk=node=>{classes.push(node.className);node.children.forEach(walk);};walk(node);return {text:node.children.map(token=>token.textContent).join(''),classes};})()",context);
  assert.equal(result.text,context.pythonSource);
  assert.ok(result.classes.includes('token string-interpolation'));
  assert.ok(result.classes.includes('token builtin'));
  const html=readFileSync(new URL('../public/index.html',import.meta.url),'utf8');
  assert.ok(html.indexOf('/vendor/prism/prism-python-1.30.0.min.js')<html.indexOf('src="/app.js"'));
  assert.match(html,/prism-python-1\.30\.0\.min\.js" data-manual/);
  const app=readFileSync(new URL('../public/app.js',import.meta.url),'utf8');
  assert.ok(!app.includes('const pythonKeywords'));
});

test('Code View and editor use the same programming font stack',()=>{
  const css=readFileSync(new URL('../public/style.css',import.meta.url),'utf8');
  assert.match(css,/--code-font:\s*Consolas,/);
  assert.match(css,/\.view-value-code, \.view-value-key \{ font-family: var\(--code-font\)/);
  assert.match(css,/\.python-highlight \{[^}]*font: 13px\/1\.5 var\(--code-font\)/);
  assert.ok(!css.includes('ui-monospace, monospace'));
});

test('Criteria View uses compact full-width rows for instructions and category descriptions',()=>{
  const {context,nodes}=workspace([]);
  vm.runInContext("criteriaProfiles={[sampleProfileIds.application]:profileFixture('Application','Distinguish retries from final failures.',{normal:'Successful operation.',warning:'Recoverable issue.',error:'Final failure.',security:'Unauthorized action.',other:'Insufficient context.'})};handleViewCriteria('617706a3-c4ee-426f-81cf-7f5d80ecf67a')",context);
  const fields=nodes.get('criteria-view').children.find(node=>node.className?.includes('view-details'));
  assert.ok(fields.className.includes('criteria-details'));
  assert.deepEqual(fields.children.map(field=>field.children[0].textContent),['Name','Criteria ID','Decision Instructions','Default Chart Decision','Category (Choice)','Urgency (Score)','Work Ticket (Noul)']);
  const css=readFileSync(new URL('../public/style.css',import.meta.url),'utf8');
  assert.match(css,/\.criteria-details > div:nth-child\(n\+3\) \{ grid-column: 1 \/ -1;/);
});

test('Selecting a Task without history clears another Task results and statistics',async()=>{
  const {context,nodes}=workspace([]);
  await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext("registeredTasks=[{id:'idle',name:'Never Run',mode:'batch',sources:[]}];results=[{log:'old',category:'normal',elapsedMs:1}];completed=1;completionOrder=[0];render();renderTaskMonitor();",context);
  await nodes.get('running-tasks').children[0].onclick();
  assert.equal(vm.runInContext('results.length',context),0);
  assert.equal(vm.runInContext('completed',context),0);
  assert.equal(nodes.get('result-context').children[0].textContent,'Never Run');
  assert.equal(nodes.get('message').textContent,'No executions yet.');
});


test('Task availability switch reflects disabled state and blocks Run',()=>{
  const {nodes,context}=workspace([]);
  vm.runInContext('registeredTasks[0].enabled=false;renderTasks()',context);
  const row=nodes.get('task-list').children[0].children[1];
  const toggle=row.children[1].children[0];
  assert.equal(toggle.attributes.role,'switch');
  assert.equal(toggle.attributes['aria-checked'],'false');
  assert.equal(row.children.at(-1).children[0].disabled,true);
  vm.runInContext('registeredTasks[0].enabled=true;renderTasks()',context);
  assert.equal(nodes.get('task-list').children[0].children[1].children[1].children[0].attributes['aria-checked'],'true');
});


test('Shared messages show errors in red and clear the error state on success',()=>{
  const {nodes,context}=workspace([]);
  for(const id of ['task-message','source-message','criteria-message','action-message','ssh-key-message','ssh-host-message','results-settings-message','message']) {
    vm.runInContext(`handleMessage('${id}','Failed',true)`,context);
    assert.match(nodes.get(id).className,/error-message/);
    vm.runInContext(`handleMessage('${id}','Saved')`,context);
    assert.doesNotMatch(nodes.get(id).className,/error-message/);
    assert.equal(nodes.get(id).textContent,'Saved');
  }
});

test('Unavailable Task toggle endpoint displays a readable error',async()=>{
  const {nodes,context}=workspace([]);
  vm.runInContext("fetch=async()=>({status:405});",context);
  await vm.runInContext("handleToggleTask(registeredTasks[0],{disabled:false})",context);
  assert.match(nodes.get('task-message').textContent,/Restart the DeciFlow/);
  assert.match(nodes.get('task-message').className,/error-message/);
});


test('SSH Host selector stays visible without a disclosure control',()=>{
  const {context}=workspace([]);
  const picker=vm.runInContext("hostPicker({hostIds:[]},()=>{})",context);
  assert.equal(picker.children[0].className,'host-picker-title');
  assert.equal(picker.children[1].type,'search');
  assert.equal(picker.children[0].onclick,undefined);
});


test('Task Monitor labels Source, type and optional Action without Host details',()=>{
  const {nodes,context}=workspace([]);
  vm.runInContext(`registeredSources=[{id:'remote',name:'System Logs',type:'ssh'}];sshHosts=[{id:'host',name:'Oracle'}];registeredActions=[{id:'ElasticSearch',name:'ElasticSearch'},{id:'Notify',name:'Notify'}];registeredTasks=[{id:'monitor',name:'Monitor',mode:'realtime',enabled:true,sources:[{sourceId:'remote',hostIds:['host'],actionId:'ElasticSearch'}],latestRun:{state:'stopped',counts:{completed:125,failed:2}}}];renderTaskMonitor()`,context);
  const card=nodes.get('running-tasks').children[0];
  assert.equal(card.children.length,4);
  assert.deepEqual(card.children[1].children.map(node=>node.textContent),['Enabled','Stopped']);
  assert.equal(card.children[2].textContent,'Source: System Logs · Source Hosts: 1');
  assert.equal(card.children[3].textContent,'Type: Remote File (SSH) / Mode: Realtime / Action: ElasticSearch');
  card.getBoundingClientRect=()=>({left:20,top:20,bottom:100});
  card.onfocus();
  assert.match(nodes.get('task-monitor-tooltip').children[2].textContent,/Source Hosts \(1\):\nOracle/);
  assert.equal(nodes.get('task-monitor-tooltip').hidden,false);
  card.onkeydown({key:'Escape'});
  assert.equal(nodes.get('task-monitor-tooltip').hidden,true);
  assert.doesNotMatch(card.children[3].textContent,/Oracle|Host:/);
  vm.runInContext("registeredSources=[{id:'local',name:'DeciFlow',type:'local'}];registeredTasks[0].sources=[{sourceId:'local',actionId:''}];renderTaskMonitor()",context);
  assert.equal(nodes.get('running-tasks').children[0].children[2].textContent,'Source: DeciFlow · Source Hosts: 1');
  assert.equal(nodes.get('running-tasks').children[0].children[3].textContent,'Type: Local File / Mode: Realtime / Action: None');
});


test('Monitor availability and execution state use shared badge styling',()=>{
  const css=readFileSync(new URL('../public/style.css',import.meta.url),'utf8');
  assert.match(css,/\.task-state\.idle\s*\{\s*color: #7c3aed/);
  assert.match(css,/\.monitor-state, \.monitor-availability\s*\{[^}]*height: 20px;[^}]*background: #e7ece9/);
  const {nodes,context}=workspace([]);
  vm.runInContext('renderTaskMonitor()',context);
  const status=nodes.get('running-tasks').children[0].children[1];
  assert.equal(status.children[0].className,'monitor-availability enabled');
  assert.equal(status.children[1].className,'task-state monitor-state idle');
});


test('Task Monitor card surface follows execution state independently of selection',()=>{
  const {nodes,context}=workspace([]);
  vm.runInContext(`registeredTasks=[{id:'active',name:'Active',mode:'realtime',activeRun:{}},{id:'stopped',name:'Stopped',mode:'realtime',latestRun:{state:'stopped'}}];selectedTaskId='stopped';renderTaskMonitor()`,context);
  const cards=nodes.get('running-tasks').children;
  assert.match(cards[0].className,/monitor-card-running/);
  assert.match(cards[1].className,/monitor-card-stopped/);
  assert.equal(cards[1].attributes['aria-pressed'],'true');
});


test('Source editor accepts multiple paths in one multiline field',async()=>{
  const {context}=workspace([]);
  await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext('handleEditSource(0)',context);
  assert.equal(vm.runInContext('sourceFields.path.rows',context),3);
  vm.runInContext("sourceFields.path.value='/logs/*.log\\n/logs/*.txt'",context);
  assert.equal(vm.runInContext('sourceFields.path.value',context),'/logs/*.log\n/logs/*.txt');
});


test('Monitor counts distinct Source Hosts while tooltip includes all assignments',()=>{
  const {nodes,context}=workspace([]);
  vm.runInContext(`registeredSources=[{id:'one',name:'Application',type:'ssh',path:'/var/log/app.log'},{id:'two',name:'System',type:'ssh',path:'/var/log/messages'}];sshHosts=[{id:'a',name:'Alpha',host:'alpha.example',username:'reader',port:22},{id:'b',name:'Beta',host:'beta.example',username:'logs',port:2222}];registeredActions=[{id:'ElasticSearch',name:'ElasticSearch'},{id:'Notify',name:'Notify'}];registeredTasks=[{id:'monitor',name:'Fleet',mode:'batch',enabled:true,sources:[{sourceId:'one',hostIds:['a','b'],actionId:'Notify',profile:'4e6d5417-611e-49e0-8e23-2444a0f49ee4',chunkEvents:2},{sourceId:'two',hostIds:['a'],actionId:''}]}];renderTaskMonitor()`,context);
  const card=nodes.get('running-tasks').children[0];
  assert.equal(card.children[2].textContent,'Source: Application, System · Source Hosts: 2');
  assert.doesNotMatch(card.children[2].textContent,/Alpha|Beta/);
  card.getBoundingClientRect=()=>({left:10,top:10,bottom:90});
  card.onfocus();
  const tooltip=nodes.get('task-monitor-tooltip');
  const text=tooltip.children.map(child=>child.textContent).join('\n');
  for(const part of ['Application','System','Alpha · reader@alpha.example:22','Beta · logs@beta.example:2222','/var/log/app.log','Action: Notify','Action: None'])assert.ok(text.includes(part));
  card.onblur();assert.equal(tooltip.hidden,true);
});


test('Reviewed export downloads only corrected categories through its own DB endpoint',()=>{
  const {nodes,context}=workspace([]);
  let action;
  context.document.body={append(){}};
  const create=context.document.createElement;
  context.document.createElement=()=>{const node=create();node.submit=()=>{action=node.action;};return node;};
  vm.runInContext("pagedView={};activeJobId='review-run';completed=1",context);
  nodes.get('export-reviewed').onclick();
  assert.equal(action,'/api/jobs/review-run/export-reviewed');
  nodes.get('export').onclick();
  assert.equal(action,'/api/jobs/review-run/export');
});


test('Task tooltip waits for one stationary second and stays open during movement',()=>{
  const {nodes,context}=workspace([]);
  let now=0,next=0;const timers=new Map();
  context.setTimeout=(callback,delay)=>{const id=++next;timers.set(id,{callback,due:now+delay});return id;};
  context.clearTimeout=id=>timers.delete(id);
  const advance=ms=>{now+=ms;for(const [id,timer] of [...timers])if(timer.due<=now){timers.delete(id);timer.callback();}};
  vm.runInContext('renderTaskMonitor()',context);
  const card=nodes.get('running-tasks').children[0],tip=nodes.get('task-monitor-tooltip');
  card.getBoundingClientRect=()=>({left:10,top:10,bottom:90});
  card.onmouseenter();assert.equal(tip.hidden,true);
  advance(500);assert.equal(tip.hidden,true);
  card.onmousemove();advance(999);assert.equal(tip.hidden,true);
  advance(1);assert.equal(tip.hidden,false);
  card.onmousemove();assert.equal(tip.hidden,false);
  advance(1000);assert.equal(tip.hidden,false);
  card.onmouseleave();tip.onmouseenter();advance(500);
  assert.equal(tip.hidden,false);
  card.onmouseenter();assert.equal(tip.hidden,false);
  tip.matches=selector=>selector===':hover';card.onblur();
  assert.equal(tip.hidden,false);
  tip.onmouseleave();advance(200);assert.equal(tip.hidden,true);
  card.onmouseenter();advance(500);card.onmouseleave();advance(2500);
  assert.equal(tip.hidden,true);
  card.onmouseenter();card.onkeydown({key:'Escape'});advance(2000);
  assert.equal(tip.hidden,true);
  card.onfocus();assert.equal(tip.hidden,false);
});


test('Configuration reset uses the styled destructive confirmation and Cancel sends nothing',async()=>{
  const {nodes,context}=workspace([]);
  let resets=0;
  context.fetch=async(path)=>{
    if(path==='/api/reset')resets++;
    return {ok:true,json:async()=>({dataDirectory:'/tmp/test-data',instanceId:'before',resetting:false})};
  };
  await vm.runInContext('handleLoadResetStatus()',context);
  assert.equal(nodes.get('reset-deciflow').disabled,false);
  context.document.getElementById('reset-dialog').showModal=function(){this.returnValue='cancel';this.onclose();};
  await nodes.get('reset-deciflow').onclick();
  assert.equal(resets,0);
  assert.equal(nodes.get('reset-confirm-directory').textContent,'/tmp/test-data');
  vm.runInContext("handleNavigation('settings','configuration')",context);
  assert.equal(nodes.get('settings-configuration').hidden,false);
  assert.equal(nodes.get('settings-ssh-hosts').hidden,true);
  const html=readFileSync(new URL('../public/index.html',import.meta.url),'utf8');
  assert.match(html,/This permanently deletes all DeciFlow application data/);
  assert.match(html,/Yes, Reset DeciFlow/);
});


test('Confirmed reset submits once and reloads only after a new server instance returns',async()=>{
  const {nodes,context}=workspace([]);await new Promise(resolve=>setImmediate(resolve));
  let accepted=false,reloaded=false,requests=0;
  context.fetch=async(path,options)=>{
    if(path==='/api/reset'){
      requests++;assert.equal(JSON.parse(options.body).confirmation,'RESET DECIFLOW');accepted=true;
      return {ok:true,json:async()=>({instanceId:'before',resetting:true})};
    }
    return {ok:true,json:async()=>({instanceId:accepted?'after':'before',dataDirectory:'/tmp/test-data',resetting:false})};
  };
  context.setTimeout=callback=>{callback();return 1;};
  context.location={reload(){reloaded=true;}};
  await vm.runInContext('handleLoadResetStatus()',context);
  context.document.getElementById('reset-dialog').showModal=function(){this.returnValue='reset';this.onclose();};
  await nodes.get('reset-deciflow').onclick();
  assert.equal(requests,1);assert.equal(reloaded,true);
});

test('Clone Criteria opens an unsaved Add Profile draft and preserves source metadata', async () => {
  const criteria = Object.fromEntries(['normal', 'warning', 'error', 'security', 'other'].map(key => [key, `${key} definition`]));
  const profiles = { [sampleProfileIds.general]: profileFixture('General','Default',criteria), custom: { ...profileFixture('Authentication','Inspect authentication',criteria), normalization: 'single_line_syslog_header' } };
  const { nodes, context } = workspace([], undefined, undefined, profiles);
  await new Promise(resolve => setImmediate(resolve));
  await nodes.get('nav-criteria').onclick();
  nodes.get('criteria-registry').children[0].children[1].children.at(-1).children[2].onclick();
  assert.equal(nodes.get('criteria-editor').children[0].children[0].textContent, 'Add Profile');
  assert.match(vm.runInContext('criteriaDraftId', context), /^[0-9a-f-]{36}$/);
  assert.equal(vm.runInContext('criteriaFields.id', context), undefined);
  assert.equal(vm.runInContext('criteriaFields.label.value', context), 'Authentication (Clone)');
  assert.equal(vm.runInContext('criteriaFields.instructions.value', context), profiles.custom.instructions);
  for (const key of Object.keys(criteria)) assert.equal(vm.runInContext(`decisionRows[0].options.find(option=>option.key.value==='${key}').text.value`, context), criteria[key]);
  assert.equal(vm.runInContext('Object.keys(criteriaProfiles).length', context), 2);
  nodes.get('cancel-criteria').onclick();
  criteriaRow(nodes, 'General').children.at(-1).children[2].onclick();
  assert.equal(vm.runInContext('criteriaFields.label.value', context), 'General (Clone)');
  nodes.get('cancel-criteria').onclick();
  vm.runInContext("handleCloneCriteria('custom'); decisionRows[0].options[0].text.value='Edited definition';", context);
  const cloneId = vm.runInContext('criteriaDraftId', context);
  let saved;
  context.fetch = async (_path, options) => { saved = JSON.parse(options.body); return { ok: true, json: async () => ({ profiles: saved }) }; };
  await nodes.get('save-criteria').onclick();
  assert.equal(saved[cloneId].normalization, profiles.custom.normalization);
  assert.equal(saved[cloneId].label, 'Authentication (Clone)');
  assert.equal(saved[cloneId].questions.category.criteria.normal, 'Edited definition');
  assert.deepEqual(saved.custom, profiles.custom);
  assert.equal(nodes.get('criteria-editor').hidden, true);
});


test('Criteria UUIDs stay internal, independent of Name and stable across edits', async () => {
  const criteria = Object.fromEntries(['normal', 'warning', 'error', 'security', 'other'].map(key => [key, key]));
  const { nodes, context } = workspace([], undefined, undefined, { [sampleProfileIds.general]: profileFixture('General','Default',criteria) });
  await nodes.get('nav-criteria').onclick();
  nodes.get('add-criteria').onclick();
  const first = vm.runInContext('criteriaDraftId', context);
  assert.match(first, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  assert.equal(vm.runInContext('criteriaFields.id', context), undefined);
  vm.runInContext("criteriaFields.label.value='한글 123'; criteriaFields.label.oninput();", context);
  assert.equal(nodes.get('save-criteria').disabled, false);
  assert.equal(vm.runInContext('criteriaDraftId', context), first);
  nodes.get('cancel-criteria').onclick(); nodes.get('add-criteria').onclick();
  assert.notEqual(vm.runInContext('criteriaDraftId', context), first);
  nodes.get('cancel-criteria').onclick();
  vm.runInContext("handleEditCriteria('4e6d5417-611e-49e0-8e23-2444a0f49ee4'); criteriaFields.label.value='Renamed'; criteriaFields.label.oninput();", context);
  assert.equal(vm.runInContext('criteriaDraftId', context), '4e6d5417-611e-49e0-8e23-2444a0f49ee4');
});

test('Repeated Criteria clones report duplicate names immediately without losing the draft', async () => {
  const criteria = Object.fromEntries(['normal', 'warning', 'error', 'security', 'other'].map(key => [key, key]));
  const profiles = { [sampleProfileIds.general]: profileFixture('General','Default',criteria), general_clone: profileFixture('General (Clone)','Copy',criteria) };
  const { nodes, context } = workspace([], undefined, undefined, profiles);
  await nodes.get('nav-criteria').onclick();
  vm.runInContext("handleCloneCriteria('4e6d5417-611e-49e0-8e23-2444a0f49ee4'); criteriaFields.instructions.value='Important draft';", context);
  assert.match(nodes.get('criteria-message').textContent, /Name already exists/);
  assert.match(nodes.get('criteria-message').className, /error-message/);
  assert.equal(nodes.get('save-criteria').disabled, true);
  await nodes.get('save-criteria').onclick();
  assert.equal(vm.runInContext('criteriaFields.instructions.value', context), 'Important draft');
  vm.runInContext("criteriaFields.label.value='General (Clone) 2'; criteriaFields.label.oninput();", context);
  assert.equal(nodes.get('save-criteria').disabled, false);
  assert.equal(nodes.get('criteria-message').textContent, '');
  assert.equal(vm.runInContext('criteriaFields.id', context), undefined);
});


test('Legacy Results route opens Configuration and Results is absent from Settings navigation', () => {
  const navigation = {hash:'#settings/results'};
  const {nodes}=workspace([], undefined, undefined, undefined, navigation);
  assert.equal(nodes.get('settings-title').textContent,'Configurations');
  assert.equal(nodes.get('settings-configuration').hidden,false);
  assert.equal(navigation.hash,'#settings/configuration');
  const html=readFileSync(new URL('../public/index.html',import.meta.url),'utf8');
  assert.ok(!html.includes('id="nav-results-settings"'));
  assert.ok(!html.includes('id="settings-results"'));
  assert.ok(html.indexOf('id="settings-configuration"')<html.indexOf('id="results-settings-form"'));
  assert.ok(html.indexOf('id="results-settings-form"')<html.indexOf('id="reset-deciflow"'));
  assert.ok(html.indexOf('id="reset-deciflow"')<html.indexOf('id="save-results-settings"'));
  assert.ok(html.indexOf('id="save-results-settings"')<html.indexOf('</form>',html.indexOf('id="results-settings-form"')));
  assert.match(html, /id="reset-deciflow"[^>]*type="button"/);
});


test('SSH Key Edit renames UUID metadata without sending key material or changing host selection', async () => {
  const {nodes,context}=workspace([]);
  await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext("sshKeys=[{id:'key-uuid',name:'Original',privatePath:'/keys/key-uuid/private_key',publicPath:'/keys/key-uuid/public_key.pub',publicKey:'PUBLIC'}];sshHosts=[{id:'host-uuid',name:'Remote',host:'example',port:22,username:'reader',keyId:'key-uuid',keyPath:'/keys/key-uuid/private_key'}];renderSSHKeys();",context);
  const controls=nodes.get('ssh-key-list').children[0].children[1].children[0].children[2];
  controls.children[1].onclick();
  assert.equal(nodes.get('add-ssh-key-title').textContent,'Edit SSH Key');
  assert.equal(nodes.get('ssh-key-material').hidden,true);
  assert.equal(nodes.get('ssh-key-name').value,'Original');
  nodes.get('ssh-key-name').value='Renamed';
  let body;
  context.fetch=async(path,options)=>{
    assert.equal(path,'/api/ssh-keys');assert.equal(options.method,'PATCH');
    body=JSON.parse(options.body);
    return {ok:true,json:async()=>({keys:[{id:'key-uuid',name:'Renamed',privatePath:'/keys/key-uuid/private_key',publicPath:'/keys/key-uuid/public_key.pub',publicKey:'PUBLIC'}]})};
  };
  await nodes.get('ssh-key-form').onsubmit({preventDefault(){}});
  assert.deepEqual(body,{id:'key-uuid',name:'Renamed'});
  assert.equal(nodes.get('ssh-key-editor').hidden,true);
  assert.equal(nodes.get('ssh-host-list').children[0].children[1].children[0].children[2].textContent,'Renamed');
  vm.runInContext('handleEditHost(sshHosts[0])',context);
  assert.equal(nodes.get('ssh-host-key').value,'key-uuid');
  assert.equal(nodes.get('ssh-host-key').children[0].text,'Renamed');
});


test('Action rename refreshes monitor labels while Tasks keep their UUID assignment', async () => {
  const {nodes,context}=workspace([]);
  await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext("registeredActions=[{id:'action-uuid',name:'Original',pythonVersion:'3.12',modules:[],code:'pass'}];registeredTasks=[{id:'task-uuid',name:'Analysis',mode:'batch',sources:[{sourceId:sampleSources[0].id,actionId:'action-uuid'}]}];handleEditAction(0);actionRows[0].name.value='Renamed';",context);
  context.fetch=async(path,options)=>({ok:true,json:async()=>({actions:JSON.parse(options.body)})});
  await nodes.get('save-actions').onclick();
  assert.equal(vm.runInContext('registeredActions[0].id',context),'action-uuid');
  assert.equal(vm.runInContext('registeredTasks[0].sources[0].actionId',context),'action-uuid');
  assert.match(nodes.get('running-tasks').children[0].children[3].textContent,/Action: Renamed/);
});


test('SSH connection status distinguishes key UUIDs and ignores display renames', async () => {
  const {context}=workspace([]);
  await new Promise(resolve=>setImmediate(resolve));
  const keys=vm.runInContext(`(() => {
    const host={host:'logs.example',port:22,username:'reader',keyId:'first'};
    return [hostConnectionKey(host),hostConnectionKey({...host,name:'Renamed'}),
      hostConnectionKey({...host,keyId:'second'}),
      hostConnectionKey({...host,keyPath:'/keys/first/private_key'})];
  })()`,context);
  assert.equal(keys[0],keys[1]);
  assert.notEqual(keys[0],keys[2]);
  assert.equal(keys[0],keys[3]);
});

test('JSONL Source format requires a content field and fixes Task chunk size at one',async()=>{
  const {context,nodes}=workspace([]);
  await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext("handleEditSource(registeredSources.length)",context);
  assert.equal(vm.runInContext('sourceFields.contentField.parentElement.hidden',context),true);
  vm.runInContext("sourceFields.format.value='jsonl';sourceFields.format.onchange();sourceFields.contentField.value='consulting_content';sourceFields.name.value='VOC';sourceFields.path.value='/host-logs/sample-logs/voc-asia-culture-center-consulting-qna.jsonl'",context);
  assert.equal(vm.runInContext('sourceFields.contentField.parentElement.hidden',context),false);
  await nodes.get('save-sources').onclick();
  assert.equal(vm.runInContext('registeredSources.at(-1).format',context),'jsonl');
  vm.runInContext("updateSourceSettings([registeredSources.at(-1).id]);",context);
  assert.equal(vm.runInContext('sourceRows[0].size.disabled',context),true);
  assert.equal(vm.runInContext('sourceRows[0].size.value',context),'1');
  vm.runInContext("sourceRows[0].name.value=registeredSources[0].id;sourceRows[0].name.onchange()",context);
  assert.equal(vm.runInContext('sourceRows[0].size.disabled',context),false);
});

test('All ten mixed decisions appear equally and can be filtered and reviewed',async()=>{
  const event=result(0,false),definitions={},answers={};
  for(let i=0;i<10;i++) {
    const type=i<2?'choice':i<5?'score':'noul';
    definitions[`q${i}`]={label:`Decision ${i}`,type,instructions:'Use observed evidence.',...(type==='choice'?{criteria:{pending:'Pending.',done:'Done.'}}:type==='score'?{criteria:['Low','High']}:{})};
    answers[`q${i}`]=type==='choice'?{choice:'pending',confidence:1,probabilities:{pending:1,done:0}}:type==='score'?{score:.25,probabilities:{0:.75,1:.25}}:{noul:.8};
  }
  Object.assign(event.result,{inputFormat:'jsonl',category:'pending',criteriaGroup:'voc',defaultDecision:'q0',profileLabel:'VOC',decisionDefinitions:definitions,decisions:answers});
  const {context,nodes}=workspace([event]);await runTask(nodes);
  const row=nodes.get('results').children[0];assert.equal(decisionCards(row).length,10);
  assert.equal(row.children[0].children.some(child=>child.className==='all-decisions'),false);
  assert.deepEqual(decisionCards(row).map(card=>card.children[0].textContent),Array.from({length:10},(_,i)=>`Decision ${i} (${i<2?'Choice':i<5?'Score':'Noul'})`));
  assert.equal(row.children[1].className,'original-input');
  assert.equal(row.children[1].children[0].textContent,'Input');
  showDecisions(context,['voc:q0']);
  assert.equal(decisionCards(nodes.get('results').children[0]).length,1);
  const reviews=row.children.at(-2).children[1];assert.equal(reviews.children.length,10);
  const input=reviews.children[5].children[0];input.value='0.2';await input.onchange();
  assert.equal(vm.runInContext('results[0].reviewerDecisions.q5',context),.2);
  assert.equal(vm.runInContext('results[0].decisions.q5.noul',context),.8);
  assert.equal(vm.runInContext('hasReviewerChange(results[0])',context),true);

});

test('Criteria editor adds, reorders and saves typed decisions without editing templates',async()=>{
  const criteria={[sampleProfileIds.general]:profileFixture('General','Default',{normal:'Normal',warning:'Warning',error:'Error',security:'Security',other:'Other'})};
  const {context,nodes}=workspace([],undefined,undefined,criteria);await nodes.get('nav-criteria').onclick();
  nodes.get('add-criteria').onclick();
  vm.runInContext("criteriaFields.label.value='Customer Review';criteriaFields.label.oninput()",context);
  nodes.get('criteria-editor').children.at(-1).onclick();
  vm.runInContext("decisionRows[1].label.value='Follow-up';decisionRows[1].instructions.value='Is follow-up required?';decisionRows[1].type.value='noul';decisionRows[1].type.onchange();decisionRows[1].panel.children.at(-1).children[0].onclick()",context);
  assert.equal(vm.runInContext('decisionRows[0].type.value',context),'noul');
  await nodes.get('save-criteria').onclick();
  assert.equal(vm.runInContext("Object.values(criteriaProfiles).find(p=>p.label==='Customer Review').questions.decision_2.type",context),'noul');
  assert.deepEqual(JSON.parse(vm.runInContext('JSON.stringify(criteriaProfiles[sampleProfileIds.general].questions)',context)),criteria[sampleProfileIds.general].questions);
});

for(const engine of ['laya','jev']) {
  test(`${engine} screenshot metrics separate request time, Action time and active throughput`,async()=>{
    const durations=[299,270,183,214],arrivals=[18319,24444,28936,37917];
    const events=[{type:'start',engine,total:null},...durations.map((duration,index)=>{
      const item=result(index,false);item.elapsedMs=arrivals[index];item.result.elapsedMs=duration;
      item.result.actionExecution={name:'Elasticsearch',status:'success',elapsedMs:[716,462,308,357][index]};return item;
    }),{type:'timing',elapsedMs:55000,activeProcessingMs:966}];
    const {context,nodes}=workspace(events);await runTask(nodes);
    assert.equal(elapsedValues(nodes)[0],'55 sec');
    assert.equal(elapsedValues(nodes)[1],'966 ms (1.8%)');
    assert.equal(processingValues(nodes).Avg,'241.5 ms');
    assert.equal(nodes.get('summary').children[2].children[0].textContent,'4.141 chunks/s');
    vm.runInContext('elapsedMs=40000;render()',context);
    assert.equal(nodes.get('summary').children[2].children[0].textContent,'4.141 chunks/s');
  });
}

test('Paged metrics use whole-run counts and server percentiles independently of visible rows',()=>{
  const {nodes,context}=workspace([]);
  vm.runInContext(`
    results=[{log:'visible',category:'normal',elapsedMs:9999}];completionOrder=[0];completed=100;
    elapsedMs=10000;activeProcessingMs=10000;
    const stats=updateResultStatistics(false);
    pagedView={summary:{...stats,total:100,failed:5,processingMs:20000,
      processingPercentiles:{minMs:12,maxMs:700,medianMs:180,p95Ms:300,p99Ms:500}},snapshotTotal:100,hasNext:false};
    render();
  `,context);
  const metric=index=>index>=5 && index<=8?processingValues(nodes)[['Avg','P(50)','P(95)','P(99)'][index-5]]:nodes.get('summary').children[index===9?2:index].children[0].textContent;
  assert.equal(processingValues(nodes).Min,'12 ms');assert.equal(processingValues(nodes).Max,'700 ms');
  assert.equal(metric(5),'200 ms');assert.equal(metric(6),'180 ms');
  assert.equal(metric(7),'300 ms');assert.equal(metric(8),'500 ms');assert.equal(metric(9),'9.500 chunks/s');
  nodes.get('review-filter').value='needs-review';vm.runInContext('render()',context);
  assert.equal(metric(5),'200 ms');assert.equal(metric(9),'9.500 chunks/s');
  vm.runInContext('elapsedMs=20000;render()',context);assert.equal(metric(9),'9.500 chunks/s');
  vm.runInContext('elapsedMs=100000000;activeProcessingMs=100000000;render()',context);assert.equal(metric(9),'<0.001 chunks/s');
});

for(const values of [[],[7],[183,214,270,299],Array.from({length:100},(_,i)=>i+1)]) {
  test(`Whole-run latency percentiles for ${values.length} records include failures and ignore Action time`,()=>{
    const {nodes,context}=workspace([]);
    context.durations=values;
    vm.runInContext(`results=durations.map((elapsedMs,index)=>({log:'case '+index,category:'normal',elapsedMs,...(index===durations.length-1?{error:'failed'}:{}),actionExecution:{status:'success',elapsedMs:5000}}));completionOrder=results.map((_,index)=>index);completed=results.length;render()`,context);
    const actual=index=>processingValues(nodes)[['P(50)','P(95)','P(99)'][index-6]];
    const sorted=[...values].sort((a,b)=>a-b),n=sorted.length;
    assert.equal(processingValues(nodes).Min,n?vm.runInContext(`formatDuration(${sorted[0]})`,context):'N/A');
    assert.equal(processingValues(nodes).Max,n?vm.runInContext(`formatDuration(${sorted[n-1]})`,context):'N/A');
    const median=n?(sorted[Math.floor((n-1)/2)]+sorted[Math.floor(n/2)])/2:null;
    for(const [index,value] of [[6,median],[7,n?sorted[Math.ceil(.95*n)-1]:null],[8,n?sorted[Math.ceil(.99*n)-1]:null]])assert.equal(actual(index),value===null?'N/A':vm.runInContext(`formatDuration(${value})`,context));
  });
}


test('Processing Time groups six small labels in one metric without separate percentile boxes',()=>{
  const {nodes,context}=workspace([]);
  vm.runInContext("results=[{log:'one',category:'normal',elapsedMs:200}];completionOrder=[0];completed=1;render()",context);
  const metrics=nodes.get('summary').children;
  assert.equal(metrics.length,6);
  assert.equal(metrics[5].textContent,'Processing Time');
  assert.equal(metrics[5].children[0].attributes['aria-label'],'Processing Time Statistics');
  assert.deepEqual(processingValues(nodes),{Avg:'200 ms',Min:'200 ms',Max:'200 ms','P(50)':'200 ms','P(95)':'200 ms','P(99)':'200 ms'});
  assert.equal(nodes.get('needs-review-count').textContent,'Needs Review: 0');
});


test('Source Hosts Detail builds many hosts only on demand and refreshes whole-run counts',()=>{
  const {nodes,context}=workspace([]);
  vm.runInContext(`
    runHosts=Array.from({length:200},(_,i)=>({hostId:'host-'+i,hostName:'Host '+String(i).padStart(3,'0'),collectionState:'reading'}));
    results=[{log:'record',hostId:'host-0',hostName:'Host 000',category:'normal',elapsedMs:2}];
    completionOrder=[0];completed=1;render();
  `,context);
  assert.equal(nodes.get('source-hosts-detail').disabled,false);
  assert.equal((nodes.get('source-hosts-rows')?.children.length || 0),0);
  nodes.get('source-hosts-dialog').showModal=()=>{nodes.get('source-hosts-dialog').open=true;};
  nodes.get('source-hosts-detail').onclick();
  const rows=nodes.get('source-hosts-rows');
  assert.equal(rows.children.length,200);
  assert.deepEqual(rows.children[0].children[2].children.map(node=>node.textContent),['1',' / ','0',' / ','1']);
  assert.deepEqual(rows.children[199].children[2].children.map(node=>node.textContent),['0',' / ','0',' / ','0']);
  nodes.get('host-filter').value='host-199';nodes.get('host-filter').onchange();
  assert.equal(rows.children.length,200);
  assert.deepEqual(rows.children[0].children[2].children.map(node=>node.textContent),['1',' / ','0',' / ','1']);
});


test('Score levels use a dedicated layout and keep added level IDs hidden',()=>{
  const {context}=workspace([]);
  context.consultationFixture=readProfileTemplate('consultation');
  vm.runInContext(`
    criteriaProfiles={[sampleProfileIds.general]:consultationFixture,[sampleProfileIds.consultation]:consultationFixture};
    handleEditCriteria('41bbe1dc-85cb-4ab0-ab79-cd7c4e6f8e72');
    const scoreRow=decisionRows.find(row=>row.type.value==='score');
    if(scoreRow.options.some(option=>!option.key.hidden))throw Error('Visible score ID');
    const scoreOptions=scoreRow.options[0].entry.parentElement;
    if(scoreOptions.attributes['data-type']!=='score')throw Error('Wrong score layout');
    scoreRow.panel.children.find(node=>node.textContent==='Add Option / Level').onclick();
    if(!scoreRow.options.at(-1).key.hidden)throw Error('New score ID visible');
    scoreRow.type.value='choice';scoreRow.type.onchange();
    if(scoreOptions.attributes['data-type']!=='choice' || scoreRow.options.some(option=>option.key.hidden))throw Error('Choice layout not restored');
  `,context);
});


test('Decision headers track names, types and positions through editor changes',()=>{
  const {context}=workspace([]);
  context.consultationFixture=readProfileTemplate('consultation');
  const headers=()=>JSON.parse(vm.runInContext('JSON.stringify(decisionRows.map(row=>row.legend.textContent))',context));
  vm.runInContext("criteriaProfiles={[sampleProfileIds.general]:consultationFixture,[sampleProfileIds.consultation]:consultationFixture};handleEditCriteria('41bbe1dc-85cb-4ab0-ab79-cd7c4e6f8e72')",context);
  assert.equal(headers()[0],'Decision 1 · 문의 유형 · Choice');
  assert.equal(headers()[3],'Decision 4 · 긴급도 · Score');
  vm.runInContext("decisionRows[0].label.value='Renamed';decisionRows[0].label.oninput();decisionRows[0].type.value='noul';decisionRows[0].type.onchange()",context);
  assert.equal(headers()[0],'Decision 1 · Renamed · Noul');
  vm.runInContext("decisionRows[0].panel.children.at(-1).children[1].onclick()",context);
  assert.equal(headers()[1],'Decision 2 · Renamed · Noul');
  vm.runInContext("decisionRows[0].panel.children.at(-1).children.at(-1).onclick()",context);
  assert.equal(headers()[0],'Decision 1 · Renamed · Noul');
  vm.runInContext("$('criteria-editor').children.at(-1).onclick()",context);
  assert.equal(headers().at(-1),'Decision 5 · decision_5 · Choice');
});


test('Profile settings and Decisions share the same section design',()=>{
  const {context,nodes}=workspace([]);
  vm.runInContext("criteriaProfiles={[sampleProfileIds.general]:profileFixture('General','Use evidence.',{normal:'Normal',warning:'Warning',error:'Error',security:'Security',other:'Other'})};handleEditCriteria('4e6d5417-611e-49e0-8e23-2444a0f49ee4')",context);
  const profile=nodes.get('criteria-editor').children.find(node=>node.className==='criteria-section profile-settings');
  assert.equal(profile.className,'criteria-section profile-settings');
  assert.equal(profile.children[0].textContent,'Profile Settings');
  assert.equal(profile.children[1].className,'view-details');
  assert.equal(profile.children[2].className,'action-registration');
  assert.equal(vm.runInContext("decisionRows.every(row=>row.panel.className.includes('criteria-section'))",context),true);
});


test('Custom classification colors differ by option and match result badges',()=>{
  const {context,nodes}=workspace([]);
  context.vocFixture=readProfileTemplate('consultation');
  vm.runInContext(`
    const definition=vocFixture.questions.inquiry_type;
    results=Object.keys(definition.criteria).map(choice=>({log:choice,category:choice,
      criteriaGroup:'voc',profileLabel:vocFixture.label,
      defaultDecision:'inquiry_type',decisionDefinitions:{inquiry_type:definition},
      decisions:{inquiry_type:{choice,probabilities:{[choice]:1}}},elapsedMs:1}));
    completionOrder=results.map((_,i)=>i);completed=results.length;render();
  `,context);
  const styles=nodes.get('category-chart').children.map(row=>row.children[1].children[0].attributes.style);
  assert.equal(new Set(styles).size,5);
  for(const [index,choice] of ['예약','취소·변경·환불','요금·할인','시설·이용 안내'].entries()){
    context.selectedChoice=choice;
    const badgeStyle=vm.runInContext("renderDecisionCard('inquiry_type',vocFixture.questions.inquiry_type,{choice:selectedChoice,probabilities:{[selectedChoice]:1}},{}).children[1].attributes.style",context);
    assert.ok(styles[index].endsWith(badgeStyle));
  }
  assert.match(styles[4],/background:#84938c/);
  const before=[...styles];nodes.get('chart-uncertain').onclick();
  assert.deepEqual(nodes.get('category-chart').children.map(row=>row.children[1].children[0].attributes.style.split(';background:')[1]),before.map(style=>style.split(';background:')[1]));
});


test('Criteria field help explains scope, IDs and answer types',()=>{
  const {context,nodes}=workspace([]);
  context.vocHelpFixture=readProfileTemplate('consultation');
  vm.runInContext("criteriaProfiles={[sampleProfileIds.general]:vocHelpFixture,[sampleProfileIds.consultation]:vocHelpFixture};handleEditCriteria('41bbe1dc-85cb-4ab0-ab79-cd7c4e6f8e72')",context);
  const profile=nodes.get('criteria-editor').children.find(node=>node.className==='criteria-section profile-settings').children[2];
  assert.match(profile.children[0].children.at(-1).textContent,/Profile name/);
  assert.match(profile.children[1].children.at(-1).textContent,/Changing it does not change AI answers, uncertainty or filters/);
  assert.match(profile.children[2].children.at(-1).textContent,/Rules shared by every decision/);
  assert.match(vm.runInContext("decisionRows[0].id.attributes['aria-description']",context),/Unique result key/);
  assert.equal(vm.runInContext("Object.hasOwn(decisionRows[0],'summary')",context),false);
  assert.match(vm.runInContext("decisionRows[0].panel.children.find(node=>node.className==='criteria-help').textContent",context),/unique Option ID/);
  vm.runInContext("decisionRows[0].type.value='score';decisionRows[0].type.onchange()",context);
  assert.match(vm.runInContext("decisionRows[0].panel.children.find(node=>node.className==='criteria-help').textContent",context),/lowest to highest/);
  vm.runInContext("decisionRows[0].type.value='noul';decisionRows[0].type.onchange()",context);
  assert.match(vm.runInContext("decisionRows[0].panel.children.find(node=>node.className==='criteria-help').textContent",context),/Yes probability/);
  assert.equal(vm.runInContext("Object.hasOwn(readDecisionProfile().questions.inquiry_type,'criteria')",context),false);
});


test('Running a Task opens Main',async()=>{
  const {nodes,context}=workspace([{type:'start',engine:'laya',total:0},{type:'done',elapsedMs:0}]);
  vm.runInContext("handleNavigation('tasks')",context);
  await runTask(nodes);
  assert.equal(vm.runInContext('currentView',context),'main');
  assert.equal(nodes.get('tasks-page').hidden,true);
  assert.equal(nodes.get('main-page').hidden,false);
});


test('Sources in use allow editing and show dependency warnings',async()=>{
  const {nodes,context}=workspace([]);
  await new Promise(resolve=>setImmediate(resolve));
  context.fetch=async()=>({ok:true,json:async()=>({references:['Task: My Monitor']})});
  vm.runInContext(`registeredSources=[{id:'local-source',name:'Logs',type:'local',path:'/logs'}];handleEditSource(0);`,context);
  await new Promise(resolve=>setImmediate(resolve));
  assert.notEqual(vm.runInContext('sourceFields.type.disabled',context),true);
  assert.ok(nodes.get('source-editor').children[0].children.some(node=>node.textContent.includes('In use: Task: My Monitor')));
  context.fetch=async()=>({ok:false,json:async()=>({error:'Save failed'})});
  await nodes.get('save-sources').onclick();
  assert.equal(vm.runInContext('sourceFields.type.disabled',context),false);
});


test('Criteria token estimates update for shared rules, options and structural changes without saving',()=>{
  const {context,nodes,requests}=workspace([]);
  context.tokenFixture=readProfileTemplate('consultation');
  vm.runInContext("criteriaProfiles={[sampleProfileIds.general]:tokenFixture,[sampleProfileIds.consultation]:tokenFixture};criteriaTokenLimits={head_tokens:256,context_tokens:8192};handleEditCriteria('41bbe1dc-85cb-4ab0-ab79-cd7c4e6f8e72')",context);
  const total=()=>vm.runInContext('criteriaTokenEstimates().reduce((sum,q)=>sum+q.tokens,0)',context);
  const panel=()=>nodes.get('criteria-editor').children[1];
  assert.equal(panel().attributes.role,'status');
  assert.match(panel().children[1].textContent,/Total ≈/);
  const initial=total(),calls=requests.length;
  vm.runInContext("criteriaFields.instructions.value+='A'.repeat(400);criteriaFields.instructions.oninput()",context);
  assert.ok(total()>=initial+500);
  const shared=total();
  vm.runInContext("handleRenderCriteriaTokens()",context);
  assert.equal(total(),shared);
  vm.runInContext("decisionRows[0].options[0].text.value+='가'.repeat(200);decisionRows[0].options[0].text.oninput()",context);
  assert.equal(total(),shared+160);
  assert.ok(panel().children.some(node=>/48-token/.test(node.textContent || '')));
  const options=total();
  vm.runInContext("decisionRows[0].options[0].entry.children[2].onclick()",context);
  assert.ok(total()<options);
  const beforeAdd=total();
  nodes.get('criteria-editor').children.at(-1).onclick();
  assert.ok(total()>beforeAdd);
  vm.runInContext("decisionRows.at(-1).panel.children.at(-1).children.at(-1).onclick()",context);
  assert.equal(total(),beforeAdd);
  assert.equal(requests.length,calls);
});

test('Criteria estimates distinguish Laya head and Jev request limits and retain expanded details',()=>{
  const {context,nodes}=workspace([]);
  vm.runInContext("criteriaProfiles={[sampleProfileIds.general]:profileFixture('General','Use evidence.',{normal:'Normal',warning:'Warning',error:'Error',security:'Security',other:'Other'})};criteriaTokenLimits={head_tokens:1,context_tokens:8192};handleEditCriteria('4e6d5417-611e-49e0-8e23-2444a0f49ee4')",context);
  const panel=()=>nodes.get('criteria-editor').children[1];
  assert.match(panel().className,/estimate-warning/);
  assert.ok(panel().children.some(node=>/question head budget/.test(node.textContent || '')));
  const details=panel().children.at(-1);details.open=true;details.ontoggle();
  vm.runInContext("engine='jev';engineLabel='Jev';criteriaTokenLimits={head_tokens:1,context_tokens:32000,request_tokens:64000};handleRenderCriteriaTokens()",context);
  assert.equal(panel().className,'criteria-token-estimate');
  assert.ok(panel().children.at(-1).open);
  assert.ok(panel().children.some(node=>/64,000/.test(node.textContent || '')));
  vm.runInContext('criteriaTokenLimits.request_tokens=1;handleRenderCriteriaTokens()',context);
  assert.match(panel().className,/estimate-warning/);
  assert.ok(panel().children.some(node=>/before input is added/.test(node.textContent || '')));
});


test('Uncertainty stays separate from the complete long decision value in summary and details',()=>{
  const {context}=workspace([]);
  const values=vm.runInContext(`
    const choice='시설·이용 안내 및 프로그램 이용 방법에 관한 긴 문의';
    const definition={label:'문의 유형',type:'choice',criteria:{[choice]:'시설 문의'}};
    const record={defaultDecision:'inquiry_type',decisionAssessments:{inquiry_type:{uncertain:true,candidates:[choice],reviewReasons:['low_answer_probability']}}};
    const card=renderDecisionCard('inquiry_type',definition,{choice,probabilities:{[choice]:.4}},record);
    [card.children[1].textContent,card.children[2].children[0].textContent,card.children[1].title];
  `,context);
  assert.equal(values[0],'시설·이용 안내 및 프로그램 이용 방법에 관한 긴 문의');
  assert.equal(values[1],'Uncertain');
  assert.ok(values[2].includes(values[0]));
});

test('Task History stays below its row through refresh and closes for another detail', async () => {
  const {nodes,context}=workspace([]);
  await new Promise(resolve=>setImmediate(resolve));
  context.fetch=async()=>({ok:true,json:async()=>({runs:[]})});
  vm.runInContext(`registeredTasks=[{id:'one',name:'One',mode:'batch',sources:[]},{id:'two',name:'Two',mode:'batch',sources:[]}];renderTasks()`,context);
  const table=()=>nodes.get('task-list').children[0];
  const click=(row,label)=>table().children[row].children.at(-1).children.find(button=>button.textContent===label).onclick();
  click(1,'History');
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(table().children[2].children[0].children[0],nodes.get('task-history'));
  assert.equal(nodes.get('task-registry').hidden,false);
  vm.runInContext('renderTasks()',context);
  assert.equal(table().children[2].children[0].children[0],nodes.get('task-history'));
  click(3,'View');
  assert.equal(nodes.get('task-history').hidden,true);
  assert.equal(table().children[3].children[0].children[0],nodes.get('task-view'));
  click(1,'History');
  click(1,'History');
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(nodes.get('task-history').hidden,true);
  assert.equal(table().children.length,3);
});


test('Result context emphasizes Task name and reports non-JSON API responses', async () => {
  const {nodes,context}=workspace([]);
  vm.runInContext("renderResultContext('Sample VOC Asia Culture Center Consulting QnA','2026-10-17T00:00:00Z','run-one')",context);
  assert.equal(nodes.get('result-context').children[0].textContent,'Sample VOC Asia Culture Center Consulting QnA');
  assert.equal(nodes.get('result-context').children[0].className,'result-task-name');
  context.htmlResponse={status:502,ok:false,json:async()=>{throw new SyntaxError('Unexpected token <');}};
  await assert.rejects(vm.runInContext("readResultResponse(htmlResponse,'/api/jobs/run-one/results')",context),/\/api\/jobs\/run-one\/results.*invalid JSON.*HTTP 502/);
});


test('Task polling reports HTML response metadata and preserves existing Tasks',async()=>{
  const {context,nodes}=workspace([]);
  await new Promise(resolve=>setImmediate(resolve));
  const count=vm.runInContext('registeredTasks.length',context);
  context.fetch=async()=>({ok:false,status:502,url:'http://localhost/api/tasks',headers:{get:()=> 'text/html'},json:async()=>{throw new SyntaxError("Unexpected token '<'");}});
  await vm.runInContext('handleLoadTasks()',context);
  assert.match(nodes.get('task-message').textContent,/\/api\/tasks.*HTTP 502, text\/html/);
  assert.equal(nodes.get('task-monitor-message').hidden,false);
  assert.equal(vm.runInContext('registeredTasks.length',context),count);
});

test('Task Pause and Resume controls follow active state without starting a new run',async()=>{
  const {nodes,context}=workspace([]);
  await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext("registeredTasks=[{id:'pause-task',name:'Pausing Task',mode:'batch',sources:[],activeRun:{jobId:'same-run',state:'running'}}];handleNavigation('tasks');renderTasks()",context);
  await vm.runInContext("handleLoadTasks()",context);
  const controls=()=>nodes.get('task-list').children[0].children[1].children.at(-1).children;
  const button=label=>controls().find(item=>item.textContent===label);
  assert.equal(button('Pause').disabled,false);
  assert.equal(button('Resume'),undefined);
  const paths=[];
  context.fetch=async path=>{
    paths.push(path);
    if(path==='/api/tasks')return {ok:true,json:async()=>({tasks:vm.runInContext('registeredTasks',context)})};
    const state=path.endsWith('/pause')?'paused':'running';
    vm.runInContext(`registeredTasks[0].activeRun.state='${state}'`,context);
    return {ok:true,json:async()=>({jobId:'same-run',state})};
  };
  await button('Pause').onclick();
  assert.equal(button('Pause'),undefined);
  assert.equal(button('Resume').disabled,false);
  assert.equal(button('Stop').disabled,false);
  assert.equal(button('Run').disabled,true);
  assert.equal(vm.runInContext('currentView',context),'tasks');
  await button('Resume').onclick();
  assert.equal(button('Pause').disabled,false);
  assert.equal(button('Resume'),undefined);
  assert.deepEqual(paths,['/api/tasks/pause-task/pause','/api/tasks','/api/tasks/pause-task/resume','/api/tasks']);
});


test('Pause on an older server explains restart without parsing its plain-text response',async()=>{
  const {nodes,context}=workspace([]);
  await new Promise(resolve=>setImmediate(resolve));
  context.fetch=async()=>({status:405,ok:false,json:async()=>{throw new Error('Should not parse Method Not Allowed');}});
  await vm.runInContext("handlePauseTask('task-one','pause')",context);
  assert.match(nodes.get('task-message').textContent,/Pause\/Resume is unavailable.*restart.*Restarting interrupts active executions/);
});


test('Main reconnects to the same recovered execution after a server outage',async()=>{
  const {context}=workspace([]);
  await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext(`currentView='main';monitoringReady=true;followLatestTask=false;busy=false;
    activeJobId='same-run';selectedTaskId=registeredTasks[0].id;
    registeredTasks[0].activeRun={jobId:'same-run',state:'paused'};
    globalThis.watched=[];handleWatchRun=async run=>{watched.push(run.jobId);busy=true;};`,context);
  await vm.runInContext('handleLoadTasks()',context);
  assert.equal(vm.runInContext('watched.join()',context),'same-run');
  await vm.runInContext('handleLoadTasks()',context);
  assert.equal(vm.runInContext('watched.length',context),1);
});

function enableCleanRoutes(context,navigation) {
  const writes=[];
  const write=(replace,path)=>{
    const url=new URL(path,'http://localhost');
    navigation.pathname=url.pathname;navigation.search=url.search;navigation.hash=url.hash;
    writes.push({replace,path});
  };
  context.URLSearchParams=URLSearchParams;
  context.history={pushState:(_state,_title,path)=>write(false,path),replaceState:(_state,_title,path)=>write(true,path)};
  return writes;
}

test('Task History, View, Edit and Cancel expose distinct clean URLs',async()=>{
  const navigation={pathname:'/tasks',search:'',hash:''};
  const {context,nodes,listeners}=workspace([],undefined,undefined,undefined,navigation);
  await new Promise(resolve=>setImmediate(resolve));
  const writes=enableCleanRoutes(context,navigation);
  context.fetch=async path=>{
    if(path==='/api/tasks/test-task/runs')return {ok:true,json:async()=>({runs:[]})};
    if(path==='/api/tasks')return {ok:true,json:async()=>({tasks:vm.runInContext('registeredTasks',context)})};
    return {ok:true,json:async()=>({hosts:[],keys:[]})};
  };
  vm.runInContext('renderTasks()',context);
  const controls=()=>nodes.get('task-list').children[0].children[1].children.at(-1).children;
  const button=label=>controls().find(item=>item.textContent===label);
  assert.equal(button('History').attributes.href,'/tasks/test-task/history');
  button('History').onclick();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(navigation.pathname,'/tasks/test-task/history');
  assert.equal(nodes.get('task-history').hidden,false);
  button('View').onclick();
  assert.equal(navigation.pathname,'/tasks/test-task');
  await button('Edit').onclick();
  assert.equal(navigation.pathname,'/tasks/test-task/edit');
  nodes.get('cancel-task').onclick();
  assert.equal(navigation.pathname,'/tasks');
  navigation.pathname='/tasks/test-task/history';
  await listeners.get('popstate')();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(nodes.get('task-history').hidden,false);
  assert.ok(writes.every(write=>!write.path.includes('#')));
});

test('Direct execution link loads its exact ID without running a Task',async()=>{
  const navigation={pathname:'/',search:'',hash:''};
  const {context,listeners}=workspace([],undefined,undefined,undefined,navigation);
  await new Promise(resolve=>setImmediate(resolve));
  enableCleanRoutes(context,navigation);
  const paths=[];
  context.fetch=async path=>{paths.push(path);return {ok:true,json:async()=>({jobId:'linked-run',state:'stopped',settings:{taskId:'test-task'}})};};
  vm.runInContext('globalThis.watched=[];handleWatchRun=async job=>{watched.push(job.jobId);}',context);
  navigation.pathname='/runs/linked-run';
  await listeners.get('popstate')();
  assert.equal(vm.runInContext('watched.join()',context),'linked-run');
  assert.deepEqual(paths,['/api/jobs/linked-run']);
});

test('Run filter URLs preserve pages while background polls replace history',async()=>{
  const navigation={pathname:'/',search:'',hash:''};
  const {context,nodes}=workspace([],undefined,undefined,undefined,navigation);
  await new Promise(resolve=>setImmediate(resolve));
  const writes=enableCleanRoutes(context,navigation);
  vm.runInContext("currentView='main';activeJobId='linked-run';pagedView={id:'linked-run',cursors:[null,100,70],through:130};page=2",context);
  nodes.get('review-filter').value='needs-review';nodes.get('log-search').value='synthetic query';
  nodes.get('processing-filter').value='successful';
  vm.runInContext('handleSyncRunRoute()',context);
  const params=new URLSearchParams(navigation.search);
  assert.equal(navigation.pathname,'/runs/linked-run');
  assert.equal(params.get('cursors'),'100,70');assert.equal(params.get('through'),'130');
  assert.equal(params.get('review'),'needs-review');assert.equal(params.get('search'),'synthetic query');
  assert.equal(params.get('processing'),'successful');
  assert.equal(params.has('decision'),false);assert.equal(params.has('certainty'),false);
  nodes.get('host-filter').value='host-two';
  vm.runInContext('handleSyncRunRoute(true)',context);
  assert.equal(writes.at(-1).replace,true);
});

test('Resource links share stable IDs across Sources Actions Criteria and SSH lists',async()=>{
  const navigation={pathname:'/',search:'',hash:''};
  const {context,nodes}=workspace([],undefined,undefined,undefined,navigation);
  await new Promise(resolve=>setImmediate(resolve));
  enableCleanRoutes(context,navigation);
  vm.runInContext(`
    registeredSources=[{id:'source-id',name:'Source',type:'local',path:'/synthetic'}];
    registeredActions=[{id:'action-id',name:'Action',code:'print(1)',modules:[]}];
    criteriaProfiles={[sampleProfileIds.general]:profileFixture('Sample General System','Test',{normal:'Normal'}),'criteria-id':profileFixture('Criteria','Test',{normal:'Normal'})};
    sshKeys=[{id:'key-id',name:'Key',privatePath:'/synthetic/key',publicKey:'synthetic'}];
    sshHosts=[{id:'host-id',name:'Host',host:'synthetic',port:22,username:'reader',keyId:'key-id'}];
    renderSources();renderActions();renderCriteria();renderSSHKeys();renderSSHHosts();
  `,context);
  for(const path of ['/sources/source-id','/actions/action-id','/criteria/criteria-id','/settings/ssh-keys/key-id','/settings/ssh-hosts/host-id']){
    assert.equal(vm.runInContext(`routeOpeners.has(${JSON.stringify(path)})`,context),true);
    assert.equal(vm.runInContext(`routeOpeners.has(${JSON.stringify(path+'/edit')})`,context),true);
    vm.runInContext(`routeOpeners.get(${JSON.stringify(path)})()`,context);
    assert.equal(navigation.pathname,path);
  }
});

test('Modified clicks preserve native link behavior and commands have no href',async()=>{
  const navigation={pathname:'/tasks',search:'',hash:''};
  const {nodes,context}=workspace([],undefined,undefined,undefined,navigation);
  await new Promise(resolve=>setImmediate(resolve));enableCleanRoutes(context,navigation);
  vm.runInContext('renderTasks()',context);
  const controls=nodes.get('task-list').children[0].children[1].children.at(-1).children;
  const view=controls.find(button=>button.textContent==='View');
  view.onclick({ctrlKey:true,preventDefault(){throw Error('Native link was intercepted');}});
  assert.equal(navigation.pathname,'/tasks');
  for(const label of ['Run','Stop','Pause','Delete'])assert.equal(controls.find(button=>button.textContent===label).attributes.href,undefined);
});

test('Back and Forward restore filters within a live execution without restarting its watcher',async()=>{
  const navigation={pathname:'/',search:'',hash:''};
  const {context,listeners}=workspace([],undefined,undefined,undefined,navigation);
  await new Promise(resolve=>setImmediate(resolve));enableCleanRoutes(context,navigation);
  vm.runInContext("busy=true;activeJobId='same';pagedView={id:'same'};globalThis.applied=[];handleApplyRunRoute=async path=>applied.push(path);handleWatchRun=()=>{throw Error('Live watcher restarted');}",context);
  context.fetch=async()=>({ok:true,json:async()=>({jobId:'same',state:'running',settings:{taskId:'test-task'}})});
  navigation.pathname='/runs/same';navigation.search='?review=needs-review';
  await listeners.get('popstate')();
  assert.equal(vm.runInContext('applied.join()',context),'/runs/same?review=needs-review');
});

test('Reopening a completed execution at its base URL clears stale expanded sections',async()=>{
  const navigation={pathname:'/',search:'',hash:''};
  const {context}=workspace([],undefined,undefined,undefined,navigation);
  await new Promise(resolve=>setImmediate(resolve));enableCleanRoutes(context,navigation);
  navigation.pathname='/runs/same';
  vm.runInContext("expandedResultDetails.set('same:2',new Set(['input']));handleLoadResultSettings=async()=>{};handleRefreshResults=async()=>{};handleLoadTasks=async()=>{}",context);
  await vm.runInContext("handlePagedProcessing({jobId:'same',state:'completed',settings:{mode:'batch',taskName:'Same'}})",context);
  assert.equal(vm.runInContext('expandedResultDetails.size',context),0);
});


test('Task Source None clears its dependency and active Tasks allow editing', async () => {
  const {nodes,context}=workspace([]);
  await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext(`
    registeredSources=[{id:'source',name:'Logs',type:'local',path:'/input.log'}];
    updateSourceSettings(['source']);
    sourceRows[0].name.value='';sourceRows[0].name.onchange();
  `,context);
  assert.equal(vm.runInContext('sourceRows[0].path',context),'');
  assert.equal(nodes.get('file-path').value,'');
  for(const state of ['running','pausing','paused']) {
    vm.runInContext(`registeredTasks=[{id:'task',name:'Logs',mode:'batch',sources:[],activeRun:{state:'${state}'}}];renderTasks()`,context);
    const table=nodes.get('task-list').children[0];
    const controls=table.children[1].children.at(-1).children;
    assert.notEqual(controls.find(button=>button.textContent==='Edit').disabled,true);
    assert.equal(controls.find(button=>button.textContent==='Run').disabled,true);
  }
});


test('Criteria None survives profile refresh and blocks Task execution', async () => {
  const {nodes,context}=workspace([]);
  await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext(`
    updateSourceSettings(['1'.padStart(32,'0')]);
    sourceRows[0].profile.value='';sourceRows[0].profile.onchange();
    handleCriteriaLabels({[sampleProfileIds.general]:{label:'Sample General System'}});
  `,context);
  assert.equal(vm.runInContext('sourceRows[0].profile.value',context),'');
  assert.equal(vm.runInContext('sourceRows[0].profile.children[0].text',context),'None');
  vm.runInContext(`registeredTasks=[{id:'task',name:'Logs',mode:'batch',sources:[{sourceId:'source',profile:''}]}];renderTasks()`,context);
  const controls=nodes.get('task-list').children[0].children[1].children.at(-1).children;
  assert.equal(controls.find(button=>button.textContent==='Run').disabled,true);
  assert.equal(Boolean(controls.find(button=>button.textContent==='Edit').disabled),false);
});


test('Run progress shows state without repeating summary counts', async () => {
  const {nodes,context}=workspace([]);
  await new Promise(resolve=>setImmediate(resolve));
  for(const state of ['failed','completed']) {
    vm.runInContext(`handleRunProgress('${state}','batch')`,context);
    assert.equal(nodes.get('message').textContent,'');
  }
  vm.runInContext("handleRunProgress('paused','batch')",context);
  assert.equal(nodes.get('run-state').textContent,'Paused');
  assert.match(nodes.get('run-state').className,/task-state monitor-state paused/);
  assert.equal(nodes.get('message').textContent,'');
});


test('Disabled Tasks are hidden from Task Monitor and return when enabled', async () => {
  const {nodes,context}=workspace([]);
  await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext(`registeredTasks=[{id:'on',name:'Enabled Task',mode:'batch',sources:[],enabled:true},{id:'off',name:'Disabled Task',mode:'batch',sources:[],enabled:false}];renderTasks()`,context);
  assert.equal(nodes.get('running-tasks').children.length,1);
  assert.equal(nodes.get('running-tasks').children[0].children[0].textContent,'Enabled Task');
  assert.equal(nodes.get('task-list').children[0].children.length,3);
  vm.runInContext('registeredTasks[1].enabled=true;renderTasks()',context);
  assert.equal(nodes.get('running-tasks').children.length,2);
});


test('Task polling failure preserves results and recovers its own warning', async () => {
  const {nodes,context}=workspace([]);
  await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext("registeredTasks=[{id:'saved',name:'Saved',sources:[]}];renderTasks();handleMessage('message','Paused');",context);
  context.fetch=async()=>({status:503,ok:false,headers:{get:()=> 'text/html'},json:async()=>{throw new SyntaxError('Unexpected token <');}});
  await vm.runInContext('handleLoadTasks()',context);
  assert.equal(nodes.get('message').textContent,'Paused');
  assert.equal(nodes.get('task-monitor-message').hidden,false);
  assert.match(nodes.get('task-monitor-message').textContent,/retrying automatically/);
  assert.match(nodes.get('task-monitor-message').title,/HTTP 503/);
  assert.equal(vm.runInContext('registeredTasks[0].id',context),'saved');
  context.fetch=async()=>({ok:true,json:async()=>({tasks:[]})});
  await vm.runInContext('handleLoadTasks()',context);
  assert.equal(nodes.get('task-monitor-message').hidden,true);
  assert.equal(nodes.get('task-message').textContent,'');
  assert.equal(nodes.get('message').textContent,'Paused');
});

test('Task list polling does not overlap an outstanding request', async () => {
  const {context}=workspace([]);
  await new Promise(resolve=>setImmediate(resolve));
  let release;let calls=0;
  context.fetch=()=>{calls++;return new Promise(resolve=>{release=resolve;});};
  const first=vm.runInContext('handleLoadTasks()',context);
  const second=vm.runInContext('handleLoadTasks()',context);
  assert.equal(first,second);
  assert.equal(calls,1);
  release({ok:true,json:async()=>({tasks:[]})});
  await first;
});

function elapsedValues(nodes) {
  return [3,4].map(index=>nodes.get('summary').children[index].children[0].textContent);
}

test('Elapsed times use separate metrics and review count appears beside host details', async () => {
  const {nodes,context}=workspace([]);
  await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext('elapsedMs=65000;activeProcessingMs=28900;render()',context);
  const metrics=nodes.get('summary').children;
  assert.equal(metrics.length,6);
  assert.equal(metrics[3].textContent,'Total Elapsed Time');
  assert.equal(metrics[4].textContent,'Active Processing Time');
  assert.deepEqual(elapsedValues(nodes),['1 min 5 sec','28.9 sec (44.5%)']);
  assert.equal(nodes.get('needs-review-count').textContent,'Needs Review: 0');
  const html=readFileSync(new URL('../public/index.html',import.meta.url),'utf8');
  assert.match(html,/class="result-display-settings"[^]*?id="decision-display-menu"[^]*?id="host-status"[^]*?id="needs-review-count"[^]*?id="source-hosts-detail"[^]*?class="result-toolbar"[^]*?id="result-filter-type"/);
});


test('Main link uses the logo root URL and polling preserves it', async () => {
  const navigation={pathname:'/tasks',search:'',hash:''};
  const {nodes,context}=workspace([],undefined,undefined,undefined,navigation);
  await new Promise(resolve=>setImmediate(resolve));
  enableCleanRoutes(context,navigation);
  vm.runInContext("activeJobId='selected-run';pagedView={id:'selected-run',cursors:[null],through:10};page=0",context);
  nodes.get('nav-main').onclick();
  assert.equal(navigation.pathname,'/');
  vm.runInContext('handleSyncRunRoute(true)',context);
  assert.equal(navigation.pathname,'/');
  const html=readFileSync(new URL('../public/index.html',import.meta.url),'utf8');
  assert.match(html,/class="brand" href="\/"/);
  assert.match(html,/id="nav-main" href="\/"/);
});


test('Results omit More Decision Results when every decision is already visible', async () => {
  const {nodes}=workspace([result(0,false)]);
  await runTask(nodes);
  assert.equal(nodes.get('results').children[0].children[0].children.some(child=>child.className==='all-decisions'),false);
});


test('Source list separates input metadata and paths and keeps inline View on refresh', async () => {
  const {context,nodes}=workspace([]);
  await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext(`registeredSources=[
    {id:'local',name:'Local Logs',type:'local',path:'/logs/server.log\\n/logs/access.log'},
    {id:'remote',name:'Remote QnA',type:'ssh',format:'jsonl',contentField:'consulting_content',path:'/data/<archive>/government-consultations.jsonl'}
  ];renderSources();`,context);
  const table=()=>nodes.get('source-registry').children[0];
  assert.deepEqual(table().children[0].children.map(cell=>cell.textContent),['Name','Input','Manage']);
  const input=table().children[1].children[1];
  assert.deepEqual(input.children[0].children.map(tag=>tag.textContent),['Local File','TEXT (Chunk)']);
  assert.deepEqual(input.children[1].children.map(path=>path.textContent),['/logs/server.log','/logs/access.log']);
  const remote=table().children[2].children[1];
  assert.deepEqual(remote.children[0].children.map(tag=>tag.textContent),['Remote File (SSH)','JSONL (Line)']);
  assert.equal(remote.children[1].children[0].textContent,'/data/<archive>/government-consultations.jsonl');
  table().children[1].children.at(-1).children[0].onclick();
  vm.runInContext('renderSources()',context);
  assert.equal(table().children[2].className,'inline-view-row');
  assert.equal(nodes.get('source-view').hidden,false);
  nodes.get('source-search').value='government-consultations';
  vm.runInContext('renderSources()',context);
  assert.equal(table().children.length,2);
  assert.equal(table().children[1].children[0].textContent,'Remote QnA');
});


test('Manager lists sort English and Korean names naturally without changing edit targets', async () => {
  const names=['Zulu','나무','Alpha 10','가방','alpha 2'];
  const expected=['가방','나무','alpha 2','Alpha 10','Zulu'];
  for(const manager of ['source','action','criteria','task']) {
    const {context,nodes}=workspace([]);
    await new Promise(resolve=>setImmediate(resolve));
    const records=names.map((name,index)=>({id:String(index),name,label:name,type:'local',path:`/logs/${index}`,code:'pass',sources:[],mode:'batch',enabled:false,timezone:'UTC',cron:''}));
    const general={label:'Sample General System',instructions:'Classify the input.',defaultDecision:'category',questions:{category:{label:'Category',type:'choice',criteria:{normal:'Normal',other:'Other'}}}};
    const setup={
      source:`registeredSources=${JSON.stringify(records)};renderSources()`,
      action:`registeredActions=${JSON.stringify(records)};renderActions()`,
      criteria:`criteriaProfiles={[sampleProfileIds.general]:${JSON.stringify(general)}};criteriaProfiles={...criteriaProfiles,...Object.fromEntries(${JSON.stringify(records)}.map(item=>[item.id,{...criteriaProfiles[sampleProfileIds.general],label:item.name}]))};renderCriteria()`,
      task:`registeredTasks=${JSON.stringify(records)};renderTasks()`,
    };
    vm.runInContext(setup[manager],context);
    const table=nodes.get(manager==='task'?'task-list':`${manager}-registry`).children[0];
    const rows=table.children.slice(1);
    assert.deepEqual(rows.map(row=>row.children[0].textContent),manager==='criteria'?['가방','나무','alpha 2','Alpha 10','Sample General System','Zulu']:expected,manager);
    if(manager!=='criteria') {
      const collection={source:'registeredSources',action:'registeredActions',task:'registeredTasks'}[manager];
      assert.equal(vm.runInContext(`JSON.stringify(${collection}.map(item=>item.name))`,context),JSON.stringify(names));
    }else{
      assert.deepEqual(criteriaRow(nodes,'Sample General System').children.at(-1).children.map(button=>button.textContent),['View','Edit','Clone','Delete','Ref.']);
    }
    const selected=rows.find(row=>row.children[0].textContent==='alpha 2');
    const edit=selected.children.at(-1).children.find(button=>button.textContent==='Edit');
    await edit.onclick();
    const selectedId=vm.runInContext({source:'editingSource',action:'editingAction',criteria:'editingCriteria',task:'editingTask'}[manager],context);
    assert.equal(selectedId,manager==='source' || manager==='action'?4:'4',manager);
  }
});


test('Token warnings distinguish truncated input, shortened Criteria and unsent requests', async () => {
  for(const engine of ['laya','jev']){
    const events=[result(0,false),result(1,false),result(2,false),result(3,false)];
    events[0].result={...events[0].result,engine,log:'truncated input',error:'Input exceeded the budget.',providerResponse:{usage:{truncated:true}}};
    events[1].result={...events[1].result,engine,log:'shortened criteria',review:true,providerResponse:{usage:{truncated:false,criteria_tokens_dropped:{category:15}}}};
    events[2].result={...events[2].result,engine,log:'unsent request',error:'Request too large.',inputLimitExceeded:'request_bytes'};
    events[3].result={...events[3].result,engine,log:'ordinary failure',error:'Could not inspect token limits.',providerResponse:{usage:{truncated:false,criteria_tokens_dropped:{category:0}}}};
    const {nodes,context}=workspace(events);
    await runTask(nodes);
    const row=log=>nodes.get('results').children.find(item=>item.children[1].children[1].textContent===log);
    const warning=log=>row(log).children[0].children.find(item=>item.className==='result-token-warning');
    assert.equal(warning('truncated input').children[0].textContent,'Input Token Limit');
    assert.match(warning('truncated input').children[1].textContent,/prediction was rejected/);
    assert.equal(warning('shortened criteria').children[0].textContent,'Criteria Shortened');
    assert.match(warning('shortened criteria').children[1].textContent,/Category/);
    assert.equal(warning('unsent request').children[0].textContent,'Request Size Limit');
    assert.match(warning('unsent request').children[1].textContent,/not sent/);
    assert.equal(warning('ordinary failure'),undefined);
    assert.match(row('truncated input').className,/token-limited/);
    vm.runInContext('render()',context);
    assert.equal(warning('shortened criteria').children[0].textContent,'Criteria Shortened');
  }
});


test('Result filter type switches controls without changing filters or making requests', async () => {
  const {context,nodes}=workspace([result(0,false),result(1,true)]);
  await runTask(nodes);
  context.fetch=()=>{throw new Error('Switching filter type must not fetch');};
  nodes.get('review-filter').value='needs-review';nodes.get('review-filter').onchange();
  assert.deepEqual(logs(nodes),['log-1']);
  nodes.get('result-filter-type').value='log-search';nodes.get('result-filter-type').onchange();
  assert.equal(nodes.get('log-search').hidden,false);
  assert.equal(nodes.get('review-filter').hidden,true);
  assert.equal(nodes.get('review-filter').value,'needs-review');
  assert.deepEqual(logs(nodes),['log-1']);
  nodes.get('log-search').value='log-1';nodes.get('log-search').oninput();
  const chips=nodes.get('active-result-filters');
  assert.equal(chips.children.length,3);
  const first=chips.children[0];
  vm.runInContext('renderResultFilters()',context);
  assert.equal(chips.children[0],first);
  chips.children.find(button=>button.textContent.startsWith('Review Status:')).onclick();
  assert.equal(nodes.get('review-filter').value,'all');
  assert.equal(nodes.get('log-search').value,'log-1');
  chips.children.find(button=>button.textContent==='Clear All').onclick();
  assert.equal(nodes.get('log-search').value,'');
  assert.equal(chips.hidden,true);
  assert.equal(nodes.get('result-filter-type').value,'log-search');
  assert.deepEqual(logs(nodes),['log-1','log-0']);
});

test('AI Criteria preserves generated decisions through save without legacy visibility flags', async()=>{
  const general=readProfileTemplate('general');
  const generated=readProfileTemplate('consultation');
  generated.label='AI Generated Test';
  const {nodes,context}=workspace([],undefined,undefined,{[sampleProfileIds.general]:general});
  await new Promise(resolve=>setImmediate(resolve));
  await nodes.get('nav-criteria').onclick();
  vm.runInContext("handleEditCriteria('')",context);
  const walk=node=>[node,...(node.children || []).flatMap(child=>typeof child==='object'?walk(child):[])];
  const details=walk(nodes.get('criteria-editor')).find(node=>node.className?.includes('criteria-generator'));
  const fetch=context.fetch;let submitted;
  context.fetch=async(path,options)=>{
    if(path==='/api/criteria/samples')return {ok:true,json:async()=>({samples:['Private sample','Other sample']})};
    if(path==='/api/criteria/generate'){submitted=JSON.parse(options.body);return {ok:true,json:async()=>({profile:generated,analysisPurpose:'Evaluate status and urgency'})};}
    return fetch(path,options);
  };
  details.open=true;await details.ontoggle();
  const findLabel=label=>walk(details).find(node=>node.attributes?.['aria-label']===label);
  findLabel('Sample Source').value=vm.runInContext('sampleSources[0].id',context);
  findLabel('Sample Source').onchange();
  const button=caption=>walk(details).find(node=>node.textContent===caption && node.onclick);
  const sampleCount=findLabel('Sample Count');
  assert.equal(sampleCount.value,'10');
  assert.equal(sampleCount.type,'number');assert.equal(sampleCount.min,'1');assert.ok(!sampleCount.max);assert.equal(sampleCount.step,'1');
  let previewBody;const previewFetch=context.fetch;
  context.fetch=async(path,options)=>{
    if(path==='/api/criteria/samples')previewBody=JSON.parse(options.body);
    return previewFetch(path,options);
  };
  sampleCount.value='0';await button('Preview Source Samples').onclick();
  assert.equal(previewBody,undefined);
  for(const value of ['1','15','30','51','101','1000']){
    sampleCount.value=value;sampleCount.oninput();
    await button('Preview Source Samples').onclick();
    assert.equal(previewBody.sampleCount,Number(value));
  }
  assert.equal(button('Generate Criteria').disabled,false);
  sampleCount.value='10';sampleCount.oninput();
  assert.equal(button('Generate Criteria').disabled,true);
  assert.equal(findLabel('Sample 1'),undefined);
  await button('Preview Source Samples').onclick();
  assert.equal(previewBody.sampleCount,10);
  findLabel('Sample 1').value='Redacted sample';
  findLabel('Analysis Purpose Mode').value='manual';findLabel('Analysis Purpose Mode').onchange();
  findLabel('Analysis Purpose').value='Evaluate status and urgency';
  await button('Generate Criteria').onclick();
  assert.deepEqual(submitted,{purposeMode:'manual',purpose:'Evaluate status and urgency',samples:['Redacted sample','Other sample']});
  const visibleProfile=structuredClone(generated);
  for(const question of Object.values(visibleProfile.questions))delete question.summary;
  assert.deepEqual(JSON.parse(vm.runInContext('JSON.stringify(readDecisionProfile())',context)),visibleProfile);
  assert.equal(Object.keys(vm.runInContext('criteriaProfiles',context)).length,1);
  const id=vm.runInContext('criteriaDraftId',context);
  await nodes.get('save-criteria').onclick();
  assert.deepEqual(JSON.parse(vm.runInContext(`JSON.stringify(criteriaProfiles['${id}'])`,context)),visibleProfile);
});

test('Failed AI generation preserves the draft and edited samples',async()=>{
  const general=readProfileTemplate('general');
  const {nodes,context}=workspace([],undefined,undefined,{[sampleProfileIds.general]:general});await new Promise(resolve=>setImmediate(resolve));
  await nodes.get('nav-criteria').onclick();
  vm.runInContext("handleEditCriteria('');criteriaFields.label.value='Keep This Draft'",context);
  const walk=node=>[node,...(node.children || []).flatMap(child=>typeof child==='object'?walk(child):[])];
  const details=walk(nodes.get('criteria-editor')).find(node=>node.className?.includes('criteria-generator'));
  const original=context.fetch;
  context.fetch=async(path,options)=>path==='/api/criteria/generate'?{ok:false,json:async()=>({error:'Generation failed.'})}:path==='/api/criteria/samples'?{ok:true,json:async()=>({samples:['sample']})}:original(path,options);
  details.open=true;await details.ontoggle();
  await walk(details).find(node=>node.textContent==='Preview Source Samples').onclick();
  const input=walk(details).find(node=>node.attributes?.['aria-label']==='Sample 1');input.value='Edited sample';
  walk(details).find(node=>node.attributes?.['aria-label']==='Analysis Purpose').value='Classify';
  await walk(details).find(node=>node.textContent==='Generate Criteria').onclick();
  assert.equal(vm.runInContext('criteriaFields.label.value',context),'Keep This Draft');
  assert.equal(input.value,'Edited sample');
  assert.ok(walk(details).some(node=>node.textContent==='Generation failed.'));
});

test('AI sample guidance explains TEXT grouping, fixed JSONL records, SSH selection and purpose',async()=>{
  const {context}=workspace([]);await new Promise(resolve=>setImmediate(resolve));
  const original=context.fetch;
  context.fetch=async(path,options)=>path==='/api/sources'?{ok:true,json:async()=>({sources:[
    {id:'local-text',name:'Local Text',type:'local',format:'text'},
    {id:'local-jsonl',name:'Local JSONL',type:'local',format:'jsonl'},
    {id:'remote-text',name:'Remote Text',type:'ssh',format:'text'},
    {id:'remote-jsonl',name:'Remote JSONL',type:'ssh',format:'jsonl'},
  ]})}:original(path,options);
  const details=vm.runInContext('renderCriteriaGenerator()',context);
  const walk=node=>[node,...(node.children || []).flatMap(child=>typeof child==='object'?walk(child):[])];
  const field=label=>walk(details).find(node=>node.attributes?.['aria-label']===label);
  details.open=true;await details.ontoggle();
  const source=field('Sample Source'),count=field('Events Per Sample'),host=field('Sample SSH Host');
  for(const type of ['local','remote']){
    source.value=`${type}-text`;source.onchange();count.value='5';
    assert.equal(count.disabled,false);assert.equal(count.parentElement.hidden,false);assert.equal(host.parentElement.hidden,type==='local');
    assert.match(count.attributes['aria-description'],/five events/);
    assert.match(count.attributes['aria-description'],/does not change any Task/);
    source.value=`${type}-jsonl`;source.onchange();
    assert.equal(count.disabled,true);assert.equal(count.value,'1');
    assert.equal(count.parentElement.hidden,true);
    assert.ok(walk(details).some(node=>node.textContent?.includes('One JSONL record is one sample')));
    assert.ok(walk(details).some(node=>node.textContent?.includes('randomly selects up to the selected Sample Count')));
  }
  assert.match(field('Analysis Purpose').attributes['aria-description'],/priority rules, exclusions/);
  assert.ok(walk(details).some(node=>node.textContent?.includes('Classify failures, urgency')));
});

test('Analysis purpose defaults to automatic and preserves manual input when switching',async()=>{
  const general=readProfileTemplate('general');
  const generated=readProfileTemplate('consultation');
  const {nodes,context}=workspace([],undefined,undefined,{[sampleProfileIds.general]:general});await new Promise(resolve=>setImmediate(resolve));
  await nodes.get('nav-criteria').onclick();vm.runInContext("handleEditCriteria('')",context);
  const walk=node=>[node,...(node.children || []).flatMap(child=>typeof child==='object'?walk(child):[])];
  const details=walk(nodes.get('criteria-editor')).find(node=>node.className?.includes('criteria-generator'));
  const field=label=>walk(details).find(node=>node.attributes?.['aria-label']===label);
  const mode=field('Analysis Purpose Mode'),purpose=field('Analysis Purpose');
  assert.equal(mode.value,'automatic');assert.equal(purpose.parentElement.hidden,true);
  mode.value='manual';mode.onchange();assert.equal(purpose.parentElement.hidden,false);purpose.value='My objective';
  mode.value='automatic';mode.onchange();assert.equal(purpose.value,'My objective');assert.equal(purpose.disabled,true);
  let submitted;const original=context.fetch;
  context.fetch=async(path,options)=>{
    if(path==='/api/criteria/samples')return {ok:true,json:async()=>({samples:['A consultation']})};
    if(path==='/api/criteria/generate'){submitted=JSON.parse(options.body);return {ok:true,json:async()=>({profile:generated,analysisPurpose:'Suggested follow-up analysis'})};}
    return original(path,options);
  };
  details.open=true;await details.ontoggle();
  await walk(details).find(node=>node.textContent==='Preview Source Samples').onclick();
  await walk(details).find(node=>node.textContent==='Generate Criteria').onclick();
  assert.equal(submitted.purposeMode,'automatic');assert.equal(submitted.purpose,'');
  assert.ok(walk(nodes.get('criteria-editor')).some(node=>node.textContent==='Suggested Analysis Purpose'));
  assert.ok(walk(nodes.get('criteria-editor')).some(node=>node.textContent==='Suggested follow-up analysis'));
});

test('New Criteria separates optional AI generation from template and manual authoring',async()=>{
  const general=readProfileTemplate('general');
  const {nodes,context}=workspace([],undefined,undefined,{[sampleProfileIds.general]:general});await new Promise(resolve=>setImmediate(resolve));
  await nodes.get('nav-criteria').onclick();
  vm.runInContext("criteriaTemplates={[sampleProfileIds.general]:criteriaProfiles[sampleProfileIds.general]};handleEditCriteria('')",context);
  const children=nodes.get('criteria-editor').children;
  const generator=children.findIndex(node=>node.className==='criteria-section criteria-generator');
  const divider=children.findIndex(node=>node.className==='criteria-authoring-divider');
  const template=children.findIndex(node=>node.className==='criteria-template-start');
  const profile=children.findIndex(node=>node.className==='criteria-section profile-settings');
  assert.ok(generator<divider && divider<template && template<profile);
  assert.equal(children[template].children[0].attributes['aria-label'],'Start From Template');
});


test('Starting an empty paged run removes the previous run cards', async()=>{
  const {nodes,context}=pagedWorkspace();
  await vm.runInContext("handlePagedProcessing({jobId:'previous',state:'completed',settings:{mode:'batch'},pagedResults:true})",context);
  assert.equal(nodes.get('results').children.length,50);
  const original=context.fetch;
  context.fetch=async(path,options)=>{
    const response=await original(path,options);
    if(!path.endsWith('/results'))return response;
    const data=await response.json();
    data.items=[];data.sequence=0;data.hasNext=false;
    data.summary.total=0;data.summary.groups={all:0,certain:0,uncertain:0};
    return {ok:true,json:async()=>data};
  };
  await vm.runInContext("handlePagedProcessing({jobId:'new',state:'completed',settings:{mode:'batch'},pagedResults:true})",context);
  assert.equal(vm.runInContext('completed',context),0);
  assert.equal(nodes.get('results').children.length,1);
  assert.equal(nodes.get('results').children[0].textContent,'No results to display.');
  assert.equal(nodes.get('page-info').textContent,'Page 1 · 0 results shown');
});


test('HTTP check runs once per load and cannot overwrite actual request status',async()=>{
  for(const engine of ['laya','jev']){
    const {nodes,context}=workspace([], {host:{hostname:'host',addresses:[],os:'Linux'},engine,configured:true,model:'test'});
    const original=context.fetch;let checks=0,finish;
    context.fetch=(path,options)=>{
      if(path!=='/api/engine-health')return original(path,options);
      checks++;return new Promise(resolve=>{finish=resolve;});
    };
    await new Promise(resolve=>setImmediate(resolve));
    const connection=nodes.get('status').children[1];
    assert.equal(connection.textContent,' (Checking…)');
    vm.runInContext("handleEngineResultConnection({engineConnection:'connected'})",context);
    assert.equal(connection.textContent,' (Operational)');
    assert.match(connection.title,/Last actual classification request/);
    finish({ok:true,json:async()=>({engine,connection:'disconnected'})});
    await new Promise(resolve=>setImmediate(resolve));
    assert.equal(connection.textContent,' (Operational)');
    vm.runInContext("render();handleNavigation('tasks');handleNavigation('main')",context);
    assert.equal(checks,1);
    vm.runInContext("handleEngineResultConnection({engineConnection:'api_error',httpStatus:401})",context);
    assert.equal(connection.textContent,' (Auth Error)');
    assert.match(connection.title,/Authentication failed/);
    vm.runInContext("handleEngineResultConnection({engineConnection:'connected',error:'Invalid classification response'})",context);
    assert.equal(connection.textContent,' (API Error)');
  }
});

test('paged historical results do not override HTTP status but new live results do',async()=>{
  const {nodes,context,append}=pagedWorkspace();
  vm.runInContext("engineConnectionNode=document.createElement('strong');handleEngineConnection('reachable','health')",context);
  const caption=()=>vm.runInContext('engineConnectionNode.textContent',context);
  await vm.runInContext("handlePagedProcessing({jobId:'live',state:'running',settings:{mode:'batch'},pagedResults:true})",context);
  assert.equal(caption(),' (Reachable)');
  append();await vm.runInContext('handleRefreshResults(false,true)',context);
  assert.equal(caption(),' (Operational)');
  vm.runInContext("handleEngineResultConnection({engineConnection:'disconnected'})",context);
  await vm.runInContext("handlePagedProcessing({jobId:'history',state:'completed',settings:{mode:'batch'},pagedResults:true})",context);
  assert.equal(caption(),' (Unreachable)');
});


test('stream replay ignores completed runs and old requests in running runs',async()=>{
  for(const state of ['completed','running']){
    const {context,nodes}=workspace([], {host:{hostname:'host',addresses:[],os:'Linux'},engine:'laya',configured:true,model:'test'});
    await new Promise(resolve=>setImmediate(resolve));
    const original=context.fetch;
    context.fetch=(path,options)=>path.endsWith('/events')?Promise.resolve({ok:true,body:{}}):original(path,options);
    context.readEvents=async(_,receive)=>{
      receive({type:'start',engine:'laya',total:1});
      receive({type:'result',index:0,elapsedMs:1,result:{log:'old',category:'normal',elapsedMs:1,requestedAt:'2000-01-01T00:00:00Z',engineConnection:'connected'}});
      receive({type:'done',state:'completed',elapsedMs:1});
    };
    await vm.runInContext(`handleProcessing({jobId:'old',state:'${state}',settings:{mode:'batch',sources:[]},counts:{completed:1}})`,context);
    assert.equal(nodes.get('status').children[1].textContent,' (Reachable)');
  }
});


test('missing HTTP check route is distinct from an engine API error',async()=>{
  const {nodes,context}=workspace([], {host:{hostname:'host',addresses:[],os:'Linux'},engine:'laya',configured:true,model:'test'});
  await new Promise(resolve=>setImmediate(resolve));
  context.fetch=async()=>({ok:false,status:404,json:async()=>{throw Error('Not JSON');}});
  await vm.runInContext('handleCheckEngineConnection()',context);
  const connection=nodes.get('status').children[1];
  assert.equal(connection.textContent,' (Check Unavailable)');
  assert.match(connection.title,/Restart the DeciFlow UI server/);
  vm.runInContext("handleEngineResultConnection({engineConnection:'connected'})",context);
  assert.equal(connection.textContent,' (Operational)');
});

test('first page of a new stopped run updates availability without replaying old requests',async()=>{
  for(const engine of ['laya','jev']){
    const {context,nodes}=pagedWorkspace();
    vm.runInContext(`engine='${engine}';engineConnectionNode=document.createElement('strong');handleEngineConnection('check_unavailable','health')`,context);
    const requestedAt='2000-01-01T00:00:00Z';
    const original=context.fetch;
    context.fetch=async(path,options)=>{
      const response=await original(path,options);
      if(path==='/api/tasks/test-task/run')return {ok:true,json:async()=>({jobId:'new',state:'stopped',settings:{mode:'batch'},pagedResults:true})};
      if(!path.endsWith('/results'))return response;
      const data=await response.json();
      data.snapshot.state='stopped';
      data.items=[{sequence:2,result:{log:'new',engine,requestedAt,category:'normal',elapsedMs:1,engineConnection:'connected'}}];
      return {ok:true,json:async()=>data};
    };
    await runTask(nodes);
    assert.equal(vm.runInContext('engineConnectionNode.textContent',context),' (Operational)');
    vm.runInContext("handleEngineResultConnection({engineConnection:'disconnected'})",context);
    await vm.runInContext('handleRefreshResults(true)',context);
    assert.equal(vm.runInContext('engineConnectionNode.textContent',context),' (Unreachable)');
  }
});


test('Result numbers survive filtering and uncertainty stays beside the unchanged probability',async()=>{
  const first=result(0,false),second=result(7,false);
  first.result.decisionAssessments={category:{uncertain:true,reviewReasons:['low_answer_probability']}};
  const {nodes,context}=workspace([first,second]);await runTask(nodes);
  const number=row=>row.children[0].children.find(node=>node.className.includes('result-header')).children[0].textContent;
  assert.deepEqual(nodes.get('results').children.map(number),['Result #2','Result #1']);
  const card=decisionCards(nodes.get('results').children[1])[0];
  assert.equal(card.children[0].children.length,0);
  assert.match(card.children[2].textContent,/selected probability/);
  assert.equal(card.children[2].children[0].textContent,'Uncertain');
  nodes.get('log-search').value='log-7';vm.runInContext('render()',context);
  assert.deepEqual(nodes.get('results').children.map(number),['Result #2']);
});


test('Latest page numbers follow completed totals and return from an older page',async()=>{
  const {nodes,context,append}=pagedWorkspace(212);
  await vm.runInContext("handlePagedProcessing({jobId:'paged',state:'completed',settings:{mode:'batch'},pagedResults:true})",context);
  const number=()=>nodes.get('results').children[0].children[0].children.find(node=>node.className.includes('result-header')).children[0].textContent;
  assert.equal(number(),'Result #212');
  append();await vm.runInContext('handleRefreshResults(false,true)',context);
  assert.equal(number(),'Result #213');
  await nodes.get('next').onclick();
  append();await vm.runInContext('handleRefreshResults(false,true)',context);
  await nodes.get('pause-updates').onclick();
  assert.equal(number(),'Result #214');
});


test('Removed More Decision Results links open the latest results instead of freezing an old page',async()=>{
  const {nodes,context,queries}=pagedWorkspace(212);
  context.URLSearchParams=URLSearchParams;
  await vm.runInContext("handlePagedProcessing({jobId:'paged',state:'completed',settings:{mode:'batch'},pagedResults:true})",context);
  await vm.runInContext("handleApplyRunRoute('/runs/paged?result=101&detail=decisions&cursors=102&through=212')",context);
  assert.equal(vm.runInContext('page',context),0);
  assert.equal(queries.at(-1).before,undefined);
  assert.equal(logs(nodes)[0],'record-212');
  assert.equal(nodes.get('results').children[0].children[0].children.find(node=>node.className.includes('result-header')).children[0].textContent,'Result #212');
});

test('Overview selects every decision without inference and restores paged aggregates',async()=>{
  const item=result(0,false);
  Object.assign(item.result,{category:'a',criteriaGroup:'voc',profileLabel:'VOC',defaultDecision:'area',
    decisionDefinitions:{area:{label:'Area',type:'choice',criteria:{a:'A',b:'B'}},response:{label:'Response',type:'choice',criteria:{pending:'Pending',done:'Done'}},urgency:{label:'Urgency',type:'score',criteria:['Low','High']},followup:{label:'Follow-up',type:'noul'}},
    decisions:{area:{choice:'a',probabilities:{a:1,b:0}},response:{choice:'pending',probabilities:{pending:1,done:0}},urgency:{score:.5,probabilities:{0:.5,1:.5}},followup:{noul:.75}}});
  const {nodes,context,requests}=workspace([item]);await runTask(nodes);
  assert.equal(nodes.get('chart-criteria').hidden,true);
  assert.equal(nodes.get('chart-criteria-name').textContent,'VOC');
  assert.equal(nodes.get('classification-group').children.length,4);
  assert.equal(nodes.get('classification-group').value,'voc:area');
  const requestCount=requests.length;
  const values=()=>nodes.get('category-chart').children.map(row=>row.children[2].textContent);
  for(const [id,expected] of [['response',['1 (100.0%)','0 (0.0%)']],['urgency',['0 (0.0%)','1 (100.0%)']],['followup',['0 (0.0%)','0 (0.0%)','0 (0.0%)','1 (100.0%)']]]) {
    nodes.get('classification-group').value=`voc:${id}`;nodes.get('classification-group').onchange();assert.deepEqual(values(),expected);
  }
  assert.deepEqual(nodes.get('category-chart').children.map(row=>row.children[0].textContent),['Below 25%','25% to <50%','50% to <75%','75% to 100%']);
  assert.equal(nodes.get('chart-decision-note').textContent,'Chunks by Yes probability.');
  assert.equal(requests.length,requestCount);
  vm.runInContext('pagedView={summary:JSON.parse(JSON.stringify(updateResultStatistics()))};results=[];renderCategoryChart()',context);
  assert.deepEqual(values(),['0 (0.0%)','0 (0.0%)','0 (0.0%)','1 (100.0%)']);
});

test('Overview Criteria selector chooses the default decision and single decisions keep dropdowns',async()=>{
  const first=result(0,false),second=result(1,false);
  for(const [item,identity] of [[first,'one'],[second,'two']])Object.assign(item.result,{criteriaGroup:identity,profileLabel:identity,defaultDecision:'category',decisionDefinitions:{category:{label:'Category',type:'choice',criteria:{normal:'Normal'}}},decisions:{category:{choice:'normal',probabilities:{normal:1}}}});
  const {nodes}=workspace([first,second]);await runTask(nodes);
  assert.notEqual(nodes.get('chart-criteria').hidden,true);
  assert.equal(nodes.get('chart-criteria').children.length,2);
  nodes.get('chart-criteria').value='two';nodes.get('chart-criteria').onchange();
  assert.equal(nodes.get('classification-group').value,'two:category');
  assert.notEqual(nodes.get('classification-group').hidden,true);
  assert.equal(nodes.get('classification-group').children.length,1);
  assert.equal(nodes.get('category-chart').children[0].children[2].textContent,'1 (100.0%)');
});

function assessmentFixture(index=0,reverse=false) {
  const event=result(index,false);
  Object.assign(event.result,{criteriaGroup:'stable',profileId:'custom',profileLabel:'Review Fixture',defaultDecision:'area',category:'a',
    decisionDefinitions:{area:{label:'Area',type:'choice',criteria:{a:'A',b:'B'},reviewOptions:[]},response:{label:'Response',type:'choice',criteria:{done:'Done',pending:'Pending'},reviewOptions:[]},urgency:{label:'Urgency',type:'score',criteria:['Low','High']},followup:{label:'Follow-up',type:'noul'}},
    decisions:{area:{choice:'a',probabilities:reverse?{a:.52,b:.48}:{a:.95,b:.05}},response:{choice:'done',probabilities:reverse?{done:.95,pending:.05}:{done:.52,pending:.48}},urgency:{score:.5,probabilities:{0:.5,1:.5}},followup:{noul:.5}}});
  return event;
}

test('Every Choice shows its own uncertainty and chart counts; Score and Noul have no certainty groups',async()=>{
  const {nodes}=workspace([assessmentFixture()]);await runTask(nodes);
  const cards=decisionCards(nodes.get('results').children[0]);
  assert.equal(cards[0].children[2].children.length,0);
  assert.equal(cards[1].children[2].children[0].textContent,'Uncertain');
  assert.match(cards[1].children.at(-1).textContent,/Done 52.0% vs Pending 48.0%/);
  assert.equal(nodes.get('needs-review-count').textContent,'Needs Review: 1');
  assert.equal(nodes.get('chart-certain').textContent,'Certain · 1 (100.0%)');
  nodes.get('classification-group').value='stable:response';nodes.get('classification-group').onchange();
  assert.equal(nodes.get('chart-uncertain').textContent,'Uncertain · 1 (100.0%)');
  assert.equal(nodes.get('chart-certain').textContent,'Certain · 0 (0.0%)');
  nodes.get('chart-uncertain').onclick();
  for(const id of ['urgency','followup']) {
    nodes.get('classification-group').value=`stable:${id}`;nodes.get('classification-group').onchange();
    assert.equal(nodes.get('chart-certain').hidden,true);assert.equal(nodes.get('chart-uncertain').hidden,true);
    assert.match(nodes.get('chart-totals').textContent,/1 classified chunk/);
  }
});

test('Show Decisions supports multiple selections without filtering results or requesting data',async()=>{
  const failed=result(2,false);failed.result.error='timeout';
  const {context,nodes,requests}=workspace([assessmentFixture(),assessmentFixture(1,true),failed]);await runTask(nodes);
  const count=requests.length;const before=logs(nodes);
  showDecisions(context,['stable:response','stable:urgency']);
  assert.deepEqual(logs(nodes),before);
  assert.equal(nodes.get('classification-group').value,'stable:area');
  for(const row of nodes.get('results').children.slice(1))assert.deepEqual(decisionCards(row).map(card=>card.children[0].textContent),['Response (Choice)','Urgency (Score)']);
  assert.equal(nodes.get('decision-display-summary').textContent,'Show Decisions · 2');
  nodes.get('show-all-decisions').onclick();
  assert.equal(decisionCards(nodes.get('results').children[1]).length,4);
  assert.equal(requests.length,count);
});

test('Missing Choice evidence is Not Assessed and never inherited from another decision',async()=>{
  const event=assessmentFixture();delete event.result.decisions.response.probabilities;
  const {nodes}=workspace([event]);await runTask(nodes);
  nodes.get('classification-group').value='stable:response';nodes.get('classification-group').onchange();
  assert.equal(nodes.get('chart-certain').textContent,'Certain · 0 (0.0%)');
  assert.equal(nodes.get('chart-unassessed').hidden,false);
  assert.equal(nodes.get('chart-unassessed').textContent,'Not Assessed · 1 (100.0%)');
  nodes.get('chart-unassessed').onclick();
  assert.match(nodes.get('chart-totals').textContent,/1 classified chunk/);
});

test('Default chart save preserves all AI results and does not run inference',async()=>{
  const profile={label:'Review Fixture',instructions:'Use evidence.',defaultDecision:'area',questions:assessmentFixture().result.decisionDefinitions};
  const event=assessmentFixture();delete event.result.profileId;
  const {nodes,context}=workspace([event],undefined,undefined,{[sampleProfileIds.general]:profileFixture('General','General',{normal:'Normal',warning:'Warning',error:'Error',security:'Security',other:'Other'}),custom:profile});
  await runTask(nodes);
  const before=vm.runInContext('JSON.stringify(results)',context);
  const calls=[],originalFetch=context.fetch;context.fetch=(path,options)=>{calls.push({path,method:options?.method});return originalFetch(path,options);};
  nodes.get('classification-group').value='stable:followup';nodes.get('classification-group').onchange();
  assert.equal(nodes.get('set-chart-default').hidden,false);
  await nodes.get('set-chart-default').onclick();
  assert.equal(vm.runInContext('criteriaProfiles.custom.defaultDecision',context),'followup');
  assert.equal(vm.runInContext('Object.hasOwn(criteriaProfiles.custom,"primaryQuestion")',context),false);
  assert.equal(vm.runInContext('JSON.stringify(results)',context),before);
  assert.equal(nodes.get('set-chart-default').hidden,true);
  assert.deepEqual(calls,[{path:'/api/criteria',method:'POST'},{path:'/api/criteria',method:'PUT'}]);
});

test('Criteria editor saves any default type and explicit review options without a primary projection',()=>{
  const {nodes,context}=workspace([]);
  context.defaultFixture={label:'Review Fixture',instructions:'Use evidence.',defaultDecision:'followup',questions:assessmentFixture().result.decisionDefinitions};
  vm.runInContext("criteriaProfiles={[sampleProfileIds.general]:defaultFixture,custom:defaultFixture};handleEditCriteria('custom')",context);
  assert.equal(vm.runInContext('criteriaFields.primary.options.length',context),4);
  assert.equal(vm.runInContext('criteriaFields.primary.value',context),'followup');
  vm.runInContext("decisionRows[1].options[1].review.checked=true",context);
  const profile=vm.runInContext('readDecisionProfile()',context);
  assert.equal(profile.defaultDecision,'followup');assert.equal(Object.hasOwn(profile,'primaryQuestion'),false);
  assert.deepEqual(Array.from(profile.questions.response.reviewOptions),['pending']);
  assert.equal(nodes.get('criteria-editor').hidden,false);
});

test('Clear All removes result filters without changing Show Decisions',async()=>{
  const {context,nodes}=workspace([assessmentFixture(),assessmentFixture(1,true)]);await runTask(nodes);
  showDecisions(context,['stable:response']);
  nodes.get('processing-filter').value='successful';nodes.get('processing-filter').onchange();
  nodes.get('active-result-filters').children.find(node=>node.textContent==='Clear All').onclick();
  assert.equal(nodes.get('processing-filter').value,'all');
  assert.equal(logs(nodes).length,2);
  assert.equal(decisionCards(nodes.get('results').children[0]).length,1);
});

test('Failed default save preserves the previous default and all AI results',async()=>{
  const profile={label:'Review Fixture',instructions:'Use evidence.',defaultDecision:'area',questions:assessmentFixture().result.decisionDefinitions};
  const {nodes,context}=workspace([assessmentFixture()],undefined,undefined,{[sampleProfileIds.general]:profile,custom:profile});
  await runTask(nodes);const before=vm.runInContext('JSON.stringify(results)',context);
  const originalFetch=context.fetch;
  context.fetch=(path,options)=>path==='/api/criteria' && options.method==='PUT'?Promise.resolve({ok:false,json:async()=>({error:'Save failed'})}):originalFetch(path,options);
  nodes.get('classification-group').value='stable:followup';nodes.get('classification-group').onchange();
  await nodes.get('set-chart-default').onclick();
  assert.equal(nodes.get('set-chart-default').hidden,false);
  assert.match(nodes.get('chart-default-message').textContent,/Save failed/);
  assert.equal(vm.runInContext('JSON.stringify(results)',context),before);
});

test('Changing only the default keeps canonical definitions and drops obsolete visibility metadata',()=>{
  const {context}=workspace([]);
  context.systemDefaultFixture=readProfileTemplate('http_access');
  const saved=vm.runInContext("criteriaProfiles={[sampleProfileIds.general]:systemDefaultFixture,custom:systemDefaultFixture};handleEditCriteria('custom');criteriaFields.primary.value='ticket';readDecisionProfile()",context);
  assert.equal(saved.defaultDecision,'ticket');

  assert.deepEqual(JSON.parse(JSON.stringify(saved.questions)),context.systemDefaultFixture.questions);
  context.typedDefaultFixture={label:'Typed',instructions:'Evidence.',defaultDecision:'area',questions:{area:{label:'Area',type:'choice',instructions:'Choose.',criteria:{a:'A',other:'Other'}}}};
  const typed=vm.runInContext("criteriaProfiles={[sampleProfileIds.general]:systemDefaultFixture,custom:typedDefaultFixture};handleEditCriteria('custom');readDecisionProfile()",context);
  assert.equal(Object.hasOwn(typed.questions.area,'summary'),false);
  assert.deepEqual(Array.from(typed.questions.area.reviewOptions),[]);
  const expected=structuredClone(context.typedDefaultFixture.questions);expected.area.reviewOptions=[];
  assert.deepEqual(JSON.parse(JSON.stringify(typed.questions)),expected);
});

test('Opening another run starts with its default instead of the previous chart selection',async()=>{
  const events=[{type:'start',engine:'laya',total:1},assessmentFixture(),{type:'done',state:'completed'}];
  const {nodes}=workspace(events);await runTask(nodes);
  nodes.get('classification-group').value='stable:response';nodes.get('classification-group').onchange();
  nodes.get('chart-uncertain').onclick();
  const next=assessmentFixture();next.result.defaultDecision='followup';
  events[1]=next;await runTask(nodes);
  assert.equal(nodes.get('classification-group').value,'stable:followup');
  assert.equal(nodes.get('chart-all').attributes['aria-pressed'],'true');
  assert.equal(nodes.get('chart-uncertain').hidden,true);
});


test('Criteria can be empty and created with AI without a General profile', async () => {
  const { nodes, context } = workspace([], undefined, undefined, {});
  await nodes.get('nav-criteria').onclick();
  assert.equal(nodes.get('criteria-registry').children[0].textContent, 'No criteria yet. Add a profile or generate one with AI.');
  assert.equal(nodes.get('add-criteria').disabled, false);
  nodes.get('add-criteria').onclick();
  assert.equal(nodes.get('criteria-editor').hidden, false);
  assert.ok(nodes.get('criteria-editor').children.some(child=>child.className.includes('criteria-generator')));
  nodes.get('cancel-criteria').onclick();
  vm.runInContext("criteriaProfiles={[sampleProfileIds.general]:profileFixture('General','Evidence.',{normal:'Normal',warning:'Warning',error:'Error',security:'Security',other:'Other'})};renderCriteria();", context);
  await criteriaRow(nodes, 'General').children.at(-1).children.find(button=>button.textContent==='Delete').onclick();
  assert.equal(vm.runInContext('Object.keys(criteriaProfiles).length', context), 0);
  let saved;
  context.fetch=async (_path,options)=>{saved=JSON.parse(options.body);return {ok:true,json:async()=>({profiles:saved})};};
  await nodes.get('save-criteria').onclick();
  assert.deepEqual(saved, {});
  assert.equal(nodes.get('criteria-registry').children[0].textContent, 'No criteria yet. Add a profile or generate one with AI.');
});


test('History shows each saved engine and requested model instead of current server settings', async () => {
  const {nodes,context}=workspace([]);
  await new Promise(resolve=>setImmediate(resolve));
  const runs=[
    {jobId:'jev-run',state:'completed',startedAt:'2026-10-17T00:00:00Z',settings:{trigger:'manual',engine:'jev',model:'archived-jev-model'},counts:{completed:2}},
    {jobId:'laya-run',state:'completed',startedAt:'2026-10-17T01:00:00Z',settings:{trigger:'cron',engine:'laya',model:'archived-laya-model'},counts:{completed:2}},
    {jobId:'old-run',state:'failed',startedAt:'2026-10-17T02:00:00Z',settings:{trigger:'manual'},counts:{completed:0}},
  ];
  const calls=[];
  context.fetch=async path=>{calls.push(path);return {ok:true,json:async()=>({runs})};};
  vm.runInContext("engine='laya';criteriaTokenModel='current-model';registeredTasks=[{id:'one',name:'One',mode:'batch',timezone:'UTC',sources:[]}];renderTasks()",context);
  nodes.get('task-list').children[0].children[1].children.at(-1).children.find(button=>button.textContent==='History').onclick();
  await new Promise(resolve=>setImmediate(resolve));
  const table=nodes.get('task-history').children[1];
  assert.deepEqual(table.children[0].children.map(cell=>cell.textContent),['Started','Finished','Trigger','Decision Engine','Requested Model','State','Results','Manage']);
  assert.equal(table.children[1].children[3].textContent,'Jev');
  assert.equal(table.children[1].children[4].textContent,'archived-jev-model');
  assert.equal(table.children[2].children[3].textContent,'Laya');
  assert.equal(table.children[2].children[4].textContent,'archived-laya-model');
  assert.equal(table.children[3].children[3].textContent,'Not Recorded');
  assert.equal(table.children[3].children[4].textContent,'Not Recorded');
  assert.deepEqual(calls,['/api/tasks/one/runs']);
});

test('Reopened paged results retain their original engine and model through refresh and run switches', async () => {
  const {context,nodes}=pagedWorkspace(3);
  const original=context.fetch;
  let saved={engine:'jev',model:'archived-model'};
  context.fetch=async(path,options)=>{
    const response=await original(path,options);
    if(!path.endsWith('/results'))return response;
    const data=await response.json();
    Object.assign(data.snapshot.settings,saved);
    return {...response,json:async()=>data};
  };
  await vm.runInContext("handlePagedProcessing({jobId:'old',state:'completed',settings:{mode:'batch'},pagedResults:true})",context);
  const caption=()=>nodes.get('result-context').children[2].children[1].textContent;
  assert.equal(caption(),'Run Engine: Jev · Requested Model: archived-model');
  assert.equal(vm.runInContext('resultEngine',context),'jev');
  vm.runInContext("engine='laya';criteriaTokenModel='current-model'",context);
  await vm.runInContext('handleRefreshResults(false,true)',context);
  assert.equal(caption(),'Run Engine: Jev · Requested Model: archived-model');
  saved={engine:'laya',model:'another-archived-model'};
  await vm.runInContext("handlePagedProcessing({jobId:'other',state:'completed',settings:{mode:'batch'},pagedResults:true})",context);
  assert.equal(caption(),'Run Engine: Laya · Requested Model: another-archived-model');
  saved={};
  await vm.runInContext("handlePagedProcessing({jobId:'legacy',state:'completed',settings:{mode:'batch'},pagedResults:true})",context);
  assert.equal(caption(),'Run Engine: Not Recorded · Requested Model: Not Recorded');
  assert.equal(vm.runInContext('resultEngine',context),null);
});


test('Every result shows a copyable Response with exact bodies and failure diagnostics', async () => {
  const answer={type:'choice',choice:'normal',confidence:1,probabilities:{normal:1,warning:0,error:0,security:0,other:0}};
  const cases=[
    {engine:'jev',httpStatus:200,responseContentType:'application/json',providerResponse:{answersInDecisions:true,model:'saved-model'},decisions:{category:answer},decisionDefinitions:{category:{label:'Category',type:'choice',criteria:{normal:'Normal',warning:'Warning',error:'Error',security:'Security',other:'Other'}}}},
    {engine:'laya',httpStatus:200,error:'Invalid Laya response format.',responseValidationError:{path:'answers.category',message:'Missing required field: category.'},providerResponse:{answers:{}}},
    {engine:'jev',httpStatus:502,error:'Jev request failed (HTTP 502)',providerResponseText:'<script>window.bad=true</script>\nUpstream error'},
    {engine:'laya',httpStatus:200,error:'Invalid Laya response format.',providerResponseText:''},
    {engine:'jev',error:'Request timed out.',engineConnection:'timeout'},
    {engineConnection:'connected',httpStatus:200},
  ];
  const events=[{type:'start',engine:'jev',total:cases.length},...cases.map((fields,index)=>{const event=result(index);Object.assign(event.result,fields);return event;})];
  const {nodes,context}=workspace(events);
  let copied;
  context.navigator={clipboard:{writeText:async text=>{copied=text;}}};
  await runTask(nodes);
  const disclosure=row=>row.children.find(child=>child.children[0]?.textContent==='Response');
  for(let index=0;index<cases.length;index++){
    const row=nodes.get('results').children.find(row=>row.children[1].children[1].textContent===`log-${index}`);
    assert.ok(row, `Missing result ${index}: ${nodes.get("message").textContent}`);
    const response=disclosure(row);
    assert.ok(response);
    assert.match(response.className,/result-disclosure/);
    assert.ok(!response.className.includes('result-json'));
    const review=row.children.find(child=>child.children[0]?.textContent==='Review');
    if(!cases[index].error)assert.match(review.className,/result-disclosure/);
    assert.equal(response.children[1].className,'json-panel');
    const pre=response.children[1].children[1];
    assert.equal(pre.textContent,'');
    response.open=true;response.ontoggle();
    const message=JSON.parse(pre.textContent);
    if(index===0){
      assert.deepEqual(message.body,{model:'saved-model',answers:{category:answer}});
      assert.equal(cases[0].providerResponse.answersInDecisions,true);
    }
    if(index===1)assert.deepEqual(message.responseValidationError,cases[index].responseValidationError);
    if(index===2 || index===3){assert.equal(message.body,cases[index].providerResponseText);assert.equal(pre.children.length,0);}
    if(index===4){assert.equal(message.body,null);assert.match(message.message,/No provider response was received/);}
    if(index===5){assert.equal(message.body,null);assert.match(message.message,/not recorded/);}
    await response.children[1].children[0].children[0].onclick();
    assert.equal(copied,pre.textContent);
    assert.equal(response.children[1].children[0].children[1].textContent,'Copied');
    assert.equal(row.children.at(-1).children[0].textContent,'View Result JSON');
  }
  vm.runInContext('render(false)',context);
  assert.ok(nodes.get('results').children.every(row=>disclosure(row).open));
});

test('Response stays expanded across persisted page navigation without inference', async () => {
  const {context,nodes}=pagedWorkspace(60);
  await vm.runInContext("handlePagedProcessing({jobId:'responses',state:'completed',settings:{mode:'batch'},pagedResults:true})",context);
  const response=()=>nodes.get('results').children[0].children.find(child=>child.children[0]?.textContent==='Response');
  response().open=true;response().ontoggle();
  await nodes.get('next').onclick();
  assert.equal(response().open,false);
  await nodes.get('previous').onclick();
  assert.equal(response().open,true);
  assert.match(response().children[1].children[1].textContent,/not recorded/);
});


test('Result metadata is collapsed under Details while Action failures stay visible', async () => {
  const success=result(0,false),failure=result(1,false),plain=result(2,false);
  Object.assign(success.result,{source:'/host-logs/sample-logs/voc-local-gov-consulting-qna.jsonl',line:60,recordNumber:60,profile:'efb7c8ca-61c1-4785-b38d-0a86764ca758',profileLabel:'Sample VOC Local Gov Consulting QnA',chunkEvents:1,eventCount:1,actionExecution:{name:'Sample Elasticsearch',status:'success',elapsedMs:254,exitCode:0}});
  Object.assign(failure.result,{source:'ssh://host/logs',line:7,hostName:'Remote Host',hostAddress:'host',hostPort:22,actionExecution:{name:'Notify',status:'failed',elapsedMs:12,exitCode:7,error:'Connection refused'}});
  const {nodes,context}=workspace([{type:'start',engine:'laya',total:3},success,failure,plain]);
  await runTask(nodes);
  const row=index=>nodes.get('results').children.find(row=>row.children[1].children[1].textContent===`log-${index}`);
  const details=index=>row(index).children.find(child=>child.children[0]?.textContent==='Details');
  assert.equal(details(0).open,false);
  assert.equal(details(1).open,false);
  assert.equal(details(2),undefined);
  const values=Object.fromEntries(details(0).children[1].children.map(field=>[field.children[0].textContent,field.children[1].textContent]));
  assert.equal(values.Action,'Sample Elasticsearch · success · 254ms · exit 0');
  assert.equal(values.Source,'/host-logs/sample-logs/voc-local-gov-consulting-qna.jsonl · File line 60 · JSONL Record 60');
  assert.equal(values.Criteria,'Sample VOC Local Gov Consulting QnA · Chunk: 1 event (max 1)');
  assert.ok(!row(0).children.some(child=>child.className==='caption'&&child.textContent?.startsWith('Action execution:')));
  assert.ok(row(1).children.some(child=>child.className==='error-message'&&child.textContent==='Action execution: Notify · failed · 12ms · exit 7 · Connection refused'));
  const failedValues=Object.fromEntries(details(1).children[1].children.map(field=>[field.children[0].textContent,field.children[1].textContent]));
  assert.equal(failedValues.Host,'Remote Host (host:22)');
  assert.equal(failedValues.Source,'ssh://host/logs · File line 7');
  details(0).open=true;details(0).ontoggle();
  vm.runInContext('render(false)',context);
  assert.equal(details(0).open,true);
  const json=row(0).children.at(-1);json.open=true;json.ontoggle();
  const saved=JSON.parse(json.children[1].children[1].textContent);
  assert.equal(saved.source,success.result.source);
  assert.equal(saved.recordNumber,60);
  assert.deepEqual(saved.actionExecution,success.result.actionExecution);
});

test('Details expansion survives persisted pagination without new engine checks or inference', async () => {
  const {context,nodes}=pagedWorkspace(60);
  await new Promise(resolve=>setImmediate(resolve));
  const original=context.fetch,paths=[];
  context.fetch=async(path,options)=>{
    paths.push(path);
    const response=await original(path,options);
    if(!path.endsWith('/results'))return response;
    const data=await response.json();
    for(const item of data.items || [])Object.assign(item.result,{source:'/logs/input.log',line:item.sequence,profile:'4e6d5417-611e-49e0-8e23-2444a0f49ee4',chunkEvents:1});
    return {...response,json:async()=>data};
  };
  await vm.runInContext("handlePagedProcessing({jobId:'metadata',state:'completed',settings:{mode:'batch'},pagedResults:true})",context);
  const details=()=>nodes.get('results').children[0].children.find(child=>child.children[0]?.textContent==='Details');
  assert.equal(details().open,false);
  const calls=paths.length;
  details().open=true;details().ontoggle();
  assert.equal(paths.length,calls);
  await nodes.get('next').onclick();assert.equal(details().open,false);
  await nodes.get('previous').onclick();assert.equal(details().open,true);
  assert.ok(paths.every(path=>path==='/api/settings'||path==='/api/tasks'||path.endsWith('/results')));
});


test('Result scroll buttons use the results pane on desktop and section alignment on mobile', async () => {
  const {nodes,context}=workspace([{type:'start',engine:'laya',total:1},result(0,false)]);
  vm.runInContext('render()',context);
  assert.equal(nodes.get('result-scroll-controls').hidden,true);
  await runTask(nodes);
  assert.equal(nodes.get('result-scroll-controls').hidden,false);
  const panel=context.document.getElementById('classification-results'),scrolls=[],alignments=[];
  panel.scrollHeight=900;panel.scrollTo=options=>scrolls.push(options);panel.scrollIntoView=options=>alignments.push(options);
  context.getComputedStyle=()=>({overflowY:'auto'});
  context.matchMedia=()=>({matches:false});
  context.fetch=()=>{throw Error('Scrolling must not make API requests');};
  nodes.get('results-scroll-top').onclick();nodes.get('results-scroll-bottom').onclick();
  assert.deepEqual(JSON.parse(JSON.stringify(scrolls)),[{top:0,behavior:'smooth'},{top:900,behavior:'smooth'}]);
  assert.equal(alignments.length,0);
  context.getComputedStyle=()=>({overflowY:'visible'});
  context.matchMedia=()=>({matches:true});
  nodes.get('results-scroll-top').onclick();nodes.get('results-scroll-bottom').onclick();
  assert.deepEqual(JSON.parse(JSON.stringify(alignments)),[{block:'start',behavior:'auto'},{block:'end',behavior:'auto'}]);
  assert.equal(scrolls.length,2);
  vm.runInContext('completed=0;results=[];completionOrder=[];render()',context);
  assert.equal(nodes.get('result-scroll-controls').hidden,true);
});

test('Configurations show override sources and save only explicitly enabled fields',async()=>{
  const {nodes,context}=workspace([]);let saved,reloaded=0;const calls=[];
  const fields=[
    {key:'DECISION_ENGINE',label:'Decision Engine',group:'Engine',options:['laya','jev'],value:'laya',fallback:'laya',source:'Default',help:'No automatic fallback.',reference:'Decision engine: laya or jev.'},
    {key:'LAYA_API_URL',label:'API URL',group:'Laya',value:'http://localhost:8000/v1/systemone',fallback:'http://localhost:8000/v1/systemone',source:'Environment',help:'Full URL.',reference:'Include /v1/systemone.'},
  ];
  const metadata={resultsPerPage:30,fields,overrides:{},environment:[],credentials:{JEV_API_KEY:false}};
  context.location={reload(){reloaded++;}};
  context.fetch=async(path,options)=>{
    calls.push(path);assert.equal(path,'/api/configuration');
    if(options.method==='PUT')saved=JSON.parse(options.body);
    return {ok:true,json:async()=>metadata};
  };
  await vm.runInContext('handleLoadRuntimeConfiguration()',context);
  assert.equal(nodes.get('save-results-settings').disabled,false);
  assert.equal(vm.runInContext("runtimeControls.get('DECISION_ENGINE').input.disabled",context),true);
  vm.runInContext("runtimeControls.get('LAYA_API_URL').checkbox.checked=true;runtimeControls.get('LAYA_API_URL').checkbox.onchange();runtimeControls.get('LAYA_API_URL').input.value='http://localhost:9000/v1/systemone'",context);
  nodes.get('results-per-page').value='50';
  await nodes.get('results-settings-form').onsubmit({preventDefault(){}});
  assert.deepEqual(saved,{resultsPerPage:50,runtimeOverrides:{LAYA_API_URL:'http://localhost:9000/v1/systemone'}});
  assert.equal(reloaded,1);
  assert.deepEqual(calls,['/api/configuration','/api/configuration']);
  vm.runInContext("runtimeControls.get('LAYA_API_URL').checkbox.checked=false;runtimeControls.get('LAYA_API_URL').checkbox.onchange()",context);
  assert.equal(vm.runInContext("runtimeControls.get('LAYA_API_URL').input.value",context),fields[1].fallback);
});

test('Restart confirmation defaults to cancel and does not request restart on cancellation',async()=>{
  const {nodes,context}=workspace([]);const calls=[];
  context.fetch=async(path)=>{calls.push(path);assert.equal(path,'/api/reset/status');return {ok:true,json:async()=>({activeRuns:2})};};
  const dialog=context.document.getElementById('maintenance-dialog');dialog.showModal=()=>{};
  const pending=nodes.get('restart-deciflow').onclick();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(dialog.returnValue,'cancel');
  assert.match(nodes.get('maintenance-description').textContent,/2 active runs/);
  assert.equal(nodes.get('maintenance-approve').className,'warning');
  dialog.onclose();await pending;
  assert.ok(calls.every(path=>path==='/api/reset/status'));
});

test('Criteria ID is read-only and copyable in View and Edit; rename keeps it and Clone creates a fresh UUID',async()=>{
  const id=sampleProfileIds.general;
  const {context,nodes}=workspace([],undefined,undefined,{[id]:systemProfile});
  await nodes.get('nav-criteria').onclick();
  const copied=[];context.navigator={clipboard:{writeText:async value=>copied.push(value)}};
  vm.runInContext('handleViewCriteria(sampleProfileIds.general)',context);
  const identity=nodes.get('criteria-view').children.find(node=>node.className?.includes('view-details')).children.find(field=>field.children[0].textContent==='Criteria ID').children[1].children[0];
  assert.equal(identity.children[0].textContent,id);
  assert.equal(identity.children[0].attributes['aria-label'],'Criteria ID');
  await identity.children[1].onclick();
  assert.deepEqual(copied,[id]);assert.equal(identity.children[2].textContent,'Copied');
  vm.runInContext('handleEditCriteria(sampleProfileIds.general)',context);
  const panel=nodes.get('criteria-editor').children.find(node=>node.className==='criteria-section profile-settings');
  const editIdentity=panel.children[1].children[0].children[1].children[0];
  assert.equal(editIdentity.children[0].textContent,id);
  assert.equal(vm.runInContext('criteriaFields.id',context),undefined);
  await editIdentity.children[1].onclick();assert.deepEqual(copied,[id,id]);
  vm.runInContext("criteriaFields.label.value='Renamed';",context);
  await nodes.get('save-criteria').onclick();
  assert.equal(vm.runInContext('criteriaProfiles[sampleProfileIds.general].label',context),'Renamed');
  vm.runInContext('handleEditCriteria(sampleProfileIds.general)',context);
  assert.equal(vm.runInContext('criteriaDraftId',context),id);
  vm.runInContext('handleCloneCriteria(sampleProfileIds.general)',context);
  const clone=vm.runInContext('criteriaDraftId',context);
  assert.notEqual(clone,id);assert.match(clone,/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  assert.equal(vm.runInContext('criteriaProfiles[sampleProfileIds.general].label',context),'Renamed');
});

test('Criteria ID copy failure keeps the ID selectable and allows retry',async()=>{
  const {context}=workspace([]);
  context.navigator={clipboard:{writeText:async()=>{throw Error('Clipboard unavailable');}}};
  const value=vm.runInContext('criteriaIdentityValue(sampleProfileIds.local_gov)',context);
  await value.children[1].onclick();
  assert.equal(value.children[0].textContent,sampleProfileIds.local_gov);
  assert.equal(value.children[2].textContent,'Copy failed. Select and copy the ID.');
  assert.equal(value.children[1].disabled,false);
});


test('Show Decisions groups multiple Criteria and preserves distinct checkbox keys',()=>{
  const {context,nodes}=workspace([]);
  vm.runInContext(`renderDecisionDisplay({
    'one:area':{identity:'one',criteria:'First Criteria',label:'Area'},
    'two:area':{identity:'two',criteria:'Second Criteria',label:'Area'}
  })`,context);
  const groups=nodes.get('decision-display-options').children;
  assert.deepEqual(groups.map(group=>group.children[0].textContent),['First Criteria','Second Criteria']);
  assert.equal(groups[0].children[1].children[0].checked,true);
  assert.equal(groups[1].children[1].children[0].attributes['aria-label'],'Second Criteria · Area');
});

test('Processing Status filters result cards independently of displayed decisions',async()=>{
  const html=readFileSync(new URL('../public/index.html',import.meta.url),'utf8');
  assert.doesNotMatch(html,/id="(?:decision-filter|certainty-filter|category-filter|category-selection)"/);
  const failed=result(2,false);failed.result.error='Invalid response';
  const {context,nodes}=workspace([assessmentFixture(),assessmentFixture(1,true),failed]);await runTask(nodes);
  showDecisions(context,['stable:response']);
  const select=nodes.get('processing-filter');
  select.value='successful';select.onchange();assert.deepEqual(logs(nodes),['log-1','log-0']);
  select.value='failed';select.onchange();assert.deepEqual(logs(nodes),['log-2']);
  select.value='all';select.onchange();assert.equal(logs(nodes).length,3);
  assert.equal(decisionCards(nodes.get('results').children[1]).length,1);
});

test('Archived display changes preserve paging and avoid server requests while processing filters use the API',async()=>{
  const {context,nodes}=workspace([assessmentFixture(),assessmentFixture(1,true)]);await runTask(nodes);
  const summary=vm.runInContext('updateResultStatistics()',context);
  const items=vm.runInContext('results.map((result,index)=>({sequence:index+1,result}))',context);
  const queries=[];
  context.fetch=async(path,options)=>{
    assert.equal(path,'/api/jobs/scope/results');queries.push(JSON.parse(options.body));
    return {ok:true,json:async()=>({snapshot:{jobId:'scope',state:'completed',settings:{mode:'batch'}},summary:{...summary,hosts:Object.fromEntries(summary.hosts),sources:Object.fromEntries(summary.sources)},items,sequence:2,limit:30,hasNext:false})};
  };
  context.scopeItems=items;context.scopeSummary=summary;context.URLSearchParams=URLSearchParams;
  vm.runInContext("pagedView={id:'scope',items:scopeItems,summary:scopeSummary,revision:0,cursors:[null,3]};page=1;render(false,true)",context);
  const pageInfo=nodes.get('page-info').textContent;
  showDecisions(context,['stable:response','stable:urgency']);
  assert.equal(queries.length,0);assert.equal(vm.runInContext('page',context),1);
  assert.equal(nodes.get('page-info').textContent,pageInfo);
  assert.equal(decisionCards(nodes.get('results').children[0]).length,2);
  const select=nodes.get('processing-filter');select.value='successful';await select.onchange();
  assert.equal(queries.at(-1).processing,'successful');
  assert.equal(Object.hasOwn(queries.at(-1),'decision'),false);
  await vm.runInContext("handleApplyRunRoute('/runs/scope?processing=successful&show=%5B%22stable%3Aresponse%22%2C%22stable%3Aurgency%22%5D')",context);
  assert.equal(select.value,'successful');
  assert.equal(decisionCards(nodes.get('results').children[0]).length,2);
});

test('Show Decisions keeps cards from other Criteria and resets for another run',async()=>{
  const other=assessmentFixture(1);other.result.criteriaGroup='other';other.result.profileLabel='Other Criteria';
  const {context,nodes}=workspace([assessmentFixture(),other]);await runTask(nodes);
  showDecisions(context,['stable:response']);
  assert.deepEqual(logs(nodes),['log-1','log-0']);
  const unrelated=nodes.get('results').children[0];
  assert.equal(decisionCards(unrelated)[0].textContent,'No decisions selected for this result.');
  assert.equal(decisionCards(nodes.get('results').children[1])[0].children[0].textContent,'Response (Choice)');
  vm.runInContext('handleResetChart();render()',context);
  assert.equal(nodes.get('decision-display-summary').textContent,'Show Decisions · All');
  assert.equal(decisionCards(nodes.get('results').children[0]).length,4);
});


test('Show Decisions closes outside and on Escape while inside clicks preserve the menu',()=>{
  const {context,nodes}=workspace([]);
  context.inside={};context.outside={};context.focused=false;
  const menu=context.document.getElementById('decision-display-menu');menu.contains=target=>target===context.inside;
  context.document.getElementById('decision-display-summary').focus=()=>{context.focused=true;};
  context.fetch=()=>{throw Error('Dismissal must not fetch');};
  menu.open=true;vm.runInContext('handleDecisionDisplayOutsideClick({target:inside})',context);
  assert.equal(menu.open,true);
  vm.runInContext('handleDecisionDisplayOutsideClick({target:outside})',context);assert.equal(menu.open,false);
  menu.open=true;vm.runInContext("handleDecisionDisplayKeydown({key:'Tab'})",context);assert.equal(menu.open,true);
  vm.runInContext("handleDecisionDisplayKeydown({key:'Escape',preventDefault(){}})",context);
  assert.equal(menu.open,false);assert.equal(context.focused,true);
  const html=readFileSync(new URL('../public/index.html',import.meta.url),'utf8');
  const types=html.match(/<select id="result-filter-type"[^]*?<\/select>/)[0];
  assert.match(types,/<select[^>]*>\s*<option value="log-search">Search Text/);
  assert.equal(nodes.get('result-filter-type').value,'log-search');
});


test('Run status uses Task badge styles beside original engine metadata for every state',()=>{
  const {context,nodes}=workspace([]);
  const badge=nodes.get('run-state');
  for(const state of ['running','starting','pausing','paused','stopped','skipped','completed','failed']){
    vm.runInContext(`renderResultContext('Run','2026-10-20T00:00:00Z','example',{engine:'jev',model:'archived-model'});handleRunProgress('${state}','batch')`,context);
    const row=nodes.get('result-context').children[2];
    assert.equal(row.className,'run-engine-context');
    assert.equal(row.children[0],badge);assert.equal(badge.hidden,false);
    assert.equal(badge.className,`task-state monitor-state ${state}`);
    assert.equal(badge.textContent,state[0].toUpperCase()+state.slice(1));
    assert.match(row.children[1].textContent,/Jev.*archived-model/);
    assert.equal(nodes.get('message').textContent,'');
  }
  vm.runInContext("handleRunProgress('unknown','batch')",context);assert.equal(badge.hidden,true);
});


test('Review Status shows whole-run counts and excludes processing failures from both review groups',async()=>{
  const failed=result(2,true);failed.result.error='timeout';
  const {context,nodes}=workspace([result(0,false),result(1,true),failed]);await runTask(nodes);
  const select=nodes.get('review-filter');
  const labels=()=>select.options.map(option=>option.text);
  assert.deepEqual(labels(),['All Results (3)','Needs Review (1)','No Review Needed (1)']);
  select.value='needs-review';select.onchange();
  assert.equal(select.value,'needs-review');assert.deepEqual(logs(nodes),['log-1']);
  assert.deepEqual(labels(),['All Results (3)','Needs Review (1)','No Review Needed (1)']);
  context.largeReviewCounts={total:4000,failed:20,review:3261};
  vm.runInContext('renderReviewFilter(largeReviewCounts);renderResultFilters()',context);
  assert.deepEqual(labels(),['All Results (4,000)','Needs Review (3,261)','No Review Needed (719)']);
  assert.equal(select.value,'needs-review');
  assert.equal(nodes.get('active-result-filters').children[0].textContent,'Review Status: Needs Review ×');
});

test('Paged Review Status counts use the whole archived run rather than its current page',async()=>{
  const {context,nodes}=pagedWorkspace(1000);
  await vm.runInContext("handlePagedProcessing({jobId:'paged',state:'completed',settings:{mode:'batch'},pagedResults:true})",context);
  assert.equal(nodes.get('results').children.length,50);
  assert.deepEqual(nodes.get('review-filter').options.map(option=>option.text),['All Results (1,000)','Needs Review (0)','No Review Needed (1,000)']);
});


test('Saving a chart default survives a fresh Main page without opening Criteria',async()=>{
  let profiles={custom:{label:'Review Fixture',instructions:'Use evidence.',defaultDecision:'area',questions:assessmentFixture().result.decisionDefinitions}};
  const first=workspace([assessmentFixture()],undefined,undefined,profiles);await runTask(first.nodes);
  const original=first.context.fetch;
  first.context.fetch=async(path,options)=>{
    if(path==='/api/criteria'){
      if(options.method==='PUT')profiles=JSON.parse(options.body);
      return {ok:true,json:async()=>({profiles})};
    }
    return original(path,options);
  };
  first.nodes.get('classification-group').value='stable:response';first.nodes.get('classification-group').onchange();
  await first.nodes.get('set-chart-default').onclick();assert.equal(profiles.custom.defaultDecision,'response');
  const status={host:{hostname:'host',addresses:[],os:'Linux'},engine:'laya',configured:true,model:'test',chartDefaults:{custom:profiles.custom.defaultDecision}};
  const fresh=workspace([assessmentFixture()],status);await runTask(fresh.nodes);await new Promise(resolve=>setImmediate(resolve));
  assert.equal(vm.runInContext('Object.keys(criteriaProfiles).length',fresh.context),0);
  assert.equal(fresh.nodes.get('classification-group').value,'stable:response');
  assert.equal(fresh.nodes.get('classification-group').options.find(option=>option.value==='stable:response').text,'Response (Default)');
  assert.equal(fresh.nodes.get('set-chart-default').hidden,true);
  assert.equal(vm.runInContext('results[0].defaultDecision',fresh.context),'area');
});

test('Late default metadata corrects snapshot defaults without overriding a manual chart choice',async()=>{
  for(const manual of [false,true]){
    let release;const status=new Promise(resolve=>{release=resolve;});
    const {context,nodes}=workspace([assessmentFixture()],status);await runTask(nodes);
    assert.equal(nodes.get('classification-group').value,'stable:area');
    if(manual){nodes.get('classification-group').value='stable:urgency';nodes.get('classification-group').onchange();}
    release({host:{hostname:'host',addresses:[],os:'Linux'},engine:'laya',configured:true,model:'test',chartDefaults:{custom:'response'}});
    await new Promise(resolve=>setImmediate(resolve));
    assert.equal(nodes.get('classification-group').value,manual?'stable:urgency':'stable:response');
    assert.equal(nodes.get('classification-group').options.find(option=>option.value==='stable:response').text,'Response (Default)');
    assert.equal(vm.runInContext('results[0].defaultDecision',context),'area');
  }
});


test('Chart default action shares the Decision control row',()=>{
  const html=readFileSync(new URL('../public/index.html',import.meta.url),'utf8');
  assert.match(html,/<dd class="chart-decision-control">[^]*?id="classification-group"[^]*?id="set-chart-default"[^>]*>Set as Default<\/button><\/dd>/);
});


test('SSH test results share success, failure, checking and approval colors across editor and list',()=>{
  const {context,nodes}=workspace([]);
  const cases=[[null,'connection-unchecked'],[{checking:true},'connection-checking'],[{connected:true},'connection-ok'],[{connected:false,error:'Denied'},'connection-failed'],[{connected:false,hostKey:{fingerprint:'SHA256:test'}},'connection-warning'],[{changed:true},'connection-warning']];
  for(const [result,expected] of cases){
    context.connectionFixture=result;
    assert.equal(vm.runInContext('connectionStatusClass(connectionFixture)',context),expected);
    vm.runInContext('renderHostTestResult(connectionFixture)',context);
    assert.equal(nodes.get('ssh-host-test-result').className,`caption ssh-connection-result ${expected}`);
  }
  assert.match(vm.runInContext("connectionStatus({hostKey:{}})",context),/^Approval Required/);
  nodes.get('ssh-host-form').oninput();
  assert.equal(nodes.get('ssh-host-test-result').textContent,'');
  assert.match(nodes.get('ssh-host-test-result').className,/connection-unchecked/);
});


test('Selected Source paths use the same plain multiline format before and after changing Source',()=>{
  const {context,nodes}=workspace([]);
  context.multipleSourcePaths='/var/log/messages\n/var/log/secure';
  vm.runInContext(`registeredSources=[{id:'multi',name:'Remote System Log',type:'ssh',path:multipleSourcePaths},{id:'single',name:'Single',type:'local',path:'/var/log/app.log'}];updateSourceSettings(['multi'])`,context);
  const row=nodes.get('source-settings').children[0];
  const path=row.children[0].children[1];
  assert.equal(path.textContent,context.multipleSourcePaths);
  vm.runInContext("sourceRows[0].name.value='single';sourceRows[0].name.onchange()",context);
  assert.equal(path.textContent,'/var/log/app.log');
  vm.runInContext("sourceRows[0].name.value='multi';sourceRows[0].name.onchange()",context);
  assert.equal(path.textContent,context.multipleSourcePaths);
});

test('HDFS Source exposes connection settings without connecting on edit or View', async () => {
  const {nodes,context}=workspace([],null);
  await new Promise(resolve=>setImmediate(resolve));
  context.hdfsSource={id:'00000000000000000000000000000009',name:'HDFS Data',type:'hdfs',endpoint:'hdfs://namenode.example.test:8020',host:'namenode.example.test',port:8020,path:'/data/*.jsonl',format:'jsonl',contentField:'text',username:'reader',ticketCache:'/run/hdfs-ticket'};
  vm.runInContext('registeredSources=[hdfsSource];sourcesLoaded=true;registeredTasks=[];',context);
  const requests=[];
  context.fetch=async(path,options)=>{if(path==='/api/delete-check')return {ok:true,json:async()=>({references:[],details:[]})};requests.push({path,options});return {ok:true,json:async()=>({connected:true,fileCount:3})};};
  vm.runInContext('handleEditSource(0)',context);
  assert.equal(requests.length,0);
  assert.equal(vm.runInContext('sourceFields.endpoint.parentElement.hidden',context),false);
  assert.equal(vm.runInContext('sourceFields.endpoint.value',context),'hdfs://namenode.example.test:8020');
  assert.equal(vm.runInContext('sourceFields.host',context),undefined);
  assert.equal(vm.runInContext('sourceFields.port',context),undefined);
  const hostHelp=vm.runInContext('sourceFields.endpoint.parentElement.children[0].textContent',context);
  assert.ok(hostHelp.includes('hdfs://hostname:port'));
  assert.ok(hostHelp.includes('fs.defaultFS'));
  assert.ok(hostHelp.includes('HADOOP_CONF_DIR'));
  assert.ok(hostHelp.includes('/etc/hadoop/conf'));
  assert.match(vm.runInContext('sourceFields.path.placeholder',context),/^\/warehouse\//);
  assert.ok(vm.runInContext('sourceFields.path.parentElement.children[0].textContent',context).includes('without hdfs://'));
  assert.equal(vm.runInContext('sourceFields.ticketCache.value',context),'/run/hdfs-ticket');
  const form=nodes.get('source-editor').children[0];
  const button=form.children.find(item=>item.textContent==='Test Connection');
  assert.equal(button.hidden,false);
  await button.onclick();
  assert.equal(requests[0].path,'/api/sources/hdfs-test');
  assert.equal(JSON.parse(requests[0].options.body).endpoint,'hdfs://namenode.example.test:8020');
  assert.ok(form.children.some(item=>item.textContent.includes('Connected (HDFS (Native))')));
  let rejectTest;context.fetch=()=>new Promise((resolve,reject)=>{rejectTest=reject;});
  const pending=button.onclick();
  vm.runInContext('sourceFields.endpoint.value="hdfs://changed.example.test:8020";sourceFields.endpoint.oninput()',context);
  rejectTest(new Error('Stale connection failure'));await pending;
  assert.equal(form.children.some(item=>item.textContent.includes('Stale connection failure')),false);
  vm.runInContext('sourceFields.type.value="local";sourceFields.type.onchange()',context);
  assert.equal(button.hidden,true);
  assert.equal(vm.runInContext('sourceFields.endpoint.parentElement.hidden',context),true);
  assert.match(vm.runInContext('sourceFields.path.placeholder',context),/^\/var\/log\//);
  vm.runInContext('handleCloseSource();renderSources()',context);
  const table=nodes.get('source-registry').children[0];
  table.children[1].children.at(-1).children[0].onclick();
  assert.equal(requests.length,1);
  assert.equal(vm.runInContext('sourceTypeLabel(hdfsSource)',context),'HDFS (Native)');
});

 test('WebHDFS Source shows HTTP fields and shares the explicit connection test', async () => {
  const {nodes,context}=workspace([],null);
  await new Promise(resolve=>setImmediate(resolve));
  context.webSource={id:'00000000000000000000000000000009',name:'Web Data',type:'webhdfs',endpoint:'https://nn.test:9871',host:'nn.test',port:9871,path:'/data',format:'text',username:'reader',tokenFile:'/run/token',caFile:'/run/ca.pem'};
  vm.runInContext('registeredSources=[webSource];sourcesLoaded=true;registeredTasks=[];handleEditSource(0)',context);
  for(const field of ['endpoint','username','tokenFile','caFile'])assert.equal(vm.runInContext(`sourceFields.${field}.parentElement.hidden`,context),false);
  for(const field of ['ticketCache'])assert.equal(vm.runInContext(`sourceFields.${field}.parentElement.hidden`,context),true);
  assert.match(vm.runInContext('sourceFields.path.placeholder',context),/^\/warehouse\//);
  assert.ok(vm.runInContext('sourceFields.path.parentElement.children[0].textContent',context).includes('HTTP(S) endpoint'));
  const requests=[];context.fetch=async(path,options)=>{requests.push({path,options});return {ok:true,json:async()=>({connected:true,fileCount:2})};};
  const form=nodes.get('source-editor').children[0];
  await form.children.find(item=>item.textContent==='Test Connection').onclick();
  assert.equal(JSON.parse(requests[0].options.body).endpoint,'https://nn.test:9871');
  assert.ok(form.children.some(item=>item.textContent.includes('Connected (HDFS (WebHDFS))')));
  assert.equal(vm.runInContext('sourceTypeLabel(webSource)',context),'HDFS (WebHDFS)');
});


test('Existing Criteria can be revised with AI without changing identity or saving automatically', async()=>{
  const original=readProfileTemplate('general');
  const revised=structuredClone(original);revised.instructions='AI revised rules.';
  const id=sampleProfileIds.general;
  const {nodes,context}=workspace([],undefined,undefined,{[id]:original});
  await nodes.get('nav-criteria').onclick();vm.runInContext('handleEditCriteria(sampleProfileIds.general)',context);
  vm.runInContext("criteriaFields.instructions.value='Unsaved local rules.'",context);
  const walk=node=>[node,...(node.children || []).flatMap(child=>typeof child==='object'?walk(child):[])];
  const generator=walk(nodes.get('criteria-editor')).find(node=>node.className?.includes('criteria-generator'));
  assert.equal(generator.children[0].textContent,'Generate With AI');
  const purpose=walk(generator).find(node=>node.attributes?.['aria-label']==='Additional Instructions');
  const generate=walk(generator).find(node=>node.textContent==='Generate Criteria' && node.onclick);
  assert.equal(generate.disabled,false);purpose.value='Clarify missing evidence.';
  const originalFetch=context.fetch;let body;
  context.fetch=async(path,options)=>{
    if(path==='/api/criteria/generate'){body=JSON.parse(options.body);return {ok:true,json:async()=>({profile:revised,analysisPurpose:purpose.value})};}
    return originalFetch(path,options);
  };
  await generate.onclick();
  assert.equal(body.currentProfile.instructions,'Unsaved local rules.');assert.deepEqual(body.samples,[]);
  assert.equal(vm.runInContext('editingCriteria',context),id);
  assert.equal(vm.runInContext('criteriaDraftId',context),id);
  assert.equal(vm.runInContext('criteriaFields.instructions.value',context),'AI revised rules.');
  assert.equal(vm.runInContext('criteriaProfiles[sampleProfileIds.general].instructions',context),original.instructions);
  await nodes.get('save-criteria').onclick();
  assert.equal(vm.runInContext('Object.keys(criteriaProfiles).length',context),1);
  assert.equal(vm.runInContext('criteriaProfiles[sampleProfileIds.general].instructions',context),'AI revised rules.');
});

test('AI revision ignores replies for changed or reopened editor drafts',async()=>{
  const original=readProfileTemplate('general');const revised={...original,instructions:'Stale AI rules.'};
  for(const reopen of [false,true]){
    const {nodes,context}=workspace([],undefined,undefined,{[sampleProfileIds.general]:original});
    await nodes.get('nav-criteria').onclick();vm.runInContext('handleEditCriteria(sampleProfileIds.general)',context);
    const walk=node=>[node,...(node.children || []).flatMap(child=>typeof child==='object'?walk(child):[])];
    const generator=walk(nodes.get('criteria-editor')).find(node=>node.className?.includes('criteria-generator'));
    const purpose=walk(generator).find(node=>node.attributes?.['aria-label']==='Additional Instructions');purpose.value='Revise rules';
    let finish;const originalFetch=context.fetch;
    context.fetch=(path,options)=>path==='/api/criteria/generate'?new Promise(resolve=>{finish=resolve;}):originalFetch(path,options);
    const pending=walk(generator).find(node=>node.textContent==='Generate Criteria' && node.onclick).onclick();
    if(reopen)vm.runInContext('handleCloseCriteria();handleEditCriteria(sampleProfileIds.general)',context);
    vm.runInContext("criteriaFields.instructions.value='Latest manual rules.'",context);
    finish({ok:true,json:async()=>({profile:revised,analysisPurpose:'Revise rules'})});await pending;
    assert.equal(vm.runInContext('criteriaFields.instructions.value',context),'Latest manual rules.');
  }
});

test('Reference dialogs fetch fresh details only when clicked and distinguish loading failures',async()=>{
  const {nodes,context}=workspace([]);await new Promise(resolve=>setImmediate(resolve));
  const dialog=context.document.getElementById('references-dialog');dialog.showModal=()=>{dialog.open=true;};
  const calls=[];let details=[{relation:'Task Assignment',id:'task-id',name:'Worker',status:'Disabled',mode:'batch',sourceIds:['source-id'],sourceNames:['Logs']}];
  context.fetch=async(path,options)=>{calls.push({path,body:JSON.parse(options.body)});return {ok:true,json:async()=>({references:['Task: Worker'],details})};};
  const button=vm.runInContext("referenceButton('Source','source-id','Logs')",context);
  assert.equal(calls.length,0);await button.onclick();
  assert.equal(calls[0].path,'/api/delete-check');assert.deepEqual(calls[0].body,{kind:'Source',id:'source-id'});
  assert.equal(nodes.get('references-title').textContent,'Source References');
  assert.match(nodes.get('references-summary').textContent,/1 reference/);
  const table=nodes.get('references-content').children[0];
  assert.deepEqual(table.children[0].children.map(cell=>cell.textContent),['Type','Name','ID']);
  const row=table.children[1];assert.equal(row.children[0].textContent,'Task');
  assert.equal(row.children[1].textContent,'Worker');
  assert.equal(row.children[1].children.length,0);
  assert.equal(row.children[2].children[0].textContent,'task-id');
  for(const cell of row.children.slice(2)){
    assert.equal(cell.children[0].attributes.href,'/tasks/task-id');
    assert.equal(cell.children[0].attributes.target,'_blank');
  }
  details=[];await button.onclick();assert.equal(nodes.get('references-summary').textContent,'No references.');
  context.fetch=async()=>({ok:false,json:async()=>({error:'Unavailable'})});await button.onclick();
  assert.match(nodes.get('references-summary').textContent,/Could not load references/);
});

test('Views show reference details above configuration and isolate late replies',async()=>{
  const {nodes,context}=workspace([]);await new Promise(resolve=>setImmediate(resolve));
  let finish;
  context.fetch=()=>new Promise(resolve=>{finish=resolve;});
  vm.runInContext("handleViewConfiguration('source-view','Logs',[['Name','Logs']],{kind:'Source',id:'logs'})",context);
  const view=nodes.get('source-view');const old=view.children[1];
  assert.equal(view.children[0].children.length,1);
  assert.equal(old.children[0].textContent,'References');
  assert.equal(old.children[1].textContent,'Loading references…');
  finish({ok:true,json:async()=>({details:[{relation:'Task Assignment',name:'Worker',id:'task-id',status:'Disabled'}]})});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(old.children[2].children[0].children[1].children[1].textContent,'Worker');
  vm.runInContext("handleViewConfiguration('source-view','Other',[['Name','Other']],{kind:'Source',id:'other'})",context);
  const pending=finish;
  vm.runInContext("handleViewConfiguration('source-view','Latest',[['Name','Latest']],{kind:'Source',id:'latest'})",context);
  pending({ok:true,json:async()=>({details:[]})});await new Promise(resolve=>setImmediate(resolve));
  assert.equal(view.children[1].children[1].textContent,'Loading references…');
  finish({ok:false,json:async()=>({error:'Unavailable'})});await new Promise(resolve=>setImmediate(resolve));
  assert.match(view.children[1].children[1].textContent,/Could not load references/);
});


test('Run URLs restore chart choices, certainty, visible decisions and filter controls without inference',async()=>{
  const navigation={pathname:'/',search:'',hash:''};
  const {context,nodes}=workspace([assessmentFixture()],undefined,undefined,undefined,navigation);
  await runTask(nodes);enableCleanRoutes(context,navigation);navigation.pathname='/runs/test-job';
  vm.runInContext("const summary=updateResultStatistics();pagedView={id:'test-job',summary,cursors:[null],items:[],through:1};currentView='main';",context);
  nodes.get('classification-group').value='stable:response';nodes.get('classification-group').onchange();
  nodes.get('chart-uncertain').onclick();showDecisions(context,['stable:response']);
  nodes.get('result-filter-type').value='review-filter';nodes.get('result-filter-type').onchange();
  const path=navigation.pathname+navigation.search;const params=new URLSearchParams(navigation.search);
  assert.equal(params.get('chart'),'stable:response');assert.equal(params.get('certainty'),'uncertain');
  assert.deepEqual(JSON.parse(params.get('show')),['stable:response']);assert.equal(params.get('filter'),'review-filter');
  let fetches=0;context.fetch=async()=>{fetches++;throw Error('Unexpected request');};
  vm.runInContext("handleResetChart();handleRefreshResults=async()=>render(false,true)",context);
  await vm.runInContext(`handleApplyRunRoute(${JSON.stringify(path)})`,context);
  assert.equal(nodes.get('classification-group').value,'stable:response');
  assert.equal(vm.runInContext('chartCertainty',context),'uncertain');
  assert.equal(vm.runInContext('[...shownDecisionKeys].join()',context),'stable:response');
  assert.equal(nodes.get('result-filter-type').value,'review-filter');assert.equal(fetches,0);
  await vm.runInContext("handleApplyRunRoute('/runs/test-job?chart=deleted&show=broken')",context);
  assert.equal(vm.runInContext('shownDecisionKeys',context),null);
  assert.equal(vm.runInContext('chartSelectionExplicit',context),false);
});

test('List searches survive refresh within a tab and tolerate unavailable storage',async()=>{
  const data=new Map();const session={getItem:key=>data.get(key) || null,setItem:(key,value)=>data.set(key,value)};
  const first=workspace([],undefined,undefined,undefined,null,session);
  await new Promise(resolve=>setImmediate(resolve));
  for(const id of ['source-search','criteria-search','action-search','task-search','ssh-key-search','ssh-host-search']){
    first.nodes.get(id).value='Selected name';first.nodes.get(id).oninput();
  }
  const second=workspace([],undefined,undefined,undefined,null,session);
  for(const id of ['source-search','criteria-search','action-search','task-search','ssh-key-search','ssh-host-search'])assert.equal(second.nodes.get(id).value,'Selected name');
  const blocked=workspace([],undefined,undefined,undefined,null,{getItem:()=>{throw Error('Blocked');},setItem:()=>{throw Error('Blocked');}});
  blocked.nodes.get('criteria-search').value='Search';assert.doesNotThrow(()=>blocked.nodes.get('criteria-search').oninput());
});

for(const revising of [false,true])test(`${revising?'Revision':'Generation'} samples paginate by 10 and submit edits across all pages`,async()=>{
  const profile=readProfileTemplate('general');const {nodes,context}=workspace([],undefined,undefined,{[sampleProfileIds.general]:profile});
  await nodes.get('nav-criteria').onclick();vm.runInContext(`handleEditCriteria(${revising?'sampleProfileIds.general':"''"})`,context);
  const walk=node=>[node,...(node.children || []).flatMap(child=>typeof child==='object'?walk(child):[])];
  const generator=walk(nodes.get('criteria-editor')).find(node=>node.className?.includes('criteria-generator'));
  const find=label=>walk(generator).find(node=>node.attributes?.['aria-label']===label);
  const button=text=>walk(generator).find(node=>node.textContent===text && node.onclick);
  let previews=0,submitted;const original=context.fetch;
  context.fetch=async(path,options)=>{
    if(path==='/api/criteria/samples'){previews++;return {ok:true,json:async()=>({samples:Array.from({length:21},(_,i)=>`sample-${i+1}`)})};}
    if(path==='/api/criteria/generate'){submitted=JSON.parse(options.body);return {ok:false,json:async()=>({error:'Test response'})};}
    return original(path,options);
  };
  generator.open=true;await generator.ontoggle();await button('Preview Source Samples').onclick();
  const list=walk(generator).find(node=>node.className==='criteria-sample-list');
  assert.equal(list.children.length,10);assert.equal(find('Previous Samples').disabled,true);
  find('Sample 1').value='edited-first';find('Next Samples').onclick();
  assert.equal(list.children.length,10);assert.equal(find('Sample 1'),undefined);find('Sample 11').value='edited-eleventh';
  find('Next Samples').onclick();assert.equal(list.children.length,1);assert.equal(find('Next Samples').disabled,true);
  button('Remove Sample').onclick();assert.equal(list.children.length,10);assert.equal(find('Next Samples').disabled,true);
  assert.ok(find('Sample 11'));assert.equal(find('Sample 11').value,'edited-eleventh');
  find('Previous Samples').onclick();assert.equal(find('Sample 1').value,'edited-first');assert.equal(previews,1);
  if(revising){find('Additional Instructions').value='Keep the decisions';}
  await button('Generate Criteria').onclick();
  assert.equal(submitted.samples.length,20);assert.equal(submitted.samples[0],'edited-first');assert.equal(submitted.samples[10],'edited-eleventh');
  assert.equal(submitted.samples.includes('sample-21'),false);
  find('Sample Count').value='12';find('Sample Count').oninput();
  assert.equal(walk(generator).find(node=>node.className==='criteria-samples').hidden,true);
});

for(const revising of [false,true])test(`${revising?'Edit':'Create'} shares automatic/manual modes and optional additional instructions`,async()=>{
  const profile=readProfileTemplate('general');const {nodes,context}=workspace([],undefined,undefined,{[sampleProfileIds.general]:profile});
  await nodes.get('nav-criteria').onclick();vm.runInContext(`handleEditCriteria(${revising?'sampleProfileIds.general':"''"})`,context);
  const walk=node=>[node,...(node.children || []).flatMap(child=>typeof child==='object'?walk(child):[])];
  const generator=walk(nodes.get('criteria-editor')).find(node=>node.className?.includes('criteria-generator'));
  const field=label=>walk(generator).find(node=>node.attributes?.['aria-label']===label);
  const generate=walk(generator).find(node=>node.textContent===('Generate Criteria') && node.onclick);
  const mode=field('Analysis Purpose Mode'),purpose=field('Analysis Purpose'),extra=field('Additional Instructions');
  assert.equal(mode.value,'automatic');assert.notEqual(mode.parentElement.hidden,true);assert.equal(purpose.parentElement.hidden,true);
  let submitted;const original=context.fetch;
  context.fetch=async(path,options)=>{
    if(path==='/api/criteria/samples')return {ok:true,json:async()=>({samples:['Sample input']})};
    if(path==='/api/criteria/generate'){submitted=JSON.parse(options.body);return {ok:false,json:async()=>({error:'Mock response'})};}
    return original(path,options);
  };
  if(!revising){generator.open=true;await generator.ontoggle();await walk(generator).find(node=>node.textContent==='Preview Source Samples').onclick();}
  assert.equal(generate.disabled,false);await generate.onclick();assert.equal(submitted.purposeMode,'automatic');assert.equal(submitted.additionalInstructions,undefined);
  mode.value='manual';mode.onchange();assert.equal(purpose.parentElement.hidden,false);assert.equal(generate.disabled,true);
  purpose.value='Classify operational issues';purpose.oninput();assert.equal(generate.disabled,false);
  extra.value='  Write Korean labels.  ';await generate.onclick();assert.equal(submitted.additionalInstructions,'Write Korean labels.');assert.equal(submitted.purpose,purpose.value);
  mode.value='automatic';mode.onchange();await generate.onclick();assert.equal(submitted.purpose,'');assert.equal(submitted.additionalInstructions,'Write Korean labels.');assert.equal(purpose.value,'Classify operational issues');
});

for(const format of ['text','jsonl'])test(`${format} Input has a consistent disclosure and remembers manual state`,async()=>{
  const success=result(0,false),failure=result(1,false);success.result.inputFormat=format;failure.result.inputFormat=format;failure.result.error='Failed request';
  const {nodes,context}=workspace([success,failure]);await runTask(nodes);
  const input=()=>nodes.get('results').children[0].children.find(node=>node.className==='original-input');
  for(const row of nodes.get('results').children){
    const section=row.children.find(node=>node.className==='original-input');
    assert.equal(section.tagName,'details');assert.equal(section.children[0].textContent,'Input');assert.equal(section.open,format==='text');
  }
  input().open=format!=='text';input().ontoggle();
  vm.runInContext('render()',context);assert.equal(input().open,format!=='text');
  input().open=format==='text';input().ontoggle();
  vm.runInContext('render()',context);assert.equal(input().open,format==='text');
});

test('Default-expanded TEXT Input does not rewrite URLs and preserves manual collapse across paged object replacements',async()=>{
  const navigation={pathname:'/',search:'',hash:''};const {context,nodes}=workspace([result(0,false)],undefined,undefined,undefined,navigation);
  await runTask(nodes);const writes=enableCleanRoutes(context,navigation);navigation.pathname='/runs/scope';
  vm.runInContext("activeJobId='scope';resultCursors.set(results[0],1);render()",context);
  const input=()=>nodes.get('results').children[0].children.find(node=>node.className==='original-input');
  assert.equal(input().open,true);input().ontoggle();assert.equal(writes.length,0);
  input().open=false;input().ontoggle();
  vm.runInContext('results=results.map(item=>({...item}));resultCursors.set(results[0],1);render()',context);
  assert.equal(input().open,false);
  input().open=true;input().ontoggle();assert.match(navigation.search,/detail=input/);
  vm.runInContext('render()',context);assert.equal(input().open,true);
});

test('Overview applies combined filters while metrics remain whole-run and decisions stay available for zero matches',async()=>{
  const first=assessmentFixture(),second=assessmentFixture(1);Object.assign(first.result,{hostId:'one',source:'/a',log:'target one'});Object.assign(second.result,{hostId:'two',source:'/b',log:'target two'});
  const {context,nodes}=workspace([first,second]);await runTask(nodes);
  const total=()=>nodes.get('summary').children[0].children[0].children.map(node=>node.textContent).join('');
  const metricBefore=total();nodes.get('host-filter').value='one';nodes.get('host-filter').onchange();
  assert.match(nodes.get('chart-totals').textContent,/Filtered Results · 1 classified/);assert.equal(total(),metricBefore);
  nodes.get('source-filter').value='/b';nodes.get('source-filter').onchange();
  assert.match(nodes.get('chart-totals').textContent,/0 classified/);assert.ok(nodes.get('classification-group').children.length>0);
  assert.ok(nodes.get('category-chart').children.every(row=>row.children[2].textContent==='0 (0.0%)'));
  nodes.get('source-filter').value='all';nodes.get('source-filter').onchange();showDecisions(context,['stable:response']);
  assert.match(nodes.get('chart-totals').textContent,/1 classified/);
  nodes.get('host-filter').value='all';nodes.get('host-filter').onchange();assert.doesNotMatch(nodes.get('chart-totals').textContent,/Filtered Results/);
});

test('Paged Overview uses server-filtered aggregates instead of visible rows and refreshes when the count is unchanged',async()=>{
  const {context,nodes}=workspace([assessmentFixture(),assessmentFixture(1)]);await runTask(nodes);
  const all=vm.runInContext('updateResultStatistics()',context);const filtered=structuredClone({...all,hosts:undefined,sources:undefined});filtered.total=80;
  for(const entry of Object.values(filtered.decisionGroups))for(const values of Object.values(entry.counts))for(const key of Object.keys(values))values[key]=0;
  filtered.decisionGroups['stable:area'].counts.all.a=80;
  context.filteredChart=filtered;context.allChart=all;
  vm.runInContext("pagedView={id:'scope',summary:allChart,chartSummary:filteredChart,items:[],cursors:[null],revision:0};$('host-filter').value='one';render(false,true)",context);
  assert.equal(nodes.get('category-chart').children[0].children[2].textContent,'80 (100.0%)');
  vm.runInContext("pagedView.chartSummary.total=40;pagedView.chartSummary.decisionGroups['stable:area'].counts.all.a=40;render(false,true)",context);
  assert.equal(nodes.get('category-chart').children[0].children[2].textContent,'40 (100.0%)');
});
