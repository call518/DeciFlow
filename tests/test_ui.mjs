import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { test } from 'node:test';

function workspace(events) {
  const nodes = new Map();
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
    fetch: async path => path === '/api/status'
      ? new Promise(() => {})
      : { ok: true, body: {} },
    readEvents: async (_, receive) => events.forEach(receive),
  });
  context.document.getElementById('review-filter').value = 'all';
  const source = readFileSync(new URL('../public/app.js', import.meta.url), 'utf8');
  vm.runInContext(source.replace(/^import .*;\n/, ''), context);
  return { nodes, context };
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
  const select = nodes.get('results').children[0].children.at(-1).children[0];
  select.value = 'warning';
  select.onchange();
  vm.runInContext('render()', context);
  assert.equal(nodes.get('results').children[0].children.at(-1).children[0].value,
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
