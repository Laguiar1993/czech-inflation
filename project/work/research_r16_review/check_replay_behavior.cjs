// DOM-contract execution of the self-contained artifact; no browser or network.
// Checks program behavior and generated SVG text, not visual layout/pixel QA.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const path = process.argv[2];
const html = fs.readFileSync(path, 'utf8');
const data = JSON.parse(fs.readFileSync(path.replace(/[^/\\]+$/, 'replay_data.json'), 'utf8'));
const scripts = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
assert.equal(scripts.length, 1);
assert(!/<script[^>]+src=|<link[^>]+href=["']https?:/.test(html));
class Element {
  constructor(name, dataset = {}) { this.name=name; this.dataset=dataset; this.events={}; this.children={}; this.style={}; this.attrs={}; this._html=''; this.offsetWidth=270; }
  set innerHTML(s) {
    this._html=s;
    if(this.name==='rounds') {
      for(const kind of ['chart','score']) this.children['.'+kind]=[...s.matchAll(new RegExp(`class="${kind}" data-k="(\\d+)"`, 'g'))].map(m=>new Element(kind,{k:m[1]}));
    }
    if(this.name==='chart') { this.children.svg = new Element('svg'); this.children['.tip']=new Element('tip'); this.children['.cross']=new Element('cross'); this.children.svg.children['.cross']=this.children['.cross']; }
  }
  get innerHTML() { return this._html; }
  querySelectorAll(s) { return this.children[s] || []; }
  querySelector(s) { return this.children[s] || null; }
  addEventListener(name, fn) { this.events[name]=fn; }
  setAttribute(name,v) { this.attrs[name]=v; }
  getBoundingClientRect() { return {left:0,top:0,width:640,height:330}; }
}
const ids={}; for(const id of ['chips','rounds','eyebrow','method','clock-select','round-select']) ids[id]=new Element(id);
ids['clock-select'].value='report'; ids['round-select'].value='all';
const switches=new Element('switch-head'); const saved=new Map();
const document={getElementById:id=>{assert(id in ids);return ids[id];},querySelector:s=>{assert.equal(s,'.switch-head');return switches;}};
const context={document,localStorage:{getItem:k=>saved.get(k),setItem:(k,v)=>saved.set(k,v)},console};
vm.runInNewContext(scripts[0],context,{timeout:15000});
const rounds=ids.rounds;
function inspect(expected) {
  const charts=rounds.querySelectorAll('.chart'),scores=rounds.querySelectorAll('.score');
  assert.equal(charts.length,expected);assert.equal(scores.length,expected);
  for(const c of charts) { assert(c.innerHTML.includes('<svg')); assert(!/NaN|Infinity|undefined/.test(c.innerHTML)); c.events.pointermove({currentTarget:c,clientX:300}); assert.equal(c.querySelector('.tip').hidden,false); c.events.pointerleave({currentTarget:c}); assert.equal(c.querySelector('.tip').hidden,true); }
  for(const s of scores) assert(!/NaN|Infinity|undefined/.test(s.innerHTML));
}
inspect(data.reportsByClock.report.length);
for(const mode of ['report','cutoff']) {
  ids['clock-select'].value=mode; ids['clock-select'].events.change();
  ids['round-select'].value='all';ids['round-select'].events.change();inspect(data.reportsByClock[mode].length);
  for(const report of data.reportsByClock[mode]) { ids['round-select'].value=report.report_date;ids['round-select'].events.change();inspect(1); assert(rounds.innerHTML.includes(report.id)); }
}
ids['round-select'].value='all';ids['round-select'].events.change();
switches.events.click({target:{closest:()=>({dataset:{action:'all'}})}});
inspect(data.reportsByClock.cutoff.length);
assert.equal(Object.keys(rounds.querySelectorAll('.chart')[0]._ctx.maps).length,data.series.filter(x=>x.kind==='model').length);
const before=rounds.querySelectorAll('.score')[0].innerHTML;
const chip=new Element('chip');const input={dataset:{id:'STATE_FAST_R15'},closest:s=>s==='.chip'?chip:input};
ids.chips.events.change({target:input});
assert(!('STATE_FAST_R15' in rounds.querySelectorAll('.chart')[0]._ctx.maps));
ids.chips.events.change({target:input});
assert.equal(rounds.querySelectorAll('.score')[0].innerHTML,before);
switches.events.click({target:{closest:()=>({dataset:{action:'default'}})}});inspect(data.reportsByClock.cutoff.length);
const result={artifact:path,sha256:crypto.createHash('sha256').update(html).digest('hex'),report_rounds:data.reportsByClock.report.length,cutoff_rounds:data.reportsByClock.cutoff.length,checks:['all rounds both clocks','individual round selection','all models','checkbox off/on','reset','tooltip enter/leave','finite SVG geometry','score restore','no external resources'],limitation:'DOM-contract and SVG string checks; not browser layout or visual pixel inspection'};
console.log(JSON.stringify(result,null,2));
