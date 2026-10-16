import { readEvents } from './stream.js';

const $ = id => document.getElementById(id);
const labels = { normal: 'Normal', warning: 'Warning', error: 'Error', security: 'Security', other: 'Other' };

const expandedJson = new WeakSet();
function orderedResult(result) {
  const metadata = ['requestedAt', 'decidedAt', 'schemaVersion', 'eventId', 'engine', 'engineConnection', 'requestedModel', 'source', 'sourceId', 'sourceName', 'sourceType', 'hostId', 'hostName', 'hostAddress', 'hostPort', 'sourceFailure', 'chunkSequence', 'sourcePatterns', 'line', 'lineEnd', 'lineCount', 'eventCount', 'profile', 'chunkEvents', 'incomplete', 'elapsedMs', 'requestBytes', 'inputBudget', 'httpStatus', 'responseHeaders', 'action', 'actionExecution'];
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
const defaultSourceProfiles = Object.freeze({
  '/host-logs/var/log/messages': 'general',
  '/host-logs/sample-logs/access-1k.log': 'http_access',
  '/host-logs/sample-logs/SSH_2k.log': 'authentication',
});
const sampleSources = [
  { id: '1'.padStart(32, '0'), name: 'System messages', type: 'local', path: '/host-logs/var/log/messages' },
  { id: '2'.padStart(32, '0'), name: 'Sample HTTP access', type: 'local', path: '/host-logs/sample-logs/access-1k.log' },
  { id: '3'.padStart(32, '0'), name: 'Sample SSH authentication', type: 'local', path: '/host-logs/sample-logs/SSH_2k.log' },
];
let registeredSources = sampleSources.map(source => ({ ...source }));
let sourceSnapshots = [];
const defaultFilePaths = Object.freeze({ batch: sampleSources.map(source => source.id).join('\n'), realtime: sampleSources.map(source => source.id).join('\n') });
const filePaths = { ...defaultFilePaths };
$('file-path').value = filePaths[sourceMode];
let engine = 'laya';
let resultEngine = engine;
let resultSourceMode = sourceMode;
let engineLabel = 'Laya';
let engineConnection = 'not_checked';
let engineConnectionNode;
function handleEngineConnection(state) {
  engineConnection = state;
  if (!engineConnectionNode) return;
  const captions = { not_checked: 'Not checked', connected: 'Connected', disconnected: 'Disconnected', timeout: 'Timed out', api_error: 'API error' };
  engineConnectionNode.textContent = ` (${captions[state]})`;
  engineConnectionNode.className = `engine-connection ${state}`;
  engineConnectionNode.title = 'Last actual engine request; not a continuous health check. Local input rejections do not change this status.';
}
function needsReview(result) {
  return !result.error && Boolean(result.review);
}
function element(tag, text, className = '') {
  const node = document.createElement(tag);
  node.textContent = text;
  node.className = className;
  return node;
}
function handleCloseConfiguration(id) {
  $(id).replaceChildren(); $(id).hidden = true;
  if (id === 'source-view') {
    $('source-editor').hidden = editingSource === null; $('cancel-source').hidden = editingSource === null;
    $('save-sources').disabled = savingSources;
  } else if (id === 'action-view') {
    $('action-editor').hidden = editingAction === null;
    $('cancel-action').hidden = editingAction === null;
    $('action-environment-status').hidden = editingAction === null;
    $('save-actions').disabled = preparingActions;
  } else {
    $('criteria-editor').hidden = editingCriteria === null;
    $('cancel-criteria').hidden = editingCriteria === null;
    $('save-criteria').disabled = !criteriaLoaded || savingCriteria;
  }
}
function handleViewConfiguration(id, title, fields) {
  const container = $(id);
  if (id === 'source-view') {
    $('source-editor').hidden = true; $('cancel-source').hidden = true; $('save-sources').disabled = true;
  } else if (id === 'action-view') {
    $('action-editor').hidden = true; $('cancel-action').hidden = true;
    $('action-environment-status').hidden = true;
    $('save-actions').disabled = true;
  } else {
    $('criteria-editor').hidden = true; $('cancel-criteria').hidden = true;
    $('save-criteria').disabled = true;
  }
  const row = element('div', '', 'action-registration');
  for (const [caption, value] of fields) {
    if (value === undefined) continue;
    const label = element('label', caption, 'action-code-label');
    const input = element('textarea', '');
    input.value = Array.isArray(value) ? value.join('\n') : String(value);
    input.readOnly = true; input.rows = caption === 'Python code' ? 14 : 3;
    input.setAttribute('aria-label', caption);
    if (caption === 'Python code') { input.className = 'action-code'; input.spellcheck = false; }
    label.append(input); row.append(label);
  }
  const close = element('button', 'Cancel', 'quiet');
  close.type = 'button'; close.onclick = () => handleCloseConfiguration(id);
  const header = element('div', '', 'card-title');
  header.append(element('h3', title), close);
  container.replaceChildren(); container.append(header, row);
  container.hidden = false; container.scrollIntoView?.({ block: 'nearest' });
}
let sshKeys = [];
function handleCloseKey() {
  $('ssh-key-registry').hidden = false; $('ssh-key-view').hidden = true;
  $('ssh-key-editor').hidden = true;
  $('ssh-key-name').value = ''; $('ssh-key-file').value = ''; $('ssh-key-paste').value = '';
  pastedPrivateKey = '';
}
function handleAddKey() {
  handleCloseKey();
  $('ssh-key-registry').hidden = true; $('ssh-key-editor').hidden = false;
  $('ssh-key-message').textContent = '';
}
function handleViewKey(key) {
  handleCloseKey(); $('ssh-key-registry').hidden = true;
  const view = $('ssh-key-view'); view.replaceChildren();
  const header = element('div', '', 'card-title');
  const close = element('button', 'Back to list', 'quiet'); close.type = 'button'; close.onclick = handleCloseKey;
  header.append(element('h3', key.name), close); view.append(header);
  const card = element('div', '', 'ssh-key-card');
  for (const [caption, value] of [['Private key path', key.privatePath], ['Public key path', key.publicPath], ['Public key', key.publicKey], ['Private key', '****']]) {
    const label = element('label', caption); const field = element('textarea', '');
    field.readOnly = true; field.rows = caption === 'Public key' ? 3 : 2; field.value = value;
    field.setAttribute('aria-label', `${key.name}: ${caption}`); label.append(field); card.append(label);
  }
  view.append(card); view.hidden = false;
}
function renderSSHKeys() {
  const list = $('ssh-key-list'); list.replaceChildren();
  const table = element('table', '', 'action-list');
  const header = element('tr', '');
  for (const title of ['Name', 'Private key path', 'Manage']) header.append(element('th', title));
  const head = element('thead', ''); head.append(header); table.append(head);
  const body = element('tbody', ''); const query = $('ssh-key-search').value.toLowerCase();
  for (const key of sshKeys.filter(key => key.name.toLowerCase().includes(query))) {
    const row = element('tr', ''); row.append(element('td', key.name), element('td', key.privatePath));
    const controls = element('td', '', 'action-list-controls');
    for (const [caption, handler] of [['View', () => handleViewKey(key)], ['Delete', () => handleDeleteKey(key.name)]]) {
      const button = element('button', caption, 'quiet'); button.type = 'button'; button.onclick = handler; controls.append(button);
    }
    row.append(controls); body.append(row);
  }
  table.append(body); list.append(table);
  if (!body.children.length) list.append(element('p', 'No matching SSH keys.', 'caption'));
}
$('open-add-ssh-key').onclick = handleAddKey;
$('cancel-ssh-key').onclick = handleCloseKey;
$('ssh-key-search').oninput = renderSSHKeys;
async function handleKeyResponse(response) {
  if (response.status === 404 || response.status === 405) {
    throw new Error('SSH key API is unavailable. Restart the DeciFlow UI server or container to load the updated backend.');
  }
  let data;
  try { data = await response.json(); }
  catch { throw new Error(`SSH key API returned an invalid response (HTTP ${response.status}). Check the DeciFlow server.`); }
  if (!response.ok) throw new Error(data.error || 'Could not manage SSH keys.');
  return data;
}
async function handleLoadKeys() {
  try {
    const response = await fetch('/api/ssh-keys', { method: 'POST' });
    const data = await handleKeyResponse(response);
    sshKeys = data.keys; renderSSHKeys();
  } catch (error) { $('ssh-key-message').textContent = error.message; }
}
let pastedPrivateKey = '';
$('ssh-key-paste').onpaste = event => {
  event.preventDefault();
  pastedPrivateKey = event.clipboardData.getData('text/plain');
  $('ssh-key-paste').value = pastedPrivateKey ? '****' : '';
};
$('ssh-key-paste').oninput = () => { pastedPrivateKey = $('ssh-key-paste').value; };
$('ssh-key-method').onchange = () => {
  const method = $('ssh-key-method').value;
  for (const [value, field, input] of [['paste', 'ssh-key-paste-field', 'ssh-key-paste'], ['path', 'ssh-key-path-field', 'ssh-key-path'], ['upload', 'ssh-key-upload-field', 'ssh-key-file']]) {
    $(field).hidden = method !== value; $(input).required = method === value;
    $(input).value = '';
  }
  pastedPrivateKey = '';
};
$('ssh-key-form').onsubmit = async event => {
  event.preventDefault();
  const method = $('ssh-key-method').value || 'upload';
  const body = { name: $('ssh-key-name').value.trim(), inputMethod: method };
  $('add-ssh-key').disabled = true;
  $('ssh-key-message').textContent = 'Adding SSH key…';
  try {
    if (!/^[A-Za-z0-9_ -]{1,64}$/.test(body.name)) throw new Error('Enter a name of 1–64 letters, digits, spaces, underscores, or hyphens.');
    if (method === 'path') {
      body.privateKeyPath = $('ssh-key-path').value.trim();
      if (!body.privateKeyPath) throw new Error('Enter a private key file path.');
    } else if (method === 'upload') {
      const file = $('ssh-key-file').files?.[0];
      if (!file || file.size > 65536) throw new Error('Select a private key file of at most 64 KiB.');
      body.privateKey = await file.text();
    } else {
      if (!pastedPrivateKey || pastedPrivateKey.length > 65536) throw new Error('Paste a private key of at most 64 KiB.');
      body.privateKey = pastedPrivateKey;
    }
    const response = await fetch('/api/ssh-keys', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await handleKeyResponse(response);
    sshKeys = data.keys; renderSSHKeys();
    handleCloseKey();
    $('ssh-key-message').textContent = 'SSH key added.';
  } catch (error) { $('ssh-key-message').textContent = error.message; }
  finally {
    pastedPrivateKey = ''; $('ssh-key-paste').value = ''; $('ssh-key-file').value = '';
    $('add-ssh-key').disabled = false;
  }
};
async function handleDeleteKey(name) {
  if (!globalThis.confirm(`Delete SSH key "${name}"? Both key files will be permanently removed. This cannot be undone.`)) return;
  try {
    const response = await fetch('/api/ssh-keys', { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) });
    const data = await handleKeyResponse(response);
    sshKeys = data.keys; renderSSHKeys(); $('ssh-key-message').textContent = 'SSH key deleted.';
  } catch (error) { $('ssh-key-message').textContent = error.message; }
}
let sshHosts = [];
let editingSSHHost = null;
const sshHostChecks = new Map();
function hostConnectionKey(host) {
  return JSON.stringify([host.host,host.port,host.username,host.keyPath]);
}
function hostDraft() {
  return {...(editingSSHHost ? {id:editingSSHHost} : {}),name:$('ssh-host-name').value,host:$('ssh-host-address').value,port:Number($('ssh-host-port').value),username:$('ssh-host-user').value,keyPath:$('ssh-host-key').value};
}
function connectionStatus(result) {
  if(!result)return 'Not checked';
  if(result.checking)return 'Checking…';
  return `${result.connected?'Connected (SSH + SFTP)':'Failed'} · ${result.checkedAt ? new Date(result.checkedAt).toLocaleString() : ''}${result.elapsedMs!==undefined ? ` · ${result.elapsedMs}ms` : ''}${result.error ? ` · ${result.error}` : ''}`;
}
let hostApprovalQueue = Promise.resolve();
function handleApproveHostKey(presented) {
  const approval = hostApprovalQueue.then(() => new Promise(resolve => {
    const dialog = $('ssh-trust-dialog');
    $('ssh-trust-host').textContent = `${presented.host}:${presented.port}`;
    $('ssh-trust-algorithm').textContent = presented.publicKey.split(' ')[0];
    $('ssh-trust-fingerprint').textContent = presented.fingerprint;
    dialog.returnValue = 'cancel';
    dialog.onclose = () => resolve(dialog.returnValue === 'approve');
    dialog.showModal();
  }));
  hostApprovalQueue = approval.catch(() => false);
  return approval;
}
async function handleTestHost(host=null, automatic=false) {
  const draft=host || hostDraft(); const key=hostConnectionKey(draft);
  if(sshHostChecks.get(key)?.checking)return;
  sshHostChecks.set(key,{checking:true});renderSSHHosts();
  if(!host){$('test-ssh-host').disabled=true;$('ssh-host-test-result').textContent='Checking SSH authentication and SFTP…';}
  let result;
  try {
    const payload=host?{id:host.id}:draft;
    const request=async body=>{
      const response=await fetch('/api/ssh-hosts/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      if(response.status===404 || response.status===405)throw new Error('SSH connection test unavailable. Reload hosts or restart the DeciFlow UI server.');
      const data=await response.json();if(!response.ok)throw new Error(data.error);return data;
    };
    result=await request(payload);
    if(result.hostKey && automatic){
      result.error='Host key approval required. Use Test Connection to review the fingerprint.';
    }else if(result.hostKey){
      const presented=result.hostKey;
      if(await handleApproveHostKey(presented)){
        result=await request({...payload,trustedHostKey:presented.publicKey});
      }else{result.error=`Host key was not approved: ${presented.fingerprint}`;}
    }
  }catch(error){result={connected:false,error:error.message};}
  sshHostChecks.set(key,result);renderSSHHosts();
  if(!host){$('test-ssh-host').disabled=false;$('ssh-host-test-result').textContent=hostConnectionKey(hostDraft())===key ? connectionStatus(result) : 'Connection settings changed. Test again.';}
}
let hostCheckTimer;
let hostChecksRunning = false;
function hostChecksVisible() {
  return currentView === 'settings' && !document.hidden && !$('settings-ssh-hosts').hidden && !$('ssh-host-registry').hidden;
}
function handleScheduleHostChecks() {
  clearTimeout(hostCheckTimer);
  if (hostChecksVisible()) hostCheckTimer = setTimeout(handleAutoCheckHosts, 0);
}
async function handleAutoCheckHosts() {
  if (hostChecksRunning || !hostChecksVisible()) return;
  hostChecksRunning = true;
  clearTimeout(hostCheckTimer);
  try {
    for (const host of [...sshHosts].sort(compareNames)) {
      if (!hostChecksVisible() || $('ssh-trust-dialog').open) break;
      if (!sshHosts.some(item => item.id === host.id && hostConnectionKey(item) === hostConnectionKey(host))) continue;
      await handleTestHost(host, true);
    }
  } finally {
    hostChecksRunning = false;
    if (hostChecksVisible()) hostCheckTimer = setTimeout(handleAutoCheckHosts, 30000);
  }
}
document.addEventListener?.('visibilitychange', handleScheduleHostChecks);
$('test-ssh-host').onclick=()=>handleTestHost();
$('ssh-host-form').oninput=()=>{$('ssh-host-test-result').textContent='';};
function handleCloseHost() {
  editingSSHHost = null; $('ssh-host-registry').hidden = false;
  $('ssh-host-editor').hidden = true; $('ssh-host-view').hidden = true;
  handleScheduleHostChecks();
}
function renderSSHHosts() {
  const list = $('ssh-host-list'); list.replaceChildren();
  const table = element('table', '', 'action-list'); const header = element('tr', '');
  for (const title of ['Name', 'Connection', 'SSH key', 'Status', 'Manage']) header.append(element('th', title));
  const head = element('thead', ''); head.append(header); table.append(head);
  const body = element('tbody', ''); const query = $('ssh-host-search').value.toLowerCase();
  for (const host of sshHosts.filter(host => `${host.name} ${host.host} ${host.username}`.toLowerCase().includes(query))) {
    const row = element('tr', '');
    row.append(element('td', host.name), element('td', `${host.username}@${host.host}:${host.port}`), element('td', sshKeys.find(key => key.privatePath === host.keyPath)?.name || host.keyPath));
    const controls = element('td', '', 'action-list-controls');
    for (const [caption, handler] of [['View', () => handleViewHost(host)], ['Edit', () => handleEditHost(host)], ['Delete', () => handleDeleteHost(host)]]) {
      const button = element('button', caption, 'quiet'); button.type = 'button'; button.onclick = handler; controls.append(button);
    }
    const check=sshHostChecks.get(hostConnectionKey(host));
    const test=element('button', 'Test Connection', 'quiet'); test.type='button';test.disabled=Boolean(check?.checking);test.onclick=()=>handleTestHost(host);controls.append(test);
    row.append(element('td',connectionStatus(check),check?.connected?'connection-ok':check && !check.checking?'connection-failed':''),controls); body.append(row);
  }
  table.append(body); list.append(table);
  if (!body.children.length) list.append(element('p', 'No matching SSH hosts.', 'caption'));
}
async function handleLoadHosts() {
  try {
    const response = await fetch('/api/ssh-hosts', { method: 'POST' });
    if (response.status === 404 || response.status === 405) throw new Error('SSH host API is unavailable. Restart the DeciFlow UI server or container.');
    const data = await response.json(); if (!response.ok) throw new Error(data.error);
    sshHosts = data.hosts; renderSSHHosts();
    handleScheduleHostChecks();
  } catch (error) { $('ssh-host-message').textContent = error.message; }
}
function handleEditHost(host = null) {
  handleCloseHost(); editingSSHHost = host?.id || null;
  $('ssh-host-registry').hidden = true; $('ssh-host-editor').hidden = false;
  $('ssh-host-editor-title').textContent = host ? 'Edit SSH host' : 'Add SSH host';
  for (const [id, value] of [['ssh-host-name', host?.name || ''], ['ssh-host-address', host?.host || ''], ['ssh-host-port', host?.port || 22], ['ssh-host-user', host?.username || '']]) $(id).value = String(value);
  const keys = $('ssh-host-key'); keys.replaceChildren();
  for (const key of sshKeys) keys.append(new Option(key.name, key.privatePath));
  if (host?.keyPath && !sshKeys.some(key => key.privatePath === host.keyPath)) keys.append(new Option(host.keyPath, host.keyPath));
  keys.value = host?.keyPath || ''; $('ssh-host-message').textContent = '';
  $('ssh-host-test-result').textContent='';
}
function handleViewHost(host) {
  handleCloseHost(); $('ssh-host-registry').hidden = true;
  const view = $('ssh-host-view'); view.replaceChildren();
  const header = element('div', '', 'card-title'); const close = element('button', 'Back to list', 'quiet');
  close.type = 'button'; close.onclick = handleCloseHost;
  header.append(element('h3', host.name), close); view.append(header);
  const fields = element('div', '', 'ssh-key-card');
  for (const [caption, value] of [['Host', host.host], ['Port', host.port], ['SSH user', host.username], ['SSH key path', host.keyPath]]) {
    const label = element('label', caption); const input = element('textarea', ''); input.readOnly = true; input.rows = 2; input.value = String(value);
    label.append(input); fields.append(label);
  }
  view.append(fields); view.hidden = false;
}
$('open-add-ssh-host').onclick = () => handleEditHost();
$('cancel-ssh-host').onclick = handleCloseHost;
$('ssh-host-search').oninput = renderSSHHosts;
$('ssh-host-form').onsubmit = async event => {
  event.preventDefault(); $('save-ssh-host').disabled = true;
  try {
    const host = hostDraft();
    const response = await fetch('/api/ssh-hosts', {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(host)});
    const data = await response.json(); if (!response.ok) throw new Error(data.error);
    sshHosts = data.hosts; renderSSHHosts(); handleCloseHost();
    registeredSources = registeredSources.map(source => {
      const host = sshHosts.find(host => host.id === source.hostId);
      return host ? {...source, host:host.host, port:host.port, username:host.username, keyPath:host.keyPath, hostName:host.name} : source;
    });
    renderSources(); if (!busy) updateSourceSettings(sourceRows.map(row => row.path));
    $('ssh-host-message').textContent = 'SSH host saved. Changes apply to new runs.';
  } catch (error) { $('ssh-host-message').textContent = error.message; }
  finally { $('save-ssh-host').disabled = false; }
};
async function handleDeleteHost(host) {
  if (!globalThis.confirm(`Delete SSH host "${host.name}"? Sources and running jobs must stop referencing it first.`)) return;
  try {
    const response = await fetch('/api/ssh-hosts', {method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:host.id})});
    const data = await response.json(); if (!response.ok) throw new Error(data.error);
    sshHosts = data.hosts; renderSSHHosts(); $('ssh-host-message').textContent = 'SSH host deleted.';
  } catch (error) { $('ssh-host-message').textContent = error.message; }
}
let registeredTasks = [];
let selectedTaskId = '';
let editingTask = null;
let monitoringPromise = Promise.resolve();
let monitorSelection = 0;
let followLatestTask = true;
let monitoringReady = false;

function taskExecution(task) {
  return task.mode === 'realtime' ? `Realtime${task.resumeOnRestart ? ' · resume on restart' : ''}` : task.cron ? `Batch · ${task.cron} · ${task.timezone}${task.enabled ? '' : ' · paused'}` : 'Batch · Manual';
}
function taskTime(value, timezone = 'UTC') {
  return value ? new Date(value).toLocaleString('en-GB', {timeZone:timezone,hour12:false}) : '—';
}
function renderTaskMonitor() {
  const list=$('running-tasks'); list.replaceChildren();
  const running=registeredTasks.filter(task=>task.activeRun || task.starting).sort(compareNames);
  for(const task of running) {
    const button=element('button','','running-task'); button.type='button';
    button.setAttribute('aria-pressed',String(task.id===selectedTaskId));
    button.append(element('strong',task.name),element('span',`${task.starting?'Starting':'Running'} · ${task.mode==='realtime'?'Realtime':'Batch'}`,'caption'));
    button.disabled=!task.activeRun;
    button.onclick=()=>handleSelectTask(task.id);
    list.append(button);
  }
  if(!running.length)list.append(element('p','No Tasks are currently running. Start a Task from Tasks.','caption'));
  const task=registeredTasks.find(task=>task.id===selectedTaskId);
  $('monitor-task-info').textContent=task ? `${task.name} · ${taskExecution(task)} · ${task.sources.length} Source(s)` : 'Select a running Task to view its results.';
  const run=task?.activeRun || task?.latestRun;
  $('monitor-task-status').textContent=task ? `${task.starting ? 'Starting' : run?.state || 'Idle'}${task.nextRunAt ? ` · Next: ${taskTime(task.nextRunAt,task.timezone)} (${task.timezone})` : ''}${run?.counts ? ` · ${run.counts.completed} completed · ${run.counts.failed} failed requests · ${run.counts.actionFailed} failed Actions` : ''}` : '';
  $('stop').disabled=!task?.activeRun;
}
function renderTasks() {
  $('task-registry').hidden=editingTask!==null;
  const list=$('task-list'); list.replaceChildren();
  const table=element('table','','action-list'); const head=element('tr','');
  for(const title of ['Name','Execution','Status','Next run','Manage']) head.append(element('th',title));
  table.append(head); const query=$('task-search').value.toLowerCase();
  for(const task of registeredTasks.filter(task=>task.name.toLowerCase().includes(query))) {
    const row=element('tr',''); const run=task.activeRun || task.latestRun;
    row.append(element('td',task.name),element('td',taskExecution(task)),element('td',task.starting ? 'Starting' : run?.state || 'Idle',`task-state ${task.starting?'running':run?.state || 'idle'}`),element('td',task.nextRunAt ? `${taskTime(task.nextRunAt,task.timezone)} (${task.timezone})` : '—'));
    const controls=element('td','','action-list-controls');
    for(const [label,handler] of [['Run',()=>handleRunTask(task.id)],['Stop',()=>handleStopTask(task.id)],['View',()=>handleViewTask(task)],['Edit',()=>handleEditTask(task)],['History',()=>handleTaskHistory(task)],['Delete',()=>handleDeleteTask(task)]]) {
      const button=element('button',label,'quiet'); button.type='button';button.onclick=handler;
      if(label==='Run')button.disabled=Boolean(task.activeRun || task.starting);
      if(label==='Stop')button.disabled=!task.activeRun;
      controls.append(button);
    }
    row.append(controls);table.append(row);
  }
  list.append(table);renderTaskMonitor();
}
async function handleLoadTasks() {
  try {
    const response=await fetch('/api/tasks',{method:'POST'});
    if(response.status===404 || response.status===405)throw new Error('Tasks API is unavailable. Restart the DeciFlow UI server or container.');
    const data=await response.json();if(!response.ok)throw new Error(data.error);
    registeredTasks=data.tasks;renderTasks();
    const selected=registeredTasks.find(task=>task.id===selectedTaskId);
    const run=selected?.activeRun || selected?.latestRun;
    if(monitoringReady && followLatestTask && currentView==='main' && run && run.jobId!==activeJobId)handleWatchRun(run);
  } catch(error) { $('task-message').textContent=error.message; $('monitor-task-status').textContent=error.message; }
}
function handleCloseTask() {
  editingTask=null; $('task-registry').hidden=false;$('task-editor').hidden=true;$('task-view').hidden=true;$('task-history').hidden=true;
}
function handleTaskMode() {
  const realtime=$('source-mode').value==='realtime'; const cron=!realtime && $('task-trigger').value==='cron';
  $('task-trigger-field').hidden=realtime;
  for(const id of ['task-cron-field','task-timezone-field','task-enabled-field'])$(id).hidden=!cron;
  $('task-resume-field').hidden=!realtime;
  $('task-mode-note').textContent=realtime ? 'Realtime monitors new data lines until stopped. Automatic restart is opt-in; lines written during downtime are not replayed.' : cron ? 'Each scheduled Batch reads files from the beginning and can repeat Actions for the same data. Overlapping occurrences are skipped. Missed schedules are not replayed. No automatic retries.' : 'Manual Batch reads files from the beginning once, then finishes as Completed or Failed.';
}
async function handleEditTask(task=null) {
  await sourceLoadPromise;
  await handleLoadHosts();
  if(!sourcesLoaded){$('task-message').textContent='Load Sources before editing Tasks.';return;}
  handleCloseTask();editingTask=task?.id || '';
  $('task-registry').hidden=true;$('task-editor').hidden=false;
  $('task-editor-title').textContent=task?'Edit Task':'Add Task';$('task-name').value=task?.name || '';
  $('source-mode').value=task?.mode || 'batch';$('task-trigger').value=task?.cron?'cron':'manual';
  $('task-cron').value=task?.cron || '';$('task-timezone').value=task?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  $('task-enabled').checked=task?.enabled ?? true;$('task-resume').checked=task?.resumeOnRestart || false;
  sourcePreferences.clear();
  for(const source of task?.sources || [])sourcePreferences.set(source.sourceId,{profile:source.profile,chunkEvents:source.chunkEvents,action:source.action || '',hostIds:[...(source.hostIds || [])]});
  const paths=task?.sources.map(source=>source.sourceId) || registeredSources.slice(0,1).map(source=>source.id);
  $('file-path').value=paths.join('\n');updateSourceSettings(paths);handleTaskMode();$('task-message').textContent='';
}
$('add-task').onclick=()=>handleEditTask();$('cancel-task').onclick=handleCloseTask;$('task-search').oninput=renderTasks;
$('task-form').onsubmit=async event=>{
  event.preventDefault();$('save-task').disabled=true;
  try {
    const mode=$('source-mode').value;
    const sources=sourceRows.map(({path,profile,size,action,hostIds})=>({sourceId:path,profile:profile.value,chunkEvents:Number(size.value),action:action.value,...(hostIds?.length?{hostIds:[...hostIds]}:{})}));
    const task={...(editingTask?{id:editingTask}:{}),name:$('task-name').value,mode,sources,cron:mode==='batch' && $('task-trigger').value==='cron'?$('task-cron').value:'',timezone:$('task-timezone').value || 'UTC',enabled:$('task-enabled').checked,resumeOnRestart:mode==='realtime' && $('task-resume').checked};
    const response=await fetch('/api/tasks',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(task)});
    const data=await response.json();if(!response.ok)throw new Error(data.error);
    registeredTasks=data.tasks;handleCloseTask();renderTasks();$('task-message').textContent='Task saved. Changes apply to new runs.';
  }catch(error){$('task-message').textContent=error.message;}
  finally{$('save-task').disabled=false;}
};
function handleViewTask(task) {
  handleCloseTask();$('task-registry').hidden=true;const view=$('task-view');view.replaceChildren();
  const header=element('div','','card-title');const back=element('button','Back to list','quiet');back.type='button';back.onclick=handleCloseTask;
  header.append(element('h3',task.name),back);view.append(header);
  view.append(element('p',taskExecution(task)));
  const list=element('ul','');for(const source of task.sources){const definition=registeredSources.find(item=>item.id===source.sourceId);list.append(element('li',`${definition?.name || source.sourceId} · ${definition?.path || 'Source unavailable'} · ${profileLabels[source.profile] || source.profile} · ${source.chunkEvents} event(s) · Action: ${source.action || 'None'}${source.hostIds?.length ? ` · Hosts: ${source.hostIds.map(id=>sshHosts.find(host=>host.id===id)?.name || id).join(', ')}` : ''}`));}
  view.append(list);view.hidden=false;
}
async function handleDeleteTask(task) {
  if(!globalThis.confirm(`Delete Task "${task.name}"? Saved run history will remain on disk. Stop running executions first.`))return;
  try {
    const response=await fetch('/api/tasks',{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:task.id})});
    const data=await response.json();if(!response.ok)throw new Error(data.error);
    registeredTasks=data.tasks;if(selectedTaskId===task.id)selectedTaskId='';renderTasks();
  }catch(error){$('task-message').textContent=error.message;}
}
async function handleTaskHistory(task) {
  try {
    const response=await fetch(`/api/tasks/${task.id}/runs`,{method:'POST'});const data=await response.json();if(!response.ok)throw new Error(data.error);
    handleCloseTask();$('task-registry').hidden=true;const view=$('task-history');view.replaceChildren();
    const header=element('div','','card-title');const back=element('button','Back to list','quiet');back.type='button';back.onclick=handleCloseTask;
    const refresh=element('button','Refresh','quiet');refresh.type='button';refresh.onclick=()=>handleTaskHistory(task);
    header.append(element('h3',`${task.name} · Latest 50 executions`),refresh,back);view.append(header);
    const table=element('table','','action-list');const head=element('tr','');for(const title of ['Started','Finished','Trigger','State','Results','Manage'])head.append(element('th',title));table.append(head);
    for(const run of data.runs){const row=element('tr','');row.append(element('td',`${taskTime(run.startedAt,task.timezone)} (${task.timezone})`),element('td',taskTime(run.finishedAt,task.timezone)),element('td',run.settings.trigger),element('td',run.state,`task-state ${run.state}`),element('td',`${run.counts?.completed || 0} chunks · ${run.counts?.failed || 0} failed requests · ${run.counts?.actionFailed || 0} failed Actions${run.error?` · ${run.error}`:''}`));const cell=element('td','');const button=element('button','View results','quiet');button.type='button';button.onclick=()=>{followLatestTask=false;selectedTaskId=task.id;handleNavigation('main');renderTaskMonitor();return handleWatchRun(run);};cell.append(button);row.append(cell);table.append(row);}
    view.append(table);if(!data.runs.length)view.append(element('p','No executions yet.','caption'));view.hidden=false;
  }catch(error){$('task-message').textContent=error.message;}
}
async function handleWatchRun(job) {
  if(busy && activeJobId===job.jobId)return monitoringPromise;
  const selection=++monitorSelection;
  if(busy){activeRequest?.abort();await monitoringPromise;}
  if(selection!==monitorSelection)return;
  monitoringPromise=handleProcessing(job);return monitoringPromise;
}
async function handleRunTask(identity) {
  const task=registeredTasks.find(task=>task.id===identity);
  if(!task){$('message').textContent='Select a saved Task first.';return;}
  followLatestTask=true;monitoringReady=true;selectedTaskId=identity;handleNavigation('main');renderTaskMonitor();
  try {
    if(task.activeRun)return await handleWatchRun(task.activeRun);
    const response=await fetch(`/api/tasks/${identity}/run`,{method:'POST'});const job=await response.json();if(!response.ok)throw new Error(job.error);
    await handleLoadTasks();return await handleWatchRun(job);
  }catch(error){$('message').className='error-message';$('message').textContent=error.message;}
}
async function handleStopTask(identity) {
  try{const response=await fetch(`/api/tasks/${identity}/stop`,{method:'POST'});const data=await response.json();if(!response.ok)throw new Error(data.error);await handleLoadTasks();}
  catch(error){$('task-message').textContent=error.message;}
}
async function handleSelectTask(identity) {
  followLatestTask=true;monitoringReady=true;
  const task=registeredTasks.find(task=>task.id===identity);selectedTaskId=task?.id || '';
  renderTaskMonitor();
  if(task?.activeRun || task?.latestRun)return handleWatchRun(task.activeRun || task.latestRun);
}

let currentView = null;
let currentSettingsSection = null;
function handleMenuNavigation(view, section=null) {
  if (view === 'sources') {
    handleCloseConfiguration('source-view'); handleCloseSource();
  } else if (view === 'actions') {
    handleCloseConfiguration('action-view'); handleCloseAction();
  } else if (view === 'criteria') {
    handleCloseConfiguration('criteria-view'); handleCloseCriteria();
  } else if (view === 'tasks') {
    handleCloseTask();
  } else if (view === 'settings') {
    handleCloseKey(); handleCloseHost();
  }
  handleNavigation(view, section);
}
function handleNavigation(view, section=null) {
  currentView = view;
  currentSettingsSection = view === 'settings' ? section : null;
  if (view === 'settings' || view === 'sources') handleLoadKeys().then(handleLoadHosts);
  const hash = view === 'main' ? '' : view === 'settings' && section ? `#settings/${section}` : `#${view}`;
  if (globalThis.location && globalThis.location.hash !== hash) globalThis.location.hash = hash;
  $('main-page').hidden = view !== 'main';
  $('settings-page').hidden = view !== 'settings';
  $('nav-settings').setAttribute('aria-current', view === 'settings' && !section ? 'page' : 'false');
  $('nav-settings').setAttribute('data-active', String(view === 'settings'));
  const settingsHeading = section === 'ssh-keys'
    ? ['SSH Keys', 'Manage authentication keys for SSH connections.']
    : section === 'ssh-hosts'
      ? ['SSH Hosts', 'Manage remote hosts and test SSH connections.']
      : ['Settings', 'Manage shared application settings.'];
  $('settings-title').textContent = settingsHeading[0];
  $('settings-description').textContent = settingsHeading[1];
  $('settings-overview').hidden = Boolean(section);
  for(const id of ['ssh-keys','ssh-hosts']) {
    $(`settings-${id}`).hidden = view !== 'settings' || section !== id;
    $(`nav-${id}`).setAttribute('aria-current', view === 'settings' && section===id ? 'page' : 'false');
  }
  handleScheduleHostChecks();
  $('tasks-page').hidden = view !== 'tasks';
  $('nav-tasks').setAttribute('aria-current', view === 'tasks' ? 'page' : 'false');
  if (view === 'tasks') { handleLoadTasks(); handleLoadHosts(); }
  $('sources-page').hidden = view !== 'sources';
  $('nav-sources').setAttribute('aria-current', view === 'sources' ? 'page' : 'false');
  $('actions-page').hidden = view !== 'actions';
  $('criteria-page').hidden = view !== 'criteria';
  $('nav-criteria').setAttribute('aria-current', view === 'criteria' ? 'page' : 'false');
  $('nav-main').setAttribute('aria-current', view === 'main' ? 'page' : 'false');
  $('nav-actions').setAttribute('aria-current', view === 'actions' ? 'page' : 'false');
}
$('nav-settings').onclick = () => { handleMenuNavigation('settings'); };
$('nav-ssh-keys').onclick = () => handleMenuNavigation('settings','ssh-keys');
$('nav-ssh-hosts').onclick = () => handleMenuNavigation('settings','ssh-hosts');
$('nav-tasks').onclick = () => handleMenuNavigation('tasks');
$('manage-tasks').onclick = () => handleMenuNavigation('tasks');
$('nav-main').onclick = () => handleNavigation('main');
$('nav-actions').onclick = () => handleMenuNavigation('actions');
$('nav-sources').onclick = () => { handleMenuNavigation('sources'); if (!sourcesLoaded) return handleLoadSources(); };
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
let preparingActionIndex = null;
let actionStatusTimer;
const sourcePreferences = new Map();
try {
  for (const [path, preference] of JSON.parse(localStorage.getItem('deciflow-source-preferences') || '[]')) sourcePreferences.set(path, { profile: preference.profile, chunkEvents: preference.chunkEvents });
} catch { /* Keep the UI usable when browser storage is unavailable or invalid. */ }
let editingAction = null;
function renderActions() {
  $('action-list').hidden = editingAction !== null;
  const editorStatus = preparingActions ? 'preparing' : registeredActions[editingAction]?.environmentStatus || 'not_ready';
  $('action-environment-status').hidden = editingAction === null || $('action-editor').hidden === true;
  $('action-environment-status').textContent = { ready: 'Ready', preparing: 'Preparing...', not_ready: 'Not ready', external: 'External' }[editorStatus];
  $('action-environment-status').className = `action-status ${editorStatus}`;
  $('action-registry').replaceChildren();
  const query = $('action-search').value.trim().toLowerCase();
  let matches = 0;
  const table = element('table', '', 'action-list');
  const header = element('tr', '');
  for (const title of ['Name', 'Python', 'Modules', 'Status', 'Manage']) header.append(element('th', title));
  table.append(header);
  registeredActions.forEach((action, index) => {
    if (!action.name.toLowerCase().includes(query)) return;
    matches++;
    const row = element('tr', '');
    const modules = Array.isArray(action.modules) ? action.modules.join(', ') : action.modules;
    for (const value of [action.name, action.pythonVersion || 'External', modules || 'Standard library']) row.append(element('td', value));
    const state = action.pythonVersion && preparingActions && (index === preparingActionIndex || (preparingActionIndex === null && action.environmentStatus === 'not_ready')) ? 'preparing' : action.environmentStatus || (action.pythonVersion ? 'not_ready' : 'external');
    const status = element('td', '', 'action-status-cell');
    const badge = element('span', { ready: 'Ready', preparing: 'Preparing...', not_ready: 'Not ready', external: 'External' }[state], `action-status ${state}`);
    badge.setAttribute('role', 'status'); status.append(badge); row.append(status);
    const controls = element('td', '', 'action-list-controls');
    for (const [caption, handler] of [
      ['View', () => handleViewConfiguration('action-view', action.name, [['Name', action.name], ['ID', action.id], ['Python version', action.pythonVersion], ['Modules', action.modules || []], ['Python executable', action.python], ['Script path', action.script], ['Python code', action.code]])],
      ['Edit', () => handleEditAction(index)],
      ['Reset venv', () => handleResetAction(index)],
      ['Delete', () => { registeredActions.splice(index, 1); handleCloseConfiguration('action-view'); renderActions(); $('action-message').textContent = 'Deletion pending. Save changes to apply.'; }],
    ]) {
      const button = element('button', caption, 'quiet');
      button.type = 'button'; button.disabled = preparingActions || (caption !== 'View' && editingAction !== null) || (caption === 'Reset venv' && (!action.id || !action.pythonVersion));
      button.onclick = handler; controls.append(button);
    }
    row.append(controls); table.append(row);
  });
  $('action-registry').append(matches ? table : element('p', registeredActions.length ? 'No Actions match your search.' : 'No Actions registered. Click Add action to create one.', 'caption'));
  $('add-action').disabled = preparingActions || editingAction !== null;
}
function scheduleActionStatus() {
  if (actionStatusTimer) return;
  if (registeredActions.some(action => action.environmentStatus === 'preparing')) actionStatusTimer = setTimeout(handleRefreshActionStatus, 2000);
}
async function handleRefreshActionStatus() {
  clearTimeout(actionStatusTimer); actionStatusTimer = undefined;
  try {
    const response = await fetch('/api/actions');
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    const states = new Map(data.actions.map(action => [action.id, action.environmentStatus]));
    for (const action of registeredActions) {
      if (states.has(action.id)) action.environmentStatus = states.get(action.id);
      else if (action.pythonVersion) action.environmentStatus = 'not_ready';
    }
    renderActions();
  } catch { /* Keep the last known status; the operation error is shown separately. */ }
  scheduleActionStatus();
}
async function handleResetAction(index) {
  preparingActionIndex = index;
  preparingActions = true; $('save-actions').disabled = true;
  renderActions();
  $('action-message').textContent = 'Rebuilding the saved Action environment…';
  try {
    const response = await fetch(`/api/actions/${registeredActions[index].id}/reset`, { method: 'POST' });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    registeredActions[index] = data.action;
    handleCloseConfiguration('action-view');
    $('action-message').textContent = 'Action environment rebuilt with pip and locked dependencies.';
  } catch (error) { await handleRefreshActionStatus(); $('action-message').textContent = error.message; }
  finally { preparingActionIndex = null; preparingActions = false; $('save-actions').disabled = $('action-view').hidden === false; renderActions(); }
}
$('action-search').oninput = renderActions;
function handleEditAction(index) {
  handleCloseConfiguration('action-view');
  editingAction = index;
  const action = registeredActions[index] || { pythonVersion: '3.12', code: defaultActionCode };
  const row = element('div', '', 'action-registration');
  const fields = { id: { value: action.id || '' } };
  for (const [key, caption] of [['name', 'Name'], ['pythonVersion', 'Python version (e.g. 3.12)'], ['modules', 'Modules (one per line; versions optional)'], ['code', 'Python code']]) {
    const label = element('label', caption);
    const input = element(['modules', 'code'].includes(key) ? 'textarea' : 'input', '');
    input.value = key === 'modules' && Array.isArray(action.modules) ? action.modules.join('\n') : action[key] || (key === 'pythonVersion' ? '3.12' : '');
    if (key === 'name') input.readOnly = index < registeredActions.length;
    if (key === 'modules') input.rows = 3;
    if (key === 'code') { input.rows = 14; input.spellcheck = false; input.className = 'action-code'; label.className = 'action-code-label'; }
    input.setAttribute('aria-label', caption);
    label.append(input);
    if (key === 'name' && !input.readOnly) {
      const note = element('span', 'Name cannot be changed after creation.', 'caption error-message');
      note.id = 'action-name-note';
      input.setAttribute('aria-describedby', note.id);
      label.append(note);
    }
    if (['pythonVersion', 'modules'].includes(key) && index < registeredActions.length) {
      const note = element('span', 'Changing Python version or modules replaces the environment after preparation succeeds. Stop runs using this Action before editing.', 'caption');
      note.id = `action-${key}-note`;
      input.setAttribute('aria-describedby', note.id);
      label.append(note);
    }
    row.append(label); fields[key] = input;
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
  preparingActionIndex = editingAction;
  preparingActions = true;
  $('save-actions').disabled = true;
  $('add-action').disabled = true; $('cancel-action').disabled = true;
  renderActions();
  $('action-message').textContent = 'Preparing Python environments and installing modules…';
  for (const fields of actionRows) for (const input of Object.values(fields)) input.disabled = true;
  try {
    const values = registeredActions.slice();
    if (editingAction !== null) values[editingAction] = { ...registeredActions[editingAction], ...Object.fromEntries(Object.entries(actionRows[0]).map(([key, input]) => [key, input.value])) };
    if (editingAction !== null && registeredActions[editingAction]) values[editingAction].name = registeredActions[editingAction].name;
    const response = await fetch('/api/actions', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(values) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    registeredActions = data.actions;
    handleCloseConfiguration('action-view'); handleCloseAction(); updateSourceSettings();
    $('action-message').textContent = 'Actions saved and environments ready. Changes apply to the next run.';
  } catch (error) { $('action-message').textContent = error.message; }
  finally {
    preparingActionIndex = null; preparingActions = false;
    $('save-actions').disabled = false; $('add-action').disabled = false;
    for (const fields of actionRows) for (const input of Object.values(fields)) input.disabled = false;
    $('cancel-action').disabled = false; renderActions();
  }
};
fetch('/api/actions', { method: 'POST' }).then(async response => {
  const data = await response.json();
  if (!response.ok) throw new Error(data.error);
  registeredActions = data.actions; renderActions(); updateSourceSettings(); scheduleActionStatus();
}).catch(error => { $('action-message').textContent = error.message; });
let criteriaProfiles = {};
let criteriaLoaded = false;
let savingCriteria = false;
let editingCriteria = null;
let criteriaFields = {};
function handleViewCriteria(id) {
  const profile = criteriaProfiles[id];
  handleViewConfiguration('criteria-view', profile.label, [['Profile ID', id], ['Name', profile.label], ['Decision instructions', profile.instructions], ...Object.entries(labels).map(([key, label]) => [label, profile.criteria[key]]), ['Normalization', profile.normalization]]);
}
function renderCriteria() {
  $('criteria-list').hidden = editingCriteria !== null;
  const defaultTable = element('table', '', 'action-list');
  const defaultHeader = element('tr', '');
  for (const title of ['Name', 'Profile ID', 'Manage']) defaultHeader.append(element('th', title));
  const defaultRow = element('tr', '');
  defaultRow.append(element('td', criteriaProfiles.general.label), element('td', 'general'));
  const defaultControls = element('td', '', 'action-list-controls');
  const viewDefault = element('button', 'View', 'quiet');
  viewDefault.type = 'button'; viewDefault.disabled = savingCriteria;
  viewDefault.onclick = () => handleViewCriteria('general');
  defaultControls.append(viewDefault); defaultRow.append(defaultControls);
  defaultTable.append(defaultHeader, defaultRow);
  $('criteria-default').replaceChildren(); $('criteria-default').append(defaultTable);
  const table = element('table', '', 'action-list');
  const header = element('tr', '');
  for (const title of ['Name', 'Profile ID', 'Manage']) header.append(element('th', title));
  table.append(header);
  const query = $('criteria-search').value.trim().toLowerCase();
  let matches = 0;
  for (const [id, profile] of Object.entries(criteriaProfiles)) {
    if (id === 'general' || !profile.label.toLowerCase().includes(query)) continue;
    matches++;
    const row = element('tr', '');
    row.append(element('td', profile.label), element('td', id));
    const controls = element('td', '', 'action-list-controls');
    for (const [caption, handler] of [
      ['View', () => handleViewCriteria(id)],
      ['Edit', () => handleEditCriteria(id)],
      ['Delete', () => { delete criteriaProfiles[id]; handleCloseConfiguration('criteria-view'); renderCriteria(); $('criteria-message').textContent = 'Deletion pending. Save changes to apply.'; }],
    ]) {
      const button = element('button', caption, 'quiet');
      button.type = 'button';
      button.disabled = savingCriteria || (caption !== 'View' && editingCriteria !== null);
      button.onclick = handler; controls.append(button);
    }
    row.append(controls); table.append(row);
  }
  $('criteria-registry').replaceChildren();
  $('criteria-registry').append(matches ? table : element('p', 'No profiles match your search.', 'caption'));
  $('add-criteria').disabled = !criteriaLoaded || savingCriteria || editingCriteria !== null;
}
function handleEditCriteria(id) {
  handleCloseConfiguration('criteria-view');
  editingCriteria = id;
  const profile = criteriaProfiles[id] || { label: '', instructions: '', criteria: { ...criteriaProfiles.general.criteria } };
  const row = element('div', '', 'action-registration');
  criteriaFields = {};
  for (const [key, caption] of [['id', 'Profile ID (lowercase letters, digits, _ or -)'], ['label', 'Name'], ['instructions', 'Decision instructions'], ...Object.entries(labels)]) {
    const label = element('label', caption);
    const input = element(['id', 'label'].includes(key) ? 'input' : 'textarea', '');
    input.value = key === 'id' ? id : (profile[key] ?? profile.criteria[key] ?? '');
    if (key === 'id') input.readOnly = Boolean(criteriaProfiles[id]);
    input.setAttribute('aria-label', caption);
    if (key !== 'id' && key !== 'label') { input.rows = 3; label.className = 'action-code-label'; }
    label.append(input); row.append(label); criteriaFields[key] = input;
  }
  $('criteria-editor').replaceChildren(); $('criteria-editor').append(row);
  $('criteria-editor').hidden = false; $('cancel-criteria').hidden = false;
  renderCriteria();
}
function handleCloseCriteria() {
  editingCriteria = null; criteriaFields = {};
  $('criteria-editor').replaceChildren(); $('criteria-editor').hidden = true;
  $('cancel-criteria').hidden = true;
  if (criteriaLoaded) renderCriteria();
}
function handleCriteriaLabels(profiles) {
  for (const key of Object.keys(profileLabels)) delete profileLabels[key];
  for (const [id, profile] of Object.entries(profiles)) profileLabels[id] = profile.label;
  let missing = false;
  for (const select of sourceRows.map(row => row.profile)) {
    const selected = select.value;
    select.replaceChildren();
    if (!profileLabels[selected]) missing = true;
    for (const [id, label] of Object.entries(profileLabels)) select.append(new Option(label, id));
    select.value = profileLabels[selected] ? selected : '';
  }
  return missing;
}
$('nav-criteria').onclick = async () => {
  handleMenuNavigation('criteria');
  if (criteriaLoaded) return;
  $('criteria-message').textContent = 'Loading criteria…';
  try {
    const response = await fetch('/api/criteria', { method: 'POST' });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    criteriaProfiles = data.profiles; criteriaLoaded = true;
    $('save-criteria').disabled = false; renderCriteria();
    $('criteria-message').textContent = '';
  } catch (error) { $('criteria-message').textContent = error.message; }
};
$('criteria-search').oninput = renderCriteria;
$('add-criteria').onclick = () => handleEditCriteria('');
$('cancel-criteria').onclick = handleCloseCriteria;
$('save-criteria').onclick = async () => {
  savingCriteria = true; $('save-criteria').disabled = true; $('cancel-criteria').disabled = true;
  renderCriteria();
  for (const input of Object.values(criteriaFields)) input.disabled = true;
  try {
    const values = { ...criteriaProfiles };
    if (editingCriteria !== null) {
      const id = criteriaFields.id.value.trim();
      if (!editingCriteria && Object.hasOwn(values, id)) throw new Error('Profile ID already exists.');
      values[id] = { ...criteriaProfiles[editingCriteria], label: criteriaFields.label.value, instructions: criteriaFields.instructions.value, criteria: Object.fromEntries(Object.keys(labels).map(key => [key, criteriaFields[key].value])) };
    }
    const response = await fetch('/api/criteria', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(values) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    criteriaProfiles = data.profiles; handleCloseConfiguration('criteria-view'); handleCloseCriteria();
    const missing = handleCriteriaLabels(criteriaProfiles);
    $('criteria-message').textContent = 'Criteria saved. Changes apply to new runs.' + (missing ? ' Select replacements for deleted profiles in Tasks.' : '');
  } catch (error) { $('criteria-message').textContent = error.message; }
  finally {
    savingCriteria = false; $('save-criteria').disabled = false; $('cancel-criteria').disabled = false;
    for (const input of Object.values(criteriaFields)) input.disabled = false;
    renderCriteria();
  }
};
let sourcesLoaded = false;
let editingSource = null;
let sourceFields = {};
let savingSources = false;
function sourceDescription(source) {
  return `${source.type === 'ssh' ? 'Remote File (SSH)' : 'Local File'} · ${source.path}`;
}
function renderSources() {
  $('source-list').hidden = editingSource !== null;
  const table = element('table', '', 'action-list');
  const header = element('tr', '');
  for (const caption of ['Name', 'Type / path', 'Manage']) header.append(element('th', caption));
  table.append(header);
  const query = $('source-search').value.trim().toLowerCase();
  for (const [index, source] of registeredSources.entries()) {
    if (!`${source.name} ${sourceDescription(source)}`.toLowerCase().includes(query)) continue;
    const row = element('tr', '');
    row.append(element('td', source.name), element('td', sourceDescription(source)));
    const controls = element('td', '', 'action-list-controls');
    for (const [caption, handler] of [
      ['View', () => handleViewConfiguration('source-view', source.name, [['Type', source.type === 'ssh' ? 'Remote File (SSH)' : 'Local File'], ['Name', source.name], ['Path / pattern', source.path]])],
      ['Edit', () => handleEditSource(index)],
      ['Delete', () => { registeredSources.splice(index, 1); handleCloseConfiguration('source-view'); renderSources(); $('source-message').textContent = 'Deletion pending. Save changes to apply.'; }],
    ]) {
      const button = element('button', caption, 'quiet'); button.type = 'button';
      button.disabled = !sourcesLoaded || savingSources || (caption !== 'View' && editingSource !== null);
      button.onclick = handler; controls.append(button);
    }
    row.append(controls); table.append(row);
  }
  $('source-registry').replaceChildren(); $('source-registry').append(table);
  $('add-registered-source').disabled = !sourcesLoaded || savingSources || editingSource !== null;
}
function handleEditSource(index) {
  handleCloseConfiguration('source-view'); editingSource = index;
  const source = registeredSources[index] || { name: '', type: 'local', path: '', port: 22 };
  const form = element('div', '', 'action-registration'); sourceFields = {};
  for (const [key, caption] of [['type', 'Type'], ['name', 'Name'], ['path', 'File path / pattern']]) {
    const label = element('label', caption);
    const input = element(key === 'type' ? 'select' : 'input', '');
    if (key === 'type') { input.append(new Option('Local File', 'local'), new Option('Remote File (SSH)', 'ssh')); }
    else input.type = 'text';
    input.value = String(source[key] ?? (key === 'port' ? 22 : '')); input.setAttribute('aria-label', caption);
    label.append(input); form.append(label); sourceFields[key] = input;
    if (!['name', 'type', 'path'].includes(key)) label.className = 'ssh-source-field';
  }
  const updateFields = () => {
    for (const label of form.children) if (label.className === 'ssh-source-field') label.hidden = sourceFields.type.value !== 'ssh';
  };
  sourceFields.type.onchange = updateFields; updateFields();
  form.append(element('p', 'Remote File defines a common path or pattern. Select one or more SSH Hosts per Source in Tasks. Approve host fingerprints in Settings → SSH Hosts.', 'caption'));
  $('source-editor').replaceChildren(); $('source-editor').append(form);
  $('source-editor').hidden = false; $('cancel-source').hidden = false; renderSources();
}
function handleCloseSource() {
  editingSource = null; sourceFields = {}; $('source-editor').replaceChildren();
  $('source-editor').hidden = true; $('cancel-source').hidden = true; renderSources();
}
$('source-search').oninput = renderSources;
$('add-registered-source').onclick = () => handleEditSource(registeredSources.length);
$('cancel-source').onclick = handleCloseSource;
$('save-sources').onclick = async () => {
  if (!sourcesLoaded) { $('source-message').textContent = 'Load Sources before saving.'; return; }
  savingSources = true; $('save-sources').disabled = true; renderSources();
  for (const input of Object.values(sourceFields)) input.disabled = true;
  try {
    const values = registeredSources.map(source => ({ ...source }));
    if (editingSource !== null) {
      const fields = Object.fromEntries(Object.entries(sourceFields).map(([key, input]) => [key, key === 'port' ? Number(input.value) : input.value]));
      values[editingSource] = { ...values[editingSource], ...fields };
    }
    const response = await fetch('/api/sources', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(values) });
    const data = await response.json(); if (!response.ok) throw new Error(data.error);
    registeredSources = data.sources; handleCloseConfiguration('source-view'); handleCloseSource();
    if (!busy) updateSourceSettings(sourceRows.map(row => row.path));
    $('source-message').textContent = 'Sources saved. Changes apply to new runs. Select replacements for deleted sources in Tasks.';
  } catch (error) { $('source-message').textContent = error.message; }
  finally { savingSources = false; $('save-sources').disabled = false; for (const input of Object.values(sourceFields)) input.disabled = false; renderSources(); }
};
function compareNames(left, right) {
  return left.name.localeCompare(right.name, 'ko', {numeric:true, sensitivity:'base'});
}
function selectionInput(items, value, caption, placeholder) {
  const input = element('select', ''); input.disabled = false;
  input.setAttribute('aria-label', caption);
  if (placeholder) input.append(new Option(placeholder, ''));
  for (const item of [...items].sort(compareNames)) {
    const option = new Option(item.name, item.name);
    option.title = item.label || item.name;
    input.append(option);
  }
  if (value && !items.some(item => item.name === value)) {
    input.append(new Option(`Unavailable: ${value}`, value));
  }
  input.value = value;
  return input;
}
let sourceRows = [];
let runSourcePatterns = [];
let runHosts = [];
function profileSelect(value) {
  const select = element('select', '');
  for (const [key, label] of Object.entries(profileLabels)) select.append(new Option(label, key));
  select.value = profileLabels[value] ? value : '';
  return select;
}
function hostPicker(source, save) {
  const picker=element('details','','host-picker');
  const summary=element('summary','');
  const search=element('input','');search.type='search';search.placeholder='Search SSH Hosts…';search.setAttribute('aria-label','Search target SSH Hosts');
  const tools=element('div','','host-picker-tools');
  const select=element('button','Select all shown','quiet');select.type='button';
  const clear=element('button','Clear','quiet');clear.type='button';tools.append(select,clear);
  const list=element('div','','host-picker-list');
  const update=()=>{
    summary.textContent=`SSH Hosts · ${source.hostIds.length} selected`;
    list.replaceChildren();const query=search.value.toLowerCase();
    const items=[...sshHosts].sort(compareNames);
    for(const id of source.hostIds)if(!items.some(host=>host.id===id))items.push({id,name:`Unavailable: ${id}`,host:''});
    for(const host of items.filter(host=>`${host.name} ${host.host} ${host.username || ''}`.toLowerCase().includes(query))){
      const label=element('label','','host-picker-option');const input=element('input','');input.type='checkbox';input.checked=source.hostIds.includes(host.id);
      input.onchange=()=>{source.hostIds=input.checked?[...new Set([...source.hostIds,host.id])]:source.hostIds.filter(id=>id!==host.id);save();update();};
      label.append(input,element('span',`${host.name}${host.host?` · ${host.host}:${host.port}`:''}`));list.append(label);
    }
    if(!list.children.length)list.append(element('p','No matching SSH Hosts. Register hosts in Settings.','caption'));
  };
  search.oninput=update;
  select.onclick=()=>{const query=search.value.toLowerCase();source.hostIds=[...new Set([...source.hostIds,...sshHosts.filter(host=>`${host.name} ${host.host} ${host.username}`.toLowerCase().includes(query)).map(host=>host.id)])];save();update();};
  clear.onclick=()=>{source.hostIds=[];save();update();};
  picker.append(summary,search,tools,list);picker.refresh=update;update();return picker;
}
function updateSourceSettings(paths = $('file-path').value.split('\n').map(s => s.trim()).filter(Boolean)) {
  $('source-settings').replaceChildren();
  sourceRows = [];
  for (const path of paths) {
    const definitionForDefaults = registeredSources.find(source => source.id === path);
    const preference = sourcePreferences.get(path) || sourcePreferences.get(definitionForDefaults?.path) || { profile: defaultSourceProfiles[sampleSources.find(source => source.id === path)?.path || definitionForDefaults?.path || path] || 'general', chunkEvents: 1 };
    const row = element('div', '', 'source-setting');
    const definition = [...registeredSources, ...sourceSnapshots].find(source => source.id === path || (source.type === 'local' && source.path === path));
    const name = selectionInput(registeredSources.map(source => ({ name: source.name, label: sourceDescription(source) })), definition?.name || '', 'Registered source', '');
    name.className = 'source-path-input';
    const pathLabel = element('label', 'Source ', 'source-path');
    const selectedPath = element('span', definition?.path ? `Path: ${definition.path}` : '', 'source-selected-path');
    selectedPath.hidden = !definition?.path;
    selectedPath.setAttribute('aria-live', 'polite');
    pathLabel.append(name, selectedPath);
    const profile = profileSelect(preference.profile);
    profile.disabled = false;
    profile.setAttribute('aria-label', `Decision profile for ${path}`);
    const size = element('input', '');
    size.disabled = false;
    size.type = 'number'; size.min = '1'; size.step = '1'; size.value = String(preference.chunkEvents);
    size.setAttribute('aria-label', `Events per chunk for ${path}`);
    const label = element('label', 'Events/chunk ');
    label.append(size);
    const criteriaLabel = element('label', 'Criteria ', 'criteria-label');
    criteriaLabel.append(profile);
    const action = selectionInput(registeredActions.filter(item => item.name), preference.action || '', `Action for ${path}`, 'None');
    const actionLabel = element('label', 'Action '); actionLabel.append(action);
    const remove = element('button', 'Remove', 'quiet source-remove');
    remove.type = 'button'; remove.disabled = false;
    row.append(pathLabel, criteriaLabel, label, actionLabel, remove);
    const save = () => {
      sourcePreferences.set(source.path, { profile: profile.value, chunkEvents: Number(size.value), action: action.value, hostIds:[...source.hostIds] });
      try { localStorage.setItem('deciflow-source-preferences', JSON.stringify([...sourcePreferences].map(([path, { profile, chunkEvents }]) => [path, { profile, chunkEvents }]))); } catch { /* Preferences remain available for this page session. */ }
    };
    profile.onchange = save; size.oninput = save; action.onchange = save;
    const source = { path: definition?.id || path, name, profile, size, action, remove, hostIds:[...(preference.hostIds || [])] };
    const hosts = hostPicker(source, save); hosts.hidden=definition?.type!=='ssh';
    row.replaceChildren();row.append(pathLabel,criteriaLabel,label,actionLabel,hosts,remove);
    name.onchange = () => {
      const selected = registeredSources.find(item => item.name === name.value);
      source.path = selected?.id || '';
      selectedPath.textContent = selected?.path ? `Path: ${selected.path}` : '';
      selectedPath.hidden = !selected?.path;
      hosts.hidden=selected?.type!=='ssh';
      if(hosts.hidden)source.hostIds=[];
      hosts.refresh();save();
      $('file-path').value = sourceRows.map(item => item.path).join('\n');
    };
    remove.onclick = () => {
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
  updateSourceSettings([...sourceRows.map(item => item.path), '']);
  sourceRows.at(-1).name.focus?.();
};
$('reset-sources').onclick = () => {
  const available = sampleSources.filter(sample => registeredSources.some(source => source.id === sample.id));
  const defaults = (available.length ? available : registeredSources.slice(0, 1)).map(source => source.id).join('\n');
  for (const path of defaults.split('\n')) sourcePreferences.set(path, { profile: defaultSourceProfiles[sampleSources.find(source => source.id === path)?.path || registeredSources.find(source => source.id === path)?.path] || 'general', chunkEvents: 1, action: '' });
  try { localStorage.setItem('deciflow-source-preferences', JSON.stringify([...sourcePreferences].map(([path, { profile, chunkEvents }]) => [path, { profile, chunkEvents }]))); } catch { /* The current page still uses the reset defaults. */ }
  filePaths[sourceMode] = defaults; $('file-path').value = defaults;
  updateSourceSettings();
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
function resultHostId(result) {
  if(result.hostId)return result.hostId;
  const remote=result.source?.match(/^ssh:\/\/(?:[^@/]+@)?([^/]+)/);
  return remote ? `legacy:${remote[1]}` : 'local';
}
function renderHostFilter() {
  const select=$('host-filter');const selected=select.value || 'all';
  const hosts=new Map(runHosts.map(host=>[host.hostId,{name:`${host.hostName} · ${host.hostAddress}:${host.hostPort}`,count:0}]));
  for(const result of results){
    if(!result)continue;const id=resultHostId(result);
    if(!hosts.has(id))hosts.set(id,{name:result.hostName || (id==='local'?'DeciFlow (Local)':id.replace('legacy:','')),count:0});
    hosts.get(id).count++;
  }
  select.replaceChildren();select.append(new Option('All hosts','all'));
  for(const [id,host] of [...hosts].sort((a,b)=>a[1].name.localeCompare(b[1].name,'ko')))select.append(new Option(`${host.name} (${host.count})`,id));
  select.value=hosts.has(selected)?selected:'all';select.disabled=!hosts.size;
  const status=$('host-status');status.replaceChildren();
  for(const host of runHosts){
    const counts=results.filter(result=>result?.hostId===host.hostId);
    status.append(element('p',`${host.hostName} · Collection: ${host.collectionState || 'pending'} · ${counts.filter(result=>!result.error).length} classified · ${counts.filter(result=>result.error).length} failed${host.error?` · ${host.error}`:''}`,host.collectionState==='failed'?'connection-failed':'caption'));
  }
}
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
function formatDuration(milliseconds) {
  if (milliseconds < 1000) return `${Number(milliseconds.toFixed(1))} ms`;
  if (milliseconds < 60000) return `${Number((milliseconds / 1000).toFixed(1))} sec`;
  const minutes = Math.floor(milliseconds / 60000);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);
  if (days) return `${days} day${days === 1 ? '' : 's'}${hours % 24 ? ` ${hours % 24} hour${hours % 24 === 1 ? '' : 's'}` : ''}`;
  if (hours) return `${hours} hour${hours === 1 ? '' : 's'}${minutes % 60 ? ` ${minutes % 60} min` : ''}`;
  const seconds = Math.floor(milliseconds / 1000) % 60;
  return `${minutes} min${seconds ? ` ${seconds} sec` : ''}`;
}
function render(updateList = true) {
  renderSourceFilter();
  renderHostFilter();
  renderCategoryChart();
  $('summary').replaceChildren();
  const processingMs = results.reduce((sum, result) => sum + result.elapsedMs, 0);
  const averageMs = completed ? processingMs / completed : 0;
  recentCompletions = recentCompletions.filter(time => time > elapsedMs - 5000);
  const throughput = elapsedMs > 0 ? recentCompletions.length * 1000 / Math.min(elapsedMs, 5000) : 0;
  const actionSuccess = results.filter(result => result.actionExecution?.status === 'success').length;
  const actionFailed = results.filter(result => result.actionExecution?.status === 'failed').length;
  const processingPercent = elapsedMs > 0 ? `${(activeProcessingMs / elapsedMs * 100).toFixed(1)}%` : 'N/A';
  for (const [label, value] of [['Success / Failed / Total', `${results.filter(r => !r.error).length} / ${results.filter(r => r.error).length} / ${results.filter(Boolean).length}`], ['Action Success / Failed / Total', `${actionSuccess} / ${actionFailed} / ${actionSuccess + actionFailed}`], ['Needs review', results.filter(needsReview).length], ['Total elapsed time', formatDuration(elapsedMs)], ['Active processing time', `${formatDuration(activeProcessingMs)} (${processingPercent})`], ['Average processing time', formatDuration(averageMs)], ['Throughput', `${throughput.toFixed(1)} chunks/s`]]) {
    const metric = element('div', label, 'metric');
    if (label === 'Success / Failed / Total') metric.title = 'Successfully classified / failed / total completed chunks. Total is success plus failure, not planned requests. Failures include connection errors, timeouts, rejected inputs, and invalid responses. Action failures do not change classification counts.';
    if (label === 'Action Success / Failed / Total') metric.title = 'Completed Action executions: success / failed / total. Unassigned sources and failed decisions do not run Actions. Action failures do not change decision counts.';
    if (label === 'Throughput') metric.title = 'Successfully classified chunks per second over the last 5 seconds, including idle time. Uses elapsed time until 5 seconds; freezes when stopped or completed.';
    if (label === 'Needs review') metric.title = 'Successful classifications only: selected category probability below 70%, top-two probability gap below 10 percentage points, collapsed options, or Other category. Failed requests are excluded.';
    if (label === 'Average processing time') metric.title = 'Mean request duration, including network/server wait and failed requests; excludes waiting for new file lines.';
    if (label === 'Active processing time') metric.title = 'Time with at least one request in flight, counting overlapping requests once. Includes network/server wait, excludes idle time; not CPU utilization.';
    const number = element('strong', label.endsWith('Success / Failed / Total') ? '' : String(value));
    if (label.endsWith('Success / Failed / Total')) {
      String(value).split(' / ').forEach((count, index) => {
        if (index) number.append(element('span', ' / '));
        number.append(element('span', count, ['count-success', 'count-failed', 'count-total'][index]));
      });
    }
    metric.append(number);
    $('summary').append(metric);
  }
  const pendingCount = updatesPaused ? completionOrder.length - pausedOrder.length : 0;
  $('pause-updates').textContent = updatesPaused ? `Resume updates${pendingCount ? ` (${pendingCount} new)` : ''}` : 'Pause updates';
  $('pause-updates').setAttribute('aria-pressed', String(updatesPaused));
  $('pause-updates').disabled = !busy && !completed && !updatesPaused;
  $('export').disabled = !completed || busy || activeJobState === 'running';
  if (updatesPaused && !updateList) return;
  if (!updatesPaused) displayedOrder = completionOrder.slice();
  $('results').replaceChildren();
  const visible = (updatesPaused ? pausedOrder : completionOrder).toReversed().map(index => results[index]).filter(r => {
    const review = $('review-filter').value;
    const category = $('category-filter').value;
    const search = $('log-search').value.toLowerCase();
    const source = $('source-filter').value || 'all';
    return (review === 'all' || (review === 'needs-review' ? needsReview(r) : !r.error && !needsReview(r)))
      && (category === 'all' || (category === 'failed' ? Boolean(r.error) : !r.error && r.category === category))
      && r.log.toLowerCase().includes(search)
      && (source === 'all' || r.sourcePatterns?.includes(source) || r.source === source)
      && (($('host-filter').value || 'all') === 'all' || resultHostId(r) === $('host-filter').value);
  });
  const pages = Math.max(1, Math.ceil(visible.length / 100));
  page = Math.min(page, pages - 1);
  $('page-info').textContent = `Page ${page + 1} of ${pages} · ${visible.length} results`;
  $('previous').disabled = page === 0;
  $('next').disabled = page >= pages - 1;
  for (const result of visible.slice(page * 100, (page + 1) * 100)) {
    const row = element('article', '', 'result');
    const top = element('div', '', result.error ? 'result-top' : 'result-summary');
    if (result.error) {
      top.append(element('span', result.sourceFailure?'Source failed':'Request failed', 'badge error'), element('span', `${result.elapsedMs}ms`));
    } else {
      const decisions = element('div', '', 'decision-grid');
      decisions.setAttribute('role', 'group'); decisions.setAttribute('aria-label', 'Decision results');
      const probability = ((result.answerProbability ?? result.probabilities?.[result.category] ?? 0) * 100).toFixed(1);
      for (const [title, value, detail, badgeClass, probabilities] of [
        ['Category (Choice)', `${result.uncertain ? 'Uncertain · ' : ''}${labels[result.category]}`, `${probability}% category probability`, `${result.category || 'other'}${result.uncertain ? ' uncertain' : ''}`, Object.entries(result.probabilities || {}).map(([key, value]) => [labels[key], value])],
        ['Urgency (Score)', Number.isFinite(result.urgency) ? `${result.urgency.toFixed(2)} / 3` : 'Not available', '0 Low → 3 Critical', 'decision-score', Object.entries(result.urgencyProbabilities || {}).map(([level, probability]) => [`${level} · ${result.urgencyLegend?.[level]?.split(':')[0] || ['Low', 'Medium', 'High', 'Critical'][Number(level)]}`, probability])],
        ['Work ticket (Noul)', Number.isFinite(result.ticketProbability) ? `${(result.ticketProbability * 100).toFixed(1)}%` : 'Not available', 'Yes probability · 0% No → 100% Yes', 'decision-noul', Number.isFinite(result.ticketProbability) ? [['Yes', result.ticketProbability], ['No', 1 - result.ticketProbability]] : []],
      ]) {
        const card = element('section', '', 'decision-card');
        const badge = element('span', value, `badge ${badgeClass}`); badge.title = `${title}: ${value}`;
        card.append(element('span', title, 'decision-label'), badge, element('span', detail, 'decision-detail'));
        if (probabilities.length) {
          const distribution = element('dl', '', 'decision-probabilities');
          distribution.setAttribute('aria-label', `${title} probabilities`);
          for (const [label, probability] of probabilities) {
            const entry = element('div', '');
            entry.append(element('dt', label), element('dd', `${(probability * 100).toFixed(1)}%`));
            distribution.append(entry);
          }
          card.append(distribution);
        }
        decisions.append(card);
      }
      if (result.uncertain) decisions.children[0].title = `Provisional model choice. ${result.candidates?.map(key => `${labels[key]} ${(result.probabilities[key] * 100).toFixed(1)}%`).join(' vs ') || 'Low confidence'}. Not a confirmed incident.`;
      if (result.uncertain) decisions.children[0].append(element('p', `Category (Choice) provisional: ${result.candidates?.map(key => `${labels[key]} ${(result.probabilities[key] * 100).toFixed(1)}%`).join(' vs ') || 'Low confidence'} · ${result.reviewReasons?.map(reason => ({ low_answer_probability: 'category probability below 70%', low_confidence: 'legacy provider confidence below 70%', close_probabilities: 'close category probabilities', collapsed_options: 'option descriptions lost distinction during token rendering', other_category: 'insufficient context / Other' })[reason]).join('; ') || 'review needed'}`, 'uncertainty-note'));
      const metadata = element('div', '', 'result-top');
      metadata.append(element('span', `Processing: ${result.elapsedMs}ms`));
      if (needsReview(result)) metadata.append(element('span', 'Category needs review', 'review'));
      top.append(decisions, metadata);
    }
    row.append(top, element('p', result.log, 'log'));
    if (result.actionExecution) {
      const execution = result.actionExecution;
      row.append(element('p', `Action execution: ${execution.name} · ${execution.status} · ${execution.elapsedMs}ms${execution.exitCode != null ? ` · exit ${execution.exitCode}` : ''}${execution.error ? ` · ${execution.error}` : ''}`, execution.status === 'failed' ? 'error-message' : 'caption'));
    }
    if (result.source) {
      const end = result.lineEnd || result.line;
      const multiple = end !== result.line;
      const realtime = resultSourceMode === 'realtime';
      const location = element('p', `${result.hostName ? `Host: ${result.hostName} (${result.hostAddress}:${result.hostPort}) · ` : ''}Source: ${result.source}${result.sourceFailure ? '' : ` · ${realtime ? 'Observed' : 'File'} ${multiple ? 'lines' : 'line'} ${multiple ? `${result.line}–${end}` : result.line}${result.incomplete ? ' · Incomplete line at rotation' : ''}`}`, 'caption');
      if (realtime) location.title = 'Sequence since monitoring started or the file rotated; not an absolute file line number.';
      row.append(location);
    }
    if (result.profile) {
      const count = result.eventCount || 1;
      row.append(element('p', `Category criteria (Choice): ${profileLabels[result.profile]} · Chunk: ${count} ${count === 1 ? 'event' : 'events'} (max ${result.chunkEvents || 1})`, 'caption'));
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
      const label = element('label', 'Reviewer category (Choice): ', 'reviewer-category');
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
  $('export').disabled = !completed || busy || activeJobState === 'running';
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
$('source-mode').onchange = handleTaskMode;
$('task-trigger').onchange = handleTaskMode;
$('stop').onclick = async () => {
  if (!selectedTaskId) return;
  $('stop').disabled = true;
  try {
    const response = await fetch(`/api/tasks/${selectedTaskId}/stop`, {method:'POST'});
    const data = await response.json(); if (!response.ok) throw new Error(data.error);
    await handleLoadTasks();
  } catch(error) { $('message').textContent=error.message; $('stop').disabled=false; }
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
      $('stop').disabled = true;
      try { jobStorage.removeItem('deciflow-job-id'); } catch { /* Storage may be disabled. */ }
      $('message').textContent = 'Previous job is unavailable. The server may have restarted.';
      return;
    }
    if (!response.ok) throw new Error((await response.json()).error);
    const job = await response.json();
    if (job.settings.taskId) selectedTaskId = job.settings.taskId;
    renderTaskMonitor();
    await handleWatchRun(job);
  } finally { restoringJob = false; }
}
async function handleProcessing(job) {
  if (busy) return;
  const sources = job.settings.sources || [];
  $('result-context').textContent=`${job.settings.taskName || registeredTasks.find(task=>task.id===job.settings.taskId)?.name || 'Task execution'} · Started: ${taskTime(job.startedAt)} (UTC) · Run: ${job.jobId}`;
  sourceMode = job.settings.mode;
  busy = true;
  renderTaskMonitor();
  activeRequest = new AbortController();
  $('export').disabled = true;
  $('stop').disabled = false;
  $('message').className = '';
  $('message').textContent = `${engineLabel} is classifying your data…`;
  let started = false;
  try {
    activeJobId = job.jobId; activeJobState = job.state; rememberJob(activeJobId);
    const response = await fetch(`/api/jobs/${activeJobId}/events`, { method: 'POST', signal: activeRequest.signal });
    if (!response.ok) throw new Error((await response.json()).error);
    await readEvents(response.body, event => {
      if (event.activeProcessingMs !== undefined) activeProcessingMs = event.activeProcessingMs;
      if (event.elapsedMs !== undefined) elapsedMs = event.elapsedMs;
      if (event.type === 'start') {
        started = true;
        resultEngine = event.engine;
        resultSourceMode = event.mode || sourceMode;
        runSourcePatterns = [...new Set(event.sourcePatterns || sources.map(source => source.path || registeredSources.find(item => item.id === source.sourceId)?.path || source.sourceId))];
        $('source-filter').value = 'all';
        $('host-filter').value='all';runHosts=event.hosts || sources.filter(source=>source.hostId).map(source=>({hostId:source.hostId,hostName:source.hostName,hostAddress:source.host,hostPort:source.port,collectionState:'pending'}));
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
      } else if (event.type === 'host-status') {
        runHosts=event.hosts;renderHostFilter();
      } else if (event.type === 'result') {
        results[event.index] = event.result;
        completionOrder.push(event.index);
        completed++;
        if (event.result.engineConnection) handleEngineConnection(event.result.engineConnection);
        else if (!event.result.error) handleEngineConnection('connected');
        if (!event.result.error) recentCompletions.push(event.elapsedMs);
        elapsedMs = event.elapsedMs;
      } else if (event.type === 'done') {
        elapsedMs = event.elapsedMs;
        activeJobState = event.state || 'completed';
      } else if (event.type === 'error') {
        activeJobState = job.state === 'skipped' ? 'skipped' : 'failed';
        throw new Error(event.error);
      }
      $('message').textContent = total === null ? `${sourceMode === 'realtime' ? 'Realtime' : 'Batch'} · ${completed.toLocaleString('en-US')} chunks completed${completed ? '' : ' · Waiting for data…'}` : `Classifying · ${completed.toLocaleString('en-US')} / ${total.toLocaleString('en-US')} chunks · ${total.toLocaleString('en-US')} ${engineLabel} requests planned`;
      scheduleRender();
    });
    $('message').textContent = `${activeJobState === 'stopped' ? 'Stopped' : activeJobState === 'failed' ? 'Failed' : 'Completed'} · ${results.filter(r => r.error).length} failed requests · ${results.filter(r => r.actionExecution?.status === 'failed').length} failed Actions`;
  } catch (error) {
    $('message').className = error.name === 'AbortError' ? '' : 'error-message';
    $('message').textContent = `${error.name === 'AbortError' ? 'Processing stopped' : error.message} · ${started ? `${completed} completed results have been retained.` : 'Previous results have been retained.'}`;
  } finally {
    busy = false;
    activeRequest.abort();
    activeRequest = undefined;
    $('stop').disabled = activeJobState !== 'running';
    clearTimeout(renderTimer);
    renderTimer = undefined;
    if (started || completed) render(false);
    $('export').disabled = !completed || activeJobState === 'running';
    handleLoadTasks();
    if (activeJobState === 'running') {
      $('message').textContent += ' · Server job continues. Click its Task in the running list to reconnect.';
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
$('host-filter').onchange = handleResultFilter;
$('previous').onclick = () => { page--; render(); };
$('next').onclick = () => { page++; render(); };
$('export').onclick = () => {
  if (!completed || busy || activeJobState === 'running') return;
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
}).then(async data => {
  $('host-name').textContent = data.host.hostname;
  $('host-os').textContent = data.host.os;
  $('host-addresses').textContent = data.host.addresses.join('\n') || 'IP unavailable';
  if (data.profiles) {
    for (const key of Object.keys(profileLabels)) delete profileLabels[key];
    Object.assign(profileLabels, data.profiles);
  }
  engine = data.engine;
  engineLabel = engine === 'laya' ? 'Laya' : 'Jev';
  $('status').textContent = 'Decision Engine: ';
  $('status').append(element('strong', engineLabel, 'selected-engine'));
  engineConnectionNode = element('strong', '');
  engineConnectionNode.setAttribute('role', 'status');
  $('status').append(engineConnectionNode);
  handleEngineConnection(engineConnection);
  $('status').append(element('span', ' · Model: '));
  $('status').append(element('strong', data.model, 'selected-model'));
  if (!data.configured) $('status').append(element('span', ' · API key required'));
  $('powered-by').textContent = `Powered by ${engineLabel}`;
  renderTaskMonitor();
  $('data-notice').textContent = engine === 'laya' ? 'Classification sends data to your configured Laya server. Laya inference has no Jev API usage fees. Remove passwords, tokens, and sensitive data before sending data to a remote server.' : 'Classification sends your data to the TypeSafe API and may incur usage charges. Remove passwords, tokens, and sensitive data first.';
  const limits = data.limits;
  $('input-limits').textContent = engine === 'laya' ? `Three decisions per chunk · Laya ${data.model} · ${limits.context_tokens.toLocaleString('en-US')} tokens including each question. Truncated predictions are discarded and original events retained for review.` : `Three decisions per chunk · ${data.model}: ${limits.context_tokens.toLocaleString('en-US')} tokens for state + questions · Local preflight budget: ${limits.max_jev_input_bytes.toLocaleString('en-US')} bytes per Jev request (not a token count). Oversized events are retained for review.`;
  await sourceLoadPromise;
  handleRestoreJob().then(()=>{monitoringReady=true;handleLoadTasks();}).catch(error => { $('message').className = 'error-message'; $('message').textContent = error.message; });
}).catch(error => { $('status').textContent = error.message || 'Server connection failed'; });

function handleRoute() {
  const hash = globalThis.location?.hash;
  const section = hash === '#settings/ssh-keys' ? 'ssh-keys' : hash === '#settings/ssh-hosts' ? 'ssh-hosts' : null;
  const view = hash === '#tasks' ? 'tasks' : hash === '#settings' || section ? 'settings' : hash === '#sources' ? 'sources' : hash === '#criteria' ? 'criteria' : hash === '#actions' ? 'actions' : 'main';
  if (view === currentView && section === currentSettingsSection) return;
  if (view === 'criteria') return $('nav-criteria').onclick();
  handleMenuNavigation(view, section);
}
if (globalThis.location) {
  globalThis.addEventListener('hashchange', handleRoute);
  handleRoute();
}

async function handleLoadSources() {
  $('source-message').textContent = 'Loading sources…';
  try {
    const response = await fetch('/api/sources', { method: 'POST' });
    const data = await response.json(); if (!response.ok) throw new Error(data.error);
    const initial = !sourcesLoaded;
    registeredSources = data.sources; sourcesLoaded = true;
    if (initial && !busy && !sourceSnapshots.length) {
      for (const mode of ['batch', 'realtime']) {
        const keys = filePaths[mode].split('\n').filter(key => registeredSources.some(source => source.id === key));
        filePaths[mode] = (keys.length ? keys : registeredSources.slice(0, 1).map(source => source.id)).join('\n');
      }
      $('file-path').value = filePaths.batch;
    }
    renderSources(); $('save-sources').disabled = false; $('source-message').textContent = '';
    if (!busy && !restoringJob) updateSourceSettings();
  } catch (error) { $('source-message').textContent = error.message; }
}
renderSources();
const sourceLoadPromise = handleLoadSources();

handleLoadTasks();
if (globalThis.setInterval) globalThis.setInterval(() => { if (!document.hidden) handleLoadTasks(); }, 5000);
