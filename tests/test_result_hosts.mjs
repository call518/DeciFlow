import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { test } from 'node:test';

const source = readFileSync(new URL('../public/app.js', import.meta.url), 'utf8');
const context = vm.createContext({});
vm.runInContext(source.slice(source.indexOf('function orderedResult('), source.indexOf('function renderJsonMessage(')), context);

test('response diagnostics and JSON ordering retain collection and processing hosts', () => {
  const result = vm.runInContext(`responseMessage({sourceHosts:['web-01'],deciflowHost:'analysis-01',providerResponse:{model:'test'}})`, context);
  assert.deepEqual(Array.from(result.sourceHosts), ['web-01']);
  assert.equal(result.deciflowHost, 'analysis-01');
  assert.equal(result.body.model, 'test');
  const ordered = vm.runInContext(`orderedResult({log:'event',sourceHosts:['web-01'],deciflowHost:'analysis-01'})`, context);
  assert.deepEqual(Object.keys(ordered), ['sourceHosts', 'deciflowHost', 'log']);
});
