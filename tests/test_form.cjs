const {test} = require('node:test');
const assert = require('node:assert/strict');
const form = require('../static/annotation-form.js');
const pure = () => ({q1:{a:null},q2:'a',q3:['n'],q3_details:{}});

test('Q2 accepts three grades and rejects removed intermediate choices',()=>{
  for(const q2 of ['a','b','c']) assert.equal(form.problem({...pure(),q2}),'');
  for(const q2 of [null,'d','n','ab','bc']) assert.match(form.problem({...pure(),q2}),/Q2/);
});

test('single SBNP needs no area; mixed regions need every area and skip later questions',()=>{
  const labels=pure(); assert.equal(form.problem(labels),'');
  form.toggleLayer(labels,'b'); assert.match(form.problem(labels),/面积/);
  assert.equal(labels.q2,'n'); assert.equal(labels.q3,null);
  labels.q1.a='k'; labels.q1.b='i'; assert.equal(form.problem(labels),'');
  form.toggleLayer(labels,'b'); assert.equal(labels.q1.a,null);
  assert.equal(labels.q2,null); assert.deepEqual(labels.q3,[]);
  assert.match(form.problem(labels),/Q2/);
});
test('a single non-SBNP layer can be submitted with later questions skipped',()=>{
  const labels={q1:{b:null},q2:null,q3:[],q3_details:{}};
  form.reconcile(labels); assert.equal(form.problem(labels),'');
  assert.equal(labels.q3,null);
});
test('both overlap cell types may be selected; deselecting parent clears them',()=>{
  const labels=pure(); form.toggleInterference(labels,'e');
  assert.deepEqual(labels.q3,['e']); assert.match(form.problem(labels),/细胞类型/);
  form.toggleDetail(labels,'e','e1'); form.toggleDetail(labels,'e','e2');
  assert.deepEqual(labels.q3_details.e,['e1','e2']); assert.equal(form.problem(labels),'');
  form.toggleInterference(labels,'e'); assert.deepEqual(labels.q3_details,{});
});
test('immune count is mandatory and mutually exclusive',()=>{
  const labels=pure(); form.toggleInterference(labels,'f'); assert.match(form.problem(labels),/数量/);
  for(const value of ['f1','f2','f3','f1']) {
    form.toggleDetail(labels,'f',value);
    assert.equal(labels.q3_details.f,value); assert.equal(form.problem(labels),'');
  }
});
test('inline details select their factor directly and clear none',()=>{
  const labels=pure();
  form.toggleDetail(labels,'e','e1'); form.toggleDetail(labels,'e','e2');
  assert.deepEqual(labels.q3,['e']); assert.deepEqual(labels.q3_details.e,['e1','e2']);
  form.toggleDetail(labels,'f','f2');
  assert.deepEqual(labels.q3,['e','f']); assert.equal(labels.q3_details.f,'f2');
  form.toggleInterference(labels,'f'); assert.equal(labels.q3_details.f,undefined);
  form.toggleInterference(labels,'n');
  form.toggleDetail(labels,'f','f3');
  assert.deepEqual(labels.q3,['f']); assert.deepEqual(labels.q3_details,{f:'f3'});
  form.toggleLayer(labels,'b');
  form.toggleDetail(labels,'e','e1'); form.toggleDetail(labels,'f','f1');
  assert.equal(labels.q3,null); assert.deepEqual(labels.q3_details,{});
});
test('none clears all interference details; mixed layers clear all later answers',()=>{
  const labels=pure(); form.toggleInterference(labels,'e'); form.toggleDetail(labels,'e','e1');
  form.toggleInterference(labels,'f'); form.toggleDetail(labels,'f','f1');
  form.toggleInterference(labels,'n'); assert.deepEqual(labels.q3,['n']); assert.deepEqual(labels.q3_details,{});
  form.toggleLayer(labels,'c'); assert.equal(labels.q3,null); assert.deepEqual(labels.q3_details,{});
  form.toggleInterference(labels,'e'); form.toggleDetail(labels,'e','e2'); assert.equal(labels.q3,null);
});
test('removing the only layer restores a completely unanswered form',()=>{
  const labels=pure(); form.toggleLayer(labels,'a');
  assert.deepEqual(labels,{q1:{},q2:null,q3:[],q3_details:{}}); assert.match(form.problem(labels),/Q1/);
});
