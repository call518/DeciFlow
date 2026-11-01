import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {test} from 'node:test';

const source=readFileSync(new URL('../public/analysis.js',import.meta.url),'utf8').replace(/\nhandleLoadAnalysis\(\);\s*$/,'');
function page(fetch,search='?run=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa&result=12'){
  const nodes=new Map();
  const node=()=>({textContent:"",className:"",disabled:true,hidden:true,children:[],append(...items){this.children.push(...items);},replaceChildren(...items){this.children=items;}});
  const context=vm.createContext({URLSearchParams,location:{search},navigator:{language:'ko-KR'},fetch,
    document:{createElement:()=>node(),getElementById:id=>{if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);}}});
  vm.runInContext(source,context);return {nodes,context};
}
const preview=available=>({configuration:{available,model:'analysis-model'},resultNumber:7,context:{input:'<script>untrusted input</script>',criteria:{instructions:'saved rules'},decisions:{category:{choice:'normal'}}}});
const ok=data=>({ok:true,status:200,json:async()=>data});

test('Analysis tab previews evidence without a paid request when settings are incomplete',async()=>{
  const calls=[];const {nodes,context}=page(async(url,options)=>{calls.push(JSON.parse(options.body));return ok(preview(false));});
  await vm.runInContext('handleLoadAnalysis()',context);
  assert.equal(calls.length,1);assert.equal(calls[0].generate,false);
  assert.equal(nodes.get('analysis-input').textContent,'<script>untrusted input</script>');
  assert.match(nodes.get('analysis-status').textContent,/OPENAI_API_KEY and OPENAI_ANALYSIS_MODEL/);
  assert.equal(nodes.get('analyze').disabled,true);
});

test('Analysis tab requests once, renders plain text and allows explicit retry',async()=>{
  const calls=[];const {nodes,context}=page(async(url,options)=>{
    const body=JSON.parse(options.body);calls.push(body);
    return ok(body.generate?{analysis:'<img onerror=alert(1)> Evidence review.',metadata:{model:'actual-model',requestedModel:'configured-model',usage:{input_tokens:10,output_tokens:5,total_tokens:15,input_tokens_details:{cached_tokens:0}}}}:preview(true));
  });
  await vm.runInContext('handleLoadAnalysis()',context);
  assert.deepEqual(calls.map(x=>x.generate),[false,true]);
  assert.equal(calls[1].language,'ko');
  assert.equal(nodes.get('analysis-content').textContent,'<img onerror=alert(1)> Evidence review.');
  const metadata=Object.fromEntries(nodes.get('analysis-metadata-values').children.map(item=>item.children.map(part=>part.textContent)));
  assert.equal(metadata['Response Model'],'actual-model');
  assert.equal(metadata['Requested Model'],'configured-model');
  assert.equal(metadata['Total Tokens'],'15');
  assert.equal(metadata['Cached Input Tokens'],'0');
  assert.equal(metadata['Reasoning Tokens'],'Not Reported');
  assert.equal(nodes.get('analysis-metadata').hidden,false);
  assert.equal(nodes.get('analyze').disabled,false);
  await nodes.get('analyze').onclick();assert.equal(calls.length,3);
});

test('Analysis errors do not automatically retry and invalid links make no requests',async()=>{
  const calls=[];const {nodes,context}=page(async(url,options)=>{
    const body=JSON.parse(options.body);calls.push(body);
    return body.generate?{ok:false,status:502,json:async()=>({error:'OpenAI timed out.'})}:ok(preview(true));
  });
  await vm.runInContext('handleLoadAnalysis()',context);
  assert.equal(calls.length,2);assert.equal(nodes.get('analysis-status').className,'error-message');
  assert.match(nodes.get('analysis-status').textContent,/timed out/);assert.equal(nodes.get('analyze').disabled,false);
  const invalid=page(()=>{throw Error('must not fetch');},'?run=invalid&result=1');
  await vm.runInContext('handleLoadAnalysis()',invalid.context);
  assert.match(invalid.nodes.get('analysis-status').textContent,/Select a saved result/);
});

test('Analysis generation rejects duplicate clicks while a request is pending',async()=>{
  let release,requests=0;
  const {context}=page(async()=>{requests++;await new Promise(resolve=>{release=resolve;});return ok({analysis:'review',metadata:{model:'analysis-model'}});});
  const pending=vm.runInContext('available=true;handleAnalyze()',context);
  await vm.runInContext('handleAnalyze()',context);assert.equal(requests,1);
  release();await pending;
});

test('Analysis metadata preserves zero counts and missing values without making requests',()=>{
  const {nodes,context}=page(()=>{throw Error('metadata rendering must not fetch');});
  const metadata={requestedModel:'configured',model:'<img onerror=alert(1)>',createdAt:1700000000,
    requestId:'req-long',responseId:'resp-long',status:'completed',elapsedMs:1234,
    usage:{input_tokens:0,output_tokens:0,total_tokens:0,output_tokens_details:{reasoning_tokens:0}}};
  context.metadata=metadata;vm.runInContext('renderAnalysisMetadata(metadata)',context);
  const fields=Object.fromEntries(nodes.get('analysis-metadata-values').children.map(item=>item.children.map(part=>part.textContent)));
  assert.equal(fields['Response Model'],'<img onerror=alert(1)>');
  assert.equal(fields['Input Tokens'],'0');assert.equal(fields['Reasoning Tokens'],'0');
  assert.equal(fields['Cached Input Tokens'],'Not Reported');
  assert.equal(fields['Request Duration'],'1.23 s (1234 ms)');
  assert.equal(fields['Created At (UTC)'],'2023-11-14T22:13:20.000Z');
});

test('Failed reanalysis clears metadata from the preceding successful response',async()=>{
  let count=0;
  const {nodes,context}=page(async()=>++count===1?ok({analysis:'review',metadata:{model:'first-model'}}):{ok:false,status:502,json:async()=>({error:'Retry failed.'})});
  await vm.runInContext('available=true;handleAnalyze()',context);
  assert.equal(nodes.get('analysis-metadata').hidden,false);
  await vm.runInContext('handleAnalyze()',context);
  assert.equal(nodes.get('analysis-metadata').hidden,true);
  assert.equal(nodes.get('analysis-metadata-values').children.length,0);
});
