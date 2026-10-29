'use strict';
// Shared form transitions are kept independent of the DOM for keyboard/UI tests.
(function(root) {
  const applicable = labels => Object.keys(labels.q1).length === 1 && 'a' in labels.q1;
  function reconcile(labels) {
    const keys = Object.keys(labels.q1);
    if(keys.length === 1) labels.q1[keys[0]] = null;
    if(!applicable(labels)) {
      labels.q2 = keys.length ? 'n' : null;
      labels.q3 = keys.length ? null : [];
      labels.q3_details = {};
    } else {
      if(labels.q2 === 'n') labels.q2 = null;
      labels.q3 ??= [];
      labels.q3_details ??= {};
      for(const key of ['e','f']) if(!labels.q3.includes(key)) delete labels.q3_details[key];
    }
    return labels;
  }
  function toggleLayer(labels, key) {
    if(key in labels.q1) delete labels.q1[key]; else labels.q1[key] = null;
    return reconcile(labels);
  }
  function toggleInterference(labels, key) {
    if(!applicable(labels)) return;
    const selected = labels.q3.includes(key);
    labels.q3 = selected ? labels.q3.filter(x=>x!==key) : key==='n' ? ['n'] : [...labels.q3.filter(x=>x!=='n'),key];
    reconcile(labels);
  }
  function toggleDetail(labels, group, value) {
    if(!applicable(labels)) return;
    if(!labels.q3.includes(group)) toggleInterference(labels,group);
    if(group==='e') {
      const current = labels.q3_details.e || [];
      labels.q3_details.e = current.includes(value) ? current.filter(x=>x!==value) : [...current,value];
    } else if(group==='f') labels.q3_details.f = value;
  }
  function problem(labels) {
    if(!labels) return '等待图像';
    const keys = Object.keys(labels.q1);
    if(!keys.length) return 'Q1 · 请至少选择一个层面或区域';
    if(keys.length>1 && Object.values(labels.q1).some(v=>!v)) return 'Q1 · 请为每个所选层面指定面积';
    if(!applicable(labels)) return '';
    if(!['a','b','c'].includes(labels.q2)) return 'Q2 · 请选择良、中或差';
    if(!labels.q3?.length) return 'Q3 · 请选择干扰因素或“不适用”';
    if(labels.q3.includes('e') && !labels.q3_details.e?.length) return 'Q3 · 请选择重叠的细胞类型，可多选';
    if(labels.q3.includes('f') && !labels.q3_details.f) return 'Q3 · 请选择免疫细胞数量';
    return '';
  }
  const api = {applicable,reconcile,toggleLayer,toggleInterference,toggleDetail,problem};
  if(typeof module!=='undefined' && module.exports) module.exports = api; else root.CCMForm = api;
})(globalThis);
