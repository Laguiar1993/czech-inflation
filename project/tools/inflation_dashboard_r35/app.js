/* R35 category momentum overview; archived forecast renderers remain unchanged. */
const MOM=DATA.category_momentum;
const directionText={picking_up:'Picking up',cooling:'Cooling',little_change:'Little change',unavailable:'Unavailable'};
let heatMode='m3',categoryId=MOM.rows[0].id,detailSeries=null;
const nice=v=>v==null?'—':fmt(v,1)+'%';
const cleanSigned=(v,n=2)=>signed(v!=null&&Math.abs(v)<.5*10**(-n)?0:v,n);
const friendlyFlag=f=>({residual_seasonality_qs:'Residual seasonal pattern',residual_seasonality_spectrum:'Seasonal spectral peak',residual_seasonality_nonparametric:'Residual seasonal pattern',residual_seasonality_diagnostics_unavailable:'Seasonality check unavailable',identifiable_seasonality_not_detected:'Weak seasonal signal',x13_warning:'Model diagnostic warning',component_endpoint_sensitive:'Some underlying groups are endpoint-sensitive',component_weak_seasonality:'Some groups have a weak seasonal signal',component_model_warning:'Model warnings in underlying groups',component_residual_seasonality:'Residual seasonal patterns in some groups'})[f]||f.replaceAll('_',' ');
function flags(row){const important=(row.quality_flags||[]).filter(f=>/endpoint|Endpoint|residual|unavailable|failed/.test(f));return important.length?' <span class="quality-mark" title="'+esc(important.map(friendlyFlag).join('; '))+'" aria-label="Adjustment check flagged">△</span>':'';}
function spark(history){
 const pts=history.slice(-12).filter(r=>Number.isFinite(r.m3));if(!pts.length)return '<span>Unavailable</span>';
 const lo=Math.min(...pts.map(r=>r.m3)),hi=Math.max(...pts.map(r=>r.m3)),range=Math.max(.5,hi-lo),start=mnum(history.slice(-12)[0].month);
 const x=m=>3+(mnum(m)-start)*10,y=v=>26-(v-lo)/range*22;
 let d='',prev=null;pts.forEach(r=>{const n=mnum(r.month);d+=(prev==null||n>prev+1?'M':'L')+x(r.month)+','+y(r.m3);prev=n;});
 const last=pts.at(-1);return '<svg class="momentum-spark" viewBox="0 0 118 30" role="img" aria-label="Last twelve months of three-month annualised inflation"><path d="'+d+'" fill="none" stroke="#3778a6" stroke-width="1.7"/><circle cx="'+x(last.month)+'" cy="'+y(last.m3)+'" r="2.3" fill="#3778a6"/></svg>';
}
function categoryLink(row){return '<button class="category-button" data-category="'+row.id+'">'+esc(row.label)+flags(row)+'<small>'+fmt(row.weight/10,1)+'% of basket</small></button>';}
function renderMomentumTable(){
 const rows=[...MOM.rows],sort=$('momentum-sort').value,key=sort==='pace'?'m3':'acceleration';
 if(sort!=='basket')rows.sort((a,b)=>a[key]==null?1:b[key]==null?-1:(sort==='down'?a[key]-b[key]:b[key]-a[key]));
 $('momentum-rows').innerHTML=rows.map(r=>'<tr data-row="'+r.id+'"><td>'+categoryLink(r)+'</td><td class="rate">'+nice(r.m3)+'</td><td>'+nice(r.m6)+'</td><td class="'+r.direction+'"><strong>'+cleanSigned(r.acceleration,2)+(r.acceleration==null?'':' pp')+'</strong><small>'+directionText[r.direction]+'</small></td><td>'+nice(r.yy)+'</td><td>'+spark(MOM.histories[r.id])+'</td></tr>').join('');
 const b=MOM.breadth;
 $('momentum-breadth').innerHTML='<b class="cooling">'+fmt(b.cooling,0)+'% cooling</b> · <b class="picking_up">'+fmt(b.picking_up,0)+'% picking up</b> · '+fmt(b.little_change,0)+'% little change'+(b.missing?' · '+fmt(b.missing,0)+'% unavailable':'')+'<small> · weighted share of the basket</small>';
}
function heatColor(v){
 if(v==null)return '#edf0f2';const cap=heatMode==='m3'?8:4,t=Math.min(1,Math.abs(v)/cap),base=[244,247,248],end=v>=0?[176,91,66]:[25,125,121];
 return 'rgb('+base.map((x,i)=>Math.round(x+(end[i]-x)*t)).join(',')+')';
}
function renderHeatmap(){
 const ms=MOM.heatmap_months,cap=heatMode==='m3'?8:4;
 text('heatmap-caption',heatMode==='m3'?'Three-month annualised inflation by category. Negative values mean prices fell over the window.':'Change in the three-month pace versus the preceding three months. Negative values mean momentum cooled.');
 $('momentum-heatmap').innerHTML='<table class="heatmap-table"><thead><tr><th>Category</th>'+ms.map(m=>'<th>'+tickMonth(mnum(m))+'</th>').join('')+'</tr></thead><tbody>'+MOM.rows.map(r=>'<tr><td><button class="category-button" data-category="'+r.id+'">'+esc(r.short)+'</button></td>'+ms.map(m=>{const h=MOM.histories[r.id].find(x=>x.month===m),v=h?.[heatMode],unit=heatMode==='m3'?'% annualised':' pp',tip=r.label+' · '+month(m)+'\n'+(heatMode==='m3'?'3m pace: ':'Change in pace: ')+fmt(v,2)+unit;return '<td><button class="heat-cell" data-category="'+r.id+'" style="background:'+heatColor(v)+';color:'+(Math.abs(v)>cap*.66?'#fff':'#17384b')+'" aria-label="'+esc(tip)+'"'+tipAttr(tip)+'>'+fmt(v,1)+'</button></td>';}).join('')+'</tr>').join('')+'</tbody></table>';
 $('heatmap-key').innerHTML='<span>≤ −'+cap+(heatMode==='m3'?'%':' pp')+'</span><span class="heat-gradient"></span><span>≥ +'+cap+(heatMode==='m3'?'%':' pp')+'</span><span>· current adjusted vintage</span>';
}
function renderMomentumDrivers(){
 const ds=MOM.drivers.filter(r=>Number.isFinite(r.value)),scale=Math.max(...ds.map(r=>Math.abs(r.value)),.01);
 const section=(title,rows,color)=>'<div class="driver-section-title"><span>'+title+'</span><span>Weighted impact</span></div>'+(rows.length?rows.map(r=>'<div class="momentum-driver-row"><button class="category-button" data-category="'+r.id+'">'+esc(r.label)+'</button><div><i style="width:'+100*Math.abs(r.value)/scale+'%;background:'+color+'"></i></div><strong style="color:'+color+'">'+cleanSigned(r.value,2)+'</strong></div>').join(''):'<p class="caption">No contributors in this direction.</p>');
 $('momentum-drivers').innerHTML=section('Pushing momentum up',ds.filter(r=>r.value>0).sort((a,b)=>b.value-a.value).slice(0,3),'#ad614b')+section('Pulling momentum down',ds.filter(r=>r.value<0).sort((a,b)=>a.value-b.value).slice(0,3),'#187c79');
 text('momentum-driver-note',(MOM.driver_complete?'All categories together: ':'Partial categories only: ')+cleanSigned(MOM.driver_complete?MOM.driver_total_log_pp:MOM.driver_partial_log_pp,2)+' annualised log pp. Fixed-weight contributions; top three in each direction shown. '+fmt(MOM.driver_coverage,0)+'% of basket weight represented.'+(MOM.driver_complete?'':' Full-basket change unavailable.')+' This describes the analytical basket, separately from official headline CPI.');
}
function compactPath(){
 const report=CURRENT.latest_cnb;
 text('compact-path-caption','September-origin model · CNB report '+report.report_date);
 chart('compact-path-chart',[{name:'Independent path',color:COLORS.core,points:CURRENT.points}],{quarters:report.cnb,target:true,height:270,label:'Current independent path and CNB quarterly averages'});
}
function showCategory(id){
 categoryId=id;detailSeries=null;const row=MOM.rows.find(r=>r.id===id);
 $('category-series').innerHTML='<option value="__block">Whole category</option>'+row.children.map(g=>'<option value="'+g+'">'+esc(MOM.groups[g].label)+'</option>').join('');
 if(!$('category-dialog').open)$('category-dialog').showModal();renderCategory();
}
function renderCategory(){
 const row=MOM.rows.find(r=>r.id===categoryId),g=$('category-series').value,group=g==='__block'?null:MOM.groups[g];
 const history=group?group.history:MOM.histories[categoryId],last=history.at(-1),label=group?group.label:row.label,info=group||row;
 text('category-title',label);text('category-scope',group?group.scope_note:'Fixed-weight category · '+fmt(row.weight/10,1)+'% of the basket · '+row.children.length+' underlying group'+(row.children.length===1?'':'s')+'.');
 $('category-numbers').innerHTML=[['3m annualised',nice(last.m3)],['6m annualised',nice(last.m6)],['Change in pace',cleanSigned(last.acceleration,2)+(last.acceleration==null?'':' pp')],['Year on year',nice(last.yy)]].map(([k,v])=>'<div><small>'+k+'</small><strong>'+v+'</strong></div>').join('');
 const series=[['m3','3m annualised','#2564a5',null],['m6','6m annualised','#168478',null],['yy','Year on year','#8d9aa7','4 4']].map(([key,name,color,dash])=>({name,color,dash,points:history.slice(-24).map(r=>[r.month,r[key]])}));
 chart('category-chart',series,{height:300,label:label+': three- and six-month annualised inflation and year-on-year inflation'});
 const axis=$('category-chart').querySelector('svg text');if(axis)axis.textContent='%, annualised / y/y';
 $('category-chart').querySelectorAll('[data-tip]').forEach(e=>e.dataset.tip=e.dataset.tip.replace('% y/y','%'));
 const f=info.quality_flags||[],revision=info.endpoint_revision_pp;
 text('category-quality',(f.length?'Adjustment checks: '+f.map(friendlyFlag).join(' · ')+'. ':'X-13 adjustment; no flagged check in this snapshot. ')+(revision==null?'Endpoint revision check unavailable.':'July 3m pace changed '+cleanSigned(revision,2)+' pp when August was added to the adjustment sample. ')+(f.includes('Endpoint-sensitive')?'Read small direction changes cautiously. ':'')+'Adjusted history can revise.');
 $('category-data').innerHTML='<table><thead><tr><th>Month</th><th>3m ann.</th><th>6m ann.</th><th>Change, pp</th><th>y/y</th></tr></thead><tbody>'+[...history].reverse().map(r=>'<tr><td>'+month(r.month)+'</td><td>'+nice(r.m3)+'</td><td>'+nice(r.m6)+'</td><td>'+cleanSigned(r.acceleration,2)+'</td><td>'+nice(r.yy)+'</td></tr>').join('')+'</tbody></table>';
}
function renderMomentumStatic(){
 text('momentum-date','Category data · '+month(MOM.month));
 text('momentum-caption','Seasonally adjusted pace · '+month(MOM.month)+' · change compares adjacent three-month windows');
 const dec=CURRENT.rows.find(r=>r.target.endsWith('-12')),gap=CURRENT.gaps.find(r=>r.quarter==='2026Q4');
 $('momentum-topline').innerHTML=[['Official headline',fmt(DATA.official_release.august.headline,1)+'%',month(DATA.official_release.august.month)+' · year on year'],['Next print',fmt(DATA.live.point,2)+'%','September nowcast · m/m'],['December path',fmt(dec.yy_exante,2)+'%','Model forecast · year on year'],['Q4 versus CNB',cleanSigned(gap.gap,2)+' pp','Quarterly mean · August CNB forecast']].map(([k,v,n])=>'<div><span>'+k+'</span><strong>'+v+'</strong><small>'+n+'</small></div>').join('');
 $('vintage-strip').innerHTML='<span><b>Category data</b> '+month(MOM.month)+'</span><span><b>Forecast origin</b> '+month(CURRENT.meta.origin)+'</span><span><b>Snapshot</b> '+DATA.snapshot_date+'</span>';
 $('momentum-method-content').innerHTML='<p><b>3m / 6m annualised:</b> compound the change in the adjusted index over the last three / six months, then express that pace at an annual rate. These are endpoint changes, not changes between quarterly-average indices.</p><p><b>Change in pace:</b> compare the latest three-month pace with the preceding three-month pace. Picking up / cooling requires a change beyond ±0.25 pp. This is a descriptive threshold, not a statistical significance test.</p><p><b>Category scope:</b> nine non-overlapping categories cover all 37 source groups. Fuel & vehicle costs includes parts and repairs. The goods and other-services blocks contain the mixed items specified by their constituent groups; they are not exact CNB core partitions. Open a category to inspect its groups.</p><p><b>Aggregation:</b> weighted geometric indices use the fixed 2026 basket weights. They describe a consistent analytical basket; official headline CPI uses its own index methodology. Category y/y is derived from captured rounded index levels and can differ slightly from published annual rates. Weighted driver contributions are additive annualised log percentage points and sum exactly to the analytical basket’s change in log pace.</p><p><b>Seasonal adjustment:</b> X-13 log decomposition with automated ARIMA and outlier treatment. Source price shocks remain in the adjusted series. No explicit moving-Easter adjustment is applied; travel prices can retain holiday effects. A failed adjustment is unavailable. A triangle marks a diagnostic or endpoint-sensitivity flag; group detail explains it. Adjusted history is the current estimated vintage and can revise.</p><p><b>Breadth:</b> the full basket weight is the denominator. Groups with missing momentum remain in the unavailable share. Coverage is '+fmt(MOM.breadth.coverage,1)+'%.</p><p><b>Sources:</b> CZSO CEN0101E monthly category levels; frozen 2026 basket weights. Retrieved '+esc(MOM.provenance.capture_completed_at)+'. Forecasts and the CNB replay retain their separately recorded inputs and clocks.</p>';
 renderMomentumTable();renderHeatmap();renderMomentumDrivers();
}
const r35Static=renderStatic;
renderStatic=function(){r35Static();renderMomentumStatic();};
const r35Redraw=redraw;
redraw=function(){r35Redraw();if(view==='overview'){renderMomentumTable();renderHeatmap();renderMomentumDrivers();compactPath();}if($('category-dialog').open)renderCategory();};
$('momentum-sort').addEventListener('change',renderMomentumTable);
$('heatmap-mode').addEventListener('click',e=>{const b=e.target.closest('[data-heat]');if(!b)return;heatMode=b.dataset.heat;document.querySelectorAll('[data-heat]').forEach(x=>x.classList.toggle('active',x===b));renderHeatmap();});
document.addEventListener('click',e=>{const b=e.target.closest('[data-category]');if(b)showCategory(b.dataset.category);});
$('category-series').addEventListener('change',renderCategory);
$('category-close').addEventListener('click',()=>$('category-dialog').close());
$('momentum-method-open').addEventListener('click',()=>$('momentum-method').showModal());
$('momentum-method-close').addEventListener('click',()=>$('momentum-method').close());
document.querySelector('.legacy-overview').addEventListener('toggle',e=>{if(e.target.open){renderTrend();renderDrivers();renderSmallOutlook();}});
renderStatic();reportOptions();renderModelToggles();renderScores();navigate(location.hash.slice(1)||'overview',false);visitMessage();
