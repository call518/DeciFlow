import { readEvents } from './stream.js';

const $ = id => document.getElementById(id);
const labels = { normal: 'Normal', warning: 'Warning', error: 'Error', security: 'Security', other: 'Other' };
const samples = [
  '2026-10-10T09:00:00 INFO gateway request completed status=200 latency=24ms',
  '2026-10-10T09:00:01 WARN cache miss rate elevated; fallback succeeded',
  '2026-10-10T09:00:02 ERROR database connection refused; checkout failed',
  '2026-10-10T09:00:03 SECURITY repeated unauthorized admin access blocked',
  '2026-10-10T09:00:04 event=zx17 value=unknown',
];
let results = [];
let completionOrder = [];
let elapsedMs = 0;
let activeProcessingMs = 0;
let busy = false;
let page = 0;
let total = 0;
let completed = 0;
let renderTimer;
let activeRequest;
let sourceMode = 'follow';
const filePaths = {
  batch: 'sample-logs/access-1k.log\n/var/log/messages\n/var/log/nginx/access*.log',
  follow: '/var/log/secure\n/var/log/messages\n/var/log/nginx/access*.log',
};
$('logs').value = samples.join('\n');
$('file-path').value = filePaths[sourceMode];
let engine = 'laya';
let resultEngine = engine;
let engineLabel = 'Laya';
function element(tag, text, className = '') {
  const node = document.createElement(tag);
  node.textContent = text;
  node.className = className;
  return node;
}
function render() {
  $('summary').replaceChildren();
  const processingMs = results.reduce((sum, result) => sum + result.elapsedMs, 0);
  const averageMs = completed ? processingMs / completed : 0;
  const processingPercent = elapsedMs > 0 ? `${(activeProcessingMs / elapsedMs * 100).toFixed(1)}%` : 'N/A';
  for (const [label, value] of [['Processed logs', completed], ['Needs review', results.filter(r => r.review).length], ['Total elapsed time', `${elapsedMs}ms`], ['Active processing time', `${activeProcessingMs}ms (${processingPercent})`], ['Average processing time', `${averageMs.toFixed(1)}ms`]]) {
    const metric = element('div', label, 'metric');
    if (label === 'Needs review') metric.title = 'Confidence below 70%, Other category, or failed request; not an error count.';
    if (label === 'Average processing time') metric.title = 'Mean request duration, including network/server wait and failed requests; excludes waiting for new file lines.';
    if (label === 'Active processing time') metric.title = 'Time with at least one request in flight, counting overlapping requests once. Includes network/server wait, excludes idle time; not CPU utilization.';
    metric.append(element('strong', String(value)));
    $('summary').append(metric);
  }
  $('results').replaceChildren();
  const visible = completionOrder.toReversed().map(index => results[index]).filter(r => $('review-filter').value === 'all' || ($('review-filter').value === 'needs-review' ? r.review : !r.review));
  const pages = Math.max(1, Math.ceil(visible.length / 100));
  page = Math.min(page, pages - 1);
  $('page-info').textContent = `Page ${page + 1} of ${pages} · ${visible.length} results`;
  $('previous').disabled = page === 0;
  $('next').disabled = page >= pages - 1;
  for (const result of visible.slice(page * 100, (page + 1) * 100)) {
    const row = element('article', '', 'result');
    const top = element('div', '', 'result-top');
    top.append(element('span', result.error ? 'Request failed' : labels[result.category], `badge ${result.category || 'error'}`));
    top.append(element('span', `${Math.round(result.confidence * 100) || 0}% confidence · ${result.elapsedMs}ms`));
    if (result.review) top.append(element('span', 'Needs review', 'review'));
    row.append(top, element('p', result.log, 'log'));
    if (result.source) row.append(element('p', `${result.source} · Line ${result.line}${result.incomplete ? ' · Incomplete line at rotation' : ''}`, 'caption'));
    if (result.error) row.append(element('p', result.error, 'error-message'));
    else {
      row.append(element('div', Object.entries(result.probabilities).map(([key, value]) => `${labels[key]} ${Math.round(value * 100)}%`).join(' · '), 'probabilities'));
      const label = element('label', 'Reviewer category: ');
      const select = element('select', '', 'correction');
      select.setAttribute('aria-label', `Reviewer category: ${result.log}`);
      select.append(new Option('Not reviewed', ''));
      for (const [key, name] of Object.entries(labels)) select.append(new Option(name, key));
      select.value = result.reviewerCategory || '';
      select.onchange = () => { result.reviewerCategory = select.value; };
      label.append(select);
      row.append(label);
    }
    $('results').append(row);
  }
  if (!visible.length) $('results').append(element('p', 'No results to display.'));
  $('export').disabled = !completed || busy;
}
function scheduleRender() {
  if (renderTimer) return;
  renderTimer = setTimeout(() => {
    renderTimer = undefined;
    render();
  }, 300);
}
$('sample').onclick = () => { $('logs').value = samples.join('\n'); };
$('source-mode').onchange = () => {
  if (sourceMode !== 'text') filePaths[sourceMode] = $('file-path').value;
  sourceMode = $('source-mode').value;
  if (sourceMode !== 'text') $('file-path').value = filePaths[sourceMode];
  $('paste-input').hidden = sourceMode !== 'text';
  $('sample').hidden = sourceMode !== 'text';
  $('file-input').hidden = sourceMode === 'text';
  $('file-notes').hidden = sourceMode === 'text';
  $('classify').textContent = sourceMode === 'follow' ? `Start realtime with ${engineLabel} ↗` : sourceMode === 'batch' ? `Run batch with ${engineLabel} ↗` : `Classify with ${engineLabel} ↗`;
};
$('stop').onclick = () => {
  $('stop').disabled = true;
  $('message').textContent = 'Stopping processing…';
  activeRequest?.abort();
};
$('classify').onclick = async () => {
  if (busy) return;
  busy = true;
  activeRequest = new AbortController();
  for (const id of ['classify', 'sample', 'export', 'source-mode', 'file-path']) $(id).disabled = true;
  $('stop').disabled = false;
  $('message').textContent = `${engineLabel} is classifying your logs…`;
  let started = false;
  try {
    const response = await fetch(sourceMode === 'text' ? '/api/classify' : '/api/file-source', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      signal: activeRequest.signal,
      body: JSON.stringify(sourceMode === 'text' ? { text: $('logs').value } : { mode: sourceMode, paths: $('file-path').value }),
    });
    if (!response.ok) throw new Error((await response.json()).error);
    await readEvents(response.body, event => {
      if (event.activeProcessingMs !== undefined) activeProcessingMs = event.activeProcessingMs;
      if (event.elapsedMs !== undefined) elapsedMs = event.elapsedMs;
      if (event.type === 'start') {
        started = true;
        resultEngine = event.engine;
        total = event.total;
        completed = 0;
        results = total === null ? [] : new Array(total);
        completionOrder = [];
        elapsedMs = 0;
        activeProcessingMs = 0;
        page = 0;
      } else if (event.type === 'result') {
        results[event.index] = event.result;
        completionOrder.push(event.index);
        completed++;
        elapsedMs = event.elapsedMs;
      } else if (event.type === 'done') {
        elapsedMs = event.elapsedMs;
      } else if (event.type === 'error') {
        throw new Error(event.error);
      }
      $('message').textContent = total === null ? `${sourceMode === 'follow' ? 'Realtime' : 'Batch'} · ${completed.toLocaleString('en-US')} events completed${completed ? '' : ' · Waiting for logs…'}` : `Classifying · ${completed.toLocaleString('en-US')} / ${total.toLocaleString('en-US')} logs · ${total.toLocaleString('en-US')} ${engineLabel} requests planned`;
      scheduleRender();
    });
    $('message').textContent = `Classification complete · ${results.filter(r => r.error).length} failed`;
  } catch (error) {
    $('message').textContent = `${error.name === 'AbortError' ? 'Processing stopped' : error.message} · ${started ? `${completed} completed results have been retained.` : 'Previous results have been retained.'}`;
  } finally {
    busy = false;
    activeRequest.abort();
    activeRequest = undefined;
    $('stop').disabled = true;
    clearTimeout(renderTimer);
    renderTimer = undefined;
    for (const id of ['classify', 'sample', 'source-mode', 'file-path']) $(id).disabled = false;
    if (started || completed) render();
    $('export').disabled = !completed;
  }
};
$('review-filter').onchange = () => { page = 0; if (completed) render(); };
$('previous').onclick = () => { page--; render(); };
$('next').onclick = () => { page++; render(); };
$('export').onclick = () => {
  const blob = new Blob([JSON.stringify({ mode: resultEngine, sourceMode, total, completed, elapsedMs, activeProcessingMs, results: results.filter(Boolean) }, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'deciflow-results.json';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
fetch('/api/status').then(async response => {
  const data = await response.json();
  if (!response.ok) throw new Error(data.error);
  return data;
}).then(data => {
  $('host-name').textContent = data.host.hostname;
  $('host-os').textContent = data.host.os;
  $('host-addresses').textContent = data.host.addresses.join('\n') || 'IP unavailable';
  engine = data.engine;
  engineLabel = engine === 'laya' ? 'Laya' : 'Jev';
  $('status').textContent = data.configured ? `● Ready to connect to ${engineLabel}` : '○ TypeSafe API key required';
  $('powered-by').textContent = `Powered by ${engineLabel}`;
  $('source-mode').onchange();
  $('classify').disabled = !data.configured;
  $('data-notice').textContent = engine === 'laya' ? 'Classification sends logs to your configured Laya server. Laya inference has no Jev API usage fees. Remove passwords, tokens, and sensitive data before sending logs to a remote server.' : 'Classification sends your logs to the TypeSafe API and may incur usage charges. Remove passwords, tokens, and sensitive data first.';
  const limits = data.limits;
  $('source-directory').textContent = `Absolute paths are supported. Relative paths start at: ${data.workingDirectory}`;
  $('input-limits').textContent = engine === 'laya' ? `One event per line · Laya ${data.model} · ${limits.context_tokens.toLocaleString('en-US')} tokens including the question. Truncated predictions are discarded and original events retained for review.` : `One event per line · ${data.model}: ${limits.context_tokens.toLocaleString('en-US')} tokens for state + question · Local preflight budget: ${limits.max_jev_input_bytes.toLocaleString('en-US')} bytes per Jev request (not a token count). Oversized events are retained for review.`;
}).catch(error => { $('status').textContent = error.message || 'Server connection failed'; });
