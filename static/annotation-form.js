'use strict';
// Shared form transitions are kept independent of the DOM for keyboard/UI tests.
(function(root) {
  const applicable = labels => Object.keys(labels.q1).length === 1 && 'a' in labels.q1;
  function reconcile(labels) {
    const keys = Object.keys(labels.q1);
    if(keys.length === 1) labels.q1[keys[0]] = null;
    if(!applicable(labels)) {
      labels.q2 = keys.length ? 'n' : null;
      labels.q3 = null;
      labels.q4 = keys.length ? null : [];
      labels.q4_details = {};
    } else {
      if(labels.q2 === 'n') labels.q2 = null;
      labels.q4 ??= [];
      labels.q4_details ??= {};
      if(!labels.q4.includes('c')) delete labels.q4_details.c;
    }
    return labels;
  }
  function toggleLayer(labels, key) {
    if(key in labels.q1) delete labels.q1[key]; else labels.q1[key] = null;
    return reconcile(labels);
  }
  function toggleInterference(labels, key) {
    if(!applicable(labels)) return;
    labels.q4 = labels.q4.includes(key) ? labels.q4.filter(x=>x!==key) : [...labels.q4,key];
    reconcile(labels);
  }
  function toggleDetail(labels, group, value) {
    if(!applicable(labels)) return;
    if(!labels.q4.includes(group)) toggleInterference(labels,group);
    labels.q4_details[group] = value;
  }
  function problem(labels) {
    if(!labels) return '等待图像';
    const keys = Object.keys(labels.q1);
    if(!keys.length) return 'Q1 · 请至少选择一个层面或区域';
    if(keys.length>1 && Object.values(labels.q1).some(v=>!v)) return 'Q1 · 请为每个所选层面指定面积';
    if(!applicable(labels)) return '';
    if(!['a','b','c'].includes(labels.q2)) return 'Q2 · 请选择良、中或差';
    if(!['a','b','c'].includes(labels.q3)) return 'Q3 · 请选择免疫细胞分布：少、中或多';
    if(labels.q4.includes('c') && !['c1','c2','c3'].includes(labels.q4_details.c)) return 'Q4 · 请选择偏亮、偏暗或显著偏暗';
    return '';
  }
  const api = {applicable,reconcile,toggleLayer,toggleInterference,toggleDetail,problem};
  if(typeof module!=='undefined' && module.exports) module.exports = api; else root.CCMForm = api;
})(globalThis);
