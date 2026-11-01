import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {test} from 'node:test';

const source=readFileSync(new URL('../public/analysis.js',import.meta.url),'utf8').replace(/\nhandleLoadAnalysis\(\);\s*$/,'');
function page(fetch,search='?run=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa&result=12'){
  const nodes=new Map();
  const context=vm.createContext({URLSearchParams,location:{search},navigator:{language:'ko-KR'},fetch,
    document:{getElementById:id=>{if(!nodes.has(id))nodes.set(id,{textContent:'',className:'',disabled:true,hidden:true});return nodes.get(id);}}});
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
    return ok(body.generate?{analysis:'<img onerror=alert(1)> Evidence review.',model:'actual-model'}:preview(true));
  });
  await vm.runInContext('handleLoadAnalysis()',context);
  assert.deepEqual(calls.map(x=>x.generate),[false,true]);
  assert.equal(calls[1].language,'ko');
  assert.equal(nodes.get('analysis-content').textContent,'<img onerror=alert(1)> Evidence review.');
  assert.equal(nodes.get('analysis-model').textContent,'Analysis Model: actual-model');
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
  const {context}=page(async()=>{requests++;await new Promise(resolve=>{release=resolve;});return ok({analysis:'review',model:'analysis-model'});});
  const pending=vm.runInContext('available=true;handleAnalyze()',context);
  await vm.runInContext('handleAnalyze()',context);assert.equal(requests,1);
  release();await pending;
});
