import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { test } from 'node:test';

const workspaceContexts = new WeakMap();
function runTask(nodes) {
  return vm.runInContext('handleRunTask(selectedTaskId)', workspaceContexts.get(nodes));
}

function workspace(events, status, storage = { getItem: () => null, setItem() {} }, criteria = null, navigation = null) {
  const nodes = new Map();
  const requests = [];
  const listeners = new Map();
  const node = () => ({
    children: [], value: '', checked: false, attributes: {},
    append(...children) { this.children.push(...children); },
    replaceChildren() { this.children = []; },
    setAttribute(name, value) { this.attributes[name] = value; },
  });
  const context = vm.createContext({
    ...(navigation ? { location: navigation, addEventListener: (name, handler) => listeners.set(name, handler) } : {}),
    document: {
      getElementById(id) {
        if (!nodes.has(id)) nodes.set(id, node());
        return nodes.get(id);
      },
      createElement: node,
    },
    Option: function(text, value) { return { text, value }; },
    localStorage: storage,
    AbortController,
    setTimeout: () => 1,
    clearTimeout() {},
    fetch: async (path, options) => {
      if (path === '/api/criteria') {
        if (!criteria) return { ok: false, json: async () => ({ error: 'Unavailable' }) };
        return { ok: true, json: async () => ({ profiles: options.method === 'PUT' ? JSON.parse(options.body) : criteria }) };
      }
      if (path === '/api/tasks') return {ok:true,json:async()=>({tasks:vm.runInContext('registeredTasks.map(task=>({...task}))',context)})};
      if (path === '/api/tasks/test-task/run') {
        const sources=vm.runInContext('sourceRows.map(({path,profile,size,action})=>({sourceId:path,profile:profile.value,chunkEvents:Number(size.value),action:action.value}))',context);
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
      if (path === '/api/status') return status ? { ok: true, json: async () => status } : new Promise(() => {});
      requests.push(JSON.parse(options.body));
      return { ok: true, body: {} };
    },
    readEvents: async (_, receive) => events.forEach(receive),
  });
  context.document.getElementById('review-filter').value = 'all';
  context.document.getElementById('category-filter').value = 'all';
  const source = readFileSync(new URL('../public/app.js', import.meta.url), 'utf8');
  vm.runInContext(source.replace(/^import .*;\n/, ''), context);
  vm.runInContext("sourcesLoaded = true; registeredTasks=[{id:'test-task',name:'Test Task',mode:'batch',sources:[],timezone:'UTC',cron:'',enabled:true}];selectedTaskId='test-task';renderTaskMonitor()", context);
  workspaceContexts.set(nodes, context);
  return { nodes, context, requests, listeners };
}

function result(index, review = true) {
  return {
    type: 'result', index, elapsedMs: index,
    result: { log: `log-${index}`, category: 'normal', confidence: .9,
      elapsedMs: 1, probabilities: { normal: 1 }, review },
  };
}

function decisionCards(row) {
  return row.children[0].children[0].children;
}

function logs(nodes) {
  return nodes.get('results').children.map(row => row.children[1].textContent);
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
  const select = nodes.get('results').children[0].children.at(-2).children[0];
  select.value = 'warning';
  select.onchange();
  vm.runInContext('render()', context);
  assert.equal(nodes.get('results').children[0].children.at(-2).children[0].value,
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
  const average = () => nodes.get('summary').children[5].children[0].textContent;
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
    assert.equal(nodes.get('summary').children[2].children[0].textContent, '1');
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
  const active = () => nodes.get('summary').children[4].children[0].textContent;
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

test('New Tasks default to one-time Batch and do not auto-resume', async () => {
  const {nodes,context}=workspace([]);await vm.runInContext('handleEditTask()',context);
  assert.equal(nodes.get('source-mode').value,'batch');assert.equal(nodes.get('task-trigger').value,'manual');
  assert.equal(nodes.get('task-resume').checked,false);assert.equal(nodes.get('task-cron-field').hidden,true);
});

test('Changing Task modes retains the Source configuration draft', async () => {
  const {nodes,context}=workspace([]);await vm.runInContext('handleEditTask()',context);
  vm.runInContext("sourceRows[0].profile.value='http_access';sourceRows[0].size.value='5';sourceRows[0].action.value='Notify'",context);
  nodes.get('source-mode').value='realtime';nodes.get('source-mode').onchange();nodes.get('source-mode').value='batch';nodes.get('source-mode').onchange();
  assert.equal(vm.runInContext('sourceRows[0].profile.value',context),'http_access');assert.equal(vm.runInContext('sourceRows[0].size.value',context),'5');
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
  const {context}=workspace([]);await vm.runInContext("handleEditTask({id:'saved',name:'Logs',mode:'batch',timezone:'UTC',cron:'',sources:[{sourceId:sampleSources[0].id,profile:'http_access',chunkEvents:3,action:'notify'}]})",context);
  assert.equal(vm.runInContext('sourceRows[0].profile.value',context),'http_access');assert.equal(vm.runInContext('sourceRows[0].size.value',context),'3');assert.equal(vm.runInContext('sourceRows[0].action.value',context),'notify');
});

test('individual JSON reflects review changes and stays open after rendering', async () => {
  const event = result(0);
  Object.assign(event.result, { profile: 'http_access', chunkEvents: 3, eventCount: 2, source: '/logs/access.log', line: 10, lineEnd: 11, log: '<script>example</script>' });
  const failed = result(1);
  failed.result = { log: 'bad input', error: 'request failed', review: true, elapsedMs: 1, profile: 'network' };
  const { nodes, context } = workspace([{ type: 'start', total: 2, engine: 'laya' }, event, failed]);
  await runTask(nodes);
  const row = nodes.get('results').children[1];
  const details = row.children.at(-1);
  assert.equal(details.children[0].textContent, 'View JSON');
  assert.equal(details.children[1].children[1].textContent, '');
  details.open = true; details.ontoggle();
  assert.equal(JSON.parse(details.children[1].children[1].textContent).lineEnd, 11);
  assert.equal(JSON.parse(details.children[1].children[1].textContent).log, '<script>example</script>');
  const select = row.children.at(-2).children[0];
  select.value = 'warning'; select.onchange();
  assert.equal(JSON.parse(details.children[1].children[1].textContent).reviewerCategory, 'warning');
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
  assert.equal(nodes.get('pause-updates').textContent, 'Resume updates (2 new)');
  nodes.get('review-filter').value = 'needs-review';
  nodes.get('review-filter').onchange();
  assert.equal(nodes.get('results').children[0].textContent, 'No results to display.');
  nodes.get('review-filter').value = 'all'; nodes.get('review-filter').onchange();
  assert.deepEqual(logs(nodes), ['log-0']);
  nodes.get('category-filter').value = 'warning'; nodes.get('category-filter').onchange();
  assert.equal(nodes.get('results').children[0].textContent, 'No results to display.');
  nodes.get('category-filter').value = 'all'; nodes.get('category-filter').onchange();
  nodes.get('log-search').value = 'LOG-1'; nodes.get('log-search').oninput();
  assert.equal(nodes.get('results').children[0].textContent, 'No results to display.');
  nodes.get('log-search').value = ''; nodes.get('log-search').oninput();
  assert.deepEqual(logs(nodes), ['log-0']);
  finish(); await run;
  assert.deepEqual(logs(nodes), ['log-0']);
  assert.equal(nodes.get('pause-updates').textContent, 'Resume updates (2 new)');
  nodes.get('pause-updates').onclick();
  assert.deepEqual(logs(nodes), ['log-2', 'log-1', 'log-0']);
  assert.equal(nodes.get('pause-updates').textContent, 'Pause updates');
  nodes.get('pause-updates').onclick();
  context.readEvents = async (_, callback) => {
    callback({ type: 'start', engine: 'laya', total: 1 }); callback(result(0));
  };
  await runTask(nodes);
  assert.equal(nodes.get('pause-updates').textContent, 'Pause updates');
  assert.deepEqual(logs(nodes), ['log-0']);
});

test('pause excludes received results that have not yet been displayed', async () => {
  const { nodes, context } = workspace([{ type: 'start', total: null, engine: 'laya' }, result(0)]);
  await runTask(nodes);
  vm.runInContext("results[1] = { log: 'queued', elapsedMs: 1, review: true }; completionOrder.push(1); completed++;", context);
  nodes.get('pause-updates').onclick();
  nodes.get('review-filter').onchange();
  assert.deepEqual(logs(nodes), ['log-0']);
  assert.equal(nodes.get('pause-updates').textContent, 'Resume updates (1 new)');
});

test('file line labels distinguish batch from observed realtime sequences', async () => {
  for (const mode of ['batch', 'realtime']) {
    const first = result(0);
    Object.assign(first.result, { source: '/var/log/secure', line: 1, lineEnd: 1, profile: 'general', eventCount: 1, chunkEvents: 1 });
    const second = result(1);
    Object.assign(second.result, { source: '/var/log/secure', line: 10, lineEnd: 12, lineCount: 3, profile: 'authentication', eventCount: 1, chunkEvents: 5 });
    const { nodes, context } = workspace([{ type: 'start', engine: 'laya', total: null, mode }, first, second]);
    await runTask(nodes);
    const rows = nodes.get('results').children;
    const prefix = mode === 'realtime' ? 'Observed' : 'File';
    assert.equal(rows[1].children[2].textContent, `Source: /var/log/secure · ${prefix} line 1`);
    assert.equal(rows[0].children[2].textContent, `Source: /var/log/secure · ${prefix} lines 10–12`);
    assert.equal(rows[1].children[3].textContent, 'Category criteria (Choice): General system · Chunk: 1 event (max 1)');
    assert.equal(rows[0].children[3].textContent, 'Category criteria (Choice): Authentication · Chunk: 1 event (max 5)');
    if (mode === 'realtime') assert.ok(rows[1].children[2].title.includes('not an absolute'));
    nodes.get('source-mode').value = mode === 'realtime' ? 'batch' : 'realtime';
    nodes.get('source-mode').onchange();
    vm.runInContext('render()', context);
    assert.equal(nodes.get('results').children[1].children[2].textContent, `Source: /var/log/secure · ${prefix} line 1`);
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
  assert.equal(nodes.get('pause-updates').textContent, 'Resume updates (1 new)');
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
  assert.ok(html.includes('Sources and decisions'));
});

test('category chart counts all sources, separates failures, and ignores filters and edits', async () => {
  const events = [{ type: 'start', engine: 'laya', total: null }];
  for (const [index, category] of ['normal', 'normal', 'warning', 'error', 'security', 'other'].entries()) {
    const event = result(index, index % 2 === 0);
    Object.assign(event.result, { category, source: index % 2 ? '/logs/http' : '/logs/system', eventCount: 10, chunkEvents: 10 });
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
  vm.runInContext("results[0].reviewerCategory = 'security'; render();", context);
  assert.equal(values()[0], '2 (33.3%)');
  nodes.get('pause-updates').onclick();
  vm.runInContext("results[7] = {category: 'security', elapsedMs: 1}; completionOrder.push(7); completed++; render(false);", context);
  assert.equal(values()[3], '2 (28.6%)');
  events.splice(0, events.length, { type: 'start', engine: 'laya', total: 0 });
  await runTask(nodes);
  assert.deepEqual(values(), Array(5).fill('0 (0.0%)'));
});

test('category overview precedes Log input and Classification results', () => {
  const html = readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');
  assert.ok(html.indexOf('Classification overview') < html.indexOf('Task monitor'));
  assert.ok(html.indexOf('Classification overview') < html.indexOf('Classification results'));
});

test('uncertain category is explicitly provisional without changing the model choice', async () => {
  const event = result(0);
  Object.assign(event.result, { category: 'error', confidence: .26, uncertain: true,
    candidates: ['error', 'other'], reviewReasons: ['low_confidence', 'close_probabilities'],
    probabilities: { normal: .01, warning: .18, error: .41, security: 0, other: .4 } });
  const { nodes } = workspace([{ type: 'start', engine: 'jev', total: 1 }, event]);
  await runTask(nodes);
  const row = nodes.get('results').children[0];
  assert.equal(decisionCards(row)[0].children[1].textContent, 'Uncertain · Error');
  assert.ok(decisionCards(row)[0].children.at(-1).textContent.includes('Error 41.0% vs Other 40.0%'));
  assert.ok(decisionCards(row)[0].children.at(-1).textContent.includes('close category probabilities'));
  const details = row.children.at(-1); details.open = true; details.ontoggle();
  assert.equal(JSON.parse(details.children[1].children[1].textContent).category, 'error');
  assert.equal(nodes.get('category-chart').children[2].children[2].textContent, '1 (100.0%)');
});

test('workspace places input and overview in the 40% column beside 60% results', () => {
  const html = readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');
  const css = readFileSync(new URL('../public/style.css', import.meta.url), 'utf8').replace(/\s*([{}:;])\s*/g, '$1');
  const leftStart = html.indexOf('<div class="input-column">');
  const leftEnd = html.indexOf('</div>\n      <section class="card output">', leftStart);
  assert.ok(leftStart >= 0 && leftEnd > leftStart);
  const left = html.slice(leftStart, leftEnd);
  assert.ok(left.includes('Task monitor'));
  assert.ok(left.includes('Classification overview'));
  assert.ok(!left.includes('Classification results'));
  assert.ok(css.includes('grid-template-columns:minmax(0,2fr) minmax(0,3fr)'));
  assert.ok(css.includes('.workspace{grid-template-columns:1fr}'));
});

test('category, review and literal log search combine and retain full aggregates', async () => {
  const normal = result(0, false);
  normal.result.log = 'Service Started [OK]';
  const warning = result(1);
  warning.result.category = 'warning';
  warning.result.log = 'Service retry [pending]';
  const failed = { type: 'result', index: 2, elapsedMs: 3,
    result: { log: 'Service request failed', error: 'timeout', review: true, elapsedMs: 2 } };
  const { nodes } = workspace([{ type: 'start', engine: 'laya', total: 3 }, normal, warning, failed]);
  await runTask(nodes);
  nodes.get('log-search').value = 'SERVICE'; nodes.get('log-search').oninput();
  assert.equal(logs(nodes).length, 3);
  nodes.get('category-filter').value = 'normal'; nodes.get('category-filter').onchange();
  assert.deepEqual(logs(nodes), ['Service Started [OK]']);
  nodes.get('review-filter').value = 'needs-review'; nodes.get('review-filter').onchange();
  assert.equal(nodes.get('results').children[0].textContent, 'No results to display.');
  nodes.get('category-filter').value = 'warning'; nodes.get('category-filter').onchange();
  nodes.get('log-search').value = '[PENDING]'; nodes.get('log-search').oninput();
  assert.deepEqual(logs(nodes), ['Service retry [pending]']);
  nodes.get('log-search').value = '.*'; nodes.get('log-search').oninput();
  assert.equal(nodes.get('results').children[0].textContent, 'No results to display.');
  nodes.get('log-search').value = ''; nodes.get('log-search').oninput();
  nodes.get('category-filter').value = 'failed'; nodes.get('category-filter').onchange();
  assert.equal(nodes.get('results').children[0].textContent, 'No results to display.');
  nodes.get('review-filter').value = 'all'; nodes.get('review-filter').onchange();
  assert.deepEqual(logs(nodes), ['Service request failed']);
  assert.equal(nodes.get('summary').children[0].children[0].children.map(node => node.textContent).join(''), '2 / 1 / 3');
  nodes.get('category-filter').value = 'all'; nodes.get('category-filter').onchange();
  nodes.get('review-filter').value = 'all'; nodes.get('review-filter').onchange();
  assert.equal(logs(nodes).length, 3);
});

test('chart certainty groups partition classified results without treating failures as uncertain', async () => {
  const events = [{ type: 'start', engine: 'laya', total: 4 }];
  for (const [index, category, uncertain, review] of [
    [0, 'normal', false, false], [1, 'error', true, true], [2, 'other', false, true],
  ]) {
    const event = result(index, review);
    Object.assign(event.result, { category, uncertain });
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
  Object.assign(event.result, { confidence: .16, answerProbability: .9 });
  const { nodes } = workspace([{ type: 'start', engine: 'laya', total: 1 }, event]);
  await runTask(nodes);
  assert.equal(decisionCards(nodes.get('results').children[0])[0].children[2].textContent, '90.0% category probability');
});

test('collapsed options show the rendering integrity warning', async () => {
  const event = result(0);
  Object.assign(event.result, {
    uncertain: true, candidates: ['normal'], reviewReasons: ['collapsed_options'],
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
  const reviewer = row.children.at(-2).children[0];
  reviewer.value = 'warning';
  reviewer.onchange();
  const actions = row.children.at(-1).children[1].children[0];
  assert.equal(actions.children[0].textContent, 'Copy');
  assert.equal(actions.children[0].className, 'json-copy');
  await actions.children[0].onclick();
  assert.equal(JSON.parse(copied).reviewerCategory, 'warning');
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
  assert.equal(nodes.get('message').className, '');
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
      assert.equal(status.children[1].textContent, ' (Not checked)');
      if (!configured) assert.equal(status.children[4].textContent, ' · API key required');
    }
  }
  const css = readFileSync(new URL('../public/style.css', import.meta.url), 'utf8').replace(/\s*([{}:;])\s*/g, '$1');
  assert.ok(css.includes('.selected-engine{color:#0057ff;font-weight:700}'));
  assert.ok(css.includes('.selected-model{color:#0057ff;font-weight:700;}'));
});


test('uncertain results retain their category color class', async () => {
  const categories = ['normal', 'warning', 'error', 'security', 'other'];
  for (const uncertain of [false, true]) {
    const events = categories.map((category, index) => {
      const event = result(index);
      Object.assign(event.result, { category, uncertain });
      return event;
    });
    const { nodes } = workspace(events);
    await runTask(nodes);
    for (const [index, row] of nodes.get('results').children.entries()) {
      const category = categories[categories.length - 1 - index];
      const badge = decisionCards(row)[0].children[1];
      assert.equal(badge.className, `badge ${category}${uncertain ? ' uncertain' : ''}`);
      assert.equal(badge.textContent.startsWith('Uncertain · '), uncertain);
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


test('throughput tracks a rolling five-second window and resets between runs', async () => {
  const success = (index, elapsedMs) => ({ ...result(index), elapsedMs });
  const failed = success(3, 5600);
  failed.result.error = 'timeout';
  const events = [{ type: 'start', engine: 'laya', total: null },
    success(0, 1000), success(1, 2000), success(2, 5500), failed,
    { type: 'timing', elapsedMs: 7000 }];
  const { nodes } = workspace(events);
  const rate = () => nodes.get('summary').children[6].children[0].textContent;
  await runTask(nodes);
  assert.equal(rate(), '0.2 chunks/s');
  nodes.get('review-filter').value = 'no-review';
  nodes.get('review-filter').onchange();
  assert.equal(rate(), '0.2 chunks/s');
  events.push({ type: 'timing', elapsedMs: 11000 });
  await runTask(nodes);
  assert.equal(rate(), '0.0 chunks/s');
  events.splice(0, events.length, { type: 'start', engine: 'jev', total: 1 },
    success(0, 1000));
  await runTask(nodes);
  assert.equal(rate(), '1.0 chunks/s');
});


test('source filtering uses input patterns with counts and combines with other filters', async () => {
  const first = result(0, false);
  Object.assign(first.result, { source: '/logs/access-1.log', sourcePatterns: ['/logs/access*.log'], log: 'request ok' });
  const second = result(1);
  Object.assign(second.result, { source: '/logs/messages', sourcePatterns: ['/logs/*', '/logs/messages'], log: 'service failed', category: 'error' });
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
  nodes.get('category-filter').value = 'normal'; nodes.get('category-filter').onchange();
  assert.equal(nodes.get('results').children[0].textContent, 'No results to display.');
  nodes.get('category-filter').value = 'all';
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
  vm.runInContext("registeredActions = [{name: 'notify', python: '/venv/bin/python', script: '/actions/notify.py'}]; renderActions(); updateSourceSettings();", context);
  const selector = nodes.get('source-settings').children[0].children[3].children[0];
  assert.match(selector.attributes['aria-label'], /^Action for /);
  assert.deepEqual(selector.children.map(option => option.text), ['None', 'notify']);
  selector.value = 'notify'; selector.onchange();
  await runTask(nodes);
  assert.equal(requests[0].sources[0].action, 'notify');
  assert.ok(nodes.get('results').children[0].children.some(node => node.textContent?.includes('Action execution: notify · failed · 12ms · exit 7')));
  assert.equal(selector.disabled, false);
});

test('Action editor sends Python versions and module lists and recovers from preparation errors', async () => {
  const { nodes, context } = workspace([]);
  await new Promise(resolve => setImmediate(resolve));
  nodes.get('add-action').onclick();
  const row = nodes.get('action-editor').children[0];
  const inputs = row.children.slice(0, 4).map(label => label.children[0]);
  assert.equal(inputs[0].readOnly, false);
  assert.equal(row.children[0].children[1].textContent, 'Name cannot be changed after creation.');
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
  table().children[2].children[4].children[1].onclick();
  assert.equal(nodes.get('action-editor').children.length, 1);
  nodes.get('action-editor').children[0].children[0].children[0].value = 'Discard';
  nodes.get('cancel-action').onclick();
  assert.equal(table().children[2].children[0].textContent, 'Second');
  table().children[2].children[4].children[1].onclick();
  assert.equal(nodes.get('action-editor').children[0].children[0].children[0].readOnly, true);
  nodes.get('action-editor').children[0].children[0].children[0].value = 'Edited';
  let sent;
  context.fetch = async (path, options) => {
    sent = JSON.parse(options.body);
    return {ok:true, json:async () => ({actions:sent})};
  };
  await nodes.get('save-actions').onclick();
  assert.equal(sent.length, 2);
  assert.equal(sent[0].name, 'First');
  assert.equal(sent[1].name, 'Second');
  assert.equal(nodes.get('action-editor').hidden, true);
  table().children[1].children[4].children[3].onclick();
  await nodes.get('save-actions').onclick();
  assert.equal(sent.length, 1);
  assert.equal(sent[0].name, 'Second');
  nodes.get('add-action').onclick();
  nodes.get('cancel-action').onclick();
  assert.equal(table().children.length, 2);
});


test('Action name search ignores case and retains original edit and delete targets', async () => {
  const { nodes, context } = workspace([]);
  await new Promise(resolve => setImmediate(resolve));
  vm.runInContext("registeredActions = [{name:'First', code:'pass'}, {name:'Notify admin', code:'pass'}, {name:'Last', code:'pass'}]; renderActions();", context);
  const search = nodes.get('action-search');
  search.value = '  NOTIFY  '; search.oninput();
  const table = nodes.get('action-registry').children[0];
  assert.equal(table.children.length, 2);
  assert.equal(table.children[1].children[0].textContent, 'Notify admin');
  table.children[1].children[4].children[1].onclick();
  assert.equal(nodes.get('action-editor').children[0].children[0].children[0].value, 'Notify admin');
  nodes.get('cancel-action').onclick();
  nodes.get('action-registry').children[0].children[1].children[4].children[3].onclick();
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
  assert.equal(path.value, 'System messages');
  path.value = '/custom/access*.log'; path.onchange();
  const profile = first.children[1].children[0];
  profile.value = 'http_access'; profile.onchange();
  first.children.at(-1).onclick();
  assert.equal(nodes.get('source-settings').children.length, 2);
  nodes.get('add-source').onclick();
  const added = nodes.get('source-settings').children[2].children[0].children[0];
  assert.equal(added.value, '');
  await runTask(nodes);
  assert.equal(requests.length, 0);
  assert.match(nodes.get('message').textContent, /Select a registered source/);
  added.value = 'System messages'; added.onchange();
  vm.runInContext("sourceRows[2].profile.value = 'http_access'; sourceRows[2].profile.onchange();", context);
  assert.equal(vm.runInContext('sourceRows[2].path', context), '1'.padStart(32,'0'));
  nodes.get('source-mode').value = 'realtime'; nodes.get('source-mode').onchange();
  nodes.get('source-mode').value = 'batch'; nodes.get('source-mode').onchange();
  assert.equal(nodes.get('source-settings').children[2].children[0].children[0].value, 'System messages');
  assert.equal(vm.runInContext('sourceRows[2].profile.value', context), 'http_access');
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
    getItem: () => JSON.stringify([['/host-logs/var/log/messages', {profile:'http_access', chunkEvents:3, action:'notify'}]]),
    setItem: (_, value) => { saved = JSON.parse(value); },
  };
  const {nodes, context, requests} = workspace([], undefined, storage);
  await new Promise(resolve => setImmediate(resolve));
  vm.runInContext("registeredActions = [{name:'notify'}]; updateSourceSettings();", context);
  const selector = () => nodes.get('source-settings').children[0].children[3].children[0];
  assert.equal(selector().value, '');
  assert.equal(vm.runInContext('sourceRows[0].profile.value', context), 'http_access');
  assert.equal(vm.runInContext('sourceRows[0].size.value', context), '3');
  await runTask(nodes);
  assert.ok(requests[0].sources.every(source => source.action === ''));
  selector().value = 'notify'; selector().onchange();
  assert.ok(saved.every(([, preference]) => !Object.hasOwn(preference, 'action')));
  nodes.get('source-mode').value = 'realtime'; nodes.get('source-mode').onchange();
  nodes.get('source-mode').value = 'batch'; nodes.get('source-mode').onchange();
  assert.equal(selector().value, 'notify');
  const reloaded = workspace([], undefined, {getItem:() => JSON.stringify(saved), setItem() {}});
  await new Promise(resolve => setImmediate(resolve));
  vm.runInContext("registeredActions = [{name:'notify'}]; updateSourceSettings();", reloaded.context);
  assert.equal(reloaded.nodes.get('source-settings').children[0].children[3].children[0].value, '');
});


test('new jobs persist their ID and reload replays results without submitting another run', async () => {
  const stored = new Map();
  const storage = {getItem:key => stored.get(key) || null, setItem:(key,value) => stored.set(key,value), removeItem:key => stored.delete(key)};
  const events = [{type:'start', engine:'laya', mode:'batch', total:1, sourcePatterns:['/custom/log']}, result(0), {type:'done', state:'completed', elapsedMs:100}];
  const first = workspace(events, undefined, storage);
  await new Promise(resolve => setImmediate(resolve));
  let submissions = 0;
  const settings = {mode:'batch', sources:[{path:'/custom/log', profile:'http_access', chunkEvents:2, action:'notify'}]};
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
  assert.equal(vm.runInContext('sourceRows[0].profile.value', reloaded.context), 'general');
  assert.equal(vm.runInContext('sourceRows[0].action.value', reloaded.context), '');
  assert.equal(reloaded.nodes.get('stop').disabled, true);
  reloaded.context.fetch = async () => ({ok:false,status:404});
  await vm.runInContext('handleRestoreJob()', reloaded.context);
  assert.equal(stored.has('deciflow-job-id'), false);
  assert.match(reloaded.nodes.get('message').textContent, /server may have restarted/);
});


test('Stop calls the server job endpoint instead of aborting the browser stream', async () => {
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
  await nodes.get('stop').onclick();
  await running;
  assert.match(nodes.get('message').textContent, /Stopped/);
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
    if (path === '/api/jobs/remembered') return {ok:true,json:async () => ({jobId:'remembered',state:'completed',settings:{mode:'batch',sources:[]}})};
    assert.equal(path, '/api/jobs/remembered/events');
    return {ok:true,body:{}};
  };
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(paths, ['/api/jobs/remembered', '/api/jobs/remembered/events']);
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
  const css = readFileSync(new URL('../public/style.css', import.meta.url), 'utf8');
  assert.match(css, /button:disabled\s*\{\s*opacity:\s*\.5;/);
});


test('Criteria management resets drafts on menu entry, saves edits, and clears deleted source selections', async () => {
  const definitions = Object.fromEntries(['normal', 'warning', 'error', 'security', 'other'].map(key => [key, `${key} evidence`]));
  const profiles = {
    general: { label: 'General system', instructions: 'General instructions', criteria: definitions },
    custom: { label: 'Custom', instructions: 'Custom instructions', criteria: definitions },
  };
  const { nodes, context } = workspace([], undefined, undefined, profiles);
  await nodes.get('nav-criteria').onclick();
  assert.equal(nodes.get('criteria-page').hidden, false);
  assert.equal(nodes.get('main-page').hidden, true);
  assert.equal(nodes.get('save-criteria').disabled, false);
  assert.equal(nodes.get('criteria-default').children[0].children[1].children[2].children[0].textContent, 'View');
  assert.equal(nodes.get('criteria-registry').children[0].children[1].children[0].textContent, 'Custom');
  nodes.get('add-criteria').onclick();
  vm.runInContext("criteriaFields.id.value='new_profile'; criteriaFields.label.value='New profile'; criteriaFields.instructions.value='New instructions';", context);
  nodes.get('nav-main').onclick();
  await nodes.get('nav-criteria').onclick();
  assert.equal(nodes.get('criteria-editor').hidden,true);
  assert.equal(vm.runInContext('editingCriteria', context),null);
  nodes.get('add-criteria').onclick();
  vm.runInContext("criteriaFields.id.value='new_profile'; criteriaFields.label.value='New profile'; criteriaFields.instructions.value='New instructions';", context);
  await nodes.get('save-criteria').onclick();
  assert.equal(vm.runInContext("profileLabels.new_profile", context), 'New profile');
  vm.runInContext("handleEditCriteria('custom'); criteriaFields.instructions.value='Edited custom';", context);
  assert.equal(vm.runInContext('criteriaFields.id.readOnly', context), true);
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
  const profiles = { general: { label: 'General system', instructions: 'Original', criteria: definitions }, custom: { label: 'Custom', instructions: 'Original', criteria: definitions } };
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
  vm.runInContext("criteriaFields.id.value='general';", context);
  await nodes.get('save-criteria').onclick();
  assert.match(nodes.get('criteria-message').textContent, /already exists/);
  assert.equal(nodes.get('save-criteria').disabled, false);
});


test('View shows read-only Action configuration without editing or losing drafts', async () => {
  const { nodes, context, requests } = workspace([]);
  await new Promise(resolve => setImmediate(resolve));
  vm.runInContext("registeredActions=[{id:'notify', name:'Notify', pythonVersion:'3.12', modules:['httpx'], code:'print(1)'}]; renderActions();", context);
  const controls = () => nodes.get('action-registry').children[0].children[1].children[4].children;
  assert.deepEqual(controls().map(button => button.textContent), ['View', 'Edit', 'Reset venv', 'Delete']);
  controls()[0].onclick();
  const values = () => nodes.get('action-view').children[1].children.map(label => label.children[0]);
  assert.equal(nodes.get('action-view').hidden, false);
  assert.ok(values().every(input => input.readOnly));
  assert.equal(values().at(-1).value, 'print(1)');
  assert.equal(vm.runInContext('editingAction', context), null);
  assert.equal(vm.runInContext('actionRows.length', context), 0);
  assert.equal(requests.length, 0);
  controls()[1].onclick();
  assert.equal(nodes.get('action-view').hidden, true);
  assert.equal(nodes.get('action-view').children.length, 0);
  assert.equal(nodes.get('action-editor').hidden, false);
  vm.runInContext("actionRows[0].code.value='Unsaved draft';", context);
  controls()[0].onclick();
  assert.equal(values().at(-1).value, 'print(1)');
  assert.equal(nodes.get('action-editor').hidden, true);
  assert.equal(nodes.get('save-actions').disabled, true);
  assert.equal(vm.runInContext('actionRows[0].code.value', context), 'Unsaved draft');
  assert.equal(nodes.get('action-view').children[0].children[1].textContent, 'Cancel');
  nodes.get('action-view').children[0].children[1].onclick();
  assert.equal(nodes.get('action-view').hidden, true);
  assert.equal(nodes.get('action-editor').hidden, false);
  assert.equal(nodes.get('save-actions').disabled, false);
  assert.equal(vm.runInContext('editingAction', context), 0);
});

test('View shows all Criteria definitions and preserves the edit draft', async () => {
  const definitions = Object.fromEntries(['normal', 'warning', 'error', 'security', 'other'].map(key => [key, `${key} evidence`]));
  const profiles = { general: { label: 'General system', instructions: 'Saved instructions', criteria: definitions }, custom: { label: 'Custom', instructions: 'Saved instructions', criteria: definitions } };
  const { nodes, context } = workspace([], undefined, undefined, profiles);
  await nodes.get('nav-criteria').onclick();
  const controls = () => nodes.get('criteria-registry').children[0].children[1].children[2].children;
  assert.deepEqual(controls().map(button => button.textContent), ['View', 'Edit', 'Delete']);
  controls()[0].onclick();
  const values = () => nodes.get('criteria-view').children[1].children.map(label => label.children[0]);
  assert.ok(values().every(input => input.readOnly));
  assert.deepEqual(values().slice(3).map(input => input.value), Object.values(definitions));
  assert.equal(vm.runInContext('editingCriteria', context), null);
  controls()[1].onclick();
  assert.equal(nodes.get('criteria-view').hidden, true);
  assert.equal(nodes.get('criteria-view').children.length, 0);
  assert.equal(nodes.get('criteria-editor').hidden, false);
  vm.runInContext("criteriaFields.instructions.value='Draft instructions';", context);
  controls()[0].onclick();
  assert.equal(values()[2].value, 'Saved instructions');
  assert.equal(nodes.get('criteria-editor').hidden, true);
  assert.equal(nodes.get('save-criteria').disabled, true);
  assert.equal(nodes.get('criteria-view').children[0].children[1].textContent, 'Cancel');
  nodes.get('criteria-view').children[0].children[1].onclick();
  assert.equal(nodes.get('criteria-view').hidden, true);
  assert.equal(nodes.get('criteria-editor').hidden, false);
  assert.equal(nodes.get('save-criteria').disabled, false);
  assert.equal(vm.runInContext('criteriaFields.instructions.value', context), 'Draft instructions');
});


test('Add closes View in both managers and enables the new editor', async () => {
  const definitions = Object.fromEntries(['normal', 'warning', 'error', 'security', 'other'].map(key => [key, key]));
  const profiles = { general: { label: 'General', instructions: 'Instructions', criteria: definitions } };
  const { nodes, context } = workspace([], undefined, undefined, profiles);
  await new Promise(resolve => setImmediate(resolve));
  vm.runInContext("registeredActions=[{name:'Notify', code:'pass'}]; renderActions();", context);
  nodes.get('action-registry').children[0].children[1].children[4].children[0].onclick();
  nodes.get('add-action').onclick();
  assert.equal(nodes.get('action-view').hidden, true);
  assert.equal(nodes.get('action-editor').hidden, false);
  assert.equal(nodes.get('save-actions').disabled, false);
  await nodes.get('nav-criteria').onclick();
  nodes.get('criteria-default').children[0].children[1].children[2].children[0].onclick();
  nodes.get('add-criteria').onclick();
  assert.equal(nodes.get('criteria-view').hidden, true);
  assert.equal(nodes.get('criteria-editor').hidden, false);
  assert.equal(nodes.get('save-criteria').disabled, false);
});


test('URL routes restore Actions and Criteria on reload and support browser history', async () => {
  const definitions = Object.fromEntries(['normal', 'warning', 'error', 'security', 'other'].map(key => [key, key]));
  const profiles = { general: { label: 'General', instructions: 'Instructions', criteria: definitions } };
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
    assert.equal(connection.textContent, ' (Not checked)');
    const states = [
      ['connected', 'Connected'], ['disconnected', 'Disconnected'],
      [undefined, 'Disconnected'], ['timeout', 'Timed out'],
      ['api_error', 'API error'], ['connected', 'Connected'],
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
    assert.equal(nodes.get('summary').children[2].children[0].textContent, '2');
    nodes.get('review-filter').value = 'needs-review'; nodes.get('review-filter').onchange();
    assert.deepEqual(logs(nodes), ['event-5', 'event-0']);
    assert.equal(connection.className, 'engine-connection connected');
  }
});


test('Default Criteria stays above search with View only and outside the editable list', async () => {
  const definitions = Object.fromEntries(['normal', 'warning', 'error', 'security', 'other'].map(key => [key, key]));
  const profiles = { general: { label: 'General system', instructions: 'Default instructions', criteria: definitions }, custom: { label: 'Custom', instructions: 'Custom instructions', criteria: definitions } };
  const { nodes } = workspace([], undefined, undefined, profiles);
  await nodes.get('nav-criteria').onclick();
  const defaultRow = () => nodes.get('criteria-default').children[0].children[1];
  assert.deepEqual(nodes.get('criteria-default').children[0].children[0].children.map(cell => cell.textContent), ['Name', 'Profile ID', 'Manage']);
  assert.equal(defaultRow().children[0].textContent, 'General system');
  assert.equal(defaultRow().children[1].textContent, 'general');
  assert.deepEqual(defaultRow().children[2].children.map(button => button.textContent), ['View']);
  assert.equal(nodes.get('criteria-registry').children[0].children.length, 2);
  nodes.get('criteria-search').value = 'missing'; nodes.get('criteria-search').oninput();
  assert.equal(defaultRow().children[0].textContent, 'General system');
  defaultRow().children[2].children[0].onclick();
  assert.equal(nodes.get('criteria-view').children[1].children[0].children[0].value, 'general');
  const html = readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');
  assert.ok(html.indexOf('id="criteria-default"') < html.indexOf('id="additional-criteria-title"'));
  assert.ok(html.indexOf('id="additional-criteria-title"') < html.indexOf('id="criteria-search"'));
});


test('Add and Edit show only the form and restore each manager list on cancel or save', async () => {
  const definitions = Object.fromEntries(['normal', 'warning', 'error', 'security', 'other'].map(key => [key, key]));
  const profiles = { general: { label: 'General', instructions: 'Default', criteria: definitions }, custom: { label: 'Custom', instructions: 'Custom', criteria: definitions } };
  const { nodes, context } = workspace([], undefined, undefined, profiles);
  await new Promise(resolve => setImmediate(resolve));
  vm.runInContext("registeredActions=[{name:'Notify', code:'pass'}]; renderActions();", context);
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
  nodes.get('criteria-default').children[0].children[1].children[2].children[0].onclick();
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
  const controls = () => nodes.get('action-registry').children[0].children[1].children[4].children;
  let finish;
  let requested;
  context.fetch = (path, options) => {
    requested = { path, options };
    return new Promise(resolve => { finish = resolve; });
  };
  const resetting = controls()[2].onclick();
  assert.equal(requested.path, `/api/actions/${'a'.repeat(32)}/reset`);
  assert.equal(requested.options.method, 'POST');
  assert.ok(controls().every(button => button.disabled));
  assert.equal(nodes.get('save-actions').disabled, true);
  finish({ ok: true, json: async () => ({ action: { id:'a'.repeat(32), name:'Notify', pythonVersion:'3.12', modules:[], code:'pass' } }) });
  await resetting;
  assert.match(nodes.get('action-message').textContent, /rebuilt with pip/);
  context.fetch = async () => ({ ok: false, json: async () => ({ error: 'Stop runs using this Action' }) });
  await controls()[2].onclick();
  assert.match(nodes.get('action-message').textContent, /Stop runs/);
  assert.equal(controls()[2].disabled, false);
  vm.runInContext("registeredActions=[{name:'External', python:'/usr/bin/python', script:'/tmp/script.py'}]; renderActions();", context);
  assert.equal(controls()[2].disabled, true);
});


test('Action status distinguishes saved readiness, reset progress, and other Actions', async () => {
  const { nodes, context } = workspace([]);
  await new Promise(resolve => setImmediate(resolve));
  vm.runInContext("registeredActions=[{id:'a'.repeat(32), name:'Ready action', pythonVersion:'3.12', environmentStatus:'ready'}, {id:'b'.repeat(32), name:'Missing action', pythonVersion:'3.12', environmentStatus:'not_ready'}, {name:'External'}]; renderActions();", context);
  const statuses = () => nodes.get('action-registry').children[0].children.slice(1).map(row => row.children[3].children[0].textContent);
  assert.deepEqual(statuses(), ['Ready', 'Not ready', 'External']);
  let finish;
  context.fetch = () => new Promise(resolve => { finish = resolve; });
  const resetting = nodes.get('action-registry').children[0].children[1].children[4].children[2].onclick();
  assert.deepEqual(statuses(), ['Preparing...', 'Not ready', 'External']);
  finish({ok:true, json:async () => ({action:{id:'a'.repeat(32), name:'Ready action', pythonVersion:'3.12', environmentStatus:'ready'}})});
  await resetting;
  assert.deepEqual(statuses(), ['Ready', 'Not ready', 'External']);
  context.fetch = async () => ({ok:true, json:async () => ({actions:[{id:'a'.repeat(32), environmentStatus:'ready'},{id:'b'.repeat(32), environmentStatus:'ready'}]})});
  await vm.runInContext('handleRefreshActionStatus()', context);
  assert.deepEqual(statuses(), ['Ready', 'Ready', 'External']);
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
  assert.equal(nodes.get('summary').children[3].children[0].textContent, '1 hour 2 min');
  assert.equal(nodes.get('summary').children[4].children[0].textContent, '1 min 5 sec (1.7%)');
  assert.equal(nodes.get('summary').children[5].children[0].textContent, '1.5 sec');
  assert.equal(vm.runInContext('elapsedMs', context), 3720000);
  assert.equal(vm.runInContext('activeProcessingMs', context), 65000);
  assert.equal(vm.runInContext('orderedResult(results[0]).elapsedMs', context), 1500);
});


test('Reset selections restores registered samples and clears Action assignments', () => {
  const values = new Map();
  const storage = { getItem: key => values.get(key) || null, setItem: (key, value) => values.set(key, value) };
  const { nodes, context } = workspace([], undefined, storage);
  vm.runInContext("sourcePreferences.set('/host-logs/var/log/messages', {profile:'network', chunkEvents:9, action:'Notify'}); filePaths.realtime='/my/live.log';", context);
  nodes.get('file-path').value = '/custom.log'; nodes.get('file-path').oninput();
  nodes.get('reset-sources').onclick();
  assert.equal(nodes.get('file-path').value, vm.runInContext('defaultFilePaths.batch', context));
  assert.equal(nodes.get('source-settings').children.length, 3);
  assert.equal(vm.runInContext('filePaths.realtime', context), '/my/live.log');
  assert.equal(vm.runInContext("sourceRows.every(row => row.profile.value===defaultSourceProfiles[registeredSources.find(source=>source.id===row.path)?.path] && row.size.value==='1' && row.action.value==='')", context), true);
  const stored = new Map(JSON.parse(values.get('deciflow-source-preferences')));
  assert.deepEqual(stored.get('1'.padStart(32,'0')), { profile:'general', chunkEvents:1 });
  nodes.get('source-mode').value = 'realtime'; nodes.get('source-mode').onchange();
  assert.equal(nodes.get('file-path').value, vm.runInContext('defaultFilePaths.batch',context));
  nodes.get('reset-sources').onclick();
  assert.equal(nodes.get('file-path').value, vm.runInContext('defaultFilePaths.realtime', context));
  vm.runInContext('busy=true', context);
  nodes.get('file-path').value = '/keep.log';
  nodes.get('reset-sources').onclick();
  assert.equal(nodes.get('file-path').value, vm.runInContext('defaultFilePaths.batch',context));
  const html = readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');
  assert.ok(html.includes('Add source</button><button id="reset-sources"'));
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
  assert.equal(nodes.get('summary').children[2].children[0].textContent, '0');
  nodes.get('review-filter').value='needs-review'; nodes.get('review-filter').onchange();
  assert.equal(counts(1), '1 / 1 / 2');
  nodes.get('pause-updates').onclick();
  vm.runInContext("results.push({log:'timeout', category:'normal', review:false, elapsedMs:1, actionExecution:{name:'Notify',status:'failed',error:'timeout',elapsedMs:30000}}); completionOrder.push(4); completed++; render(false);", context);
  assert.equal(counts(0), '4 / 1 / 5');
  assert.equal(counts(1), '1 / 2 / 3');
  const colors = nodes.get('summary').children[1].children[0].children;
  assert.deepEqual([colors[0].className,colors[2].className,colors[4].className], ['count-success','count-failed','count-total']);
});


test('Throughput follows all other classification metrics', () => {
  const { nodes, context } = workspace([]);
  vm.runInContext('render()', context);
  assert.equal(nodes.get('summary').children.at(-1).textContent, 'Throughput');
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
  event.result.urgency = 2.37;
  event.result.ticketProbability = 0.91;
  const { nodes } = workspace([
    { type: 'start', engine: 'laya', total: 1 }, event,
    { type: 'done', elapsedMs: 10 },
  ]);
  await runTask(nodes);
  const row = nodes.get('results').children[0];
  const cards = decisionCards(row);
  assert.deepEqual(cards.map(card => card.children[0].textContent), ['Category (Choice)', 'Urgency (Score)', 'Work ticket (Noul)']);
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
  assert.equal(vm.runInContext('Object.keys(sourceFields).join(",")',context),'type,name,path');
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
  vm.runInContext("registeredActions=[{name:'Notify'}]; updateSourceSettings([registeredSources[3].id]);",context);
  const picker=nodes.get('source-settings').children[0].children[0];
  assert.equal(picker.children[0].attributes['aria-label'], 'Registered source');
  assert.equal(picker.children[0].value, 'Production logs');
  assert.match(picker.children[0].children.find(option=>option.value==='Production logs').title,/Remote File.*app/);
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
  const controls=nodes.get('source-registry').children[0].children[1].children[2];
  controls.children[1].onclick();
  vm.runInContext("sourceFields.name.value='Renamed HTTP'; sourceFields.path.value='/new/access*.log';",context);
  await nodes.get('save-sources').onclick();
  assert.equal(vm.runInContext('registeredSources[1].name',context),'Renamed HTTP');
  assert.equal(vm.runInContext('registeredSources[1].id',context),'2'.padStart(32,'0'));
  assert.equal(vm.runInContext('sourceRows[1].name.value',context),'Renamed HTTP');
  assert.equal(vm.runInContext('sourceRows[1].profile.value',context),'http_access');
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
  assert.equal(nodes.get('settings-page').hidden, false);
  vm.runInContext(`sshKeys = [{name:'production',privatePath:'/data/private_key',publicPath:'/data/public_key.pub',publicKey:'ssh-ed25519 PUBLIC'}]; renderSSHKeys();`, context);
  const row = nodes.get('ssh-key-list').children[0].children[1].children[0];
  assert.equal(row.children[0].textContent, 'production');
  assert.equal(row.children[1].textContent, '/data/private_key');
  assert.equal(row.children[2].children.length, 2);
  row.children[2].children[0].onclick();
  const card = nodes.get('ssh-key-view').children[1];
  assert.equal(card.children[2].children[0].value, 'ssh-ed25519 PUBLIC');
  assert.equal(card.children[3].children[0].value, '****');
  assert.equal(nodes.get('ssh-key-registry').hidden, true);
  const calls = [];
  context.fetch = async (path, options) => {
    calls.push({path, options});
    return {ok:true, json:async()=>({keys:[]})};
  };
  context.confirm = () => false;
  await row.children[2].children[1].onclick();
  assert.equal(calls.length, 0);
  context.confirm = () => true;
  await row.children[2].children[1].onclick();
  assert.equal(calls[0].options.method, 'DELETE');
});

test('SSH key import clears file and Sources select managed keys', async () => {
  const { nodes, context } = workspace([], null);
  const key = {name:'production',privatePath:'/data/ssh-keys/production/private_key',publicPath:'/data/ssh-keys/production/public_key.pub',publicKey:'ssh-ed25519 PUBLIC'};
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
  assert.equal(nodes.get('ssh-host-key').children[0].value, key.privatePath);
});


test('SSH key methods mask pasted multiline keys and send paths without contents', async () => {
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
  vm.runInContext("sshKeys=[{name:'test',privatePath:'/keys/private',publicPath:'/keys/public',publicKey:'PUBLIC'}];renderSSHKeys()",context);
  vm.runInContext('handleViewKey(sshKeys[0])', context);
  const card = nodes.get('ssh-key-view').children[1];
  assert.equal(card.children[3].children[0].value, '****');
  assert.equal(card.children[2].children[0].value, 'PUBLIC');
});


test('SSH key form accepts spaced names and reports input and unavailable API errors', async () => {
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


test('SSH key Add, cancel and search keep the default screen compact', async () => {
  const { nodes, context } = workspace([], null);
  const get = id => context.document.getElementById(id);
  get('open-add-ssh-key').onclick();
  assert.equal(get('ssh-key-editor').hidden, false);
  assert.equal(get('ssh-key-registry').hidden, true);
  get('cancel-ssh-key').onclick();
  assert.equal(get('ssh-key-editor').hidden, true);
  vm.runInContext("sshKeys=[{name:'one',privatePath:'/one'},{name:'two',privatePath:'/two'}];renderSSHKeys()",context);
  get('ssh-key-search').value = 'two'; get('ssh-key-search').oninput();
  const rows = get('ssh-key-list').children[0].children[1].children;
  assert.equal(rows.length, 1); assert.equal(rows[0].children[0].textContent, 'two');
});


test('SSH Hosts CRUD and Remote File selection share saved connection settings', async () => {
  const {nodes,context} = workspace([], null);
  await new Promise(resolve=>setImmediate(resolve));
  const get = id => context.document.getElementById(id);
  vm.runInContext("sshKeys=[{name:'logs',privatePath:'/keys/logs/private_key'}]",context);
  get('open-add-ssh-host').onclick();
  assert.equal(get('ssh-host-editor').hidden, false);
  assert.equal(get('ssh-host-key').children[0].value, '/keys/logs/private_key');
  get('ssh-host-name').value='Production'; get('ssh-host-address').value='logs.example';
  get('ssh-host-port').value='2222'; get('ssh-host-user').value='reader';
  get('ssh-host-key').value='/keys/logs/private_key';
  const requests=[];
  context.fetch=async(path,options)=>{
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
  assert.equal(vm.runInContext('Object.keys(sourceFields).join(",")',context),'type,name,path');
  context.confirm=()=>false;
  await row.children[4].children[2].onclick(); assert.equal(requests.length,2);
  context.confirm=()=>true;
  await row.children[4].children[2].onclick(); assert.equal(requests[2].options.method,'DELETE');
  assert.equal(get('ssh-host-message').textContent,'SSH host deleted.');
});


test('Selected Source shows its path or pattern and updates without stale text', () => {
  const {nodes,context} = workspace([], null);
  vm.runInContext("registeredSources=[{id:'one',name:'Local logs',type:'local',path:'/var/log/app/*.log'},{id:'two',name:'Remote logs',type:'ssh',path:'/srv/logs/**/*.json'}];updateSourceSettings(['one'])",context);
  const label=nodes.get('source-settings').children[0].children[0];
  const input=label.children[0]; const path=label.children[1];
  assert.equal(path.textContent,'Path: /var/log/app/*.log');
  assert.equal(path.hidden,false);
  input.value='Remote logs'; input.onchange();
  assert.equal(path.textContent,'Path: /srv/logs/**/*.json');
  input.value='Unregistered'; input.onchange();
  assert.equal(path.textContent,''); assert.equal(path.hidden,true);
});


for (const engine of ['laya', 'jev']) {
  test(`${engine} presents three equal core decisions including zero and endpoint probabilities`, async () => {
    const event = result(0, false);
    event.result.urgency = 0; event.result.ticketProbability = 0;
    const {nodes,context} = workspace([{type:'start',engine,total:1},event,{type:'done',elapsedMs:1}]);
    await runTask(nodes);
    let cards=decisionCards(nodes.get('results').children[0]);
    assert.equal(cards.length,3);
    assert.ok(cards.every(card=>card.className==='decision-card'));
    assert.equal(cards[1].children[1].textContent,'0.00 / 3');
    assert.equal(cards[2].children[1].textContent,'0.0%');
    assert.equal(cards[2].children[2].textContent,'Yes probability · 0% No → 100% Yes');
    vm.runInContext('results[0].urgency=3;results[0].ticketProbability=1;render(false)',context);
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
  assert.equal(header.children[0].textContent,'Request failed');
});


for (const engine of ['laya', 'jev']) {
  test(`${engine} scopes probability distributions and review notes to each decision`, async () => {
    const event=result(0);
    Object.assign(event.result,{
      category:'normal',uncertain:true,candidates:['normal','error'],reviewReasons:['low_answer_probability','close_probabilities'],
      probabilities:{normal:.275,warning:.2,error:.251,security:.11,other:.164},
      urgency:2,urgencyProbabilities:{0:.1,1:.2,2:.3,3:.4},
      urgencyLegend:{0:'Low: routine',1:'Medium: scheduled',2:'High: prompt',3:'Critical: immediate'},
      ticketProbability:.275,
    });
    const {nodes}=workspace([{type:'start',engine,total:1},event]);
    await runTask(nodes);
    const header=nodes.get('results').children[0].children[0];
    const cards=header.children[0].children;
    const distribution=card=>card.children.find(child=>child.className==='decision-probabilities');
    const entries=card=>distribution(card).children.map(entry=>entry.children.map(value=>value.textContent).join(': '));
    assert.deepEqual(entries(cards[0]),['Normal: 27.5%','Warning: 20.0%','Error: 25.1%','Security: 11.0%','Other: 16.4%']);
    assert.deepEqual(entries(cards[1]),['0 · Low: 10.0%','1 · Medium: 20.0%','2 · High: 30.0%','3 · Critical: 40.0%']);
    assert.deepEqual(entries(cards[2]),['Yes: 27.5%','No: 72.5%']);
    assert.match(cards[0].children.at(-1).textContent,/Category \(Choice\) provisional:/);
    assert.equal(cards[1].children.some(child=>child.className==='uncertainty-note'),false);
    assert.equal(cards[2].children.some(child=>child.className==='uncertainty-note'),false);
    assert.equal(header.children[1].children.find(child=>child.className==='review').textContent,'Category needs review');
  });
}


test('Three decisions show details by default without duplicate badges or toggles', async () => {
  const event=result(0,false);
  event.result.urgency=1.41; event.result.ticketProbability=.299;
  const {nodes,context}=workspace([event]);
  await runTask(nodes);
  const header=()=>nodes.get('results').children[0].children[0];
  const badges=()=>decisionCards(nodes.get('results').children[0]).map(card=>card.children[1]);
  assert.equal(header().children[0].className,'decision-grid');
  assert.deepEqual(badges().map(badge=>badge.textContent),['Normal','1.41 / 3','29.9%']);
  assert.match(badges()[1].title,/Urgency \(Score\)/);
  assert.match(badges()[2].title,/Work ticket \(Noul\)/);
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
  assert.deepEqual(controls.children.map(button=>button.textContent),['Run','Stop','View','Edit','History','Delete']);
  assert.equal(controls.children[1].disabled,true);
});

test('Source and Action dropdowns retain every sorted option with an existing selection', async () => {
  const {nodes,context}=workspace([]);
  await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext(`
    registeredTasks=['Zulu','가나다','Alpha','나다라'].map((name,index)=>({id:String(index),name,mode:'batch',sources:[]}));
    selectedTaskId='0'; renderTaskMonitor();
    registeredSources=['Zulu','가나다','Alpha','나다라'].map((name,index)=>({id:String(index),name,type:'local',path:'/logs/'+index}));
    registeredActions=[{name:'Zulu'},{name:'Alpha'}];
    sourcePreferences.set('0',{profile:'general',chunkEvents:1,action:'Zulu'});
    updateSourceSettings(['0']);
  `,context);
  const row=nodes.get('source-settings').children[0];
  const source=row.children[0].children[0]; const action=row.children[3].children[0];
  const expected=['가나다','나다라','Alpha','Zulu'];
  assert.deepEqual(source.children.map(option=>option.value),expected);
  assert.equal(source.value,'Zulu');
  assert.deepEqual(action.children.map(option=>option.value),['','Alpha','Zulu']);
  assert.equal(action.value,'Zulu');
  const html=readFileSync(new URL('../public/index.html',import.meta.url),'utf8');
  assert.ok(html.includes('id="running-tasks"'));
  assert.equal(html.includes('Select a Task…'),false);
  assert.equal(html.includes('monitor-task-options'),false);
});

test('Main lists only running Tasks in name order and clicking changes the displayed run', async () => {
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
  assert.deepEqual(buttons.map(button=>button.children[0].textContent),['Alpha','Zulu']);
  assert.ok(buttons.every(button=>button.attributes['aria-pressed']==='false'));
  await buttons[1].onclick();
  assert.equal(vm.runInContext('selectedTaskId',context),'z');
  assert.equal(vm.runInContext('watched.join()',context),'run-z');
  assert.equal(nodes.get('running-tasks').children[1].attributes['aria-pressed'],'true');
  vm.runInContext('registeredTasks=[];renderTaskMonitor()',context);
  assert.match(nodes.get('running-tasks').children[0].textContent,/No Tasks are currently running/);
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
    sshKeys=[{name:'Key',privatePath:'/keys/private_key'}];handleEditHost();
    registeredSources=[{id:'source',name:'Logs',type:'local',path:'/logs/app.log'}];
    updateSourceSettings(['']);
  `,context);
  const key=nodes.get('ssh-host-key');
  assert.deepEqual(key.children.map(option=>option.text),['Key']);
  assert.equal(key.value,'');
  const source=nodes.get('source-settings').children[0].children[0].children[0];
  assert.deepEqual(source.children.map(option=>option.text),['Logs']);
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
  assert.match(script,/button.onclick=\(\)=>handleSelectTask\(task.id\)/);
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
  vm.runInContext("sshKeys=[{name:'Key',privatePath:'/keys/private'}];handleEditHost()",context);
  nodes.get('ssh-host-name').value='Draft';nodes.get('ssh-host-address').value='logs.example';
  nodes.get('ssh-host-port').value='2222';nodes.get('ssh-host-user').value='reader';nodes.get('ssh-host-key').value='/keys/private';
  const calls=[];
  context.fetch=async(path,options)=>{calls.push({path,body:JSON.parse(options.body)});return {ok:true,json:async()=>({connected:true,checkedAt:'2026-10-16T00:00:00Z',elapsedMs:12})};};
  await nodes.get('test-ssh-host').onclick();
  assert.equal(calls[0].path,'/api/ssh-hosts/test');
  assert.equal(calls[0].body.port,2222);
  assert.match(nodes.get('ssh-host-test-result').textContent,/Connected \(SSH \+ SFTP\)/);
  assert.equal(vm.runInContext('sshHosts.length',context),0);
  vm.runInContext("sshHosts=[{...hostDraft(),id:'saved'}];renderSSHHosts()",context);
  let row=nodes.get('ssh-host-list').children[0].children[1].children[0];
  assert.match(row.children[3].textContent,/Connected/);
  context.fetch=async(path,options)=>{calls.push({path,body:JSON.parse(options.body)});return {ok:true,json:async()=>({connected:false,error:'Permission denied',checkedAt:'2026-10-16T00:01:00Z',elapsedMs:5})};};
  await row.children[4].children[3].onclick();
  assert.deepEqual(calls[1].body,{id:'saved'});
  row=nodes.get('ssh-host-list').children[0].children[1].children[0];
  assert.match(row.children[3].textContent,/Failed.*Permission denied/);
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

test('Visible SSH Hosts auto-check sequentially, prevent duplicate passes, and repeat after 30 seconds', async () => {
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
  assert.deepEqual(calls,['a','b']);assert.equal(maxActive,1);assert.equal(delays.at(-1),30000);
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
  const profiles={general:{label:'General',instructions:'Instructions',criteria:definitions},custom:{label:'Custom',instructions:'Instructions',criteria:definitions}};
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
  await vm.runInContext("handleEditTask({id:'test-task',name:'Fleet',mode:'batch',sources:[{sourceId:'remote',profile:'general',chunkEvents:1,hostIds:['a']}]})",context);
  const row=nodes.get('source-settings').children[0];const picker=row.children[4];
  assert.equal(picker.hidden,false);assert.equal(picker.children[0].textContent,'SSH Hosts · 1 selected');
  picker.children[1].value='Beta';picker.children[1].oninput();
  assert.equal(picker.children[3].children.length,1);
  picker.children[2].children[0].onclick();
  assert.equal(picker.children[0].textContent,'SSH Hosts · 2 selected');
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
  assert.match(nodes.get('host-status').children[0].textContent,/Beta.*failed.*Host unavailable/);
  assert.equal(nodes.get('results').children[0].children[0].children[0].textContent,'Source failed');
  nodes.get('source-filter').value='/same';nodes.get('source-filter').onchange();
  assert.deepEqual(logs(nodes),['log-1']);
});
