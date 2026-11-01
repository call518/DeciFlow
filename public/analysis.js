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
async function handleAnalyze() {
  if(busy || !available)return;
  busy=true;$('analyze').disabled=true;
  $('analysis-status').className='';$('analysis-status').textContent='Analyzing…';
  $('analysis-content').textContent='';$('analysis-model').textContent='';
  try {
    const data=await requestAnalysis(true);
    $('analysis-content').textContent=data.analysis;
    $('analysis-model').textContent=`Analysis Model: ${data.model}`;
    $('analysis-status').textContent='Analysis complete.';
  }catch(error){showError(error);}
  finally{busy=false;$('analyze').disabled=!available;}
}
$('analyze').onclick=handleAnalyze;
async function handleLoadAnalysis() {
  try {
    if(!run || !/^[a-f0-9]{32}$/.test(run) || !Number.isSafeInteger(sequence) || sequence<1)throw new Error('Select a saved result from DeciFlow.');
    const data=await requestAnalysis(false);
    available=data.configuration.available;
    $('identity').textContent=`Result #${data.resultNumber} · Run: ${run}`;
    $('analysis-input').textContent=data.context.input;
    const {input,...context}=data.context;
    $('analysis-context').textContent=JSON.stringify(context,null,2);
    $('analysis-evidence').hidden=false;
    if(!available)throw new Error('Configure OPENAI_API_KEY and OPENAI_ANALYSIS_MODEL in .env.');
    await handleAnalyze();
  }catch(error){showError(error);}
}
handleLoadAnalysis();
