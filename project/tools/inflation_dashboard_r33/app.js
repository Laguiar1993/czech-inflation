/* R33 extensions: preserve the sealed R32 renderer as an imported dependency. */
function renderBriefing(){
 const a=DATA.official_release.august,j=DATA.official_release.july;
 $('briefing').innerHTML=[['WHAT CHANGED','Fuel lifted the headline','August CPI rose '+fmt(a.headline_mm)+'% m/m. Fuel inflation increased from '+fmt(j.fuel)+'% to '+fmt(a.fuel)+'% y/y; food declines partly offset it.'],['WHAT IT IMPLIES','Services inflation edged lower','Services eased from '+fmt(j.services)+'% to '+fmt(a.services)+'% y/y. Actual rents remain '+fmt(a.actual_rent)+'%; imputed rents eased to '+fmt(a.imputed_rent)+'%. Headline alone understates that persistence.'],['WHAT TO WATCH','October prints, then the energy reset','September CPI flash: 6 October; detail: 13 October. Watch pump prices, food costs and housing. January energy announcements can shift the path.']].map(([k,t,p])=>'<article class="brief-card"><div class="section-kicker">'+k+'</div><h2>'+t+'</h2><p>'+p+'</p><a href="'+esc(a.url)+'" target="_blank" rel="noopener">CZSO · August release ↗</a></article>').join('');
}
function renderDetailedBriefing(){
 const b=DATA.briefings[$('briefing-lag').value];
 $('detail-briefing').innerHTML='<div><span>'+month(b.from_month)+' → '+month(b.to_month)+'</span><strong>'+signed(b.headline_change,1)+' pp headline</strong><small>Change in the annual rate</small></div>'+b.top_moves.map(r=>'<div><span>'+esc(r.label)+'</span><strong>'+signed(r.value,2)+' pp</strong><small>Contribution change</small></div>').join('');
}
function visitMessage(){
 const key='czech-inflation-briefing-v1',current=DATA.fingerprint;
 try{const old=JSON.parse(localStorage.getItem(key)||'null');text('visit-status',!old?'First visit on this browser. The comparison below is August versus July.':old.fingerprint===current?'No new snapshot since your last visit. Monthly comparisons below are unchanged.':'A different snapshot has loaded. Compare the dated releases and validated forecast runs below; no automatic causal attribution.');localStorage.setItem(key,JSON.stringify({fingerprint:current,viewed_at:new Date().toISOString()}));}
 catch(_){text('visit-status','Visit history unavailable in this browser. Release comparisons remain explicitly dated.');}
}
function renderPressure(){
 $('momentum-table').innerHTML=DATA.pressure_rows.map(r=>'<tr><td>'+esc(r.label)+'</td><td>'+fmt(r.yy)+'%</td><td>'+fmt(r.momentum)+'%</td><td class="'+(r.change_3m>0?'up':'down')+'">'+signed(r.change_3m,1)+' pp</td></tr>').join('');
}
function renderWatch(){
 $('watch-table').innerHTML='<table class="watch-table"><thead><tr><th>Release / input</th><th>Watch for</th><th>Why it matters</th></tr></thead><tbody>'+DATA.watch.map(r=>'<tr><td><b>'+esc(r.event)+'</b><small>'+esc(r.frequency)+' · '+(r.next_release?esc(r.next_release)+' flash / '+esc(r.detail_release)+' detail':'Next date not loaded')+'</small><small>'+esc(r.block)+'</small></td><td>'+esc(r.watch)+'</td><td>'+esc(r.impact)+'<small>'+esc(r.evidence)+'</small></td></tr>').join('')+'</tbody></table>';
}
function renderRevision(){
 const r=DATA.revision;
 text('revision-badge',r.status==='available'?(r.kind==='replay_revision'?'Historical example only':'Comparable recorded runs'):'No comparable pair');
 if(r.status!=='available'){$('revision-panel').innerHTML='<p class="caption">'+esc(r.reason)+'</p><div class="revision-meta">A bridge requires two successful runs for the same target month, model and units. Components measure model-output changes; they do not by themselves identify which data release caused the change.</div>';return;}
 $('revision-panel').innerHTML='<p>'+esc(r.model)+' · '+month(r.target)+' · '+signed(r.delta,3)+' pp revision</p><p class="revision-meta">'+esc(r.old_as_of)+' → '+esc(r.new_as_of)+' · '+esc(r.kind==='replay_revision'?'Historical replay revision · not prospective':'Recorded forecast revision')+'</p><table><thead><tr><th>Component</th><th>Previous</th><th>New</th><th>Revision, pp</th></tr></thead><tbody>'+r.components.map(c=>'<tr><td>'+esc(c.name)+'</td><td>'+signed(c.old,3)+'</td><td>'+signed(c.new,3)+'</td><td>'+signed(c.delta,3)+'</td></tr>').join('')+'<tr><td>Unexplained residual</td><td>—</td><td>—</td><td>'+signed(r.residual,3)+'</td></tr></tbody></table></div><p class="footnote">Component output attribution, not a causal decomposition by data release. Path differences, when recorded, align by calendar month.</p>';
 if(r.path_changes.length)$('revision-panel').innerHTML+='<h3>Calendar-aligned path changes</h3><div class="table-wrap"><table><thead><tr><th>Target month</th><th>Previous y/y</th><th>New y/y</th><th>Change, pp</th></tr></thead><tbody>'+r.path_changes.map(p=>'<tr><td>'+month(p.target_month)+'</td><td>'+fmt(p.old,2)+'</td><td>'+fmt(p.new,2)+'</td><td>'+signed(p.delta,2)+'</td></tr>').join('')+'</tbody></table></div>';
 if(r.kind==='replay_revision')$('revision-panel').innerHTML='<p class="caption">No pair of current prospective forecasts is available. The verified July example below demonstrates how a revision will be explained.</p><details><summary>Inspect a working example · July 2026 historical replay</summary>'+$('revision-panel').innerHTML+'</details>';
}
function renderCurrentForecast(){
 const live=DATA.live;if(live.status!=='recorded')return;
 const date=new Date(live.as_of).toLocaleString('en-GB',{timeZone:'Europe/Prague',dateStyle:'medium',timeStyle:'short'})+' Prague';
 text('freshness-badge','Nowcast current · path archived');
 const card=document.querySelector('.next-card');
 card.querySelector('.badge').textContent='Recorded forecast';card.querySelector('.badge').classList.remove('amber');
 card.querySelector('.unavailable').innerHTML=fmt(live.point,2)+' <small>% m/m</small>';
 card.querySelector('.unavailable').style.color='var(--blue)';
 card.querySelector('p').textContent='BASE · as of '+date+'. Recorded before release. The path below retains its archived origin.';
 $('current-forecast-panel').innerHTML='<div class="panel-heading"><h2>'+month(live.target)+' nowcast</h2><span class="badge">Recorded prospective run</span></div><p class="caption">BASE: <b>'+fmt(live.point,3)+'% m/m</b> · '+esc(date)+'. No current consensus loaded.</p><div class="table-wrap"><table><thead><tr><th>Component</th><th>Contribution, pp</th></tr></thead><tbody>'+Object.entries(live.components).map(([k,v])=>'<tr><td>'+esc(k.replaceAll('_',' '))+'</td><td>'+signed(v,3)+'</td></tr>').join('')+'</tbody></table></div><p class="footnote">Bloomberg supplies the current inputs. August core and regulated m/m came from official CNB ARAD because the corresponding Bloomberg feeds still ended in July. This refresh updates the nowcast; the monthly path has not been re-estimated.</p>';
}
function renderGap(){
 const r=DATA.replay.reportsByClock[activeClock][reportIndex],model=Object.keys(r.paths).find(id=>selectedModels.has(id)),old=$('gap-quarter').value;
 const rows=model?(DATA.gap_explanations[activeClock][r.id][model]||[]):[];
 $('gap-quarter').innerHTML=rows.map(q=>'<option value="'+q.quarter+'">'+q.quarter+'</option>').join('');
 if(rows.some(q=>q.quarter===old))$('gap-quarter').value=old;
 const g=rows.find(q=>q.quarter===$('gap-quarter').value);
 $('gap-quarter').disabled=!rows.length;
 text('gap-caption',model?MODEL_LABELS[model]+' · '+r.season+' '+r.year+' · '+activeClock+' clock · older R27 input lane':'Select a model to explain its gap.');
 if(!g||!g.complete){text('gap-summary',g?.summary||'No complete component comparison on this selection.');$('gap-bars').innerHTML='';return;}
 text('gap-summary','Model − CNB: '+signed(g.gap,2)+' pp. '+g.summary);
 const scale=Math.max(...g.parts.map(p=>Math.abs(p.value)),.01);
 $('gap-bars').innerHTML=g.parts.map(p=>{const w=45*Math.abs(p.value)/scale,c=p.id==='unexplained'?'#8c989f':p.value<0?'#168478':'#4775a4';return '<div class="gap-row '+(p.id==='unexplained'?'residual':'')+'"><span>'+esc(p.label)+'</span><div class="gap-track"><i style="background:'+c+';left:'+(p.value<0?50-w:50)+'%;width:'+w+'%"></i></div><strong>'+signed(p.value,3)+' pp</strong></div>';}).join('');
}
function scenarioRows(food,core,energy){
 const source=DATA.updated_path.filter(r=>r.forecast_kind==='rebased'),factors=[];
 return source.map((r,i)=>{const increment=(i<3?food:0)+(i<6?core:0)+(r.month.endsWith('-01')?energy:0),f=(1+(r.model_mm+increment)/100)/(1+r.model_mm/100);factors.push([r.month,f]);const product=factors.filter(([m])=>mnum(m)>=mnum(r.month)-11).reduce((a,[,v])=>a*v,1);return {month:r.month,baseline_yy:r.implied_yy_model,scenario_yy:increment||product!==1?(100+r.implied_yy_model)*product-100:r.implied_yy_model,headline_mm_increment:increment,baseline_mm:r.model_mm,scenario_mm:r.model_mm+increment};});
}
function renderScenario(){
 const amounts=['food','core','energy'].map(k=>+$('scenario-'+k).value),rows=scenarioRows(...amounts);
 ['food','core','energy'].forEach((k,i)=>text(k+'-value',signed(amounts[i],2)+(k==='energy'?' pp in January':' pp / month')));
 const base=rows.map(r=>[r.month,r.baseline_yy]),sc=rows.map(r=>[r.month,r.scenario_yy]);
 chart('scenario-chart',[{name:'Rebased archived path',color:COLORS.core,points:base},{name:'Your scenario',color:'#aa7330',dash:'6 3',points:sc}],{height:290,target:true,label:'User assumptions around the rebased archived path'});
 const last=rows.at(-1);text('scenario-summary',amounts.every(v=>v===0)?'Neutral assumptions: the scenario exactly matches the rebased archived path.':month(last.month)+': '+fmt(last.scenario_yy,2)+'% y/y, '+signed(last.scenario_yy-last.baseline_yy,2)+' pp versus the archived baseline. No probability is assigned to this scenario.');
 const quarters=[...new Set(rows.map(r=>r.month.slice(0,4)+'Q'+Math.ceil(+r.month.slice(5)/3)))].filter(q=>qmean(base,q)!=null);
 $('scenario-table').innerHTML='<table><thead><tr><th>Full quarter</th><th>Archived baseline</th><th>Your scenario</th><th>Difference</th></tr></thead><tbody>'+quarters.map(q=>'<tr><td>'+q+'</td><td>'+fmt(qmean(base,q),2)+'%</td><td>'+fmt(qmean(sc,q),2)+'%</td><td>'+signed(qmean(sc,q)-qmean(base,q),2)+' pp</td></tr>').join('')+'</tbody></table>';
}
const oldTrend=renderTrend;
$('trend-range').removeEventListener('change',oldTrend);
renderTrend=function(){const n=+$('trend-range').value,h=M.history,keys=['headline','core','services','goods'],labels=['Headline','Core','Nontradables excl. regulated','Other tradables excl. food/fuel'];$('trend-legend').innerHTML=keys.map((k,i)=>'<span><i style="background:'+COLORS[k]+'"></i>'+labels[i]+'</span>').join('');chart('trend-chart',keys.map((k,i)=>({name:labels[i],color:COLORS[k],points:h.months.map((m,j)=>[m,h[k][j]]).slice(-n)})),{height:310,target:true,label:'Headline, core and ARAD tradables/nontradables annual inflation with distinct scopes'});};
$('trend-range').addEventListener('change',renderTrend);
const originalReplay=renderReplay;
renderReplay=function(){originalReplay();renderGap();};
const originalRedraw=redraw;
redraw=function(){originalRedraw();if(view==='forecasts'&&forecastMode==='outlook')renderScenario();};
const originalStatic=renderStatic;
renderStatic=function(){
 originalStatic();const a=DATA.official_release.august,j=DATA.official_release.july;
 text('story-intro','August headline inflation is '+fmt(a.headline)+'%. Fuel has lifted the annual rate, while services have eased to '+fmt(a.services)+'%. Housing still matters. Below, current official observations sit alongside the dated July basket and archived forecast path.');
 $('vintage-strip').innerHTML='<span><b>Snapshot</b> '+DATA.snapshot_date+'</span><span><b>Official release</b> Aug 2026 · detailed</span><span><b>37-group panel</b> Jul 2026</span><span><b>Path origin</b> Jul 2026</span>';
 const cards=[['Headline',a.headline,'August detail · y/y','July: '+fmt(j.headline)+'%',COLORS.headline],['Core (CNB)',DATA.official_release.cnb_august.core,'August observed · y/y','Separate from broad services',COLORS.core],['Services (CZSO)',a.services,'August detail · y/y','July: '+fmt(j.services)+'%',COLORS.services],['Imputed rent',a.imputed_rent,'August detail · y/y','July: '+fmt(j.imputed_rent)+'%',COLORS.goods]];
 $('metrics').innerHTML=cards.map(([name,v,caption,note,c])=>'<div class="metric"><div class="metric-label"><i class="metric-dot" style="background:'+c+'"></i>'+name+'</div><div class="metric-value">'+fmt(v)+'<small>%</small></div><div class="metric-caption">'+caption+'</div><div class="metric-note">'+note+'</div></div>').join('');
 $('source-issues').innerHTML='<div class="callout"><p><b>Different definitions, not interchangeable series.</b> In July, ARAD other tradables excluding food/fuel were +0.4%, and nontradables excluding regulated prices were +4.6%. The broader CZSO goods/services aggregates were −0.2% / +4.7%. ARAD retains first-round tax effects, so these two lines are not an exact partition of tax-corrected core inflation.</p></div><p class="caption">Historical definitions: frozen CNB ARAD metadata, series SCPICLEM02YOYPECNA / SCPICLEM03YOYPECNA. August cards: <a href="'+esc(a.url)+'" target="_blank" rel="noopener">CZSO broad aggregates and rents</a>; <a href="'+esc(DATA.official_release.cnb_august.url)+'" target="_blank" rel="noopener">CNB observed core inflation</a>. The July 37-group panel and model origin are unchanged.</p><p class="caption"><b>Why the ARAD supplement?</b> On 22 September, Bloomberg latest-value and daily-history requests for CZCIXM and CZCIRM still ended in July (1.0% / 0.2% m/m). The same observed series on ARAD supplied August (+0.3% / 0.0%). The September nowcast uses those two explicit supplements. No CNB forecast is used.</p>';
 renderBriefing();renderDetailedBriefing();renderPressure();renderWatch();renderRevision();renderCurrentForecast();
};
$('briefing-lag').addEventListener('change',renderDetailedBriefing);
$('gap-quarter').addEventListener('change',renderGap);
['food','core','energy'].forEach(k=>$('scenario-'+k).addEventListener('input',renderScenario));
$('scenario-reset').addEventListener('click',()=>{['food','core','energy'].forEach(k=>$('scenario-'+k).value='0');renderScenario();});
renderStatic();reportOptions();renderModelToggles();renderScores();navigate(location.hash.slice(1)||'overview',false);visitMessage();
