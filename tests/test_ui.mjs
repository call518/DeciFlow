import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { test } from 'node:test';

function workspace(events, status) {
  const nodes = new Map();
  const requests = [];
  const node = () => ({
    children: [], value: '', checked: false, attributes: {},
    append(...children) { this.children.push(...children); },
    replaceChildren() { this.children = []; },
    setAttribute(name, value) { this.attributes[name] = value; },
  });
  const context = vm.createContext({
    document: {
      getElementById(id) {
        if (!nodes.has(id)) nodes.set(id, node());
        return nodes.get(id);
      },
      createElement: node,
    },
    Option: function(text, value) { return { text, value }; },
    AbortController,
    setTimeout: () => 1,
    clearTimeout() {},
    fetch: async (path, options) => {
      if (path === '/api/status') return status ? { ok: true, json: async () => status } : new Promise(() => {});
      requests.push(JSON.parse(options.body));
      return { ok: true, body: {} };
    },
    readEvents: async (_, receive) => events.forEach(receive),
  });
  context.document.getElementById('review-filter').value = 'all';
  context.document.getElementById('category-filter').value = 'all';
  context.document.getElementById('chart-certainty').value = 'all';
  const source = readFileSync(new URL('../public/app.js', import.meta.url), 'utf8');
  vm.runInContext(source.replace(/^import .*;\n/, ''), context);
  return { nodes, context, requests };
}

function result(index, review = true) {
  return {
    type: 'result', index, elapsedMs: index,
    result: { log: `log-${index}`, category: 'normal', confidence: .9,
      elapsedMs: 1, probabilities: { normal: 1 }, review },
  };
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
  await nodes.get('classify').onclick();
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
  await nodes.get('classify').onclick();
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
  assert.equal(average(), '0.0ms');
  await nodes.get('classify').onclick();
  assert.equal(average(), '200.0ms');
  nodes.get('review-filter').value = 'needs-review';
  nodes.get('review-filter').onchange();
  assert.equal(average(), '200.0ms');
  assert.equal(logs(nodes).length, 1);
  events.splice(0, events.length, { type: 'start', engine: 'jev', total: 1 }, result(0));
  await nodes.get('classify').onclick();
  assert.equal(average(), '1.0ms');
});

test('three review filters partition results without changing totals', async () => {
  const events = [{ type: 'start', engine: 'laya', total: 3 },
    result(0, false), result(1),
    { type: 'result', index: 2, elapsedMs: 2,
      result: { log: 'failed-log', error: 'timeout', elapsedMs: 2, review: true } }];
  const { nodes } = workspace(events);
  await nodes.get('classify').onclick();
  assert.deepEqual(logs(nodes), ['failed-log', 'log-1', 'log-0']);
  for (const [filter, expected] of [
    ['needs-review', ['failed-log', 'log-1']],
    ['no-review', ['log-0']],
    ['all', ['failed-log', 'log-1', 'log-0']],
  ]) {
    nodes.get('review-filter').value = filter;
    nodes.get('review-filter').onchange();
    assert.deepEqual(logs(nodes), expected);
    assert.equal(nodes.get('summary').children[0].children[0].textContent, '3');
    assert.equal(nodes.get('summary').children[1].children[0].textContent, '2');
  }
  nodes.get('review-filter').value = 'no-review';
  events.splice(0, events.length, { type: 'start', engine: 'jev', total: 1 }, result(0));
  await nodes.get('classify').onclick();
  assert.equal(nodes.get('results').children[0].textContent, 'No results to display.');
});

test('analysis modes show operator-oriented labels and actions', () => {
  const html = readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');
  for (const [value, label] of [['paste', 'Paste'], ['batch', 'Batch'],
    ['realtime', 'Realtime']]) {
    assert.ok(html.includes(`<option value="${value}"${value === 'realtime' ? ' selected' : ''}>${label}</option>`));
  }
  const { nodes } = workspace([]);
  for (const [mode, action] of [['paste', 'Classify with Laya ↗'],
    ['batch', 'Run batch with Laya ↗'],
    ['realtime', 'Start realtime with Laya ↗']]) {
    nodes.get('source-mode').value = mode;
    nodes.get('source-mode').onchange();
    assert.equal(nodes.get('classify').textContent, action);
    assert.equal(nodes.get('file-input').hidden, mode === 'paste');
    assert.equal(nodes.get('file-notes').hidden, mode === 'paste');
    assert.equal(nodes.get('paste-input').hidden, mode !== 'paste');
  }
});

test('log input explains each analysis mode before the selector', () => {
  const html = readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');
  const help = html.slice(html.indexOf('class="mode-help"'), html.indexOf('class="source-controls"'));
  for (const description of [
    'Paste:</strong> Paste log text for analysis.',
    'Batch:</strong> Analyze existing log files from the beginning.',
    'Realtime:</strong> Monitor and analyze new log lines as they arrive.',
  ]) assert.ok(help.includes(description));
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
  assert.equal(active(), '0ms (N/A)');
  await nodes.get('classify').onclick();
  assert.equal(active(), '150ms (15.0%)');
  assert.ok(nodes.get('summary').children[4].title.includes('not CPU utilization'));
  nodes.get('review-filter').value = 'no-review';
  nodes.get('review-filter').onchange();
  assert.equal(active(), '150ms (15.0%)');
  events.at(-1).elapsedMs = 200;
  await nodes.get('classify').onclick();
  assert.equal(active(), '150ms (75.0%)');
  events.splice(0, events.length, { type: 'start', engine: 'jev', total: 1 }, result(0));
  await nodes.get('classify').onclick();
  assert.equal(active(), '0ms (N/A)');
});

test('connection status shares the title row without a breadcrumb header', () => {
  const html = readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');
  assert.ok(!html.includes('Workspace / Log classification'));
  assert.ok(!html.includes('<header>'));
  const title = html.match(/<div class="intro-title">(.*?)<\/div>/s)[1];
  assert.ok(title.includes('<h1>Turn logs into decisions.</h1>'));
  assert.ok(title.includes('id="status"'));
  assert.equal((html.match(/id="status"/g) || []).length, 1);
});

test('Realtime is the default mode before server status loads', () => {
  const html = readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');
  assert.ok(html.includes('<option value="realtime" selected>Realtime</option>'));
  assert.ok(html.includes('<div id="file-input">'));
  assert.ok(html.includes('<div id="paste-input" hidden>'));
  const { context } = workspace([]);
  assert.equal(vm.runInContext('sourceMode', context), 'realtime');
});

test('each mode has editable sample input and retains its own edits', () => {
  const { nodes } = workspace([]);
  assert.equal(nodes.get('file-path').value, '/host-logs/var/log/secure\n/host-logs/var/log/messages\n/host-logs/var/log/nginx/access*.log');
  assert.equal(nodes.get('logs').value.split('\n').length, 5);
  nodes.get('file-path').value = '/custom/live.log';
  nodes.get('source-mode').value = 'batch';
  nodes.get('source-mode').onchange();
  assert.equal(nodes.get('file-path').value, '/host-logs/sample-logs/access-1k.log\n/host-logs/var/log/messages\n/host-logs/var/log/nginx/access*.log');
  nodes.get('file-path').value = '/custom/batch.log';
  nodes.get('source-mode').value = 'paste';
  nodes.get('source-mode').onchange();
  nodes.get('logs').value = 'custom pasted log';
  nodes.get('source-mode').value = 'realtime';
  nodes.get('source-mode').onchange();
  assert.equal(nodes.get('file-path').value, '/custom/live.log');
  nodes.get('source-mode').value = 'batch';
  nodes.get('source-mode').onchange();
  assert.equal(nodes.get('file-path').value, '/custom/batch.log');
  nodes.get('source-mode').value = 'paste';
  nodes.get('source-mode').onchange();
  assert.equal(nodes.get('logs').value, 'custom pasted log');
  nodes.get('source-mode').value = 'realtime';
  nodes.get('source-mode').onchange();
  nodes.get('file-path').value = '';
  nodes.get('source-mode').value = 'batch';
  nodes.get('source-mode').onchange();
  nodes.get('source-mode').value = 'realtime';
  nodes.get('source-mode').onchange();
  assert.equal(nodes.get('file-path').value, '');
});

test('mode selector and descriptions use Realtime, Batch, Paste order', () => {
  const html = readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');
  const selector = html.match(/<select id="source-mode">(.*?)<\/select>/s)[1];
  assert.deepEqual([...selector.matchAll(/>(Realtime|Batch|Paste)<\/option>/g)]
    .map(match => match[1]), ['Realtime', 'Batch', 'Paste']);
  const help = html.match(/<div class="mode-help">(.*?)<\/div>/s)[1];
  assert.deepEqual([...help.matchAll(/<strong>(Realtime|Batch|Paste):/g)]
    .map(match => match[1]), ['Realtime', 'Batch', 'Paste']);
});

 test('sidebar identifies the local log source host', async () => {
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

test('source profile and chunk settings reach the API and survive mode changes', async () => {
  const { nodes, context, requests } = workspace([]);
  nodes.get('file-path').value = '/var/log/secure\n/var/log/nginx/access*.log';
  nodes.get('file-path').oninput();
  vm.runInContext(`sourceRows[0].profile.value = 'authentication'; sourceRows[0].profile.onchange(); sourceRows[0].size.value = '3'; sourceRows[0].size.oninput(); sourceRows[1].profile.value = 'http_access'; sourceRows[1].profile.onchange();`, context);
  await nodes.get('classify').onclick();
  assert.equal(requests[0].sources[0].profile, 'authentication');
  assert.equal(requests[0].sources[0].chunkLines, 3);
  assert.equal(requests[0].sources[1].profile, 'http_access');
  nodes.get('source-mode').value = 'paste'; nodes.get('source-mode').onchange();
  nodes.get('paste-profile').value = 'network'; nodes.get('paste-chunk-lines').value = '4';
  await nodes.get('classify').onclick();
  assert.equal(requests[1].profile, 'network'); assert.equal(requests[1].chunkLines, 4);
  nodes.get('source-mode').value = 'realtime'; nodes.get('source-mode').onchange();
  assert.equal(vm.runInContext('sourceRows[0].size.value', context), '3');
});

test('individual JSON reflects review changes and stays open after rendering', async () => {
  const event = result(0);
  Object.assign(event.result, { profile: 'http_access', chunkLines: 3, lineCount: 2, source: '/logs/access.log', line: 10, lineEnd: 11, log: '<script>example</script>' });
  const failed = result(1);
  failed.result = { log: 'bad input', error: 'request failed', review: true, elapsedMs: 1, profile: 'network' };
  const { nodes, context } = workspace([{ type: 'start', total: 2, engine: 'laya' }, event, failed]);
  await nodes.get('classify').onclick();
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
  const run = nodes.get('classify').onclick();
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
  assert.equal(nodes.get('summary').children[0].children[0].textContent, '3');
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
  await nodes.get('classify').onclick();
  assert.equal(nodes.get('pause-updates').textContent, 'Pause updates');
  assert.deepEqual(logs(nodes), ['log-0']);
});

test('pause excludes received results that have not yet been displayed', async () => {
  const { nodes, context } = workspace([{ type: 'start', total: null, engine: 'laya' }, result(0)]);
  await nodes.get('classify').onclick();
  vm.runInContext("results[1] = { log: 'queued', elapsedMs: 1, review: true }; completionOrder.push(1); completed++;", context);
  nodes.get('pause-updates').onclick();
  nodes.get('review-filter').onchange();
  assert.deepEqual(logs(nodes), ['log-0']);
  assert.equal(nodes.get('pause-updates').textContent, 'Resume updates (1 new)');
});

test('file line labels distinguish batch from observed realtime sequences', async () => {
  for (const mode of ['batch', 'realtime']) {
    const first = result(0);
    Object.assign(first.result, { source: '/var/log/secure', line: 1, lineEnd: 1, profile: 'general', lineCount: 1, chunkLines: 1 });
    const second = result(1);
    Object.assign(second.result, { source: '/var/log/secure', line: 10, lineEnd: 12, profile: 'authentication', lineCount: 3, chunkLines: 5 });
    const { nodes, context } = workspace([{ type: 'start', engine: 'laya', total: null, mode }, first, second]);
    await nodes.get('classify').onclick();
    const rows = nodes.get('results').children;
    const prefix = mode === 'realtime' ? 'Observed' : 'File';
    assert.equal(rows[1].children[2].textContent, `/var/log/secure · ${prefix} line 1`);
    assert.equal(rows[0].children[2].textContent, `/var/log/secure · ${prefix} lines 10–12`);
    assert.equal(rows[1].children[3].textContent, 'General system · 1 line (max 1)');
    assert.equal(rows[0].children[3].textContent, 'Authentication · 3 lines (max 5)');
    if (mode === 'realtime') assert.ok(rows[1].children[2].title.includes('not an absolute'));
    nodes.get('source-mode').value = mode === 'realtime' ? 'batch' : 'realtime';
    nodes.get('source-mode').onchange();
    vm.runInContext('render()', context);
    assert.equal(nodes.get('results').children[1].children[2].textContent, `/var/log/secure · ${prefix} line 1`);
  }
});

test('realtime can pause before receiving its first result', async () => {
  const { nodes, context } = workspace([]);
  let receive, finish;
  context.readEvents = async (_, callback) => {
    receive = callback;
    await new Promise(resolve => { finish = resolve; });
  };
  const run = nodes.get('classify').onclick();
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
  assert.ok(html.includes('<label>Criteria <select id="paste-profile">'));
});

test('category chart counts all sources, separates failures, and ignores filters and edits', async () => {
  const events = [{ type: 'start', engine: 'laya', total: null }];
  for (const [index, category] of ['normal', 'normal', 'warning', 'error', 'security', 'other'].entries()) {
    const event = result(index, index % 2 === 0);
    Object.assign(event.result, { category, source: index % 2 ? '/logs/http' : '/logs/system', lineCount: 10, chunkLines: 10 });
    events.push(event);
  }
  const failure = result(6);
  failure.result = { log: 'failed', error: 'timeout', review: true, elapsedMs: 1, category: 'error' };
  events.push(failure);
  const { nodes, context } = workspace(events);
  const values = () => nodes.get('category-chart').children.map(row => row.children[2].textContent);
  assert.deepEqual(values(), Array(5).fill('0 (0.0%)'));
  await nodes.get('classify').onclick();
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
  await nodes.get('classify').onclick();
  assert.deepEqual(values(), Array(5).fill('0 (0.0%)'));
});

test('category overview precedes Log input and Classification results', () => {
  const html = readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');
  assert.ok(html.indexOf('Classification overview') < html.indexOf('Log input'));
  assert.ok(html.indexOf('Classification overview') < html.indexOf('Classification results'));
});

test('uncertain category is explicitly provisional without changing the model choice', async () => {
  const event = result(0);
  Object.assign(event.result, { category: 'error', confidence: .26, uncertain: true,
    candidates: ['error', 'other'], reviewReasons: ['low_confidence', 'close_probabilities'],
    probabilities: { normal: .01, warning: .18, error: .41, security: 0, other: .4 } });
  const { nodes } = workspace([{ type: 'start', engine: 'jev', total: 1 }, event]);
  await nodes.get('classify').onclick();
  const row = nodes.get('results').children[0];
  assert.equal(row.children[0].children[0].textContent, 'Uncertain · Error');
  assert.ok(row.children[2].textContent.includes('Error 41.0% vs Other 40.0%'));
  assert.ok(row.children[2].textContent.includes('close category probabilities'));
  const details = row.children.at(-1); details.open = true; details.ontoggle();
  assert.equal(JSON.parse(details.children[1].children[1].textContent).category, 'error');
  assert.equal(nodes.get('category-chart').children[2].children[2].textContent, '1 (100.0%)');
});

test('workspace places input and overview in the 40% column beside 60% results', () => {
  const html = readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');
  const css = readFileSync(new URL('../public/style.css', import.meta.url), 'utf8');
  const leftStart = html.indexOf('<div class="input-column">');
  const leftEnd = html.indexOf('</div>\n      <section class="card output">', leftStart);
  assert.ok(leftStart >= 0 && leftEnd > leftStart);
  const left = html.slice(leftStart, leftEnd);
  assert.ok(left.includes('Log input'));
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
  await nodes.get('classify').onclick();
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
  assert.deepEqual(logs(nodes), ['Service request failed']);
  assert.equal(nodes.get('summary').children[0].children[0].textContent, '3');
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
  await nodes.get('classify').onclick();
  const values = () => nodes.get('category-chart').children.map(row => row.children[2].textContent);
  nodes.get('pause-updates').onclick();
  nodes.get('chart-certainty').value = 'uncertain'; nodes.get('chart-certainty').onchange();
  assert.deepEqual(values(), ['0 (0.0%)', '0 (0.0%)', '1 (100.0%)', '0 (0.0%)', '0 (0.0%)']);
  assert.equal(nodes.get('chart-totals').textContent, '1 classified chunk · 1 failed request');
  nodes.get('chart-certainty').value = 'certain'; nodes.get('chart-certainty').onchange();
  assert.deepEqual(values(), ['1 (50.0%)', '0 (0.0%)', '0 (0.0%)', '0 (0.0%)', '1 (50.0%)']);
  assert.equal(nodes.get('summary').children[0].children[0].textContent, '4');
  assert.equal(nodes.get('results').children.length, 4);
  nodes.get('chart-certainty').value = 'all'; nodes.get('chart-certainty').onchange();
  assert.equal(nodes.get('chart-totals').textContent, '3 classified chunks · 1 failed request');
});

test('truncated count includes rejected responses across chart filters and paused updates', async () => {
  const events = [{ type: 'start', engine: 'laya', total: 3 }, result(0, false),
    { type: 'result', index: 1, result: { log: 'too long', error: 'truncated', review: true, elapsedMs: 1, providerResponse: { usage: { truncated: true } } } },
    { type: 'result', index: 2, result: { log: 'timeout', error: 'timeout', review: true, elapsedMs: 1 } }];
  const { nodes, context } = workspace(events);
  await nodes.get('classify').onclick();
  assert.equal(nodes.get('chart-truncated').textContent, 'Truncated: 1');
  nodes.get('chart-certainty').value = 'certain'; nodes.get('chart-certainty').onchange();
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
  await nodes.get('classify').onclick();
  assert.equal(nodes.get('results').children[0].children[0].children[1].textContent, '90.0% category probability · 1ms');
});

test('collapsed options show the rendering integrity warning', async () => {
  const event = result(0);
  Object.assign(event.result, {
    uncertain: true, candidates: ['normal'], reviewReasons: ['collapsed_options'],
  });
  const { nodes } = workspace([{ type: 'start', engine: 'laya', total: 1 }, event]);
  await nodes.get('classify').onclick();
  const texts = nodes.get('results').children[0].children.map(child => child.textContent || '');
  assert.ok(texts.some(text => text.includes('option descriptions lost distinction')));
});

test('Copy JSON copies current reviewer edits and reports success or failure', async () => {
  const { nodes, context } = workspace([
    { type: 'start', engine: 'laya', total: 1 }, result(0),
  ]);
  let copied;
  context.navigator = { clipboard: { writeText: async text => { copied = text; } } };
  await nodes.get('classify').onclick();
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
  const css = readFileSync(new URL('../public/style.css', import.meta.url), 'utf8');
  assert.match(css, /\.quiet\{[^}]*border:1px solid/);
  assert.match(css, /\.result-json summary\{[^}]*border:1px solid/);
});

test('stream errors are red and a new successful run clears the error style', async () => {
  const events = [{ type: 'error', error: 'File access denied' }];
  const { nodes } = workspace(events);
  await nodes.get('classify').onclick();
  assert.equal(nodes.get('message').className, 'error-message');
  events.splice(0, events.length, { type: 'start', engine: 'laya', total: 1 }, result(0));
  await nodes.get('classify').onclick();
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
      assert.equal(status.children.length, configured ? 1 : 2);
      if (!configured) assert.equal(status.children[1].textContent, ' · API key required');
    }
  }
  const css = readFileSync(new URL('../public/style.css', import.meta.url), 'utf8');
  assert.ok(css.includes('.selected-engine{color:#a23e34;font-weight:700}'));
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
    await nodes.get('classify').onclick();
    for (const [index, row] of nodes.get('results').children.entries()) {
      const category = categories[categories.length - 1 - index];
      const badge = row.children[0].children[0];
      assert.equal(badge.className, `badge ${category}${uncertain ? ' uncertain' : ''}`);
      assert.equal(badge.textContent.startsWith('Uncertain · '), uncertain);
    }
  }
  const css = readFileSync(new URL('../public/style.css', import.meta.url), 'utf8');
  assert.doesNotMatch(css, /\.badge\.uncertain\{[^}]*background/);
});


test('chart bars and result badges share the same category colors', () => {
  const css = readFileSync(new URL('../public/style.css', import.meta.url), 'utf8');
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
  const rate = () => nodes.get('summary').children[2].children[0].textContent;
  await nodes.get('classify').onclick();
  assert.equal(rate(), '0.2 chunks/s');
  nodes.get('review-filter').value = 'no-review';
  nodes.get('review-filter').onchange();
  assert.equal(rate(), '0.2 chunks/s');
  events.push({ type: 'timing', elapsedMs: 11000 });
  await nodes.get('classify').onclick();
  assert.equal(rate(), '0.0 chunks/s');
  events.splice(0, events.length, { type: 'start', engine: 'jev', total: 1 },
    success(0, 1000));
  await nodes.get('classify').onclick();
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
  await nodes.get('classify').onclick();
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
  assert.equal(nodes.get('summary').children[0].children[0].textContent, '2');
  select.value = '/logs/*'; select.onchange();
  assert.deepEqual(logs(nodes), ['service failed']);
  events.splice(0, events.length, { type: 'start', engine: 'laya', total: null,
    sourcePatterns: ['/logs/new.log'] });
  await nodes.get('classify').onclick();
  assert.equal(select.value, 'all');
  assert.ok(!select.children.some(option => option.value === '/logs/messages'));
});
