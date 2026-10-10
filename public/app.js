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
const expandedJson = new WeakSet();
async function copyText(text) {
  if (globalThis.navigator?.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const previousFocus = document.activeElement;
  const buffer = document.createElement('textarea');
  buffer.value = text;
  buffer.className = 'clipboard-buffer';
  buffer.setAttribute('readonly', '');
  document.body.append(buffer);
  try {
    buffer.select();
    if (!document.execCommand('copy')) throw new Error('Clipboard unavailable');
  } finally {
    buffer.remove();
    previousFocus?.focus();
  }
}
let results = [];
let completionOrder = [];
let elapsedMs = 0;
let activeProcessingMs = 0;
let busy = false;
let page = 0;
let total = 0;
let completed = 0;
let renderTimer;
let updatesPaused = false;
let pausedOrder = [];
let displayedOrder = [];
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
let resultSourceMode = sourceMode;
let engineLabel = 'Laya';
function element(tag, text, className = '') {
  const node = document.createElement(tag);
  node.textContent = text;
  node.className = className;
  return node;
}
const profileLabels = { general: 'General system', authentication: 'Authentication', http_access: 'HTTP access', application: 'Application', network: 'Network / tcpdump text' };
const sourcePreferences = new Map();
let sourceRows = [];
function profileSelect(value) {
  const select = element('select', '');
  for (const [key, label] of Object.entries(profileLabels)) select.append(new Option(label, key));
  select.value = value;
  return select;
}
for (const [key, label] of Object.entries(profileLabels)) $('paste-profile').append(new Option(label, key));
$('paste-profile').value = 'general';
$('paste-chunk-lines').value = '1';
function updateSourceSettings() {
  $('source-settings').replaceChildren();
  sourceRows = [];
  for (const path of $('file-path').value.split('\n').map(s => s.trim()).filter(Boolean)) {
    const preference = sourcePreferences.get(path) || { profile: 'general', chunkLines: 1 };
    const row = element('div', '', 'source-setting');
    const name = element('span', path, 'source-path');
    const profile = profileSelect(preference.profile);
    profile.setAttribute('aria-label', `Decision profile for ${path}`);
    const size = element('input', '');
    size.type = 'number'; size.min = '1'; size.step = '1'; size.value = String(preference.chunkLines);
    size.setAttribute('aria-label', `Lines per chunk for ${path}`);
    const label = element('label', 'Lines/chunk ');
    label.append(size);
    const criteriaLabel = element('label', 'Criteria ', 'criteria-label');
    criteriaLabel.append(profile);
    row.append(name, criteriaLabel, label);
    const save = () => sourcePreferences.set(path, { profile: profile.value, chunkLines: Number(size.value) });
    profile.onchange = save; size.oninput = save;
    sourceRows.push({ path, profile, size });
    $('source-settings').append(row);
  }
}
$('file-path').oninput = updateSourceSettings;
updateSourceSettings();
function renderCategoryChart() {
  const counts = Object.fromEntries(Object.keys(labels).map(key => [key, 0]));
  let failed = 0;
  let truncated = 0;
  const certainty = $('chart-certainty').value;
  for (const result of results) {
    if (!result) continue;
    if (result.providerResponse?.usage?.truncated === true) truncated++;
    if (result.error) failed++;
    else if (Object.hasOwn(counts, result.category)
      && (certainty === 'all' || (certainty === 'uncertain' ? result.uncertain : !result.uncertain))) counts[result.category]++;
  }
  const classified = Object.values(counts).reduce((sum, count) => sum + count, 0);
  const maximum = Math.max(1, ...Object.values(counts));
  $('category-chart').replaceChildren();
  for (const [key, label] of Object.entries(labels)) {
    const count = counts[key];
    const percent = classified ? count / classified * 100 : 0;
    const row = element('div', '', 'category-chart-row');
    row.setAttribute('role', 'listitem');
    const track = element('div', '', 'category-bar-track');
    track.setAttribute('aria-hidden', 'true');
    const bar = element('div', '', `category-bar ${key}`);
    bar.setAttribute('style', `width:${count / maximum * 100}%`);
    track.append(bar);
    row.append(element('span', label, 'category-label'), track,
      element('span', `${count.toLocaleString('en-US')} (${percent.toFixed(1)}%)`, 'category-count'));
    $('category-chart').append(row);
  }
  $('chart-truncated').textContent = `Truncated: ${truncated.toLocaleString('en-US')}`;
  $('chart-totals').textContent = `${classified.toLocaleString('en-US')} classified ${classified === 1 ? 'chunk' : 'chunks'} · ${failed.toLocaleString('en-US')} failed ${failed === 1 ? 'request' : 'requests'}`;
}
$('chart-certainty').onchange = renderCategoryChart;
renderCategoryChart();
function render(updateList = true) {
  renderCategoryChart();
  $('summary').replaceChildren();
  const processingMs = results.reduce((sum, result) => sum + result.elapsedMs, 0);
  const averageMs = completed ? processingMs / completed : 0;
  const processingPercent = elapsedMs > 0 ? `${(activeProcessingMs / elapsedMs * 100).toFixed(1)}%` : 'N/A';
  for (const [label, value] of [['Processed chunks', completed], ['Needs review', results.filter(r => r.review).length], ['Total elapsed time', `${elapsedMs}ms`], ['Active processing time', `${activeProcessingMs}ms (${processingPercent})`], ['Average processing time', `${averageMs.toFixed(1)}ms`]]) {
    const metric = element('div', label, 'metric');
    if (label === 'Needs review') metric.title = 'Selected category probability below 70%, top-two probability gap below 10 percentage points, Other category, or failed request; not an error count.';
    if (label === 'Average processing time') metric.title = 'Mean request duration, including network/server wait and failed requests; excludes waiting for new file lines.';
    if (label === 'Active processing time') metric.title = 'Time with at least one request in flight, counting overlapping requests once. Includes network/server wait, excludes idle time; not CPU utilization.';
    metric.append(element('strong', String(value)));
    $('summary').append(metric);
  }
  const pendingCount = updatesPaused ? completionOrder.length - pausedOrder.length : 0;
  $('pause-updates').textContent = updatesPaused ? `Resume updates${pendingCount ? ` (${pendingCount} new)` : ''}` : 'Pause updates';
  $('pause-updates').setAttribute('aria-pressed', String(updatesPaused));
  $('pause-updates').disabled = !busy && !completed && !updatesPaused;
  $('export').disabled = !completed || busy;
  if (updatesPaused && !updateList) return;
  if (!updatesPaused) displayedOrder = completionOrder.slice();
  $('results').replaceChildren();
  const visible = (updatesPaused ? pausedOrder : completionOrder).toReversed().map(index => results[index]).filter(r => {
    const review = $('review-filter').value;
    const category = $('category-filter').value;
    const search = $('log-search').value.toLowerCase();
    return (review === 'all' || (review === 'needs-review' ? r.review : !r.review))
      && (category === 'all' || (category === 'failed' ? Boolean(r.error) : !r.error && r.category === category))
      && r.log.toLowerCase().includes(search);
  });
  const pages = Math.max(1, Math.ceil(visible.length / 100));
  page = Math.min(page, pages - 1);
  $('page-info').textContent = `Page ${page + 1} of ${pages} · ${visible.length} results`;
  $('previous').disabled = page === 0;
  $('next').disabled = page >= pages - 1;
  for (const result of visible.slice(page * 100, (page + 1) * 100)) {
    const row = element('article', '', 'result');
    const top = element('div', '', 'result-top');
    top.append(element('span', result.error ? 'Request failed' : `${result.uncertain ? 'Uncertain · ' : ''}${labels[result.category]}`, `badge ${result.uncertain ? 'uncertain' : result.category || 'error'}`));
    top.append(element('span', result.error ? `${result.elapsedMs}ms` : `${((result.answerProbability ?? result.probabilities?.[result.category] ?? 0) * 100).toFixed(1)}% category probability · ${result.elapsedMs}ms`));
    if (result.uncertain) top.title = `Provisional model choice. ${result.candidates?.map(key => `${labels[key]} ${(result.probabilities[key] * 100).toFixed(1)}%`).join(' vs ') || 'Low confidence'}. Not a confirmed incident.`;
    if (result.review) top.append(element('span', 'Needs review', 'review'));
    row.append(top, element('p', result.log, 'log'));
    if (result.uncertain) row.append(element('p', `Provisional: ${result.candidates?.map(key => `${labels[key]} ${(result.probabilities[key] * 100).toFixed(1)}%`).join(' vs ') || 'Low confidence'} · ${result.reviewReasons?.map(reason => ({ low_answer_probability: 'category probability below 70%', low_confidence: 'legacy provider confidence below 70%', close_probabilities: 'close category probabilities', collapsed_options: 'option descriptions lost distinction during token rendering', other_category: 'insufficient context / Other' })[reason]).join('; ') || 'review needed'}`, 'uncertainty-note'));
    if (result.source) {
      const end = result.lineEnd || result.line;
      const multiple = end !== result.line;
      const realtime = resultSourceMode === 'follow';
      const location = element('p', `${result.source} · ${realtime ? 'Observed' : 'File'} ${multiple ? 'lines' : 'line'} ${multiple ? `${result.line}–${end}` : result.line}${result.incomplete ? ' · Incomplete line at rotation' : ''}`, 'caption');
      if (realtime) location.title = 'Sequence since monitoring started or the file rotated; not an absolute file line number.';
      row.append(location);
    }
    if (result.profile) {
      const count = result.lineCount || 1;
      row.append(element('p', `${profileLabels[result.profile]} · ${count} ${count === 1 ? 'line' : 'lines'} (max ${result.chunkLines || 1})`, 'caption'));
    }
    const jsonView = element('details', '', 'result-json');
    const jsonText = element('pre', '', 'json-content');
    const jsonActions = element('div', '', 'json-actions');
    const copyButton = element('button', 'Copy', 'json-copy');
    copyButton.type = 'button';
    copyButton.setAttribute('aria-label', 'Copy this result JSON to clipboard');
    const copyStatus = element('span', '', 'caption');
    copyStatus.setAttribute('role', 'status');
    copyButton.onclick = async () => {
      copyButton.disabled = true;
      try {
        await copyText(JSON.stringify(result, null, 2));
        copyStatus.textContent = 'Copied';
      } catch {
        copyStatus.textContent = 'Copy failed. Select and copy the JSON below.';
      } finally {
        copyButton.disabled = false;
      }
    };
    jsonActions.append(copyButton, copyStatus);
    const jsonPanel = element('div', '', 'json-panel');
    jsonPanel.append(jsonActions, jsonText);
    jsonView.append(element('summary', 'View JSON'), jsonPanel);
    jsonView.open = expandedJson.has(result);
    if (jsonView.open) jsonText.textContent = JSON.stringify(result, null, 2);
    jsonView.ontoggle = () => {
      if (jsonView.open) {
        expandedJson.add(result);
        jsonText.textContent = JSON.stringify(result, null, 2);
      } else expandedJson.delete(result);
    };
    if (result.error) row.append(element('p', result.error, 'error-message'));
    else {
      row.append(element('div', Object.entries(result.probabilities).map(([key, value]) => `${labels[key]} ${Math.round(value * 100)}%`).join(' · '), 'probabilities'));
      const label = element('label', 'Reviewer category: ');
      const select = element('select', '', 'correction');
      select.setAttribute('aria-label', `Reviewer category: ${result.log}`);
      select.append(new Option('Not reviewed', ''));
      for (const [key, name] of Object.entries(labels)) select.append(new Option(name, key));
      select.value = result.reviewerCategory || '';
      select.onchange = () => {
        result.reviewerCategory = select.value;
        if (jsonView.open) jsonText.textContent = JSON.stringify(result, null, 2);
      };
      label.append(select);
      row.append(label);
    }
    row.append(jsonView);
    $('results').append(row);
  }
  if (!visible.length) $('results').append(element('p', 'No results to display.'));
  $('export').disabled = !completed || busy;
}
function scheduleRender() {
  if (renderTimer) return;
  renderTimer = setTimeout(() => {
    renderTimer = undefined;
    render(false);
  }, 300);
}
$('pause-updates').onclick = () => {
  updatesPaused = !updatesPaused;
  if (updatesPaused) pausedOrder = displayedOrder;
  clearTimeout(renderTimer);
  renderTimer = undefined;
  if (updatesPaused) render(false);
  else { pausedOrder = []; render(); }
};
$('sample').onclick = () => { $('logs').value = samples.join('\n'); };
$('source-mode').onchange = () => {
  if (sourceMode !== 'text') filePaths[sourceMode] = $('file-path').value;
  sourceMode = $('source-mode').value;
  if (sourceMode !== 'text') $('file-path').value = filePaths[sourceMode];
  updateSourceSettings();
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
  const sources = sourceRows.map(({ path, profile, size }) => ({ path, profile: profile.value, chunkLines: Number(size.value) }));
  const chunkLines = Number($('paste-chunk-lines').value);
  if ((sourceMode === 'text' ? [chunkLines] : sources.map(s => s.chunkLines)).some(n => !Number.isInteger(n) || n < 1)) {
    $('message').textContent = 'Lines per chunk must be a positive integer.'; return;
  }
  busy = true;
  for (const { profile, size } of sourceRows) { profile.disabled = true; size.disabled = true; }
  activeRequest = new AbortController();
  for (const id of ['classify', 'sample', 'export', 'source-mode', 'file-path', 'paste-profile', 'paste-chunk-lines']) $(id).disabled = true;
  $('stop').disabled = false;
  $('message').textContent = `${engineLabel} is classifying your logs…`;
  let started = false;
  try {
    const response = await fetch(sourceMode === 'text' ? '/api/classify' : '/api/file-source', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      signal: activeRequest.signal,
      body: JSON.stringify(sourceMode === 'text' ? { text: $('logs').value, profile: $('paste-profile').value, chunkLines } : { mode: sourceMode, sources }),
    });
    if (!response.ok) throw new Error((await response.json()).error);
    await readEvents(response.body, event => {
      if (event.activeProcessingMs !== undefined) activeProcessingMs = event.activeProcessingMs;
      if (event.elapsedMs !== undefined) elapsedMs = event.elapsedMs;
      if (event.type === 'start') {
        started = true;
        resultEngine = event.engine;
        resultSourceMode = event.mode || sourceMode;
        total = event.total;
        completed = 0;
        results = total === null ? [] : new Array(total);
        completionOrder = [];
        updatesPaused = false;
        pausedOrder = [];
        displayedOrder = [];
        elapsedMs = 0;
        activeProcessingMs = 0;
        page = 0;
        render(false);
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
      $('message').textContent = total === null ? `${sourceMode === 'follow' ? 'Realtime' : 'Batch'} · ${completed.toLocaleString('en-US')} events completed${completed ? '' : ' · Waiting for logs…'}` : `Classifying · ${completed.toLocaleString('en-US')} / ${total.toLocaleString('en-US')} chunks · ${total.toLocaleString('en-US')} ${engineLabel} requests planned`;
      scheduleRender();
    });
    $('message').textContent = `Classification complete · ${results.filter(r => r.error).length} failed`;
  } catch (error) {
    $('message').textContent = `${error.name === 'AbortError' ? 'Processing stopped' : error.message} · ${started ? `${completed} completed results have been retained.` : 'Previous results have been retained.'}`;
  } finally {
    busy = false;
    for (const { profile, size } of sourceRows) { profile.disabled = false; size.disabled = false; }
    activeRequest.abort();
    activeRequest = undefined;
    $('stop').disabled = true;
    clearTimeout(renderTimer);
    renderTimer = undefined;
    for (const id of ['classify', 'sample', 'source-mode', 'file-path', 'paste-profile', 'paste-chunk-lines']) $(id).disabled = false;
    if (started || completed) render(false);
    $('export').disabled = !completed;
  }
};
function handleResultFilter() {
  page = 0;
  if (completed) render();
}
$('review-filter').onchange = handleResultFilter;
$('category-filter').onchange = handleResultFilter;
$('log-search').oninput = handleResultFilter;
$('previous').onclick = () => { page--; render(); };
$('next').onclick = () => { page++; render(); };
$('export').onclick = () => {
  const blob = new Blob([JSON.stringify({ mode: resultEngine, sourceMode: resultSourceMode, total, completed, elapsedMs, activeProcessingMs, results: results.filter(Boolean) }, null, 2)], { type: 'application/json' });
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
  if (data.profiles) {
    for (const key of Object.keys(profileLabels)) delete profileLabels[key];
    Object.assign(profileLabels, data.profiles);
    const selected = $('paste-profile').value;
    $('paste-profile').replaceChildren();
    for (const [key, label] of Object.entries(profileLabels)) $('paste-profile').append(new Option(label, key));
    $('paste-profile').value = profileLabels[selected] ? selected : 'general';
  }
  engine = data.engine;
  engineLabel = engine === 'laya' ? 'Laya' : 'Jev';
  $('status').textContent = data.configured ? `● Ready to connect to ${engineLabel}` : '○ TypeSafe API key required';
  $('powered-by').textContent = `Powered by ${engineLabel}`;
  $('source-mode').onchange();
  $('classify').disabled = !data.configured;
  $('data-notice').textContent = engine === 'laya' ? 'Classification sends logs to your configured Laya server. Laya inference has no Jev API usage fees. Remove passwords, tokens, and sensitive data before sending logs to a remote server.' : 'Classification sends your logs to the TypeSafe API and may incur usage charges. Remove passwords, tokens, and sensitive data first.';
  const limits = data.limits;
  $('source-directory').textContent = `Absolute paths are supported. Relative paths start at: ${data.workingDirectory}`;
  $('input-limits').textContent = engine === 'laya' ? `One decision per chunk · Laya ${data.model} · ${limits.context_tokens.toLocaleString('en-US')} tokens including the question. Truncated predictions are discarded and original events retained for review.` : `One decision per chunk · ${data.model}: ${limits.context_tokens.toLocaleString('en-US')} tokens for state + question · Local preflight budget: ${limits.max_jev_input_bytes.toLocaleString('en-US')} bytes per Jev request (not a token count). Oversized events are retained for review.`;
}).catch(error => { $('status').textContent = error.message || 'Server connection failed'; });
