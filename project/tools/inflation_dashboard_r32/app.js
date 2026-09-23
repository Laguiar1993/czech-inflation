"use strict";
const $ = id => document.getElementById(id);
const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt = (v,n=1) => v == null || !Number.isFinite(+v) ? "—" : (+v).toFixed(n);
const signed = (v,n=2) => v == null ? "—" : (v>0?"+":"") + fmt(v,n);
const month = (m,long=false) => new Date(m+"-01T12:00:00Z").toLocaleDateString("en-GB",{month:long?"long":"short",year:"numeric",timeZone:"UTC"});
const mnum = m => {const [y,n]=m.split("-").map(Number);return y*12+n-1;};
const mstr = n => Math.floor(n/12)+"-"+String(n%12+1).padStart(2,"0");
const tickMonth = n => new Date(mstr(Math.round(n))+"-01T12:00:00Z").toLocaleDateString("en-GB",{month:"short",year:"2-digit",timeZone:"UTC"});
const qmonths = q => {const y=+q.slice(0,4),k=+q.slice(-1);return [1,2,3].map(n=>y+"-"+String((k-1)*3+n).padStart(2,"0"));};
const qmean = (points,q) => {const map=new Map(points);const v=qmonths(q).map(m=>map.get(m));return v.every(x=>x!=null&&Number.isFinite(x))?v.reduce((a,b)=>a+b,0)/3:null;};
const M=DATA.monitor;
const COLORS={headline:"#17384b",core:"#2564a5",services:"#b2813b",goods:"#168478",ROSTER_R27:"#2564a5",R24_PATH:"#7a79a4",FAST:"#7b8f9c",LOCAL_R27FOOD:"#168478",CORE_PHASE_R29B:"#8362a9",cnb:"#b55052",realised:"#183642"};
const MODEL_LABELS={ROSTER_R27:"R27 research path",R24_PATH:"R24 predecessor",FAST:"FAST reference",LOCAL_R27FOOD:"Local core + R27 food · presentation",CORE_PHASE_R29B:"Core phase · not promoted",cnb:"CNB",realised:"Realised"};
let view="overview",forecastMode="outlook",driverLag=0;
let selectedModels=new Set(["ROSTER_R27","FAST","cnb","realised"]);
let activeClock="report",reportIndex=DATA.replay.reportsByClock.report.length-1;
function text(id,value){$(id).textContent=value;}
function tipAttr(text){return ' data-tip="'+esc(text)+'"';}
function chart(id, series, opts={}){
 const host=$(id);if(!host)return;
 const W=Math.max(330,host.clientWidth||700),H=opts.height||290,L=42,R=15,T=25,B=34;
 const points=series.flatMap(s=>s.points).filter(p=>Number.isFinite(p[1]));
 if(!points.length){host.innerHTML='<p class="caption">No observations on this support.</p>';return;}
 const lo=opts.start==null?Math.min(...points.map(p=>mnum(p[0]))):mnum(opts.start);
 const hi=opts.end==null?Math.max(...points.map(p=>mnum(p[0]))):mnum(opts.end);
 const inRange=points.filter(p=>mnum(p[0])>=lo&&mnum(p[0])<=hi);
 const quarters=(opts.quarters||[]).filter(q=>mnum(qmonths(q.quarter)[0])>=lo&&mnum(qmonths(q.quarter)[2])<=hi);
 const ys=[...inRange.map(p=>p[1]),...quarters.map(q=>q.value)];
 if(opts.target)ys.push(2);
 const rawLo=Math.min(...ys),rawHi=Math.max(...ys),span=Math.max(1,rawHi-rawLo);
 const step=span<=3?.5:span<=6?1:span<=12?2:Math.ceil(span/5);
 const ymin=Math.floor((rawLo-.12*span)/step)*step,ymax=Math.ceil((rawHi+.12*span)/step)*step;
 const x=n=>L+(n-lo)/(hi-lo||1)*(W-L-R),y=v=>T+(ymax-v)/(ymax-ymin)*(H-T-B);
 let s='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="'+esc(opts.label||"Inflation, annual percentage change")+'"><title>'+esc(opts.label||"Annual inflation, percent")+'</title>';
 s+='<text x="'+L+'" y="12">%, y/y</text>';
 for(let v=ymin;v<=ymax+.001;v+=step)s+='<line class="axis" x1="'+L+'" x2="'+(W-R)+'" y1="'+y(v)+'" y2="'+y(v)+'"/><text x="'+(L-9)+'" y="'+(y(v)+3)+'" text-anchor="end">'+fmt(v,step<1?1:0)+'</text>';
 const tickStep=Math.max(1,Math.ceil((hi-lo)/(W<480?4:6)));
 for(let n=lo;n<=hi;n+=tickStep)s+='<text x="'+x(n)+'" y="'+(H-8)+'" text-anchor="middle">'+tickMonth(n)+'</text>';
 if(opts.target)s+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+y(2)+'" y2="'+y(2)+'" stroke="#a3b2bb" stroke-dasharray="3 5"/>';
 for(const line of series){
  const ps=line.points.filter(p=>mnum(p[0])>=lo&&mnum(p[0])<=hi);
  let d="",prev=null;
  ps.forEach(([m,v])=>{if(!Number.isFinite(v)){prev=null;return;}const n=mnum(m);d+=(prev==null||n>prev+1?"M":"L")+x(n)+","+y(v);prev=n;});
  s+='<path d="'+d+'" fill="none" stroke="'+line.color+'" stroke-width="'+(line.width||2.3)+'" stroke-linejoin="round"'+(line.dash?' stroke-dasharray="'+line.dash+'"':"")+'/>';
  ps.forEach(([m,v])=>{if(Number.isFinite(v))s+='<circle class="point hover-mark" cx="'+x(mnum(m))+'" cy="'+y(v)+'" r="'+(ps.length<16?3.1:2)+'" fill="'+line.color+'"'+tipAttr(line.name+"\n"+month(m)+": "+fmt(v,2)+"% y/y")+'/>';});
 }
 for(const q of quarters){
  const ms=qmonths(q.quarter),mid=x(mnum(ms[1])),yy=y(q.value);
  s+='<g class="hover-mark" tabindex="0"'+tipAttr("CNB · "+q.quarter+"\nQuarter average: "+fmt(q.value,2)+"% y/y")+'><line x1="'+x(mnum(ms[0]))+'" x2="'+x(mnum(ms[2]))+'" y1="'+yy+'" y2="'+yy+'" stroke="'+COLORS.cnb+'" stroke-width="2.2"/><path d="M'+mid+','+(yy-4)+'l4,4 -4,4 -4,-4z" fill="'+COLORS.cnb+'"/><line x1="'+x(mnum(ms[0]))+'" x2="'+x(mnum(ms[2]))+'" y1="'+yy+'" y2="'+yy+'" stroke="transparent" stroke-width="18"/></g>';
 }
 s+="</svg>";host.innerHTML=s;
}
function renderDrivers(){
 const rows=DATA.drivers[String(driverLag)],W=Math.max(330,$("driver-chart").clientWidth||500),H=300,L=W<410?132:167,R=44,T=10,B=24;
 const abs=Math.max(...rows.map(r=>Math.abs(r.value)))*1.12||1;
 const neg=Math.min(0,...rows.map(r=>r.value)),pos=Math.max(0,...rows.map(r=>r.value));
 const min=neg<0?-abs:0,max=pos>0?abs:0,x=v=>L+(v-min)/(max-min||1)*(W-L-R);
 const short={rents:"Rents incl. imputed",other_services:"Other services & mixed",vehicle_operation:"Fuel & vehicle operation",alcohol_tobacco:"Alcohol & tobacco",catering:"Catering & hotels",core_goods:"Core goods",food:"Food & beverages",energy:"Household energy",residual:"Residual"};
 const head=M.history.headline.at(-1)-(driverLag?M.history.headline.at(-1-driverLag):0);
 text("driver-caption",(driverLag?"Change in headline over "+driverLag+" month"+(driverLag>1?"s":"")+": "+signed(head,1):"Contribution to July headline: "+fmt(head,1))+" pp");
 let s='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="Component contributions to headline inflation, percentage points"><title>Component contribution '+(driverLag?"changes":"levels")+', percentage points</title><line x1="'+x(0)+'" x2="'+x(0)+'" y1="5" y2="'+(H-B)+'" stroke="#d5e0e4"/>';
 rows.forEach((r,i)=>{const yy=T+i*29,v=r.value,c=r.id==="residual"?"#a8b7bf":v<0?"#13837a":"#476e8d";
 s+='<text x="0" y="'+(yy+14)+'" style="font-size:'+(W<410?9:10)+'px">'+esc(short[r.id])+'</text><g tabindex="0" class="hover-mark"'+tipAttr(r.label+"\n"+signed(v,3)+" pp")+'><rect x="'+Math.min(x(0),x(v))+'" y="'+yy+'" width="'+Math.max(1,Math.abs(x(v)-x(0)))+'" height="19" rx="2" fill="'+c+'"/><rect x="'+L+'" y="'+yy+'" width="'+(W-L)+'" height="24" fill="transparent"/></g><text x="'+(W-2)+'" y="'+(yy+14)+'" text-anchor="end" style="fill:'+c+'">'+signed(v)+'</text>';});
 s+='<text x="'+x(0)+'" y="'+(H-3)+'" text-anchor="middle">0</text><text x="'+(W-2)+'" y="'+(H-3)+'" text-anchor="end">pp</text></svg>';
 $("driver-chart").innerHTML=s;
}
function renderTrend(){
 const n=+$("trend-range").value,h=M.history,keys=["headline","core","services","goods"],names=["Headline","Core","Services","Goods"];
 $("trend-legend").innerHTML=keys.map((k,i)=>'<span><i style="background:'+COLORS[k]+'"></i>'+names[i]+'</span>').join("");
 chart("trend-chart",keys.map((k,i)=>({name:names[i],color:COLORS[k],points:h.months.map((m,j)=>[m,h[k][j]]).slice(-n)})),{height:310,target:true,label:"Headline, core, services and goods annual inflation"});
}
function updatedPoints(){return [[M.groups_month,M.numbers.headline_yy_prev],[M.headline_month,M.numbers.headline_yy],...DATA.updated_path.filter(r=>r.forecast_kind==="rebased").map(r=>[r.month,r.implied_yy_model])];}
function renderSmallOutlook(){
 const rows=DATA.updated_path.slice(0,6);
 chart("outlook-chart",[{name:"Path updated with actual prints",color:COLORS.core,points:[[M.headline_month,M.numbers.headline_yy],...rows.map(r=>[r.month,r.implied_yy_model])]},{name:"Seasonal norm scenario",color:"#8b9ea9",dash:"5 4",points:[[M.headline_month,M.numbers.headline_yy],...rows.map(r=>[r.month,r.implied_yy_norm])]}],{height:260,target:true,label:"Updated archived path and seasonal-normal scenario"});
 const dec=rows.find(r=>r.month.endsWith("-12"));
 text("base-story",dec?"By "+month(dec.month)+", the updated path reaches "+fmt(dec.implied_yy_model)+"%, versus "+fmt(dec.implied_yy_norm)+"% with normal seasonal prints. Weak prints dropping out of the annual window help explain the rebound.":"Compare outgoing prints with the next monthly forecast to distinguish base arithmetic from new pressure.");
}
function renderStatic(){
 text("sidebar-date",new Date(DATA.snapshot_date+"T12:00:00Z").toLocaleDateString("en-GB",{day:"numeric",month:"long",year:"numeric",timeZone:"UTC"}));
 $("vintage-strip").innerHTML='<span><b>Snapshot</b> '+esc(DATA.snapshot_date)+'</span><span><b>Headline</b> '+month(M.headline_month)+' flash</span><span><b>Component detail</b> '+month(M.groups_month)+'</span><span><b>Path origin</b> '+month(DATA.vintages.model_origin)+'</span>';
 text("target-month",month(DATA.live.target,true));
 const n=M.numbers;
 $("story-title").innerHTML=n.services_yy>n.headline_yy&&n.food_yy<0?"Low headline.<br>Sticky domestic prices.":"The inflation picture,<br>beneath the headline.";
 text("story-intro","Headline is "+fmt(n.headline_yy)+"% in the "+month(M.headline_month)+" flash. The latest full detail ("+month(M.groups_month)+") shows services at "+fmt(n.services_yy)+"% and core at "+fmt(n.core_yy)+"%. Food and household energy are offsetting pressure from rents and services.");
 const cards=[["Headline",n.headline_yy,"August flash · y/y","July: "+fmt(n.headline_yy_prev)+"%",COLORS.headline],["Core",n.core_yy,month(M.groups_month)+" · y/y","A year earlier: "+fmt(n.core_yy_year_ago)+"%",COLORS.core],["Services",n.services_yy,month(M.groups_month)+" · y/y","Domestic persistence",COLORS.services],["Goods",n.goods_yy,month(M.groups_month)+" · y/y","Much cooler than services",COLORS.goods]];
 $("metrics").innerHTML=cards.map(([name,v,caption,note,c])=>'<div class="metric"><div class="metric-label"><i class="metric-dot" style="background:'+c+'"></i>'+name+'</div><div class="metric-value">'+fmt(v)+'<small>%</small></div><div class="metric-caption">'+caption+'</div><div class="metric-note">'+note+'</div></div>').join("");
 document.querySelectorAll(".groups-date").forEach(e=>e.textContent=month(M.groups_month));
 text("breadth-number",fmt(DATA.breadth.percent,0)+"%");
 $("breadth-fill").style.width=DATA.breadth.percent+"%";
 $("momentum-table").innerHTML=M.latest.map(r=>'<tr><td>'+esc(r.short)+(r.block==="other_services"?" & mixed":"")+'</td><td>'+fmt(r.yy)+'%</td><td>'+fmt(r.momentum)+'%</td><td class="'+(r.d3_yy>0?"up":"down")+'">'+signed(r.d3_yy,1)+' pp</td></tr>').join("");
 const pipeline=[["farm_prices","Farm prices","Farm → food","Food-cost pressure is easing. Positive lead correlations survive the exclusion of 2021–23."],["food_ppi","Food producer prices","Food PPI → food","The historical relationship is strongest around a one-month lead. Descriptive, not a promised pass-through."],["domestic_ppi","Domestic producer prices","PPI → core goods","The positive relation depends on the 2021–23 surge. It is not stable outside that episode."],["import_prices","Import prices","Imports → goods","Import prices are rising, but the CPI relationship is weak outside the surge. Watch FX alongside it."]];
 $("pipeline").innerHTML=pipeline.map(([key,label,channel,note])=>{const r=M.pipeline.readings[key];return '<div class="pipeline-card"><h3>'+label+'</h3><small class="footnote">'+month(r.month)+' · y/y</small><div class="reading '+(r.yy<0?"down":"up")+'">'+signed(r.yy,1)+'%</div><div class="channel">'+channel+'</div><p>'+note+'</p></div>';}).join("");
 $("print-table").innerHTML=M.prints.map(r=>'<tr><td>'+month(r.month)+'</td><td>'+fmt(r.actual)+'</td><td>'+fmt(r.consensus)+(r.era.includes("suspect")?"*":"")+'</td><td>'+fmt(r.base_recorded,2)+'</td></tr>').join("");
 const ar=DATA.last_r31c_run, names={core:"Core",food:"Food",alcohol_tobacco:"Alcohol & tobacco",administered:"Administered",fuel:"Fuel",wedge:"Reconciliation wedge"};
 $("archived-nowcast").innerHTML='<p class="caption">R31C re-run at the July release-eve clock. Historical reconstruction, not a current forecast. BASE '+fmt(ar.HARD_BASE,3)+'% m/m.</p><table><thead><tr><th>Component</th><th>Contribution, pp</th></tr></thead><tbody>'+Object.entries(names).map(([k,n])=>'<tr><td>'+n+'</td><td>'+signed(ar["contrib_"+k],3)+'</td></tr>').join("")+'</tbody></table>';
 $("bridge-table").innerHTML=DATA.updated_path.map(r=>'<tr><td>'+month(r.month)+(r.forecast_kind!=="rebased"?' <small>scenario</small>':"")+'</td><td>'+signed(r.dropping_out)+'</td><td>'+signed(r.seasonal_norm)+'</td><td>'+signed(r.model_mm)+'</td><td>'+signed(r.base_effect)+'</td><td>'+signed(r.momentum)+'</td><td>'+fmt(r.implied_yy_model)+'%</td></tr>').join("");
 $("source-table").innerHTML=DATA.sources.map(r=>'<tr><td>'+esc(r.name)+'</td><td>'+esc(r.through)+'</td><td>'+esc(r.source)+'</td><td>'+esc(r.status)+'</td></tr>').join("");
 const ps=DATA.scores.path;
 $("path-scores").innerHTML='<table><thead><tr><th>Horizon</th><th>All origins</th><th>From 2024</th></tr></thead><tbody>'+[3,6,12].map(h=>{const a=ps.find(r=>r.h===h&&r.sample==="full"),b=ps.find(r=>r.h===h&&r.sample==="origins_2024plus");return '<tr><td>'+h+' months</td><td>'+fmt(a.rmse_lane_vs_previous_truth,3)+' <small>n='+a.n+'</small></td><td>'+fmt(b.rmse_lane_vs_previous_truth,3)+' <small>n='+b.n+'</small></td></tr>';}).join("")+'</tbody></table>';
 const c=DATA.scores.cnb;
 $("path-verdict").innerHTML='<div>Matched CNB quarters · from 2024 · n='+c.pairs+'</div><p><strong>'+fmt(c.rmse_lane,3)+'</strong> model &nbsp; / &nbsp; <strong>'+fmt(c.rmse_cnb,3)+'</strong> CNB</p><p>The independent path still trails the CNB on this comparison. At four quarters ahead: '+fmt(c.rmse_lane_4q,3)+' versus '+fmt(c.rmse_cnb_4q,3)+' pp (7 pairs).</p>';
}
function quarterTable(points,cnb,actual=null,modelLabel="Independent"){
 return '<table><thead><tr><th>Quarter</th><th>'+esc(modelLabel)+'</th><th>CNB</th><th>Model − CNB</th>'+(actual?"<th>Realised</th>":"")+'</tr></thead><tbody>'+cnb.filter(q=>qmean(points,q.quarter)!=null).map(q=>{const v=qmean(points,q.quarter),a=actual?qmean(actual,q.quarter):null;return '<tr><td>'+q.quarter+'</td><td>'+fmt(v,2)+'</td><td>'+fmt(q.value,2)+'</td><td>'+signed(v-q.value)+' pp</td>'+(actual?'<td>'+fmt(a,2)+'</td>':"")+'</tr>';}).join("")+'</tbody></table>';
}
function renderPath(){
 const rebased=$("path-version").value==="rebased",points=rebased?updatedPoints():DATA.archive_path;
 const report=DATA.replay.reportsByClock.report.at(-1);
 text("path-caption",(rebased?"July-origin R31B path, mechanically updated with July/August outcomes. Future m/m forecasts are unchanged.":"Original R31B July-origin path; no later outcomes substituted.")+" CNB report: "+report.report_date+". This is not a fresh September forecast.");
 chart("path-chart",[{name:rebased?"Updated archived path":"Original July-origin path",color:COLORS.core,points}],{quarters:report.cnb,target:true,height:330,label:"Independent monthly inflation path and CNB quarterly forecast"});
 $("quarter-table").innerHTML=quarterTable(points,report.cnb);
}
function reportOptions(){
 const reports=DATA.replay.reportsByClock[activeClock];
 reportIndex=Math.min(reportIndex,reports.length-1);
 $("report-select").innerHTML=reports.map((r,i)=>'<option value="'+i+'"'+(i===reportIndex?" selected":"")+'>'+esc(r.season+" "+r.year+" · "+r.report_date)+'</option>').join("");
}
function renderModelToggles(){
 const ids=["ROSTER_R27","FAST","R24_PATH","LOCAL_R27FOOD","CORE_PHASE_R29B","cnb","realised"];
 $("model-toggles").innerHTML=ids.map(id=>'<label class="model-toggle"><input type="checkbox" data-model="'+id+'"'+(selectedModels.has(id)?" checked":"")+'><span class="swatch" style="background:'+COLORS[id]+'"></span>'+MODEL_LABELS[id]+'</label>').join("");
}
function renderReplay(){
 const r=DATA.replay.reportsByClock[activeClock][reportIndex],end=Object.values(r.paths).flat().map(p=>p[0]).sort().at(-1);
 const start=r.window.start;
 $("prev-report").disabled=reportIndex===0;
 $("next-report").disabled=reportIndex===DATA.replay.reportsByClock[activeClock].length-1;
 text("replay-caption","CNB "+r.season+" "+r.year+" · report "+r.report_date+" · cutoff "+r.cutoff_date+" | Model origin "+r.origin+" · decision clock "+r.origin_clock+". "+(activeClock==="report"?"Report-date comparison.":"Cutoff-date comparison."));
 const realised=Object.entries(DATA.replay.realised).filter(([m,v])=>m>=start&&m<=end&&Number.isFinite(v));
 let lines=Object.entries(r.paths).filter(([k])=>selectedModels.has(k)).map(([k,v])=>({name:MODEL_LABELS[k],color:COLORS[k],points:v,dash:k==="FAST"?"7 4":k==="R24_PATH"?"2 4":k==="CORE_PHASE_R29B"?"8 3 2 3":null}));
 if(selectedModels.has("realised"))lines.push({name:"Realised · current vintage",color:COLORS.realised,points:realised,width:2.8});
 // Empty model selection still permits a CNB-only chart, via quarter-midpoint domain anchors.
 if(!lines.length&&selectedModels.has("cnb"))lines=[{name:"",color:"transparent",width:0,points:r.cnb.map(q=>[qmonths(q.quarter)[1],q.value])}];
 chart("replay-chart",lines,{start,end,quarters:selectedModels.has("cnb")?r.cnb:[],target:true,height:350,label:r.season+" "+r.year+" CNB round and independent paths"});
 const score=r.score;
 $("replay-score").innerHTML=score.n?'<div class="replay-result"><span>Quarterly MAE · '+score.n+' matured quarters</span>'+Object.entries(score.mae).filter(([k])=>selectedModels.has(k)).map(([k,v])=>'<span>'+esc(MODEL_LABELS[k]||k)+' <b>'+fmt(v,2)+' pp</b></span>').join("")+'</div>':'<p class="caption">No matured forecast quarters for this report in the frozen outcomes. No score is shown.</p>';
 const tableModel=Object.keys(r.paths).find(id=>selectedModels.has(id));
 $("replay-quarter-table").innerHTML=tableModel?quarterTable(r.paths[tableModel],r.cnb,realised,MODEL_LABELS[tableModel]):'<p class="caption">Select an independent model to compare quarterly averages with the CNB.</p>';
 const blockNames={core:"Core",food_alc_tobacco:"Food, alcohol & tobacco",fuel:"Fuel",administered:"Administered prices"};
 $("replay-blocks").innerHTML=Object.keys(blockNames).map(k=>'<div class="mini-chart"><h3>'+blockNames[k]+'</h3><div class="chart" id="block-'+k+'"></div></div>').join("");
 for(const [k,b] of Object.entries(r.blocks)){
  if(!blockNames[k])continue;
  let ls=Object.entries(b.paths).filter(([id])=>selectedModels.has(id)).map(([id,points])=>({name:MODEL_LABELS[id],color:COLORS[id],points,dash:id==="FAST"?"5 4":null}));
  if(selectedModels.has("realised"))ls.push({name:"Realised component",color:COLORS.realised,points:b.realised});
  chart("block-"+k,ls,{start,end,quarters:selectedModels.has("cnb")?b.cnb:[],height:245,label:blockNames[k]+" annual inflation"});
 }
}
function renderScores(){
 const sample=$("score-sample").value,rows=DATA.scores.nowcast.filter(r=>r.sample===sample),base=rows.find(r=>r.model==="HARD_BASE");
 $("score-table").innerHTML='<tr><td>Release consensus</td><td>'+fmt(base.consensus_rmse,3)+'</td><td>Benchmark</td><td>—</td></tr>'+rows.map(r=>'<tr class="'+(r.model==="HARD_BASE"?"highlight-row":"")+'"><td>'+r.model.replace("HARD_","")+(r.model==="HARD_BASE"?' <small>default</small>':' <small>challenger</small>')+'</td><td>'+fmt(r.rmse,3)+'</td><td>'+r.closer_than_consensus+' / '+r.n+'</td><td>'+r.material_wins_big+' / '+r.material_losses_big+'</td></tr>').join("");
}
function redraw(){
 if(view==="overview"){renderTrend();renderDrivers();renderSmallOutlook();}
 if(view==="forecasts"){if(forecastMode==="outlook")renderPath();else renderReplay();}
 if(view==="data")renderScores();
}
function navigate(target,scroll=true){
 if(!["overview","forecasts","data"].includes(target))target="overview";
 view=target;
 document.querySelectorAll(".view").forEach(el=>el.hidden=el.id!==view);
 document.querySelectorAll("[data-view]").forEach(el=>{el.classList.toggle("active",el.dataset.view===view);el.setAttribute("aria-current",el.dataset.view===view?"page":"false");});
 redraw();
 if(scroll)window.scrollTo({top:0,behavior:"instant"});
}
document.querySelectorAll("[data-view]").forEach(el=>el.addEventListener("click",()=>navigate(el.dataset.view)));
document.querySelectorAll("[data-go]").forEach(el=>el.addEventListener("click",()=>navigate(el.dataset.go)));
document.querySelector(".brand").addEventListener("click",e=>{e.preventDefault();navigate("overview");});
$("driver-controls").addEventListener("click",e=>{const b=e.target.closest("[data-lag]");if(!b)return;driverLag=+b.dataset.lag;document.querySelectorAll("[data-lag]").forEach(x=>x.classList.toggle("active",x===b));renderDrivers();});
$("trend-range").addEventListener("change",renderTrend);
$("path-version").addEventListener("change",renderPath);
$("score-sample").addEventListener("change",renderScores);
$("forecast-mode").addEventListener("click",e=>{const b=e.target.closest("[data-mode]");if(!b)return;forecastMode=b.dataset.mode;document.querySelectorAll("[data-mode]").forEach(x=>x.classList.toggle("active",x===b));$("outlook-mode").hidden=forecastMode!=="outlook";$("replay-mode").hidden=forecastMode!=="replay";redraw();});
$("clock-select").addEventListener("change",()=>{activeClock=$("clock-select").value;reportOptions();renderReplay();});
$("report-select").addEventListener("change",()=>{reportIndex=+$("report-select").value;renderReplay();});
$("prev-report").addEventListener("click",()=>{reportIndex=Math.max(0,reportIndex-1);$("report-select").value=reportIndex;renderReplay();});
$("next-report").addEventListener("click",()=>{reportIndex=Math.min(DATA.replay.reportsByClock[activeClock].length-1,reportIndex+1);$("report-select").value=reportIndex;renderReplay();});
$("model-toggles").addEventListener("change",e=>{const id=e.target.dataset.model;if(!id)return;if(e.target.checked)selectedModels.add(id);else selectedModels.delete(id);renderReplay();});
document.querySelector("#replay-mode details").addEventListener("toggle",e=>{if(e.target.open)renderReplay();});
$("print").addEventListener("click",()=>window.print());
$("export").addEventListener("click",()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(DATA,null,2)],{type:"application/json"})),a=document.createElement("a");a.href=url;a.download="czech-inflation-"+DATA.snapshot_date+".json";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
const tooltip=$("tooltip");
function showTip(el,x,y){tooltip.textContent=el.dataset.tip;tooltip.hidden=false;tooltip.style.left=Math.max(8,Math.min(x+12,innerWidth-tooltip.offsetWidth-12))+"px";tooltip.style.top=Math.max(8,Math.min(y+12,innerHeight-tooltip.offsetHeight-12))+"px";}
document.addEventListener("pointermove",e=>{const el=e.target.closest("[data-tip]");if(el)showTip(el,e.clientX,e.clientY);else tooltip.hidden=true;});
document.addEventListener("focusin",e=>{const el=e.target.closest("[data-tip]");if(el){const b=el.getBoundingClientRect();showTip(el,b.x+b.width/2,b.y+b.height);}else tooltip.hidden=true;});
document.addEventListener("pointerdown",e=>{const el=e.target.closest("[data-tip]");if(el)showTip(el,e.clientX,e.clientY);});
document.addEventListener("keydown",e=>{if(e.key==="Escape")tooltip.hidden=true;});
let resizeTimer;window.addEventListener("resize",()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(redraw,120);});
renderStatic();reportOptions();renderModelToggles();renderScores();navigate(location.hash.slice(1)||"overview",false);

