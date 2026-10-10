import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { test } from 'node:test';

function workspace(events, status) {
  const nodes = new Map();
  const requests = [];
  const node = () => ({
    children: [], value: '', checked: false,
    append(...children) { this.children.push(...children); },
    replaceChildren() { this.children = []; },
    setAttribute() {},
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
  const average = () => nodes.get('summary').children[4].children[0].textContent;
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
  for (const [value, label] of [['text', 'Paste'], ['batch', 'Batch'],
    ['follow', 'Realtime']]) {
    assert.ok(html.includes(`<option value="${value}"${value === 'follow' ? ' selected' : ''}>${label}</option>`));
  }
  const { nodes } = workspace([]);
  for (const [mode, action] of [['text', 'Classify with Laya ↗'],
    ['batch', 'Run batch with Laya ↗'],
    ['follow', 'Start realtime with Laya ↗']]) {
    nodes.get('source-mode').value = mode;
    nodes.get('source-mode').onchange();
    assert.equal(nodes.get('classify').textContent, action);
    assert.equal(nodes.get('file-input').hidden, mode === 'text');
    assert.equal(nodes.get('file-notes').hidden, mode === 'text');
    assert.equal(nodes.get('paste-input').hidden, mode !== 'text');
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
  const active = () => nodes.get('summary').children[3].children[0].textContent;
  vm.runInContext('render()', context);
  assert.equal(active(), '0ms (N/A)');
  await nodes.get('classify').onclick();
  assert.equal(active(), '150ms (15.0%)');
  assert.ok(nodes.get('summary').children[3].title.includes('not CPU utilization'));
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
  assert.ok(html.includes('<option value="follow" selected>Realtime</option>'));
  assert.ok(html.includes('<div id="file-input">'));
  assert.ok(html.includes('<div id="paste-input" hidden>'));
  const { context } = workspace([]);
  assert.equal(vm.runInContext('sourceMode', context), 'follow');
});

test('each mode has editable sample input and retains its own edits', () => {
  const { nodes } = workspace([]);
  assert.equal(nodes.get('file-path').value, '/var/log/secure\n/var/log/messages\n/var/log/nginx/access*.log');
  assert.equal(nodes.get('logs').value.split('\n').length, 5);
  nodes.get('file-path').value = '/custom/live.log';
  nodes.get('source-mode').value = 'batch';
  nodes.get('source-mode').onchange();
  assert.equal(nodes.get('file-path').value, 'sample-logs/access-1k.log\n/var/log/messages\n/var/log/nginx/access*.log');
  nodes.get('file-path').value = '/custom/batch.log';
  nodes.get('source-mode').value = 'text';
  nodes.get('source-mode').onchange();
  nodes.get('logs').value = 'custom pasted log';
  nodes.get('source-mode').value = 'follow';
  nodes.get('source-mode').onchange();
  assert.equal(nodes.get('file-path').value, '/custom/live.log');
  nodes.get('source-mode').value = 'batch';
  nodes.get('source-mode').onchange();
  assert.equal(nodes.get('file-path').value, '/custom/batch.log');
  nodes.get('source-mode').value = 'text';
  nodes.get('source-mode').onchange();
  assert.equal(nodes.get('logs').value, 'custom pasted log');
  nodes.get('source-mode').value = 'follow';
  nodes.get('source-mode').onchange();
  nodes.get('file-path').value = '';
  nodes.get('source-mode').value = 'batch';
  nodes.get('source-mode').onchange();
  nodes.get('source-mode').value = 'follow';
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
  nodes.get('source-mode').value = 'text'; nodes.get('source-mode').onchange();
  nodes.get('paste-profile').value = 'network'; nodes.get('paste-chunk-lines').value = '4';
  await nodes.get('classify').onclick();
  assert.equal(requests[1].profile, 'network'); assert.equal(requests[1].chunkLines, 4);
  nodes.get('source-mode').value = 'follow'; nodes.get('source-mode').onchange();
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
  assert.equal(details.children[1].textContent, '');
  details.open = true; details.ontoggle();
  assert.equal(JSON.parse(details.children[1].textContent).lineEnd, 11);
  assert.equal(JSON.parse(details.children[1].textContent).log, '<script>example</script>');
  const select = row.children.at(-2).children[0];
  select.value = 'warning'; select.onchange();
  assert.equal(JSON.parse(details.children[1].textContent).reviewerCategory, 'warning');
  vm.runInContext('render()', context);
  const reopened = nodes.get('results').children[1].children.at(-1);
  assert.equal(reopened.open, true);
  reopened.open = false; reopened.ontoggle();
  vm.runInContext('render()', context);
  assert.equal(nodes.get('results').children[1].children.at(-1).open, false);
  const failureView = nodes.get('results').children[0].children.at(-1);
  failureView.open = true; failureView.ontoggle();
  assert.equal(JSON.parse(failureView.children[1].textContent).error, 'request failed');
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
  for (const mode of ['batch', 'follow']) {
    const first = result(0);
    Object.assign(first.result, { source: '/var/log/secure', line: 1, lineEnd: 1, profile: 'general', lineCount: 1, chunkLines: 1 });
    const second = result(1);
    Object.assign(second.result, { source: '/var/log/secure', line: 10, lineEnd: 12, profile: 'authentication', lineCount: 3, chunkLines: 5 });
    const { nodes, context } = workspace([{ type: 'start', engine: 'laya', total: null, mode }, first, second]);
    await nodes.get('classify').onclick();
    const rows = nodes.get('results').children;
    const prefix = mode === 'follow' ? 'Observed' : 'File';
    assert.equal(rows[1].children[2].textContent, `/var/log/secure · ${prefix} line 1`);
    assert.equal(rows[0].children[2].textContent, `/var/log/secure · ${prefix} lines 10–12`);
    assert.equal(rows[1].children[3].textContent, 'General system · 1 line (max 1)');
    assert.equal(rows[0].children[3].textContent, 'Authentication · 3 lines (max 5)');
    if (mode === 'follow') assert.ok(rows[1].children[2].title.includes('not an absolute'));
    nodes.get('source-mode').value = mode === 'follow' ? 'batch' : 'follow';
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
  receive({ type: 'start', engine: 'laya', mode: 'follow', total: null });
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
