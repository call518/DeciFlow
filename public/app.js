import { readEvents } from './stream.js';

const $ = id => document.getElementById(id);
function handleMessage(id,text,isError=false) {
  const node=$(id);
  node.className=(node.className || '').replace(/\berror-message\b/g,'').trim();
  if(isError)node.className+=`${node.className?' ':''}error-message`;
  node.textContent=text;
}
const labels = { normal: 'Normal', warning: 'Warning', error: 'Error', security: 'Security', other: 'Other' };

let deleteConfirmationQueue = Promise.resolve();
function handleConfirmDelete(kind, name, description, identity=name) {
  const confirmation = deleteConfirmationQueue.then(async () => {
    let references=[], failure='';
    try {
      const response=await fetch('/api/delete-check',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,id:identity})});
      const data=await response.json();if(!response.ok)throw new Error(data.error);
      if(!Array.isArray(data.references))throw new Error('Invalid dependency response.');
      references=data.references;
    }catch(error){failure=`Could not verify dependencies. ${error.message}`;}
    return new Promise(resolve => {
      const dialog=$('delete-dialog');const blocked=Boolean(failure || references.length);
      $('delete-title').textContent=blocked ? `Cannot Delete ${kind}` : `Delete ${kind}?`;
      $('delete-name').textContent=name;
      $('delete-description').textContent=failure || (blocked ? 'This item is in use. Remove these references before deleting it.' : description);
      $('delete-references').replaceChildren(...references.slice(0,5).map(reference=>element('li',reference)));
      if(references.length>5)$('delete-references').append(element('li',`And ${references.length-5} more references.`));
      $('delete-references').hidden=!references.length;
      $('delete-approve').hidden=blocked;$('delete-cancel').textContent=blocked?'Close':'Cancel';
      dialog.returnValue='cancel';
      dialog.onclose=()=>resolve(!blocked && dialog.returnValue==='delete');
      dialog.showModal();
    });
  });
  deleteConfirmationQueue=confirmation.catch(()=>false);
  return confirmation;
}

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
let pagedView = null;
let resultsPerPage = 50;
const resultCursors = new WeakMap();
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
let displayedCount = 0;
let resultStatistics;
let statisticsCursor = 0;
let statisticsResults;
let filteredResults;
let renderedRows = new Map();
let renderedPage = [];
let renderedHosts;
let renderedCount = -1;
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
const inlineViews = new Map();
function handleParkInlineView(id) {
  const state=inlineViews.get(id);if(!state)return;
  state.home?.append($(id));state.detail?.remove();state.detail=null;$(id).hidden=true;
}
function handleCloseInlineView(id) {
  inlineViews.get(id)?.button?.setAttribute('aria-expanded','false');
  handleParkInlineView(id);inlineViews.delete(id);
}
function handleMountInlineView(parent,row,id) {
  const state=inlineViews.get(id);const view=$(id);const detail=element('tr','','inline-view-row');
  const cell=element('td','','inline-view-cell');cell.colSpan=row.children.length;
  cell.append(view);detail.append(cell);parent.insertBefore(detail,row.nextSibling);
  state.detail=detail;view.hidden=false;
}
function handleAppendViewRow(parent,row,id,key) {
  parent.append(row);
  const button=Array.from(row.children[row.children.length-1].children).find(item=>item.textContent==='View');
  if(button){
    const show=button.onclick;
    button.setAttribute('aria-expanded',String(inlineViews.get(id)?.key===key));
    button.onclick=()=>{
      const same=inlineViews.get(id)?.key===key;
      const close=()=>{
        if(id==='ssh-host-view')handleCloseHost();
        else if(id==='ssh-key-view')handleCloseKey();
        else if(id==='task-view')handleCloseTask();
        else handleCloseConfiguration(id);
      };
      close();
      if(same){button.setAttribute('aria-expanded','false');return;}
      const home=$(id).parentNode;show();
      inlineViews.set(id,{key,home,detail:null,button});
      handleMountInlineView(parent,row,id);button.setAttribute('aria-expanded','true');
    };
  }
  if(inlineViews.get(id)?.key===key){inlineViews.get(id).button=button;handleMountInlineView(parent,row,id);}
}

function handleCloseConfiguration(id) {
  handleCloseInlineView(id);
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
    if (editingCriteria !== null) handleValidateCriteria(false);
  }
}
function highlightPython(target, source) {
  if(!globalThis.Prism?.languages.python){target.textContent=source;return;}
  const tokenText=value=>typeof value==='string'?value:Array.isArray(value)?value.map(tokenText).join(''):tokenText(value.content);
  const renderToken=token=>{
    if(typeof token==='string')return element('span',token);
    const aliases=token.alias ? [].concat(token.alias) : [];
    const node=element('span',tokenText(token),['token',token.type,...aliases].join(' '));
    if(typeof token.content!=='string')node.replaceChildren(...[].concat(token.content).map(renderToken));
    return node;
  };
  target.replaceChildren(...Prism.tokenize(source,Prism.languages.python).map(renderToken));
}
function handlePythonEditor(input,label) {
  label.className+=' python-editor';input.wrap='off';
  const backdrop=element('pre','','python-highlight');backdrop.setAttribute('aria-hidden','true');
  const code=element('code','');backdrop.append(code);label.append(backdrop);
  input.oninput=()=>highlightPython(code,input.value);
  input.onscroll=()=>{code.style.transform=`translate(${-input.scrollLeft}px, ${-input.scrollTop}px)`;};
  input.oninput();
}

function detailFields(fields) {
  const list=element('dl','','view-details');
  for(const [caption,value] of fields){
    if(value===undefined)continue;
    const text=Array.isArray(value)?value.join(', '):String(value);
    const block=['Python Code','Public Key','Decision Instructions','Normalization'].includes(caption);
    const field=element('div','',block || text.length>120 || text.includes('\n')?'view-field-wide':'');
    const valueClass=caption==='Python Code'?'view-value-code':caption==='Public Key'?'view-value-key':'';
    const valueNode=element('dd',text,valueClass);
    if(caption==='Python Code')highlightPython(valueNode,text);
    field.append(element('dt',caption),valueNode);list.append(field);
  }
  return list;
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
  const row = detailFields(fields);
  if(id==='criteria-view')row.className+=' criteria-details';
  const header = element('div', '', 'card-title');
  header.append(element('h3', title));
  container.replaceChildren(); container.append(header, row);
  container.hidden = false;
}
let sshKeys = [];
function handleCloseKey() {
  editingSSHKey = null;
  $('ssh-key-material').hidden = false;
  $('ssh-key-file').required = true;
  handleCloseInlineView('ssh-key-view');
  $('ssh-key-registry').hidden = false; $('ssh-key-view').hidden = true;
  $('ssh-key-editor').hidden = true;
  $('ssh-key-name').value = ''; $('ssh-key-file').value = ''; $('ssh-key-paste').value = '';
  pastedPrivateKey = '';
}
function handleAddKey(key = null) {
  handleCloseKey();
  editingSSHKey = key?.id || null;
  $('ssh-key-name').value = key?.name || '';
  $('add-ssh-key-title').textContent = key ? 'Edit SSH Key' : 'Add SSH Key';
  $('add-ssh-key').textContent = key ? 'Save Changes' : 'Add Key';
  $('ssh-key-material').hidden = Boolean(key);
  if (key) for (const id of ['ssh-key-file','ssh-key-path','ssh-key-paste']) $(id).required = false;
  $('ssh-key-registry').hidden = true; $('ssh-key-editor').hidden = false;
  handleMessage('ssh-key-message','');
}
function handleViewKey(key) {
  handleCloseKey();
  const view = $('ssh-key-view'); view.replaceChildren();
  const header = element('div', '', 'card-title');
  header.append(element('h3', key.name)); view.append(header);
  const card = detailFields([['Private Key Path', key.privatePath], ['Public Key Path', key.publicPath], ['Public Key', key.publicKey], ['Private Key', '****']]);
  view.append(card); view.hidden = false;
}
function renderSSHKeys() {
  handleParkInlineView('ssh-key-view');
  const list = $('ssh-key-list'); list.replaceChildren();
  const table = element('table', '', 'action-list');
  const header = element('tr', '');
  for (const title of ['Name', 'Private Key Path', 'Manage']) header.append(element('th', title));
  const head = element('thead', ''); head.append(header); table.append(head);
  const body = element('tbody', ''); const query = $('ssh-key-search').value.toLowerCase();
  for (const key of sshKeys.filter(key => key.name.toLowerCase().includes(query))) {
    const row = element('tr', ''); row.append(element('td', key.name), element('td', key.privatePath));
    const controls = element('td', '', 'action-list-controls');
    for (const [caption, handler] of [['View', () => handleViewKey(key)], ['Edit', () => handleAddKey(key)], ['Delete', () => handleDeleteKey(key)]]) {
      const button = element('button', caption, 'quiet'); button.type = 'button'; button.onclick = handler; controls.append(button);
    }
    row.append(controls); handleAppendViewRow(body,row,'ssh-key-view',key.id);
  }
  table.append(body); list.append(table);
  if (!body.children.length) list.append(element('p', 'No matching SSH Keys.', 'caption'));
}
$('open-add-ssh-key').onclick = () => handleAddKey();
$('cancel-ssh-key').onclick = handleCloseKey;
$('ssh-key-search').oninput = renderSSHKeys;
async function handleKeyResponse(response) {
  if (response.status === 404 || response.status === 405) {
    throw new Error('SSH Key API is unavailable. Restart the DeciFlow UI server or container to load the updated backend.');
  }
  let data;
  try { data = await response.json(); }
  catch { throw new Error(`SSH Key API returned an invalid response (HTTP ${response.status}). Check the DeciFlow server.`); }
  if (!response.ok) throw new Error(data.error || 'Could not manage SSH Keys.');
  return data;
}
async function handleLoadKeys() {
  try {
    const response = await fetch('/api/ssh-keys', { method: 'POST' });
    const data = await handleKeyResponse(response);
    sshKeys = data.keys; renderSSHKeys();
  } catch (error) { handleMessage('ssh-key-message',error.message,true); }
}
let editingSSHKey = null;
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
  const body = { name: $('ssh-key-name').value.trim(), ...(editingSSHKey ? {id:editingSSHKey} : {inputMethod: method}) };
  const editing = Boolean(editingSSHKey);
  $('add-ssh-key').disabled = true;
  handleMessage('ssh-key-message',editing ? 'Saving SSH Key…' : 'Adding SSH Key…');
  try {
    if (!/^[A-Za-z0-9_ -]{1,64}$/.test(body.name)) throw new Error('Enter a name of 1–64 letters, digits, spaces, underscores, or hyphens.');
    if (!editing && method === 'path') {
      body.privateKeyPath = $('ssh-key-path').value.trim();
      if (!body.privateKeyPath) throw new Error('Enter a private key file path.');
    } else if (!editing && method === 'upload') {
      const file = $('ssh-key-file').files?.[0];
      if (!file || file.size > 65536) throw new Error('Select a private key file of at most 64 KiB.');
      body.privateKey = await file.text();
    } else if (!editing) {
      if (!pastedPrivateKey || pastedPrivateKey.length > 65536) throw new Error('Paste a private key of at most 64 KiB.');
      body.privateKey = pastedPrivateKey;
    }
    const response = await fetch('/api/ssh-keys', { method: editing ? 'PATCH' : 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await handleKeyResponse(response);
    sshKeys = data.keys; renderSSHKeys();
    handleCloseKey();
    handleMessage('ssh-key-message',editing ? 'SSH Key renamed.' : 'SSH Key added.');
    renderSSHHosts();
  } catch (error) { handleMessage('ssh-key-message',error.message,true); }
  finally {
    pastedPrivateKey = ''; $('ssh-key-paste').value = ''; $('ssh-key-file').value = '';
    $('add-ssh-key').disabled = false;
  }
};
async function handleDeleteKey(key) {
  if (!await handleConfirmDelete('SSH Key', key.name, 'Both private and public key files will be permanently deleted. This cannot be undone.', key.id)) return;
  try {
    const response = await fetch('/api/ssh-keys', { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: key.id }) });
    const data = await handleKeyResponse(response);
    sshKeys = data.keys; renderSSHKeys(); handleMessage('ssh-key-message','SSH Key deleted.');
  } catch (error) { handleMessage('ssh-key-message',error.message,true); }
}
let sshHosts = [];
let editingSSHHost = null;
const sshHostChecks = new Map();
function hostConnectionKey(host) {
  return JSON.stringify([host.host,host.port,host.username,host.keyId || host.keyPath]);
}
function hostDraft() {
  return {...(editingSSHHost ? {id:editingSSHHost} : {}),name:$('ssh-host-name').value,host:$('ssh-host-address').value,port:Number($('ssh-host-port').value),username:$('ssh-host-user').value,keyId:$('ssh-host-key').value};
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
const autoCheckedHosts = new Set();
function hostChecksVisible() {
  return currentView === 'settings' && !document.hidden && !$('settings-ssh-hosts').hidden && !$('ssh-host-registry').hidden;
}
function handleScheduleHostChecks() {
  clearTimeout(hostCheckTimer);
  if (hostChecksVisible() && sshHosts.some(host=>!autoCheckedHosts.has(hostConnectionKey(host)))) hostCheckTimer = setTimeout(handleAutoCheckHosts, 0);
}
async function handleAutoCheckHosts() {
  if (hostChecksRunning || !hostChecksVisible()) return;
  hostChecksRunning = true;
  clearTimeout(hostCheckTimer);
  try {
    for (const host of [...sshHosts].sort(compareNames)) {
      if (!hostChecksVisible() || $('ssh-trust-dialog').open) break;
      if (!sshHosts.some(item => item.id === host.id && hostConnectionKey(item) === hostConnectionKey(host))) continue;
      const key=hostConnectionKey(host);if(autoCheckedHosts.has(key))continue;
      autoCheckedHosts.add(key);await handleTestHost(host, true);
    }
  } finally {
    hostChecksRunning = false;

  }
}
document.addEventListener?.('visibilitychange', handleScheduleHostChecks);
$('test-ssh-host').onclick=()=>handleTestHost();
$('ssh-host-form').oninput=()=>{$('ssh-host-test-result').textContent='';};
function handleCloseHost() {
  handleCloseInlineView('ssh-host-view');
  editingSSHHost = null; $('ssh-host-registry').hidden = false;
  $('ssh-host-editor').hidden = true; $('ssh-host-view').hidden = true;
  handleScheduleHostChecks();
}
function renderSSHHosts() {
  handleParkInlineView('ssh-host-view');
  const list = $('ssh-host-list'); list.replaceChildren();
  const table = element('table', '', 'action-list'); const header = element('tr', '');
  for (const title of ['Name', 'Connection', 'SSH Key', 'Status', 'Manage']) header.append(element('th', title));
  const head = element('thead', ''); head.append(header); table.append(head);
  const body = element('tbody', ''); const query = $('ssh-host-search').value.toLowerCase();
  for (const host of sshHosts.filter(host => `${host.name} ${host.host} ${host.username}`.toLowerCase().includes(query))) {
    const row = element('tr', '');
    row.append(element('td', host.name), element('td', `${host.username}@${host.host}:${host.port}`), element('td', sshKeys.find(key => key.id === host.keyId)?.name || host.keyPath));
    const controls = element('td', '', 'action-list-controls');
    for (const [caption, handler] of [['View', () => handleViewHost(host)], ['Edit', () => handleEditHost(host)], ['Delete', () => handleDeleteHost(host)]]) {
      const button = element('button', caption, 'quiet'); button.type = 'button'; button.onclick = handler; controls.append(button);
    }
    const check=sshHostChecks.get(hostConnectionKey(host));
    const test=element('button', 'Test Connection', 'quiet'); test.type='button';test.disabled=Boolean(check?.checking);test.onclick=()=>handleTestHost(host);controls.append(test);
    row.append(element('td',connectionStatus(check),check?.connected?'connection-ok':check && !check.checking?'connection-failed':''),controls); handleAppendViewRow(body,row,'ssh-host-view',host.id);
  }
  table.append(body); list.append(table);
  if (!body.children.length) list.append(element('p', 'No matching SSH Hosts.', 'caption'));
}
async function handleLoadHosts() {
  try {
    const response = await fetch('/api/ssh-hosts', { method: 'POST' });
    if (response.status === 404 || response.status === 405) throw new Error('SSH Host API is unavailable. Restart the DeciFlow UI server or container.');
    const data = await response.json(); if (!response.ok) throw new Error(data.error);
    sshHosts = data.hosts; renderSSHHosts(); renderTaskMonitor();
    handleScheduleHostChecks();
  } catch (error) { handleMessage('ssh-host-message',error.message,true); }
}
function handleEditHost(host = null) {
  handleCloseHost(); editingSSHHost = host?.id || null;
  $('ssh-host-registry').hidden = true; $('ssh-host-editor').hidden = false;
  $('ssh-host-editor-title').textContent = host ? 'Edit SSH Host' : 'Add SSH Host';
  for (const [id, value] of [['ssh-host-name', host?.name || ''], ['ssh-host-address', host?.host || ''], ['ssh-host-port', host?.port || 22], ['ssh-host-user', host?.username || '']]) $(id).value = String(value);
  const keys = $('ssh-host-key'); keys.replaceChildren();
  for (const key of sshKeys) keys.append(new Option(key.name, key.id));
  if (host?.keyId && !sshKeys.some(key => key.id === host.keyId)) keys.append(new Option('Unavailable Key', host.keyId));
  keys.value = host?.keyId || ''; handleMessage('ssh-host-message','');
  $('ssh-host-test-result').textContent='';
}
function handleViewHost(host) {
  handleCloseHost();
  const view = $('ssh-host-view'); view.replaceChildren();
  const header = element('div', '', 'card-title');
  header.append(element('h3', host.name)); view.append(header);
  const fields = detailFields([['Host', host.host], ['Port', host.port], ['SSH User', host.username], ['SSH Key Path', host.keyPath || sshKeys.find(key=>key.id===host.keyId)?.privatePath || 'Unavailable']]);
  fields.className += ' ssh-host-details';
  fields.children[3].className='view-field-wide';
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
    handleMessage('ssh-host-message','SSH Host saved. Changes apply to new runs.');
  } catch (error) { handleMessage('ssh-host-message',error.message,true); }
  finally { $('save-ssh-host').disabled = false; }
};
async function handleDeleteHost(host) {
  if (!await handleConfirmDelete('SSH Host', host.name, 'This saved connection will be deleted.', host.id)) return;
  try {
    const response = await fetch('/api/ssh-hosts', {method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:host.id})});
    const data = await response.json(); if (!response.ok) throw new Error(data.error);
    sshHosts = data.hosts; renderSSHHosts(); handleMessage('ssh-host-message','SSH Host deleted.');
  } catch (error) { handleMessage('ssh-host-message',error.message,true); }
}
let registeredTasks = [];
let selectedTaskId = '';
let editingTask = null;
let monitoringPromise = Promise.resolve();
let monitorSelection = 0;
let followLatestTask = true;
let monitoringReady = false;

function taskExecution(task) {
  return task.mode === 'realtime' ? `Realtime${task.resumeOnRestart ? ' · resume on restart' : ''}` : task.cron ? `Batch · ${task.cron} · ${task.timezone}` : 'Batch · Manual';
}
function taskTime(value, timezone = 'UTC') {
  return value ? new Date(value).toLocaleString('en-GB', {timeZone:timezone,hour12:false}) : '—';
}
let taskTooltipTimer=null;
function handleHideTaskTooltip() {
  clearTimeout(taskTooltipTimer);
  taskTooltipTimer=setTimeout(()=>{$('task-monitor-tooltip').hidden=true;},150);
}
function handleShowTaskTooltip(button,task,definitions,mode,state) {
  clearTimeout(taskTooltipTimer);
  const tooltip=$('task-monitor-tooltip');
  tooltip.taskId=task.id;
  tooltip.replaceChildren(element('strong',task.name));
  tooltip.append(element('div',`${task.enabled===false?'Disabled':'Enabled'} · ${state} · Mode: ${mode}`));
  for(const source of definitions){
    const section=element('div','','monitor-tooltip-source');
    section.textContent=`Source: ${source.name}\nFile Path / Pattern: ${source.path || 'Unavailable'}\nType: ${source.type}\nCriteria: ${source.profile} · Events/Chunk: ${source.chunkEvents}\nAction: ${source.action}\nSource Hosts (${source.hosts.length}):\n${source.hosts.map(host=>host.label).join('\n') || 'None'}`;
    tooltip.append(section);
  }
  tooltip.hidden=false;
  const rect=button.getBoundingClientRect();
  const width=Math.min(420,(globalThis.innerWidth || 1024)-24);
  const left=Math.max(12,Math.min(rect.left,(globalThis.innerWidth || 1024)-width-12));
  tooltip.setAttribute('style',`width:${width}px;left:${left}px;top:12px`);
  const height=tooltip.getBoundingClientRect?.().height || 200;
  const top=rect.bottom+8+height<(globalThis.innerHeight || 768)?rect.bottom+8:Math.max(12,rect.top-height-8);
  tooltip.setAttribute('style',`width:${width}px;left:${left}px;top:${top}px`);
}
$('task-monitor-tooltip').onmouseenter=()=>clearTimeout(taskTooltipTimer);
$('task-monitor-tooltip').onmouseleave=handleHideTaskTooltip;
function renderTaskMonitor() {
  const list=$('running-tasks'); list.replaceChildren();
  const tasks=[...registeredTasks].sort((a,b)=>Number(Boolean(b.activeRun || b.starting))-Number(Boolean(a.activeRun || a.starting)) || compareNames(a,b));
  for(const task of tasks) {
    const button=element('button','','running-task'); button.type='button';
    button.setAttribute('aria-pressed',String(task.id===selectedTaskId));
    const run=task.activeRun || task.latestRun;
    const state=task.starting?'starting':task.activeRun?'running':run?.state || 'idle';
    button.className+=` monitor-card-${state}`;
    const name=element('strong',task.name,'monitor-task-name');
    const mode=task.mode==='realtime'?'Realtime':task.cron?'Batch · Cron':'Batch · Manual';
    const definitions=(task.sources || []).map(source=>{
      const snapshot=run?.settings?.sources?.find(item=>item.sourceId===source.sourceId);
      const definition=registeredSources.find(item=>item.id===source.sourceId) || snapshot;
      const remote=definition?.type==='ssh' || Boolean(source.hostIds?.length);
      const hosts=remote?(source.hostIds || []).map(id=>{
        const saved=sshHosts.find(host=>host.id===id);
        const frozen=run?.settings?.sources?.find(item=>item.hostId===id);
        const hostName=saved?.name || frozen?.hostName || run?.hosts?.find(host=>host.hostId===id)?.hostName || id;
        const address=saved?.host || frozen?.host;
        const user=saved?.username || frozen?.username;
        const port=saved?.port || frozen?.port;
        return {id,label:`${hostName}${address?` · ${user?`${user}@`:''}${address}:${port || 22}`:''}`};
      }):[{id:'local',label:'DeciFlow (Local)'}];
      return {name:definition?.name || 'Unavailable source',path:definition?.path,type:remote?'Remote File (SSH)':'Local File',action:actionName(source.actionId),hosts,profile:profileLabels[source.profile] || source.profile || 'General system',chunkEvents:source.chunkEvents || 1};
    });
    const hostCount=new Set(definitions.flatMap(source=>source.hosts.map(host=>host.id))).size;
    const summary=element('span',`Source: ${definitions.map(source=>source.name).join(', ') || 'None'} · Source Hosts: ${hostCount}`,'caption monitor-task-sources');
    const details=element('span',`Type: ${[...new Set(definitions.map(source=>source.type))].join(', ') || 'None'} / Mode: ${mode} / Action: ${[...new Set(definitions.map(source=>source.action))].join(', ') || 'None'}`,'caption monitor-task-details');
    button.setAttribute('aria-describedby','task-monitor-tooltip');
    const showTooltip=()=>handleShowTaskTooltip(button,task,definitions,mode,state);
    const cancelTooltip=()=>{clearTimeout(taskTooltipTimer);$('task-monitor-tooltip').hidden=true;};
    button.onmouseenter=()=>{
      const tooltip=$('task-monitor-tooltip');
      if(!tooltip.hidden && tooltip.taskId===task.id){clearTimeout(taskTooltipTimer);return;}
      cancelTooltip();
      taskTooltipTimer=setTimeout(()=>{if(button.isConnected!==false)showTooltip();},1000);
    };
    button.onmousemove=()=>{if($('task-monitor-tooltip').hidden)button.onmouseenter();};
    button.onmouseleave=handleHideTaskTooltip;
    button.onfocus=showTooltip;
    button.onblur=()=>{if(!$('task-monitor-tooltip').matches?.(':hover'))cancelTooltip();};
    button.onkeydown=event=>{if(event.key==='Escape')cancelTooltip();};
    const status=element('span','','monitor-task-status');
    status.append(element('span',task.enabled===false?'Disabled':'Enabled',`monitor-availability ${task.enabled===false?'disabled':'enabled'}`),element('span',state[0].toUpperCase()+state.slice(1),`task-state monitor-state ${state}`));
    button.append(name,status,summary,details);
    button.onclick=()=>{cancelTooltip();return handleSelectTask(task.id);};
    list.append(button);
  }
  if(!tasks.length)list.append(element('p','No saved Tasks. Add a Task in Tasks.','caption'));

}
function renderTasks() {
  handleParkInlineView('task-view');
  $('task-registry').hidden=editingTask!==null;
  const list=$('task-list'); list.replaceChildren();
  const table=element('table','','action-list'); const head=element('tr','');
  for(const title of ['Name','Enabled','Execution','Status','Next Run','Manage']) head.append(element('th',title));
  table.append(head); const query=$('task-search').value.toLowerCase();
  for(const task of registeredTasks.filter(task=>task.name.toLowerCase().includes(query))) {
    const row=element('tr',''); const run=task.activeRun || task.latestRun;
    const availability=element('td','');
    const toggle=element('button','','task-toggle');toggle.type='button';
    toggle.setAttribute('role','switch');toggle.setAttribute('aria-checked',String(task.enabled !== false));
    toggle.setAttribute('aria-label',`Enable ${task.name}`);
    toggle.title=task.enabled === false?'Disabled':'Enabled';
    toggle.append(element('span','','task-toggle-knob'));
    toggle.onclick=()=>handleToggleTask(task,toggle);availability.append(toggle);
    row.append(element('td',task.name),availability,element('td',taskExecution(task)),element('td',task.starting ? 'Starting' : run?.state || 'Idle',`task-state ${task.starting?'running':run?.state || 'idle'}`),element('td',task.nextRunAt ? `${taskTime(task.nextRunAt,task.timezone)} (${task.timezone})` : '—'));
    const controls=element('td','','action-list-controls');
    for(const [label,handler] of [['Run',()=>handleRunTask(task.id)],['Stop',()=>handleStopTask(task.id)],['View',()=>handleViewTask(task)],['Edit',()=>handleEditTask(task)],['History',()=>handleTaskHistory(task)],['Delete',()=>handleDeleteTask(task)]]) {
      const button=element('button',label,'quiet'); button.type='button';button.onclick=handler;
      if(label==='Run')button.disabled=task.enabled===false || Boolean(task.activeRun || task.starting);
      if(label==='Stop')button.disabled=!task.activeRun;
      controls.append(button);
    }
    row.append(controls);handleAppendViewRow(table,row,'task-view',task.id);
  }
  list.append(table);renderTaskMonitor();
}
async function handleToggleTask(task,button) {
  button.disabled=true;
  try {
    const response=await fetch(`/api/tasks/${task.id}/enabled`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:task.enabled===false})});
    if(response.status===404 || response.status===405)throw new Error('Task controls are unavailable. Restart the DeciFlow UI server or container.');
    const data=await response.json();if(!response.ok)throw new Error(data.error);
    handleMessage('task-message','');
    await handleLoadTasks();
  }catch(error){handleMessage('task-message',error.message,true);}
  finally{button.disabled=false;}
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
  } catch(error) { handleMessage('task-message',error.message,true); handleMessage('message',error.message,true); }
}
function handleCloseTask() {
  handleCloseInlineView('task-view');
  editingTask=null; $('task-registry').hidden=false;$('task-editor').hidden=true;$('task-view').hidden=true;$('task-history').hidden=true;
}
function handleTaskMode() {
  const realtime=$('source-mode').value==='realtime'; const cron=!realtime && $('task-trigger').value==='cron';
  $('task-trigger-field').hidden=realtime;
  for(const id of ['task-cron-field','task-timezone-field'])$(id).hidden=!cron;
  $('task-resume-field').hidden=!realtime;
  $('task-mode-note').textContent=realtime ? 'Realtime monitors new data lines until stopped. Automatic restart is opt-in; lines written during downtime are not replayed.' : cron ? 'Each scheduled Batch reads files from the beginning and can repeat Actions for the same data. Overlapping occurrences are skipped. Missed schedules are not replayed. No automatic retries.' : 'Manual Batch reads files from the beginning once, then finishes as Completed or Failed.';
}
async function handleEditTask(task=null) {
  await sourceLoadPromise;
  await handleLoadHosts();
  if(!sourcesLoaded){handleMessage('task-message','Load Sources before editing Tasks.',true);return;}
  handleCloseTask();editingTask=task?.id || '';
  $('task-registry').hidden=true;$('task-editor').hidden=false;
  $('task-editor-title').textContent=task?'Edit Task':'Add Task';$('task-name').value=task?.name || '';
  $('source-mode').value=task?.mode || 'batch';$('task-trigger').value=task?.cron?'cron':'manual';
  $('task-cron').value=task?.cron || '';$('task-timezone').value=task?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  $('task-enabled').checked=task?.enabled ?? true;$('task-resume').checked=task?.resumeOnRestart || false;
  sourcePreferences.clear();
  for(const source of task?.sources || [])sourcePreferences.set(source.sourceId,{profile:source.profile,chunkEvents:source.chunkEvents,actionId:source.actionId || '',hostIds:[...(source.hostIds || [])]});
  const paths=task?.sources.map(source=>source.sourceId) || registeredSources.slice(0,1).map(source=>source.id);
  $('file-path').value=paths.join('\n');updateSourceSettings(paths);handleTaskMode();handleMessage('task-message','');
}
$('add-task').onclick=()=>handleEditTask();$('cancel-task').onclick=handleCloseTask;$('task-search').oninput=renderTasks;
$('task-form').onsubmit=async event=>{
  event.preventDefault();$('save-task').disabled=true;
  try {
    const mode=$('source-mode').value;
    const sources=sourceRows.map(({path,profile,size,action,hostIds})=>({sourceId:path,profile:profile.value,chunkEvents:Number(size.value),actionId:action.value,...(hostIds?.length?{hostIds:[...hostIds]}:{})}));
    const task={...(editingTask?{id:editingTask}:{}),name:$('task-name').value,mode,sources,cron:mode==='batch' && $('task-trigger').value==='cron'?$('task-cron').value:'',timezone:$('task-timezone').value || 'UTC',enabled:$('task-enabled').checked,resumeOnRestart:mode==='realtime' && $('task-resume').checked};
    const response=await fetch('/api/tasks',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(task)});
    const data=await response.json();if(!response.ok)throw new Error(data.error);
    registeredTasks=data.tasks;handleCloseTask();renderTasks();handleMessage('task-message','Task saved. Changes apply to new runs.');
  }catch(error){handleMessage('task-message',error.message,true);}
  finally{$('save-task').disabled=false;}
};
function handleViewTask(task) {
  handleCloseTask();const view=$('task-view');view.replaceChildren();
  const container=element('section','','task-source-card');
  const header=element('div','','task-source-heading');
  const heading=element('div','','task-detail-heading');
  heading.append(element('h3',task.name),element('span',taskExecution(task),'caption'));
  header.append(heading);container.append(header);
  const sources=element('div','','task-source-details');
  for(const source of task.sources){
    const definition=registeredSources.find(item=>item.id===source.sourceId);
    const card=element('section','','task-source-entry');
    const fields=element('dl','','view-details task-source-fields');
    for(const [label,value,wide] of [
      ['Source Name',definition?.name || source.sourceId,false],
      ['File Path / Pattern',definition?.path || 'Source unavailable',false],
      ['Source Type',definition?.type==='ssh' || source.hostIds?.length?'Remote File (SSH)':'Local File',false],
      ['Criteria',profileLabels[source.profile] || source.profile,false],
      ['Events per Chunk',String(source.chunkEvents),false],
      ['Action',actionName(source.actionId),false],
    ]){
      const field=element('div','',wide?'task-source-field-wide':'');
      field.append(element('dt',label),element('dd',value,label==='File Path / Pattern'?'task-source-path':''));fields.append(field);
    }
    const targets=element('div','','task-source-field-wide');
    targets.append(element('dt',source.hostIds?.length?`Source Hosts (${source.hostIds.length})`:'Source Host'));
    const hosts=element('dd','','task-target-hosts');
    if(source.hostIds?.length){
      for(const id of source.hostIds){
        const host=sshHosts.find(item=>item.id===id);
        hosts.append(element('span',host?.name || id,'task-target-host'));
      }
    }else hosts.append(element('span','DeciFlow (Local)','task-target-host'));
    targets.append(hosts);fields.insertBefore(targets,fields.children[3]);card.append(fields);sources.append(card);
  }
  container.append(sources);view.append(container);view.hidden=false;
}
async function handleDeleteTask(task) {
  if(!await handleConfirmDelete('Task', task.name, 'The Task, all run history, results, and reviewer corrections will be permanently deleted. Original source files are kept. This cannot be undone.', task.id))return;
  try {
    const response=await fetch('/api/tasks',{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:task.id})});
    const data=await response.json();if(!response.ok)throw new Error(data.error);
    registeredTasks=data.tasks;
    if(selectedTaskId===task.id){
      selectedTaskId='';activeRequest?.abort();pagedView=null;activeJobId=undefined;rememberJob('');
      results=[];completionOrder=[];pausedOrder=[];displayedOrder=[];completed=0;total=0;runHosts=[];runSourcePatterns=[];
      statisticsResults=undefined;filteredResults=undefined;renderedRows.clear();renderedPage=[];render();
      $('result-context').textContent='Select a Task to view its results.';handleMessage('message','');
    }
    renderTasks();
  }catch(error){handleMessage('task-message',error.message,true);}
}
async function handleTaskHistory(task) {
  try {
    const response=await fetch(`/api/tasks/${task.id}/runs`,{method:'POST'});const data=await response.json();if(!response.ok)throw new Error(data.error);
    handleCloseTask();$('task-registry').hidden=true;const view=$('task-history');view.replaceChildren();
    const header=element('div','','card-title');const back=element('button','Back to List','quiet');back.type='button';back.onclick=handleCloseTask;
    const refresh=element('button','Refresh','quiet');refresh.type='button';refresh.onclick=()=>handleTaskHistory(task);
    header.append(element('h3',`${task.name} · Latest 50 Executions`),refresh,back);view.append(header);
    const table=element('table','','action-list');const head=element('tr','');for(const title of ['Started','Finished','Trigger','State','Results','Manage'])head.append(element('th',title));table.append(head);
    for(const run of data.runs){const row=element('tr','');row.append(element('td',`${taskTime(run.startedAt,task.timezone)} (${task.timezone})`),element('td',taskTime(run.finishedAt,task.timezone)),element('td',run.settings.trigger),element('td',run.state,`task-state ${run.state}`),element('td',`${run.counts?.completed || 0} chunks · ${run.counts?.failed || 0} failed requests · ${run.counts?.actionFailed || 0} failed Actions${run.error?` · ${run.error}`:''}`));const cell=element('td','');const button=element('button','View Results','quiet');button.type='button';button.onclick=()=>{followLatestTask=false;selectedTaskId=task.id;handleNavigation('main');renderTaskMonitor();return handleWatchRun(run);};cell.append(button);row.append(cell);table.append(row);}
    view.append(table);if(!data.runs.length)view.append(element('p','No executions yet.','caption'));view.hidden=false;
  }catch(error){handleMessage('task-message',error.message,true);}
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
  if(!task){handleMessage('message','Select a saved Task first.',true);return;}
  followLatestTask=true;monitoringReady=true;selectedTaskId=identity;handleNavigation('main');renderTaskMonitor();
  try {
    if(task.activeRun)return await handleWatchRun(task.activeRun);
    const response=await fetch(`/api/tasks/${identity}/run`,{method:'POST'});const job=await response.json();if(!response.ok)throw new Error(job.error);
    await handleLoadTasks();return await handleWatchRun(job);
  }catch(error){$('message').className='error-message';handleMessage('message',error.message,true);}
}
async function handleStopTask(identity) {
  try{const response=await fetch(`/api/tasks/${identity}/stop`,{method:'POST'});const data=await response.json();if(!response.ok)throw new Error(data.error);await handleLoadTasks();}
  catch(error){handleMessage('task-message',error.message,true);}
}
async function handleSelectTask(identity) {
  followLatestTask=true;monitoringReady=true;
  const task=registeredTasks.find(task=>task.id===identity);selectedTaskId=task?.id || '';
  renderTaskMonitor();
  if(task?.activeRun || task?.latestRun)return handleWatchRun(task.activeRun || task.latestRun);
  const selection=++monitorSelection;
  activeRequest?.abort();await monitoringPromise;
  if(selection!==monitorSelection)return;
  pagedView=null;activeJobId=undefined;activeJobState=undefined;rememberJob('');
  results=[];completionOrder=[];pausedOrder=[];displayedOrder=[];completed=0;page=0;total=0;
  elapsedMs=0;activeProcessingMs=0;recentCompletions=[];runHosts=[];runSourcePatterns=[];updatesPaused=false;
  statisticsResults=undefined;filteredResults=undefined;renderedRows.clear();renderedPage=[];render();
  $('result-context').textContent=task?.name || 'Select a Task to view its results.';
  $('message').className='';handleMessage('message',task?'No executions yet.':'');

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
  if(view==='settings' && section==='ssh-hosts' && (currentView!=='settings' || currentSettingsSection!=='ssh-hosts'))autoCheckedHosts.clear();
  currentView = view;
  currentSettingsSection = view === 'settings' ? section : null;
  if (view === 'settings' || view === 'sources') handleLoadKeys().then(handleLoadHosts);
  const hash = view === 'main' ? '' : view === 'settings' && section ? `#settings/${section}` : `#${view}`;
  if (globalThis.location && globalThis.location.hash !== hash) globalThis.location.hash = hash;
  $('main-page').hidden = view !== 'main';
  if (view === 'main' && completed) render(false, true);
  $('settings-page').hidden = view !== 'settings';
  $('nav-settings').setAttribute('aria-current', view === 'settings' && !section ? 'page' : 'false');
  $('nav-settings').setAttribute('data-active', String(view === 'settings'));
  const settingsHeading = section === 'ssh-keys'
    ? ['SSH Keys', 'Manage authentication keys for SSH connections.']
    : section === 'configuration' ? ['Configurations', 'Manage result display and application maintenance settings.']
    : section === 'ssh-hosts'
      ? ['SSH Hosts', 'Manage remote hosts and test SSH connections.']
      : ['Settings', 'Manage shared application settings.'];
  $('settings-title').textContent = settingsHeading[0];
  $('settings-description').textContent = settingsHeading[1];
  $('settings-overview').hidden = Boolean(section);
  $('settings-configuration').hidden=view!=='settings' || section!=='configuration';
  $('nav-configuration').setAttribute('aria-current',view==='settings' && section==='configuration'?'page':'false');
  if(view==='settings' && section==='configuration'){handleLoadResetStatus();handleLoadResultSettings();}
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
$('nav-configuration').onclick=()=>handleMenuNavigation('settings','configuration');
$('nav-settings').onclick = () => { handleMenuNavigation('settings'); };
$('nav-ssh-keys').onclick = () => handleMenuNavigation('settings','ssh-keys');
$('nav-ssh-hosts').onclick = () => handleMenuNavigation('settings','ssh-hosts');
$('nav-tasks').onclick = () => handleMenuNavigation('tasks');
$('nav-main').onclick = () => handleNavigation('main');
$('nav-actions').onclick = () => handleMenuNavigation('actions');
$('nav-sources').onclick = () => { handleMenuNavigation('sources'); if (!sourcesLoaded) return handleLoadSources(); };
const defaultActionCode = `import json
import sys

result = json.load(sys.stdin)

# Use result["category"], result["log"], and result["source"] here.
# Replace this handler with your notification, storage, or other integration.
`;
const profileLabels = { general: 'General system', authentication: 'Sample Authentication', http_access: 'Sample HTTP access', application: 'Sample Application', network: 'Sample Network / tcpdump text' };
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
  handleParkInlineView('action-view');
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
    badge.setAttribute('role', 'status'); status.append(badge);
    if (state === 'not_ready' && action.preparationError) status.append(element('div', action.preparationError, 'error-message'));
    row.append(status);
    const controls = element('td', '', 'action-list-controls');
    for (const [caption, handler] of [
      ['View', () => handleViewConfiguration('action-view', action.name, [['Name', action.name], ['ID', action.id], ['Python Version', action.pythonVersion], ['Modules', action.modules || []], ['Python Executable', action.python], ['Script Path', action.script], ['Python Code', action.code]])],
      ['Edit', () => handleEditAction(index)],
      ['Reset venv', () => handleResetAction(index)],
      ['Delete', async () => { if (!await handleConfirmDelete('Action', action.name, 'This Action and its managed script and environment will be deleted when you save changes.', action.id)) return; registeredActions.splice(registeredActions.indexOf(action), 1); handleCloseConfiguration('action-view'); renderActions(); handleMessage('action-message','Deletion pending. Save Changes to apply.'); }],
    ]) {
      const button = element('button', caption, 'quiet');
      button.type = 'button'; button.disabled = preparingActions || (caption !== 'View' && editingAction !== null) || (caption === 'Reset venv' && (!action.id || !action.pythonVersion));
      button.onclick = handler; controls.append(button);
    }
    row.append(controls); handleAppendViewRow(table,row,'action-view',action.id || action.name);
  });
  $('action-registry').append(matches ? table : element('p', registeredActions.length ? 'No Actions match your search.' : 'No Actions registered. Click Add Action to create one.', 'caption'));
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
  handleMessage('action-message','Rebuilding the saved Action environment…');
  try {
    const response = await fetch(`/api/actions/${registeredActions[index].id}/reset`, { method: 'POST' });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    registeredActions[index] = data.action;
    handleCloseConfiguration('action-view');
    handleMessage('action-message','Action environment rebuilt with pip and locked dependencies.');
  } catch (error) { await handleRefreshActionStatus(); handleMessage('action-message',error.message,true); }
  finally { preparingActionIndex = null; preparingActions = false; $('save-actions').disabled = $('action-view').hidden === false; renderActions(); }
}
$('action-search').oninput = renderActions;
function handleEditAction(index) {
  handleCloseConfiguration('action-view');
  editingAction = index;
  const action = registeredActions[index] || { pythonVersion: '3.12', code: defaultActionCode };
  const row = element('div', '', 'action-registration');
  const fields = { id: { value: action.id || '' } };
  for (const [key, caption] of [['name', 'Name'], ['pythonVersion', 'Python Version (e.g. 3.12)'], ['modules', 'Modules (one per line; versions optional)'], ['code', 'Python Code']]) {
    const label = element('label', caption);
    const input = element(['modules', 'code'].includes(key) ? 'textarea' : 'input', '');
    input.value = key === 'modules' && Array.isArray(action.modules) ? action.modules.join('\n') : action[key] || (key === 'pythonVersion' ? '3.12' : '');
    if (key === 'name') input.readOnly = false;
    if (key === 'modules') { input.rows = 3; input.className = 'action-modules'; }
    if (key === 'code') { input.rows = 14; input.spellcheck = false; input.className = 'action-code'; label.className = 'action-code-label'; }
    input.setAttribute('aria-label', caption);
    label.append(input);
    if(key==='code')handlePythonEditor(input,label);
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
  handleMessage('action-message','Preparing Python environments and installing modules…');
  for (const fields of actionRows) for (const input of Object.values(fields)) input.disabled = true;
  try {
    const values = registeredActions.slice();
    if (editingAction !== null) values[editingAction] = { ...registeredActions[editingAction], ...Object.fromEntries(Object.entries(actionRows[0]).map(([key, input]) => [key, input.value])) };
    const response = await fetch('/api/actions', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(values) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    registeredActions = data.actions;
    handleCloseConfiguration('action-view'); handleCloseAction(); updateSourceSettings(); renderTaskMonitor();
    handleMessage('action-message','Actions saved and environments ready. Changes apply to the next run.');
  } catch (error) { handleMessage('action-message',error.message,true); }
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
}).catch(error => { handleMessage('action-message',error.message,true); });
let criteriaProfiles = {};
let criteriaLoaded = false;
let savingCriteria = false;
let editingCriteria = null;
let criteriaFields = {};
let criteriaTemplate = null;
let criteriaDraftId = null;
function handleViewCriteria(id) {
  const profile = criteriaProfiles[id];
  handleViewConfiguration('criteria-view', profile.label, [['Name', profile.label], ['Decision Instructions', profile.instructions], ...Object.entries(labels).map(([key, label]) => [label, profile.criteria[key]]), ['Normalization', profile.normalization]]);
}
function renderCriteria() {
  handleParkInlineView('criteria-view');
  $('criteria-list').hidden = editingCriteria !== null;
  const defaultTable = element('table', '', 'action-list');
  const defaultHeader = element('tr', '');
  for (const title of ['Name', 'Manage']) defaultHeader.append(element('th', title));
  const defaultRow = element('tr', '');
  defaultRow.append(element('td', criteriaProfiles.general.label));
  const defaultControls = element('td', '', 'action-list-controls');
  const viewDefault = element('button', 'View', 'quiet');
  viewDefault.type = 'button'; viewDefault.disabled = savingCriteria;
  viewDefault.onclick = () => handleViewCriteria('general');
  const cloneDefault = element('button', 'Clone', 'quiet');
  cloneDefault.type = 'button'; cloneDefault.disabled = savingCriteria || editingCriteria !== null;
  cloneDefault.onclick = () => handleCloneCriteria('general');
  defaultControls.append(viewDefault, cloneDefault); defaultRow.append(defaultControls);
  defaultTable.append(defaultHeader);handleAppendViewRow(defaultTable,defaultRow,'criteria-view','general');
  $('criteria-default').replaceChildren(); $('criteria-default').append(defaultTable);
  const table = element('table', '', 'action-list');
  const header = element('tr', '');
  for (const title of ['Name', 'Manage']) header.append(element('th', title));
  table.append(header);
  const query = $('criteria-search').value.trim().toLowerCase();
  let matches = 0;
  for (const [id, profile] of Object.entries(criteriaProfiles)) {
    if (id === 'general' || !profile.label.toLowerCase().includes(query)) continue;
    matches++;
    const row = element('tr', '');
    row.append(element('td', profile.label));
    const controls = element('td', '', 'action-list-controls');
    for (const [caption, handler] of [
      ['View', () => handleViewCriteria(id)],
      ['Edit', () => handleEditCriteria(id)],
      ['Clone', () => handleCloneCriteria(id)],
      ['Delete', async () => { if (!await handleConfirmDelete('Criteria', profile.label, 'This criteria profile will be deleted when you save changes.', id)) return; delete criteriaProfiles[id]; handleCloseConfiguration('criteria-view'); renderCriteria(); handleMessage('criteria-message','Deletion pending. Save Changes to apply.'); }],
    ]) {
      const button = element('button', caption, 'quiet');
      button.type = 'button';
      button.disabled = savingCriteria || (caption !== 'View' && editingCriteria !== null);
      button.onclick = handler; controls.append(button);
    }
    row.append(controls); handleAppendViewRow(table,row,'criteria-view',id);
  }
  $('criteria-registry').replaceChildren();
  $('criteria-registry').append(matches ? table : element('p', 'No profiles match your search.', 'caption'));
  $('add-criteria').disabled = !criteriaLoaded || savingCriteria || editingCriteria !== null;
}
function handleCloneCriteria(id) {
  const profile = criteriaProfiles[id];
  handleEditCriteria('', { ...profile, label: `${profile.label} (Clone)`, criteria: { ...profile.criteria } });
}
function handleEditCriteria(id, template = null) {
  handleCloseConfiguration('criteria-view');
  editingCriteria = id;
  criteriaTemplate = template;
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('');
  criteriaDraftId = id || `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
  const profile = criteriaProfiles[id] || template || { label: '', instructions: '', criteria: { ...criteriaProfiles.general.criteria } };
  const row = element('div', '', 'action-registration');
  criteriaFields = {};
  for (const [key, caption] of [['label', 'Name'], ['instructions', 'Decision Instructions'], ...Object.entries(labels)]) {
    const label = element('label', caption);
    const input = element(key === 'label' ? 'input' : 'textarea', '');
    input.value = profile[key] ?? profile.criteria[key] ?? '';
    input.setAttribute('aria-label', caption);
    if (key !== 'id' && key !== 'label') { input.rows = 3; label.className = 'action-code-label'; }
    label.append(input); row.append(label); criteriaFields[key] = input;
  }
  criteriaFields.label.oninput = () => handleValidateCriteria();
  criteriaFields.label.oninput();
  $('criteria-editor').replaceChildren(); $('criteria-editor').append(element('h3', id ? 'Edit Profile' : 'Add Profile'), row);
  $('criteria-editor').hidden = false; $('cancel-criteria').hidden = false;
  renderCriteria();
}
function handleValidateCriteria(showMessage = true) {
  if (editingCriteria === null) return true;
  const name = criteriaFields.label.value.trim();
  const errors = [];
  if (!name) errors.push('Name is required.');
  if (Object.entries(criteriaProfiles).some(([key, profile]) => key !== editingCriteria && profile.label.trim().toLowerCase() === name.toLowerCase())) errors.push('Name already exists.');
  if (showMessage) handleMessage('criteria-message', errors.join(' '), errors.length > 0);
  $('save-criteria').disabled = savingCriteria || errors.length > 0;
  return errors.length === 0;
}
function handleCloseCriteria() {
  editingCriteria = null; criteriaFields = {}; criteriaTemplate = null; criteriaDraftId = null;
  $('criteria-editor').replaceChildren(); $('criteria-editor').hidden = true;
  $('cancel-criteria').hidden = true;
  $('save-criteria').disabled = savingCriteria;
  handleMessage('criteria-message', '');
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
  handleMessage('criteria-message','Loading criteria…');
  try {
    const response = await fetch('/api/criteria', { method: 'POST' });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    criteriaProfiles = data.profiles; criteriaLoaded = true;
    $('save-criteria').disabled = false; renderCriteria();
    handleMessage('criteria-message','');
  } catch (error) { handleMessage('criteria-message',error.message,true); }
};
$('criteria-search').oninput = renderCriteria;
$('add-criteria').onclick = () => handleEditCriteria('');
$('cancel-criteria').onclick = handleCloseCriteria;
$('save-criteria').onclick = async () => {
  if (!handleValidateCriteria()) return;
  savingCriteria = true; $('save-criteria').disabled = true; $('cancel-criteria').disabled = true;
  renderCriteria();
  for (const input of Object.values(criteriaFields)) input.disabled = true;
  try {
    const values = { ...criteriaProfiles };
    if (editingCriteria !== null) {
      const id = criteriaDraftId;
      if (!editingCriteria && Object.hasOwn(values, id)) throw new Error('Profile ID already exists.');
      values[id] = { ...(criteriaProfiles[editingCriteria] || criteriaTemplate), label: criteriaFields.label.value, instructions: criteriaFields.instructions.value, criteria: Object.fromEntries(Object.keys(labels).map(key => [key, criteriaFields[key].value])) };
    }
    const response = await fetch('/api/criteria', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(values) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    criteriaProfiles = data.profiles; handleCloseConfiguration('criteria-view'); handleCloseCriteria();
    const missing = handleCriteriaLabels(criteriaProfiles);
    handleMessage('criteria-message','Criteria saved. Changes apply to new runs.' + (missing ? ' Select replacements for deleted profiles in Tasks.' : ''));
  } catch (error) { handleMessage('criteria-message',error.message,true); }
  finally {
    savingCriteria = false; $('save-criteria').disabled = false; $('cancel-criteria').disabled = false;
    for (const input of Object.values(criteriaFields)) input.disabled = false;
    renderCriteria();
    if (editingCriteria !== null) handleValidateCriteria(false);
  }
};
let sourcesLoaded = false;
let editingSource = null;
let sourceFields = {};
let savingSources = false;
function sourceDescription(source) {
  return `${source.type === 'ssh' ? 'Remote File (SSH)' : 'Local File'} · ${source.path.split('\n').join(' · ')}`;
}
function renderSources() {
  handleParkInlineView('source-view');
  $('source-list').hidden = editingSource !== null;
  const table = element('table', '', 'action-list');
  const header = element('tr', '');
  for (const caption of ['Name', 'Type / Path', 'Manage']) header.append(element('th', caption));
  table.append(header);
  const query = $('source-search').value.trim().toLowerCase();
  for (const [index, source] of registeredSources.entries()) {
    if (!`${source.name} ${sourceDescription(source)}`.toLowerCase().includes(query)) continue;
    const row = element('tr', '');
    row.append(element('td', source.name), element('td', sourceDescription(source)));
    const controls = element('td', '', 'action-list-controls');
    for (const [caption, handler] of [
      ['View', () => handleViewConfiguration('source-view', source.name, [['Type', source.type === 'ssh' ? 'Remote File (SSH)' : 'Local File'], ['Name', source.name], ['Path / Pattern', source.path]])],
      ['Edit', () => handleEditSource(index)],
      ['Delete', async () => { if (!await handleConfirmDelete('Source', source.name, 'This Source registration will be deleted when you save changes. Original source files are kept.', source.id)) return; registeredSources.splice(registeredSources.indexOf(source), 1); handleCloseConfiguration('source-view'); renderSources(); handleMessage('source-message','Deletion pending. Save Changes to apply.'); }],
    ]) {
      const button = element('button', caption, 'quiet'); button.type = 'button';
      button.disabled = !sourcesLoaded || savingSources || (caption !== 'View' && editingSource !== null);
      button.onclick = handler; controls.append(button);
    }
    row.append(controls); handleAppendViewRow(table,row,'source-view',source.id);
  }
  $('source-registry').replaceChildren(); $('source-registry').append(table);
  $('add-registered-source').disabled = !sourcesLoaded || savingSources || editingSource !== null;
}
function handleEditSource(index) {
  handleCloseConfiguration('source-view'); editingSource = index;
  const source = registeredSources[index] || { name: '', type: 'local', path: '', port: 22 };
  const form = element('div', '', 'action-registration'); sourceFields = {};
  for (const [key, caption] of [['type', 'Type'], ['name', 'Name'], ['path', 'File Path / Pattern']]) {
    const label = element('label', caption);
    const input = element(key === 'type' ? 'select' : key === 'path' ? 'textarea' : 'input', '');
    if (key === 'type') { input.append(new Option('Local File', 'local'), new Option('Remote File (SSH)', 'ssh')); }
    else if(key==='path'){input.rows=3;input.placeholder='/var/log/app/*.log\n/var/log/system.log';}
    else input.type = 'text';
    input.value = String(source[key] ?? (key === 'port' ? 22 : '')); input.setAttribute('aria-label', caption);
    label.append(input);if(key==='path')label.append(element('span','One file path or pattern per line. Overlapping matches are read once.','caption')); form.append(label); sourceFields[key] = input;
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
  if (!sourcesLoaded) { handleMessage('source-message','Load Sources before saving.',true); return; }
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
    handleMessage('source-message','Sources saved. Changes apply to new runs. Select replacements for deleted sources in Tasks.');
  } catch (error) { handleMessage('source-message',error.message,true); }
  finally { savingSources = false; $('save-sources').disabled = false; for (const input of Object.values(sourceFields)) input.disabled = false; renderSources(); }
};
function compareNames(left, right) {
  return left.name.localeCompare(right.name, 'ko', {numeric:true, sensitivity:'base'});
}
function actionName(id) {
  return id ? registeredActions.find(action=>action.id===id)?.name || 'Unavailable Action' : 'None';
}
function selectionInput(items, value, caption, placeholder) {
  const input = element('select', ''); input.disabled = false;
  input.setAttribute('aria-label', caption);
  if (placeholder) input.append(new Option(placeholder, ''));
  for (const item of [...items].sort(compareNames)) {
    const option = new Option(item.name, item.id);
    option.title = item.label || item.name;
    input.append(option);
  }
  if (value && !items.some(item => item.id === value)) {
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
  const picker=element('section','','host-picker');
  const summary=element('div','','host-picker-title');
  const search=element('input','');search.type='search';search.placeholder='Search SSH Hosts…';search.setAttribute('aria-label','Search source SSH Hosts');
  const tools=element('div','','host-picker-tools');
  const select=element('button','Select all shown','quiet');select.type='button';
  const clear=element('button','Clear','quiet');clear.type='button';tools.append(select,clear);
  const list=element('div','','host-picker-list');
  const update=()=>{
    summary.textContent=`Source Hosts · ${source.hostIds.length} selected`;
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
    const name = selectionInput(registeredSources.map(source => ({ id: source.id, name: source.name, label: sourceDescription(source) })), definition?.id || '', 'Registered source', '');
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
    const label = element('label', 'Events/Chunk ');
    label.append(size);
    const criteriaLabel = element('label', 'Criteria ', 'criteria-label');
    criteriaLabel.append(profile);
    const action = selectionInput(registeredActions.filter(item => item.name), preference.actionId || '', `Action for ${path}`, 'None');
    const actionLabel = element('label', 'Action '); actionLabel.append(action);
    const remove = element('button', 'Remove', 'quiet source-remove');
    remove.type = 'button'; remove.disabled = false;
    row.append(pathLabel, criteriaLabel, label, actionLabel, remove);
    const save = () => {
      sourcePreferences.set(source.path, { profile: profile.value, chunkEvents: Number(size.value), actionId: action.value, hostIds:[...source.hostIds] });
      try { localStorage.setItem('deciflow-source-preferences', JSON.stringify([...sourcePreferences].map(([path, { profile, chunkEvents }]) => [path, { profile, chunkEvents }]))); } catch { /* Preferences remain available for this page session. */ }
    };
    profile.onchange = save; size.oninput = save; action.onchange = save;
    const source = { path: definition?.id || path, name, profile, size, action, remove, hostIds:[...(preference.hostIds || [])] };
    const hosts = hostPicker(source, save); hosts.hidden=definition?.type!=='ssh';
    row.replaceChildren();row.append(pathLabel,criteriaLabel,label,actionLabel,hosts,remove);
    name.onchange = () => {
      const selected = registeredSources.find(item => item.id === name.value);
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
  for (const path of defaults.split('\n')) sourcePreferences.set(path, { profile: defaultSourceProfiles[sampleSources.find(source => source.id === path)?.path || registeredSources.find(source => source.id === path)?.path] || 'general', chunkEvents: 1, actionId: '' });
  try { localStorage.setItem('deciflow-source-preferences', JSON.stringify([...sourcePreferences].map(([path, { profile, chunkEvents }]) => [path, { profile, chunkEvents }]))); } catch { /* The current page still uses the reset defaults. */ }
  filePaths[sourceMode] = defaults; $('file-path').value = defaults;
  updateSourceSettings();
};
updateSourceSettings();
function updateResultStatistics(incremental = true) {
  if (pagedView?.summary) return pagedView.summary;
  if (!incremental || statisticsResults !== results || statisticsCursor > completionOrder.length) {
    resultStatistics = {
      total: 0, failed: 0, truncated: 0, review: 0, processingMs: 0,
      actionSuccess: 0, actionFailed: 0,
      groups: {all: 0, certain: 0, uncertain: 0},
      categories: Object.fromEntries(['all', 'certain', 'uncertain'].map(group =>
        [group, Object.fromEntries(Object.keys(labels).map(key => [key, 0]))])),
      hosts: new Map(), sources: new Map(),
    };
    statisticsCursor = 0;
    statisticsResults = results;
    // Explicit renders can reflect edited/legacy results; stream results are immutable.
    if (!incremental) {
      for (const result of results) if (result) addResultStatistics(result);
      statisticsCursor = completionOrder.length;
      return resultStatistics;
    }
  }
  for (; statisticsCursor < completionOrder.length; statisticsCursor++) {
    addResultStatistics(results[completionOrder[statisticsCursor]]);
  }
  return resultStatistics;
}
function addResultStatistics(result) {
  const stats = resultStatistics;
  stats.total++;
  stats.processingMs += result.elapsedMs || 0;
  if (result.error) stats.failed++;
  if (result.providerResponse?.usage?.truncated === true) stats.truncated++;
  if (needsReview(result)) stats.review++;
  if (result.actionExecution?.status === 'success') stats.actionSuccess++;
  if (result.actionExecution?.status === 'failed') stats.actionFailed++;
  if (!result.error && Object.hasOwn(stats.categories.all, result.category)) {
    const group = result.uncertain ? 'uncertain' : 'certain';
    stats.groups.all++; stats.groups[group]++;
    stats.categories.all[result.category]++; stats.categories[group][result.category]++;
  }
  const id = resultHostId(result);
  if (!stats.hosts.has(id)) stats.hosts.set(id, {
    name: result.hostName || (id === 'local' ? 'DeciFlow (Local)' : id.replace('legacy:', '')),
    count: 0, failed: 0,
  });
  const host = stats.hosts.get(id); host.count++; if (result.error) host.failed++;
  for (const path of new Set(result.sourcePatterns || (result.source ? [result.source] : []))) {
    stats.sources.set(path, (stats.sources.get(path) || 0) + 1);
  }
}
let chartCertainty = 'all';
function renderCategoryChart() {
  const stats = updateResultStatistics();
  const counts = stats.categories[chartCertainty];
  const {failed, truncated, groups} = stats;
  const certainty = chartCertainty;
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
  const stats = updateResultStatistics();
  const hosts = new Map(stats.hosts);
  for (const host of runHosts) hosts.set(host.hostId, {
    ...(hosts.get(host.hostId) || {count: 0, failed: 0}),
    name: `${host.hostName} · ${host.hostAddress}:${host.hostPort}`,
  });
  select.replaceChildren();select.append(new Option('All hosts','all'));
  for(const [id,host] of [...hosts].sort((a,b)=>a[1].name.localeCompare(b[1].name,'ko')))select.append(new Option(`${host.name} (${host.count})`,id));
  select.value=hosts.has(selected)?selected:'all';select.disabled=!hosts.size;
  const status=$('host-status');status.replaceChildren();
  for(const host of runHosts){
    const counts=stats.hosts.get(host.hostId) || {count:0,failed:0};
    status.append(element('p',`${host.hostName} · Collection: ${host.collectionState || 'pending'} · ${counts.count-counts.failed} classified · ${counts.failed} failed${host.error?` · ${host.error}`:''}`,host.collectionState==='failed'?'connection-failed':'caption'));
  }
}
function renderSourceFilter() {
  const select = $('source-filter');
  const selected = select.value || 'all';
  const counts = new Map(runSourcePatterns.map(path => [path, 0]));
  for (const [path, count] of updateResultStatistics().sources) counts.set(path, count);
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
function render(updateList = true, incremental = false) {
  const stats = updateResultStatistics(incremental);
  if (!incremental || renderedCount !== completed || renderedHosts !== runHosts) {
    renderSourceFilter();
    renderHostFilter();
    renderCategoryChart();
    renderedCount = completed;
    renderedHosts = runHosts;
  }
  $('summary').replaceChildren();
  const processingMs = stats.processingMs;
  const averageMs = completed ? processingMs / completed : 0;
  recentCompletions = recentCompletions.filter(time => time > elapsedMs - 5000);
  const recentCount = pagedView ? Object.entries(stats.throughputBuckets || {}).filter(([bucket])=>Number(bucket)*100>elapsedMs-5000).reduce((sum,[,count])=>sum+count,0) : recentCompletions.length;
  const throughput = elapsedMs > 0 ? recentCount * 1000 / Math.min(elapsedMs, 5000) : 0;
  const actionSuccess = stats.actionSuccess;
  const actionFailed = stats.actionFailed;
  const processingPercent = elapsedMs > 0 ? `${(activeProcessingMs / elapsedMs * 100).toFixed(1)}%` : 'N/A';
  for (const [label, value] of [['Success / Failed / Total', `${stats.total-stats.failed} / ${stats.failed} / ${stats.total}`], ['Action Success / Failed / Total', `${actionSuccess} / ${actionFailed} / ${actionSuccess + actionFailed}`], ['Needs Review', stats.review], ['Total Elapsed Time', formatDuration(elapsedMs)], ['Active Processing Time', `${formatDuration(activeProcessingMs)} (${processingPercent})`], ['Average Processing Time', formatDuration(averageMs)], ['Throughput', `${throughput.toFixed(1)} chunks/s`]]) {
    const metric = element('div', label, 'metric');
    if (label === 'Success / Failed / Total') metric.title = 'Successfully classified / failed / total completed chunks. Total is success plus failure, not planned requests. Failures include connection errors, timeouts, rejected inputs, and invalid responses. Action failures do not change classification counts.';
    if (label === 'Action Success / Failed / Total') metric.title = 'Completed Action executions: success / failed / total. Unassigned sources and failed decisions do not run Actions. Action failures do not change decision counts.';
    if (label === 'Throughput') metric.title = 'Successfully classified chunks per second over the last 5 seconds, including idle time. Uses elapsed time until 5 seconds; freezes when stopped or completed.';
    if (label === 'Needs Review') metric.title = 'Successful classifications only: selected category probability below 70%, top-two probability gap below 10 percentage points, collapsed options, or Other category. Failed requests are excluded.';
    if (label === 'Average Processing Time') metric.title = 'Mean request duration, including network/server wait and failed requests; excludes waiting for new file lines.';
    if (label === 'Active Processing Time') metric.title = 'Time with at least one request in flight, counting overlapping requests once. Includes network/server wait, excludes idle time; not CPU utilization.';
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
  const pendingCount = pagedView ? Math.max(0, completed-pagedView.snapshotTotal) : updatesPaused ? completionOrder.length - pausedOrder.length : 0;
  const historicalPage = pagedView && page>0;
  $('pause-updates').textContent = historicalPage ? `Latest Results${pendingCount ? ` (${pendingCount} new)` : ''}` : updatesPaused ? `Resume Updates${pendingCount ? ` (${pendingCount} new)` : ''}` : 'Pause Updates';
  $('pause-updates').setAttribute('aria-pressed', String(updatesPaused || Boolean(historicalPage)));
  $('pause-updates').disabled = !busy && !completed && !updatesPaused;
  $('export-reviewed').disabled = $('export').disabled = pagedView ? !completed : !completed || busy || activeJobState === 'running';
  if (updatesPaused && !updateList && !pagedView) return;
  const order = !pagedView && updatesPaused ? pausedOrder : completionOrder;
  const review = $('review-filter').value;
  const category = $('category-filter').value;
  const search = $('log-search').value.toLowerCase();
  const source = $('source-filter').value || 'all';
  const host = $('host-filter').value || 'all';
  const filterKey = JSON.stringify([review, category, search, source, host]);
  let visible = order;
  if (!pagedView && (review !== 'all' || category !== 'all' || search || source !== 'all' || host !== 'all')) {
    if (!incremental || filteredResults?.order !== order || filteredResults.key !== filterKey) {
      filteredResults = {order, key: filterKey, cursor: 0, indices: []};
    }
    for (; filteredResults.cursor < order.length; filteredResults.cursor++) {
      const index = order[filteredResults.cursor];
      const r = results[index];
      if ((review === 'all' || (review === 'needs-review' ? needsReview(r) : !r.error && !needsReview(r)))
        && (category === 'all' || (category === 'failed' ? Boolean(r.error) : !r.error && r.category === category))
        && r.log.toLowerCase().includes(search)
        && (source === 'all' || r.sourcePatterns?.includes(source) || r.source === source)
        && (host === 'all' || resultHostId(r) === host)) filteredResults.indices.push(index);
    }
    visible = filteredResults.indices;
  }
  const pageSize = pagedView ? resultsPerPage : 100;
  const pages = pagedView ? page+1+(pagedView.hasNext?1:0) : Math.max(1, Math.ceil(visible.length / pageSize));
  page = Math.min(page, pages - 1);
  $('page-info').textContent = pagedView ? `Page ${page+1} · ${visible.length} results shown` : `Page ${page + 1} of ${pages} · ${visible.length} results`;
  $('previous').disabled = page === 0;
  $('next').disabled = page >= pages - 1;
  const pageResults = (pagedView ? visible : visible.slice(Math.max(0, visible.length-(page+1)*pageSize),visible.length-page*pageSize)).toReversed().map(index=>results[index]);
  if (!updatesPaused) { displayedOrder = completionOrder; displayedCount = completionOrder.length; }
  if (incremental && pageResults.length === renderedPage.length && pageResults.every((result, index) => result === renderedPage[index])) return;
  const previousRows = incremental ? renderedRows : new Map();
  renderedRows = new Map();
  renderedPage = pageResults;
  const rows = [];
  for (const result of pageResults) {
    if (previousRows.has(result)) {
      const row = previousRows.get(result); renderedRows.set(result, row); rows.push(row); continue;
    }
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
        ['Work Ticket (Noul)', Number.isFinite(result.ticketProbability) ? `${(result.ticketProbability * 100).toFixed(1)}%` : 'Not available', 'Yes probability · 0% No → 100% Yes', 'decision-noul', Number.isFinite(result.ticketProbability) ? [['Yes', result.ticketProbability], ['No', 1 - result.ticketProbability]] : []],
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
      const label = element('label', 'Reviewer Category (Choice): ', 'reviewer-category');
      const select = element('select', '', 'correction');
      select.setAttribute('aria-label', `Reviewer category: ${result.log}`);
      select.append(new Option('Not reviewed', ''));
      for (const [key, name] of Object.entries(labels)) select.append(new Option(name, key));
      select.value = result.reviewerCategory || '';
      select.onchange = async () => {
        const previous = result.reviewerCategory;
        result.reviewerCategory = select.value;
        if (pagedView) {
          try {
            const response=await fetch(`/api/jobs/${activeJobId}/review`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sequence:resultCursors.get(result),category:select.value})});
            const data=await response.json();if(!response.ok)throw new Error(data.error);
          } catch(error) {result.reviewerCategory=previous;select.value=previous || '';handleMessage('message',error.message,true);}
        }
        if (jsonView.open) jsonText.textContent = JSON.stringify(orderedResult(result), null, 2);
      };
      label.append(select);
      row.append(label);
    }
    row.append(jsonView);
    renderedRows.set(result, row); rows.push(row);
  }
  if (!visible.length) rows.push(element('p', 'No results to display.'));
  const container = $('results');
  for (let index = 0; index < rows.length; index++) {
    if (container.children[index] !== rows[index]) {
      container.insertBefore(rows[index], container.children[index] || null);
    }
  }
  while (container.children.length > rows.length) {
    container.removeChild(container.children[container.children.length - 1]);
  }
  $('export-reviewed').disabled = $('export').disabled = pagedView ? !completed : !completed || busy || activeJobState === 'running';
}
function scheduleRender() {
  if (renderTimer) return;
  renderTimer = setTimeout(() => {
    renderTimer = undefined;
    if (!document.hidden && currentView === 'main') render(false, true);
  }, 300);
}
$('pause-updates').onclick = () => {
  if (pagedView) {
    if(page>0){updatesPaused=false;page=0;pagedView.cursors=[null];return handleRefreshResults(true);}
    updatesPaused=!updatesPaused;
    if(!updatesPaused) {page=0;pagedView.cursors=[null];return handleRefreshResults(true);}
    render(false,true);return;
  }
  updatesPaused = !updatesPaused;
  if (updatesPaused) pausedOrder = displayedOrder.slice(0, displayedCount);
  clearTimeout(renderTimer);
  renderTimer = undefined;
  if (updatesPaused) render(false);
  else { pausedOrder = []; render(); }
};
$('source-mode').onchange = handleTaskMode;
$('task-trigger').onchange = handleTaskMode;
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
      try { jobStorage.removeItem('deciflow-job-id'); } catch { /* Storage may be disabled. */ }
      handleMessage('message','Previous job is unavailable. The server may have restarted.',true);
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
  if (job.pagedResults) return handlePagedProcessing(job);
  pagedView=null;
  if (busy) return;
  const sources = job.settings.sources || [];
  $('result-context').textContent=`${job.settings.taskName || registeredTasks.find(task=>task.id===job.settings.taskId)?.name || 'Task execution'} · Started: ${taskTime(job.startedAt)} (UTC) · Run: ${job.jobId}`;
  sourceMode = job.settings.mode;
  busy = true;
  renderTaskMonitor();
  activeRequest = new AbortController();
  $('export-reviewed').disabled = $('export').disabled = true;
  $('message').className = '';
  handleMessage('message',`${engineLabel} is classifying your data…`);
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
        runHosts=event.hosts;
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
      handleMessage('message',total === null ? `${sourceMode === 'realtime' ? 'Realtime' : 'Batch'} · ${completed.toLocaleString('en-US')} chunks completed${completed ? '' : ' · Waiting for data…'}` : `Classifying · ${completed.toLocaleString('en-US')} / ${total.toLocaleString('en-US')} chunks · ${total.toLocaleString('en-US')} ${engineLabel} requests planned`);
      scheduleRender();
    });
    handleMessage('message',`${activeJobState === 'stopped' ? 'Stopped' : activeJobState === 'failed' ? 'Failed' : 'Completed'} · ${results.filter(r => r.error).length} failed requests · ${results.filter(r => r.actionExecution?.status === 'failed').length} failed Actions`);
  } catch (error) {
    $('message').className = error.name === 'AbortError' ? '' : 'error-message';
    handleMessage('message',`${error.name === 'AbortError' ? 'Processing stopped' : error.message} · ${started ? `${completed} completed results have been retained.` : 'Previous results have been retained.'}`,true);
  } finally {
    busy = false;
    activeRequest.abort();
    activeRequest = undefined;
    clearTimeout(renderTimer);
    renderTimer = undefined;
    if (started || completed) render(false, true);
    $('export-reviewed').disabled = $('export').disabled = !completed || activeJobState === 'running';
    handleLoadTasks();
    if (activeJobState === 'running') {
      $('message').textContent += ' · Server job continues. Click its Task in the running list to reconnect.';
    }
  }
}
function handleResultFilter() {
  page = 0;
  if(pagedView){pagedView.cursors=[null];return handleRefreshResults(true);}
  if (completed) render();
}
$('review-filter').onchange = handleResultFilter;
$('category-filter').onchange = handleResultFilter;
let resultSearchTimer;
$('log-search').oninput = () => {
  if(!pagedView)return handleResultFilter();
  clearTimeout(resultSearchTimer);resultSearchTimer=setTimeout(()=>handleResultFilter().catch(error=>{handleMessage('message',error.message,true);}),250);
};
$('source-filter').onchange = handleResultFilter;
$('host-filter').onchange = handleResultFilter;
$('previous').onclick = () => { if(pagedView){page--;pagedView.cursors.pop();return handleRefreshResults(true);}page--;render(); };
$('next').onclick = () => { if(pagedView){pagedView.cursors.push(pagedView.items.at(-1)?.sequence);page++;return handleRefreshResults(true);}page++;render(); };
function handleExportResults(reviewedOnly=false) {
  if(pagedView){
    const form=document.createElement('form');form.method='POST';form.action=`/api/jobs/${activeJobId}/${reviewedOnly?'export-reviewed':'export'}`;
    document.body.append(form);form.submit();form.remove();return;
  }
  if (!completed || busy || activeJobState === 'running') return;
  const exportedResults=results.filter(result=>result && (!reviewedOnly || (result.reviewerCategory && result.reviewerCategory!==result.category && !result.error))).map(orderedResult);
  const blob = new Blob([JSON.stringify({ mode: resultEngine, sourceMode: resultSourceMode, total, completed, elapsedMs, activeProcessingMs, results: exportedResults,...(reviewedOnly?{exportScope:'reviewed-changes',exported:exportedResults.length}:{}) }, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = reviewedOnly?'deciflow-reviewed-results.json':'deciflow-results.json';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$('export').onclick=()=>handleExportResults();
$('export-reviewed').onclick=()=>handleExportResults(true);
let resetInfo=null;
let resettingDeciFlow=false;
async function handleLoadResetStatus() {
  if(resettingDeciFlow)return;
  $('reset-deciflow').disabled=true;
  try{
    const response=await fetch('/api/reset/status',{method:'POST'});
    if(response.status===404 || response.status===405)throw new Error('Reset API is unavailable. Restart the DeciFlow UI server or container.');
    const data=await response.json();if(!response.ok)throw new Error(data.error);
    resetInfo=data;$('reset-data-directory').textContent=data.dataDirectory;
    $('reset-deciflow').disabled=Boolean(data.resetting);
    handleMessage('configuration-message',data.resetError || (data.resetting?'Reset is in progress…':''),Boolean(data.resetError));
  }catch(error){handleMessage('configuration-message',error.message,true);}
}
$('reset-deciflow').onclick=async()=>{
  if(!resetInfo || resettingDeciFlow)return;
  const dialog=$('reset-dialog');dialog.returnValue='cancel';$('reset-confirm-directory').textContent=resetInfo.dataDirectory;
  const confirmed=await new Promise(resolve=>{dialog.onclose=()=>resolve(dialog.returnValue==='reset');dialog.showModal();});
  if(!confirmed)return;
  resettingDeciFlow=true;$('reset-deciflow').disabled=true;
  let accepted=false;
  try{
    const response=await fetch('/api/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirmation:'RESET DECIFLOW'})});
    const data=await response.json();if(!response.ok)throw new Error(data.error);
    accepted=true;
    handleMessage('configuration-message','Reset accepted. Stopping Tasks, deleting data, and restarting…');
    for(const storage of [globalThis.localStorage,globalThis.sessionStorage]){
      if(!storage)continue;
      try{for(const key of ['deciflow-source-preferences','deciflow-job-id'])storage.removeItem?.(key);}catch{/* Browser storage may be disabled. */}
    }
    const deadline=Date.now()+60000;
    while(Date.now()<deadline){
      await new Promise(resolve=>setTimeout(resolve,1000));
      let status;
      try{
        const check=await fetch('/api/reset/status',{method:'POST'});
        if(check.ok)status=await check.json();
      }catch{/* The server closes connections while restarting. */}
      if(status && status.instanceId!==data.instanceId && !status.resetting){
        if(status.resetError)throw new Error(status.resetError);
        globalThis.location.reload();return;
      }
    }
    throw new Error('The server has not returned yet. Refresh this page after checking the server logs.');
  }catch(error){handleMessage('configuration-message',error.message,true);}
  finally{resettingDeciFlow=false;if(!accepted)$('reset-deciflow').disabled=false;}
};
async function handleLoadResultSettings() {
  try {
    const response=await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    const data=await response.json();if(!response.ok)throw new Error(data.error);
    resultsPerPage=data.resultsPerPage;$('results-per-page').value=String(resultsPerPage);
    if(!completed)$('page-info').textContent=`${resultsPerPage} results per page`;
  }catch(error){handleMessage('results-settings-message',error.message,true);}
}
$('results-settings-form').onsubmit=async event=>{
  event.preventDefault();$('save-results-settings').disabled=true;
  try{
    const response=await fetch('/api/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({resultsPerPage:Number($('results-per-page').value)})});
    const data=await response.json();if(!response.ok)throw new Error(data.error);
    resultsPerPage=data.resultsPerPage;handleMessage('results-settings-message','Settings saved.');
    if(pagedView){page=0;pagedView.cursors=[null];await handleRefreshResults(true);}
  }catch(error){handleMessage('results-settings-message',error.message,true);}
  finally{$('save-results-settings').disabled=false;}
};
async function handleRefreshResults(reset=false,poll=false) {
  const view=pagedView;if(!view)return;
  const revision=++view.revision;
  const held=poll && (page>0 || updatesPaused);
  const after=!reset && poll && !held ? view.sequence : null;
  const body={category:$('category-filter').value,review:$('review-filter').value,
    host:$('host-filter').value || 'all',source:$('source-filter').value || 'all',
    search:$('log-search').value,onlySummary:held};
  if(after!==null)body.after=after;
  if(page>0){body.before=view.cursors[page];body.through=view.through;}
  const response=await fetch(`/api/jobs/${view.id}/results`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:activeRequest?.signal});
  const data=await response.json();if(!response.ok)throw new Error(data.error);
  if(pagedView!==view || revision!==view.revision)return;
  view.summary={...data.summary,hosts:new Map(Object.entries(data.summary.hosts)),sources:new Map(Object.entries(data.summary.sources))};
  const snapshot=data.snapshot;activeJobState=snapshot.state;completed=data.summary.total;
  elapsedMs=snapshot.elapsedMs || 0;activeProcessingMs=snapshot.activeProcessingMs || 0;
  resultEngine=data.summary.engine || engine;resultSourceMode=snapshot.settings.mode;
  runHosts=snapshot.hosts || [];runSourcePatterns=[...view.summary.sources.keys()];
  if(data.items){
    const previous=new Map(view.items.map(item=>[item.sequence,item]));
    let items=data.items.map(item=>previous.get(item.sequence) || item);
    const latest=items[0]?.result;
    if(latest?.engineConnection)handleEngineConnection(latest.engineConnection);
    else if(latest && !latest.error)handleEngineConnection('connected');
    const merged=after!==null?[...items,...view.items].filter((item,index,array)=>array.findIndex(other=>other.sequence===item.sequence)===index):items;
    view.hasNext=after!==null ? view.hasNext || data.hasNext || merged.length>data.limit : data.hasNext;
    resultsPerPage=data.limit;view.items=merged.slice(0,resultsPerPage);
    results=view.items.toReversed().map(item=>{resultCursors.set(item.result,item.sequence);return item.result;});
    completionOrder=results.map((_,index)=>index);view.sequence=data.sequence;
    if(page===0)view.through=data.sequence;
    if(page===0)view.snapshotTotal=completed;
  }
  $('result-context').textContent=`${snapshot.settings.taskName || 'Task execution'} · Started: ${taskTime(snapshot.startedAt)} (UTC) · Run: ${view.id}`;
  handleMessage('message',`${activeJobState==='running'?(snapshot.settings.mode==='realtime'?'Realtime':'Batch'):activeJobState} · ${completed.toLocaleString('en-US')} chunks completed`);
  render(false,true);
}
function handlePageDelay(signal) {
  return new Promise(resolve=>{
    const finish=()=>{clearTimeout(timer);signal.removeEventListener('abort',finish);resolve();};
    const timer=setTimeout(finish,1000);signal.addEventListener('abort',finish,{once:true});
    if(signal.aborted)finish();
  });
}
async function handlePagedProcessing(job) {
  if(busy)return;
  busy=true;total=null;activeJobId=job.jobId;activeJobState=job.state;rememberJob(activeJobId);
  activeRequest=new AbortController();const controller=activeRequest;
  pagedView={id:job.jobId,items:[],cursors:[null],sequence:0,through:null,hasNext:false,snapshotTotal:0,revision:0};
  page=0;updatesPaused=false;results=[];completionOrder=[];pausedOrder=[];displayedOrder=[];
  statisticsResults=undefined;filteredResults=undefined;recentCompletions=[];renderedRows.clear();renderedPage=[];
  $('category-filter').value='all';$('review-filter').value='all';$('source-filter').value='all';$('host-filter').value='all';$('log-search').value='';
  try{
    await handleLoadResultSettings();await handleRefreshResults(true);
    while(activeJobState==='running' && !controller.signal.aborted){
      await handlePageDelay(controller.signal);if(controller.signal.aborted)break;
      if(!document.hidden && currentView==='main')await handleRefreshResults(false,true);
    }
  }catch(error){if(error.name!=='AbortError'){$('message').className='error-message';handleMessage('message',error.message,true);}}
  finally{busy=false;controller.abort();activeRequest=undefined;$('export-reviewed').disabled = $('export').disabled =!completed;handleLoadTasks();}
}
handleLoadResultSettings();
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
  await sourceLoadPromise;
  handleRestoreJob().then(()=>{monitoringReady=true;handleLoadTasks();}).catch(error => { $('message').className = 'error-message'; handleMessage('message',error.message,true); });
}).catch(error => { handleMessage('status',error.message || 'Server connection failed',true); });

function handleRoute() {
  const hash = globalThis.location?.hash;
  const section = (hash === '#settings/configuration' || hash === '#settings/results') ? 'configuration' : hash === '#settings/ssh-keys' ? 'ssh-keys' : hash === '#settings/ssh-hosts' ? 'ssh-hosts' : null;
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
  handleMessage('source-message','Loading sources…');
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
    renderSources(); renderTaskMonitor(); $('save-sources').disabled = false; handleMessage('source-message','');
    if (!busy && !restoringJob) updateSourceSettings();
  } catch (error) { handleMessage('source-message',error.message,true); }
}
renderSources();
const sourceLoadPromise = handleLoadSources();
handleLoadHosts();

handleLoadTasks();
if (globalThis.setInterval) globalThis.setInterval(() => { if (!document.hidden) handleLoadTasks(); }, 5000);

if (document.addEventListener) document.addEventListener('visibilitychange', () => {
  if (!document.hidden && currentView === 'main') scheduleRender();
});
