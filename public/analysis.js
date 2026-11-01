const $=id=>document.getElementById(id);
const params=new URLSearchParams(location.search);
const run=params.get('run'),sequence=Number(params.get('result'));
const language=navigator.language?.toLowerCase().startsWith('ko')?'ko':'en';
let available=false,busy=false;

async function requestAnalysis(generate) {
  const response=await fetch(`/api/jobs/${encodeURIComponent(run)}/analysis`,{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({sequence,generate,language}),
  });
  let data;
  try{data=await response.json();}
  catch{throw new Error(`AI Analysis returned an invalid response (HTTP ${response.status}).`);}
  if(!response.ok)throw new Error(data.error || `AI Analysis failed (HTTP ${response.status}).`);
  return data;
}
function showError(error) {
  $('analysis-status').textContent=error.message;
  $('analysis-status').className='error-message';
}
function renderAnalysisMetadata(metadata) {
  const usage=metadata.usage || {};
  const created=typeof metadata.createdAt==='number'?new Date(metadata.createdAt*1000):null;
  const fields=[
    ['Requested Model',metadata.requestedModel],['Response Model',metadata.model],
    ['Response Status',metadata.status],
    ['Request Duration',Number.isFinite(metadata.elapsedMs)?`${(metadata.elapsedMs/1000).toFixed(2)} s (${metadata.elapsedMs} ms)`:null],
    ['Input Tokens',usage.input_tokens],['Output Tokens',usage.output_tokens],['Total Tokens',usage.total_tokens],
    ['Cached Input Tokens',usage.input_tokens_details?.cached_tokens],
    ['Reasoning Tokens',usage.output_tokens_details?.reasoning_tokens],
    ['Service Tier',metadata.serviceTier],['Response ID',metadata.responseId],['Request ID',metadata.requestId],
    ['Created At (UTC)',created && Number.isFinite(created.getTime())?created.toISOString():null],
  ];
  const list=$('analysis-metadata-values');list.replaceChildren();
  for(const [label,value] of fields){
    const item=document.createElement('div'),term=document.createElement('dt'),description=document.createElement('dd');
    term.textContent=label;description.textContent=value===undefined || value===null || value===''?'Not Reported':String(value);
    item.append(term,description);list.append(item);
  }
  $('analysis-metadata').hidden=false;
}
async function handleAnalyze() {
  if(busy || !available)return;
  busy=true;$('analyze').disabled=true;
  $('analysis-status').className='';$('analysis-status').textContent='Analyzing…';
  $('analysis-content').textContent='';$('analysis-metadata').hidden=true;
  $('analysis-metadata-values').replaceChildren();
  try {
    const data=await requestAnalysis(true);
    $('analysis-content').textContent=data.analysis;
    renderAnalysisMetadata(data.metadata);
    $('analysis-status').textContent='Analysis complete.';
  }catch(error){showError(error);}
  finally{busy=false;$('analyze').disabled=!available;}
}
$('analyze').onclick=handleAnalyze;
$('close-analysis').onclick=()=>globalThis.close();
async function handleLoadAnalysis() {
  try {
    if(!run || !/^[a-f0-9]{32}$/.test(run) || !Number.isSafeInteger(sequence) || sequence<1)throw new Error('Select a saved result from DeciFlow.');
    const data=await requestAnalysis(false);
    available=data.configuration.available;
    $('identity').textContent=`Result #${data.resultNumber} · Run: ${run}`;
    $('analysis-input').textContent=data.context.input;
    $('analysis-input-section').hidden=false;
    const {input,...context}=data.context;
    $('analysis-context').textContent=JSON.stringify(context,null,2);
    $('analysis-evidence').hidden=false;
    if(!available)throw new Error('Configure OPENAI_API_KEY and OPENAI_ANALYSIS_MODEL in .env.');
    await handleAnalyze();
  }catch(error){showError(error);}
}
handleLoadAnalysis();
