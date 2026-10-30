const {test} = require('node:test');
const assert = require('node:assert/strict');
const form = require('../static/annotation-form.js');
const pure = () => ({q1:{a:null},q2:'a',q3:'a',q4:[],q4_details:{}});

test('Q2 accepts three grades and rejects removed intermediate choices',()=>{
  for(const q2 of ['a','b','c']) assert.equal(form.problem({...pure(),q2}),'');
  for(const q2 of [null,'d','n','ab','bc']) assert.match(form.problem({...pure(),q2}),/Q2/);
});
test('Q3 requires a single immune grade and Q4 may be empty',()=>{
  for(const q3 of ['a','b','c']) assert.equal(form.problem({...pure(),q3}),'');
  for(const q3 of [null,'n','f1',[],['a','b']]) assert.match(form.problem({...pure(),q3}),/Q3/);
});
test('mixed layers need every area and clear Q2 through Q4; switching back requires new grades',()=>{
  const labels=pure(); form.toggleDetail(labels,'c','c3');
  form.toggleLayer(labels,'b'); assert.match(form.problem(labels),/面积/);
  assert.equal(labels.q2,'n'); assert.equal(labels.q3,null);
  assert.equal(labels.q4,null); assert.deepEqual(labels.q4_details,{});
  labels.q1.a='k'; labels.q1.b='i'; assert.equal(form.problem(labels),'');
  form.toggleLayer(labels,'b'); assert.equal(labels.q1.a,null);
  assert.equal(labels.q2,null); assert.equal(labels.q3,null); assert.deepEqual(labels.q4,[]);
  assert.match(form.problem(labels),/Q2/);
  labels.q2='b'; assert.match(form.problem(labels),/Q3/);
});
test('a single non-SBNP layer skips all later questions and disables factor edits',()=>{
  const labels={...pure(),q1:{b:null}};
  form.reconcile(labels); assert.equal(form.problem(labels),'');
  form.toggleInterference(labels,'a'); form.toggleDetail(labels,'c','c2');
  assert.equal(labels.q3,null); assert.equal(labels.q4,null); assert.deepEqual(labels.q4_details,{});
});
test('brightness is mandatory only when selected and remains single choice',()=>{
  const labels=pure(); form.toggleInterference(labels,'c'); assert.match(form.problem(labels),/Q4/);
  for(const value of ['c1','c2','c3','c1']) {
    form.toggleDetail(labels,'c',value);
    assert.deepEqual(labels.q4_details,{c:value}); assert.equal(form.problem(labels),'');
  }
  form.toggleInterference(labels,'c');
  assert.deepEqual(labels.q4,[]); assert.deepEqual(labels.q4_details,{}); assert.equal(form.problem(labels),'');
});
test('inline brightness selects its parent and coexists with other factors',()=>{
  const labels=pure(); form.toggleInterference(labels,'a'); form.toggleInterference(labels,'b');
  form.toggleDetail(labels,'c','c2'); form.toggleInterference(labels,'d');
  assert.deepEqual(labels.q4,['a','b','c','d']); assert.deepEqual(labels.q4_details,{c:'c2'});
  form.toggleInterference(labels,'c'); assert.deepEqual(labels.q4,['a','b','d']);
  assert.deepEqual(labels.q4_details,{}); assert.equal(labels.q3,'a');
});
test('removing the only layer restores a completely unanswered form',()=>{
  const labels=pure(); form.toggleLayer(labels,'a');
  assert.deepEqual(labels,{q1:{},q2:null,q3:null,q4:[],q4_details:{}}); assert.match(form.problem(labels),/Q1/);
});
