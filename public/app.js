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
function orderedResult(result) {
  const metadata = ['requestedAt', 'decidedAt', 'schemaVersion', 'eventId', 'engine', 'requestedModel', 'source', 'sourcePatterns', 'line', 'lineEnd', 'lineCount', 'eventCount', 'profile', 'chunkEvents', 'incomplete', 'elapsedMs', 'requestBytes', 'inputBudget', 'httpStatus', 'responseHeaders', 'action', 'actionExecution'];
  return Object.fromEntries([
    ...metadata.filter(key => Object.hasOwn(result, key)).map(key => [key, result[key]]),
    ...Object.entries(result).filter(([key]) => !metadata.includes(key)),
  ]);
}
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
let recentCompletions = [];
let busy = false;
let page = 0;
let total = 0;
let completed = 0;
let renderTimer;
let updatesPaused = false;
let pausedOrder = [];
let displayedOrder = [];
let activeRequest;
let activeJobId;
let activeJobState;
let restoringJob = false;
const jobStorage = globalThis.sessionStorage || localStorage;
function rememberJob(id) {
  try { jobStorage.setItem('deciflow-job-id', id); } catch { /* Current-page processing still works. */ }
}
let sourceMode = 'batch';
const filePaths = {
  batch: '/host-logs/sample-logs/access-1k.log\n/host-logs/var/log/messages\n/host-logs/var/log/nginx/access*.log',
  realtime: '/host-logs/var/log/secure\n/host-logs/var/log/messages\n/host-logs/var/log/nginx/access*.log',
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
function handleNavigation(view) {
  $('main-page').hidden = view !== 'main';
  $('actions-page').hidden = view !== 'actions';
  $('nav-main').setAttribute('aria-current', view === 'main' ? 'page' : 'false');
  $('nav-actions').setAttribute('aria-current', view === 'actions' ? 'page' : 'false');
}
$('nav-main').onclick = () => handleNavigation('main');
$('nav-actions').onclick = () => handleNavigation('actions');
const defaultActionCode = `import json
import sys

result = json.load(sys.stdin)

# Use result["category"], result["log"], and result["source"] here.
# Replace this handler with your notification, storage, or other integration.
`;
const profileLabels = { general: 'General system', authentication: 'Authentication', http_access: 'HTTP access', application: 'Application', network: 'Network / tcpdump text' };
let registeredActions = [];
let actionRows = [];
let preparingActions = false;
const sourcePreferences = new Map();
try {
  for (const [path, preference] of JSON.parse(localStorage.getItem('deciflow-source-preferences') || '[]')) sourcePreferences.set(path, { profile: preference.profile, chunkEvents: preference.chunkEvents });
} catch { /* Keep the UI usable when browser storage is unavailable or invalid. */ }
let editingAction = null;
function renderActions() {
  $('action-registry').replaceChildren();
  const query = $('action-search').value.trim().toLowerCase();
  let matches = 0;
  const table = element('table', '', 'action-list');
  const header = element('tr', '');
  for (const title of ['Name', 'Python', 'Modules', 'Manage']) header.append(element('th', title));
  table.append(header);
  registeredActions.forEach((action, index) => {
    if (!action.name.toLowerCase().includes(query)) return;
    matches++;
    const row = element('tr', '');
    const modules = Array.isArray(action.modules) ? action.modules.join(', ') : action.modules;
    for (const value of [action.name, action.pythonVersion || 'External', modules || 'Standard library']) row.append(element('td', value));
    const controls = element('td', '', 'action-list-controls');
    for (const [caption, handler] of [
      ['Edit', () => handleEditAction(index)],
      ['Delete', () => { registeredActions.splice(index, 1); renderActions(); $('action-message').textContent = 'Deletion pending. Save changes to apply.'; }],
    ]) {
      const button = element('button', caption, 'quiet');
      button.type = 'button'; button.disabled = preparingActions || editingAction !== null;
      button.onclick = handler; controls.append(button);
    }
    row.append(controls); table.append(row);
  });
  $('action-registry').append(matches ? table : element('p', registeredActions.length ? 'No Actions match your search.' : 'No Actions registered. Click Add action to create one.', 'caption'));
  $('add-action').disabled = preparingActions || editingAction !== null;
}
$('action-search').oninput = renderActions;
function handleEditAction(index) {
  editingAction = index;
  const action = registeredActions[index] || { pythonVersion: '3.12', code: defaultActionCode };
  const row = element('div', '', 'action-registration');
  const fields = { id: { value: action.id || '' } };
  for (const [key, caption] of [['name', 'Name'], ['pythonVersion', 'Python version (e.g. 3.12)'], ['modules', 'Modules (one per line; versions optional)'], ['code', 'Python code']]) {
    const label = element('label', caption);
    const input = element(['modules', 'code'].includes(key) ? 'textarea' : 'input', '');
    input.value = key === 'modules' && Array.isArray(action.modules) ? action.modules.join('\n') : action[key] || (key === 'pythonVersion' ? '3.12' : '');
    if (key === 'modules') input.rows = 3;
    if (key === 'code') { input.rows = 14; input.spellcheck = false; input.className = 'action-code'; label.className = 'action-code-label'; }
    input.setAttribute('aria-label', caption);
    label.append(input); row.append(label); fields[key] = input;
  }
  actionRows = [fields];
  $('action-editor').replaceChildren(); $('action-editor').append(row);
  $('action-editor').hidden = false;
  $('cancel-action').hidden = false;
  renderActions();
  $('action-editor').scrollIntoView?.({ block: 'nearest' });
}
function handleCloseAction() {
  editingAction = null; actionRows = [];
  $('action-editor').replaceChildren(); $('action-editor').hidden = true;
  $('cancel-action').hidden = true;
  renderActions();
}
$('cancel-action').onclick = handleCloseAction;
$('add-action').onclick = () => handleEditAction(registeredActions.length);
$('save-actions').onclick = async () => {
  preparingActions = true;
  $('save-actions').disabled = true;
  $('add-action').disabled = true; $('cancel-action').disabled = true;
  renderActions();
  $('action-message').textContent = 'Preparing Python environments and installing modules…';
  for (const fields of actionRows) for (const input of Object.values(fields)) input.disabled = true;
  try {
    const values = registeredActions.slice();
    if (editingAction !== null) values[editingAction] = { ...registeredActions[editingAction], ...Object.fromEntries(Object.entries(actionRows[0]).map(([key, input]) => [key, input.value])) };
    const response = await fetch('/api/actions', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(values) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    registeredActions = data.actions;
    handleCloseAction(); updateSourceSettings();
    $('action-message').textContent = 'Actions saved and environments ready. Changes apply to the next run.';
  } catch (error) { $('action-message').textContent = error.message; }
  finally {
    preparingActions = false;
    $('save-actions').disabled = false; $('add-action').disabled = false;
    for (const fields of actionRows) for (const input of Object.values(fields)) input.disabled = false;
    $('cancel-action').disabled = false; renderActions();
  }
};
fetch('/api/actions', { method: 'POST' }).then(async response => {
  const data = await response.json();
  if (!response.ok) throw new Error(data.error);
  registeredActions = data.actions; renderActions(); updateSourceSettings();
}).catch(error => { $('action-message').textContent = error.message; });
let sourceRows = [];
let runSourcePatterns = [];
function profileSelect(value) {
  const select = element('select', '');
  for (const [key, label] of Object.entries(profileLabels)) select.append(new Option(label, key));
  select.value = value;
  return select;
}
for (const [key, label] of Object.entries(profileLabels)) $('paste-profile').append(new Option(label, key));
$('paste-profile').value = 'general';
$('paste-chunk-events').value = '1';
function updateSourceSettings(paths = $('file-path').value.split('\n').map(s => s.trim()).filter(Boolean)) {
  $('source-settings').replaceChildren();
  sourceRows = [];
  for (const path of paths) {
    const preference = sourcePreferences.get(path) || { profile: 'general', chunkEvents: 1 };
    const row = element('div', '', 'source-setting');
    const name = element('input', '', 'source-path-input');
    name.type = 'text'; name.value = path; name.disabled = busy;
    name.placeholder = 'File path or pattern';
    name.setAttribute('aria-label', 'File path or pattern');
    const pathLabel = element('label', 'Path ', 'source-path');
    pathLabel.append(name);
    const profile = profileSelect(preference.profile);
    profile.disabled = busy;
    profile.setAttribute('aria-label', `Decision profile for ${path}`);
    const size = element('input', '');
    size.disabled = busy;
    size.type = 'number'; size.min = '1'; size.step = '1'; size.value = String(preference.chunkEvents);
    size.setAttribute('aria-label', `Events per chunk for ${path}`);
    const label = element('label', 'Events/chunk ');
    label.append(size);
    const criteriaLabel = element('label', 'Criteria ', 'criteria-label');
    criteriaLabel.append(profile);
    const action = element('select', '');
    action.append(new Option('None', ''));
    for (const item of registeredActions.filter(item => item.name)) action.append(new Option(item.name, item.name));
    action.value = preference.action || '';
    if (action.selectedIndex < 0) action.value = '';
    action.disabled = busy;
    action.setAttribute('aria-label', `Action for ${path}`);
    const actionLabel = element('label', 'Action ');
    actionLabel.append(action);
    const remove = element('button', 'Remove', 'quiet source-remove');
    remove.type = 'button'; remove.disabled = busy;
    row.append(pathLabel, criteriaLabel, label, actionLabel, remove);
    const save = () => {
      sourcePreferences.set(name.value.trim(), { profile: profile.value, chunkEvents: Number(size.value), action: action.value });
      try { localStorage.setItem('deciflow-source-preferences', JSON.stringify([...sourcePreferences].map(([path, { profile, chunkEvents }]) => [path, { profile, chunkEvents }]))); } catch { /* Preferences remain available for this page session. */ }
    };
    profile.onchange = save; size.oninput = save; action.onchange = save;
    const source = { path, name, profile, size, action, remove };
    name.oninput = () => {
      source.path = name.value.trim();
      save();
      $('file-path').value = sourceRows.map(item => item.path).join('\n');
    };
    remove.onclick = () => {
      if (busy) return;
      const remaining = sourceRows.filter(item => item !== source).map(item => item.path);
      $('file-path').value = remaining.join('\n');
      updateSourceSettings(remaining);
    };
    sourceRows.push(source);
    $('source-settings').append(row);
  }
}
$('file-path').oninput = () => updateSourceSettings();
$('add-source').onclick = () => {
  if (busy) return;
  updateSourceSettings([...sourceRows.map(item => item.path), '']);
  sourceRows.at(-1).name.focus?.();
};
updateSourceSettings();
let chartCertainty = 'all';
function renderCategoryChart() {
  const counts = Object.fromEntries(Object.keys(labels).map(key => [key, 0]));
  let failed = 0;
  let truncated = 0;
  const groups = { all: 0, uncertain: 0, certain: 0 };
  const certainty = chartCertainty;
  for (const result of results) {
    if (!result) continue;
    if (result.providerResponse?.usage?.truncated === true) truncated++;
    if (result.error) failed++;
    else if (Object.hasOwn(counts, result.category)) {
      const group = result.uncertain ? 'uncertain' : 'certain';
      groups.all++;
      groups[group]++;
      if (certainty === 'all' || certainty === group) counts[result.category]++;
    }
  }
  for (const [key, label] of Object.entries({ all: 'All', certain: 'Certain', uncertain: 'Uncertain' })) {
    const count = groups[key];
    const percent = groups.all ? count / groups.all * 100 : 0;
    const caption = `${label} · ${count.toLocaleString('en-US')}`;
    const button = $(`chart-${key}`);
    button.textContent = key === 'all' ? caption : `${caption} (${percent.toFixed(1)}%)`;
    button.setAttribute('aria-pressed', String(certainty === key));
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
for (const key of ['all', 'certain', 'uncertain']) {
  $(`chart-${key}`).onclick = () => {
    chartCertainty = key;
    renderCategoryChart();
  };
}
renderCategoryChart();
function renderSourceFilter() {
  const select = $('source-filter');
  const selected = select.value || 'all';
  const counts = new Map(runSourcePatterns.map(path => [path, 0]));
  for (const result of results) {
    if (!result) continue;
    for (const path of new Set(result.sourcePatterns || (result.source ? [result.source] : []))) {
      counts.set(path, (counts.get(path) || 0) + 1);
    }
  }
  select.replaceChildren();
  select.append(new Option(`All sources (${completed})`, 'all'));
  for (const [path, count] of counts) select.append(new Option(`${path} (${count})`, path));
  select.value = counts.has(selected) ? selected : 'all';
  select.disabled = !counts.size;
}
function render(updateList = true) {
  renderSourceFilter();
  renderCategoryChart();
  $('summary').replaceChildren();
  const processingMs = results.reduce((sum, result) => sum + result.elapsedMs, 0);
  const averageMs = completed ? processingMs / completed : 0;
  recentCompletions = recentCompletions.filter(time => time > elapsedMs - 5000);
  const throughput = elapsedMs > 0 ? recentCompletions.length * 1000 / Math.min(elapsedMs, 5000) : 0;
  const processingPercent = elapsedMs > 0 ? `${(activeProcessingMs / elapsedMs * 100).toFixed(1)}%` : 'N/A';
  for (const [label, value] of [['Processed chunks', completed], ['Needs review', results.filter(r => r.review).length], ['Throughput', `${throughput.toFixed(1)} chunks/s`], ['Total elapsed time', `${elapsedMs}ms`], ['Active processing time', `${activeProcessingMs}ms (${processingPercent})`], ['Average processing time', `${averageMs.toFixed(1)}ms`]]) {
    const metric = element('div', label, 'metric');
    if (label === 'Throughput') metric.title = 'Successfully classified chunks per second over the last 5 seconds, including idle time. Uses elapsed time until 5 seconds; freezes when stopped or completed.';
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
    const source = $('source-filter').value || 'all';
    return (review === 'all' || (review === 'needs-review' ? r.review : !r.review))
      && (category === 'all' || (category === 'failed' ? Boolean(r.error) : !r.error && r.category === category))
      && r.log.toLowerCase().includes(search)
      && (source === 'all' || r.sourcePatterns?.includes(source) || r.source === source);
  });
  const pages = Math.max(1, Math.ceil(visible.length / 100));
  page = Math.min(page, pages - 1);
  $('page-info').textContent = `Page ${page + 1} of ${pages} · ${visible.length} results`;
  $('previous').disabled = page === 0;
  $('next').disabled = page >= pages - 1;
  for (const result of visible.slice(page * 100, (page + 1) * 100)) {
    const row = element('article', '', 'result');
    const top = element('div', '', 'result-top');
    top.append(element('span', result.error ? 'Request failed' : `${result.uncertain ? 'Uncertain · ' : ''}${labels[result.category]}`, `badge ${result.error ? 'error' : result.category || 'other'}${result.uncertain ? ' uncertain' : ''}`));
    top.append(element('span', result.error ? `${result.elapsedMs}ms` : `${((result.answerProbability ?? result.probabilities?.[result.category] ?? 0) * 100).toFixed(1)}% category probability · ${result.elapsedMs}ms`));
    if (result.uncertain) top.title = `Provisional model choice. ${result.candidates?.map(key => `${labels[key]} ${(result.probabilities[key] * 100).toFixed(1)}%`).join(' vs ') || 'Low confidence'}. Not a confirmed incident.`;
    if (result.review) top.append(element('span', 'Needs review', 'review'));
    row.append(top, element('p', result.log, 'log'));
    if (result.actionExecution) {
      const execution = result.actionExecution;
      row.append(element('p', `Action: ${execution.name} · ${execution.status} · ${execution.elapsedMs}ms${execution.exitCode != null ? ` · exit ${execution.exitCode}` : ''}${execution.error ? ` · ${execution.error}` : ''}`, execution.status === 'failed' ? 'error-message' : 'caption'));
    }
    if (result.uncertain) row.append(element('p', `Provisional: ${result.candidates?.map(key => `${labels[key]} ${(result.probabilities[key] * 100).toFixed(1)}%`).join(' vs ') || 'Low confidence'} · ${result.reviewReasons?.map(reason => ({ low_answer_probability: 'category probability below 70%', low_confidence: 'legacy provider confidence below 70%', close_probabilities: 'close category probabilities', collapsed_options: 'option descriptions lost distinction during token rendering', other_category: 'insufficient context / Other' })[reason]).join('; ') || 'review needed'}`, 'uncertainty-note'));
    if (result.source) {
      const end = result.lineEnd || result.line;
      const multiple = end !== result.line;
      const realtime = resultSourceMode === 'realtime';
      const location = element('p', `${result.source} · ${realtime ? 'Observed' : 'File'} ${multiple ? 'lines' : 'line'} ${multiple ? `${result.line}–${end}` : result.line}${result.incomplete ? ' · Incomplete line at rotation' : ''}`, 'caption');
      if (realtime) location.title = 'Sequence since monitoring started or the file rotated; not an absolute file line number.';
      row.append(location);
    }
    if (result.profile) {
      const count = result.eventCount || 1;
      row.append(element('p', `${profileLabels[result.profile]} · ${count} ${count === 1 ? 'event' : 'events'} (max ${result.chunkEvents || 1})`, 'caption'));
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
        await copyText(JSON.stringify(orderedResult(result), null, 2));
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
    if (jsonView.open) jsonText.textContent = JSON.stringify(orderedResult(result), null, 2);
    jsonView.ontoggle = () => {
      if (jsonView.open) {
        expandedJson.add(result);
        jsonText.textContent = JSON.stringify(orderedResult(result), null, 2);
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
        if (jsonView.open) jsonText.textContent = JSON.stringify(orderedResult(result), null, 2);
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
  if (sourceMode !== 'paste') filePaths[sourceMode] = $('file-path').value;
  sourceMode = $('source-mode').value;
  if (sourceMode !== 'paste') $('file-path').value = filePaths[sourceMode];
  updateSourceSettings();
  $('paste-input').hidden = sourceMode !== 'paste';
  $('sample').hidden = sourceMode !== 'paste';
  $('file-input').hidden = sourceMode === 'paste';
  $('file-notes').hidden = sourceMode === 'paste';
  $('classify').textContent = 'Run';
};
$('stop').onclick = async () => {
  $('stop').disabled = true;
  $('message').textContent = 'Stopping processing…';
  if (!activeJobId) { activeRequest?.abort(); return; }
  const connected = busy;
  try {
    const response = await fetch(`/api/jobs/${activeJobId}/stop`, { method: 'POST' });
    if (!response.ok) throw new Error((await response.json()).error);
    activeJobState = 'stopped';
    if (!connected) await handleRestoreJob();
  } catch (error) {
    $('message').className = 'error-message'; $('message').textContent = error.message;
    $('stop').disabled = false;
  }
};
async function handleRestoreJob() {
  if (busy || restoringJob) return;
  restoringJob = true;
  try {
    let id;
    try { id = activeJobId || jobStorage.getItem('deciflow-job-id'); } catch { return; }
    if (!id) return;
    const response = await fetch(`/api/jobs/${id}`, { method: 'POST' });
    if (response.status === 404) {
      activeJobId = undefined; activeJobState = undefined;
      $('classify').textContent = 'Run'; $('stop').disabled = true;
      try { jobStorage.removeItem('deciflow-job-id'); } catch { /* Storage may be disabled. */ }
      $('message').textContent = 'Previous job is unavailable. The server may have restarted.';
      return;
    }
    if (!response.ok) throw new Error((await response.json()).error);
    const job = await response.json();
    const settings = job.settings;
    $('source-mode').value = settings.mode;
    if (settings.mode === 'paste') {
      $('logs').value = settings.text;
      $('paste-profile').value = settings.profile;
      $('paste-chunk-events').value = String(settings.chunkEvents);
    } else {
      filePaths[settings.mode] = settings.sources.map(source => source.path).join('\n');
      for (const source of settings.sources) sourcePreferences.set(source.path, { profile: source.profile, chunkEvents: source.chunkEvents, action: job.state === 'running' ? source.action || '' : '' });
    }
    sourceMode = 'paste';
    $('source-mode').onchange();
    await handleProcessing(job);
  } finally { restoringJob = false; }
}
$('classify').onclick = () => restoringJob ? undefined : activeJobId && activeJobState === 'running' ? handleRestoreJob().catch(error => { $('message').textContent = error.message; }) : handleProcessing();
async function handleProcessing(job = null) {
  if (busy) return;
  const sources = sourceRows.map(({ path, profile, size, action }) => ({ path, profile: profile.value, chunkEvents: Number(size.value), action: action.value }));
  if (sourceMode !== 'paste' && (!sources.length || sources.some(source => !source.path))) {
    $('message').className = 'error-message';
    $('message').textContent = 'Enter a file path or pattern for each source.'; return;
  }
  const chunkEvents = Number($('paste-chunk-events').value);
  if ((sourceMode === 'paste' ? [chunkEvents] : sources.map(s => s.chunkEvents)).some(n => !Number.isInteger(n) || n < 1)) {
    $('message').className = 'error-message';
    $('message').textContent = 'Events per chunk must be a positive integer.'; return;
  }
  busy = true;
  for (const { name, profile, size, action, remove } of sourceRows) { name.disabled = true; profile.disabled = true; size.disabled = true; action.disabled = true; remove.disabled = true; }
  $('add-source').disabled = true;
  activeRequest = new AbortController();
  for (const id of ['classify', 'sample', 'export', 'source-mode', 'file-path', 'paste-profile', 'paste-chunk-events']) $(id).disabled = true;
  $('stop').disabled = false;
  $('message').className = '';
  $('message').textContent = `${engineLabel} is classifying your logs…`;
  let started = false;
  try {
    let response;
    if (job) { activeJobId = job.jobId; activeJobState = job.state; }
    else {
      response = await fetch(sourceMode === 'paste' ? '/api/classify' : '/api/file-source', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        signal: activeRequest.signal,
        body: JSON.stringify(sourceMode === 'paste' ? { text: $('logs').value, profile: $('paste-profile').value, chunkEvents, persist: true } : { mode: sourceMode, sources, persist: true }),
      });
      if (!response.ok) throw new Error((await response.json()).error);
      if (response.status === 202) {
        job = await response.json(); activeJobId = job.jobId; activeJobState = job.state; rememberJob(activeJobId);
      }
    }
    if (job) {
      response = await fetch(`/api/jobs/${activeJobId}/events`, { method: 'POST', signal: activeRequest.signal });
      if (!response.ok) throw new Error((await response.json()).error);
    }
    await readEvents(response.body, event => {
      if (event.activeProcessingMs !== undefined) activeProcessingMs = event.activeProcessingMs;
      if (event.elapsedMs !== undefined) elapsedMs = event.elapsedMs;
      if (event.type === 'start') {
        started = true;
        resultEngine = event.engine;
        resultSourceMode = event.mode || sourceMode;
        runSourcePatterns = sourceMode === 'paste' ? [] : [...new Set(event.sourcePatterns || sources.map(source => source.path))];
        $('source-filter').value = 'all';
        total = event.total;
        completed = 0;
        results = total === null ? [] : new Array(total);
        completionOrder = [];
        updatesPaused = false;
        pausedOrder = [];
        displayedOrder = [];
        elapsedMs = 0;
        activeProcessingMs = 0;
        recentCompletions = [];
        page = 0;
        render(false);
      } else if (event.type === 'result') {
        results[event.index] = event.result;
        completionOrder.push(event.index);
        completed++;
        if (!event.result.error) recentCompletions.push(event.elapsedMs);
        elapsedMs = event.elapsedMs;
      } else if (event.type === 'done') {
        elapsedMs = event.elapsedMs;
        activeJobState = event.state || 'completed';
      } else if (event.type === 'error') {
        activeJobState = 'failed';
        throw new Error(event.error);
      }
      $('message').textContent = total === null ? `${sourceMode === 'realtime' ? 'Realtime' : 'Batch'} · ${completed.toLocaleString('en-US')} chunks completed${completed ? '' : ' · Waiting for logs…'}` : `Classifying · ${completed.toLocaleString('en-US')} / ${total.toLocaleString('en-US')} chunks · ${total.toLocaleString('en-US')} ${engineLabel} requests planned`;
      scheduleRender();
    });
    $('message').textContent = `${activeJobState === 'stopped' ? 'Processing stopped' : 'Classification complete'} · ${results.filter(r => r.error).length} failed`;
  } catch (error) {
    $('message').className = error.name === 'AbortError' ? '' : 'error-message';
    $('message').textContent = `${error.name === 'AbortError' ? 'Processing stopped' : error.message} · ${started ? `${completed} completed results have been retained.` : 'Previous results have been retained.'}`;
  } finally {
    busy = false;
    for (const { name, profile, size, action, remove } of sourceRows) { name.disabled = false; profile.disabled = false; size.disabled = false; action.disabled = false; remove.disabled = false; }
    $('add-source').disabled = false;
    activeRequest.abort();
    activeRequest = undefined;
    $('stop').disabled = activeJobState !== 'running';
    clearTimeout(renderTimer);
    renderTimer = undefined;
    for (const id of ['classify', 'sample', 'source-mode', 'file-path', 'paste-profile', 'paste-chunk-events']) $(id).disabled = false;
    if (started || completed) render(false);
    $('export').disabled = !completed;
    if (activeJobState === 'running') {
      $('classify').textContent = 'Reconnect';
      $('message').textContent += ' · Server job continues. Reconnect to receive results.';
    }
  }
}
function handleResultFilter() {
  page = 0;
  if (completed) render();
}
$('review-filter').onchange = handleResultFilter;
$('category-filter').onchange = handleResultFilter;
$('log-search').oninput = handleResultFilter;
$('source-filter').onchange = handleResultFilter;
$('previous').onclick = () => { page--; render(); };
$('next').onclick = () => { page++; render(); };
$('export').onclick = () => {
  const blob = new Blob([JSON.stringify({ mode: resultEngine, sourceMode: resultSourceMode, total, completed, elapsedMs, activeProcessingMs, results: results.filter(Boolean).map(orderedResult) }, null, 2)], { type: 'application/json' });
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
  $('status').textContent = 'Decision Engine: ';
  $('status').append(element('strong', engineLabel, 'selected-engine'));
  $('status').append(element('span', ' · Model: '));
  $('status').append(element('strong', data.model, 'selected-model'));
  if (!data.configured) $('status').append(element('span', ' · API key required'));
  $('powered-by').textContent = `Powered by ${engineLabel}`;
  $('source-mode').onchange();
  $('classify').disabled = !data.configured;
  $('data-notice').textContent = engine === 'laya' ? 'Classification sends logs to your configured Laya server. Laya inference has no Jev API usage fees. Remove passwords, tokens, and sensitive data before sending logs to a remote server.' : 'Classification sends your logs to the TypeSafe API and may incur usage charges. Remove passwords, tokens, and sensitive data first.';
  const limits = data.limits;
  $('source-directory').textContent = `Absolute paths are supported. Relative paths start at: ${data.workingDirectory}`;
  $('input-limits').textContent = engine === 'laya' ? `One decision per chunk · Laya ${data.model} · ${limits.context_tokens.toLocaleString('en-US')} tokens including the question. Truncated predictions are discarded and original events retained for review.` : `One decision per chunk · ${data.model}: ${limits.context_tokens.toLocaleString('en-US')} tokens for state + question · Local preflight budget: ${limits.max_jev_input_bytes.toLocaleString('en-US')} bytes per Jev request (not a token count). Oversized events are retained for review.`;
  handleRestoreJob().catch(error => { $('message').className = 'error-message'; $('message').textContent = error.message; });
}).catch(error => { $('status').textContent = error.message || 'Server connection failed'; });
