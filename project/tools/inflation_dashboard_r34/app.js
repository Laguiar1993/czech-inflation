/* R34: fresh path and explanations, extending the immutable earlier renderers. */
const CURRENT=DATA.current_path,CONTEXT=DATA.forecast_context;
const componentNames={core:'Core',food:'Food',fuel:'Fuel',administered:'Administered',alcohol_tobacco:'Alcohol & tobacco',wedge:'Reconciliation wedge'};
const pathNames={ROSTER_R27:'Accepted R27 path',LOCAL_CORE_R27_SENSITIVITY:'Local core sensitivity',GENTLE_CORE_R27_SENSITIVITY:'Gentle core sensitivity'};
const pathColors={ROSTER_R27:COLORS.core,LOCAL_CORE_R27_SENSITIVITY:'#168478',GENTLE_CORE_R27_SENSITIVITY:'#8362a9'};
const currentPoints=()=>CURRENT.points;
const rangeRows=()=>CONTEXT.empirical_ranges.samples[$('uncertainty-sample').value];
const clockLabel=v=>new Date(v).toLocaleString('en-GB',{timeZone:'Europe/Prague',dateStyle:'medium',timeStyle:'short'})+' Prague';
function drawGapRows(host,g){
 const scale=Math.max(...g.parts.map(p=>Math.abs(p.value)),.01);
 $(host).innerHTML=g.parts.map(p=>{const w=45*Math.abs(p.value)/scale,c=p.id==='unexplained'?'#8c989f':p.value<0?'#168478':'#4775a4';return '<div class="gap-row '+(p.id==='unexplained'?'residual':'')+'"><span>'+esc(p.label)+'</span><div class="gap-track"><i style="background:'+c+';left:'+(p.value<0?50-w:50)+'%;width:'+w+'%"></i></div><strong>'+signed(p.value,3)+' pp</strong></div>';}).join('');
}
function renderCurrentGap(){
 const archive=$('path-version').value==='archive';
 $('current-gap-quarter').disabled=archive;
 if(archive){text('current-gap-summary','The block attribution belongs to the fresh September path. Select that vintage to inspect it.');$('current-gap-bars').innerHTML='';return;}
 const g=CURRENT.gaps.find(r=>r.quarter===$('current-gap-quarter').value);
 if(!g||!g.complete){text('current-gap-summary','Complete component coverage is unavailable for this quarter.');$('current-gap-bars').innerHTML='';return;}
 text('current-gap-summary',g.quarter+': current model '+fmt(g.model,2)+'%, CNB '+fmt(g.cnb,2)+'%; gap '+signed(g.gap,2)+' pp. '+g.summary);
 drawGapRows('current-gap-bars',g);
}
const r34OldPath=renderPath;
$('path-version').removeEventListener('change',r34OldPath);
renderPath=function(){
 const archive=$('path-version').value==='archive',points=archive?DATA.archive_path:currentPoints(),report=CURRENT.latest_cnb;
 text('path-caption',archive?'Original July-origin path, preserved unchanged for comparison.':'Re-estimated '+month(CURRENT.meta.origin)+' origin · path decision '+clockLabel(CURRENT.meta.as_of)+'. September h0 is the recorded '+clockLabel(CURRENT.meta.h0_as_of)+' BASE call. CNB report '+report.report_date+' uses an earlier information set.');
 chart('path-chart',[{name:archive?'Original July-origin path':'Fresh September-origin path',color:COLORS.core,points}],{quarters:report.cnb,target:true,height:330,label:'Current independent inflation path against the earlier CNB quarterly forecast'});
 $('quarter-table').innerHTML=quarterTable(points,report.cnb,null,archive?'July archive':'Current model');renderCurrentGap();
};
$('path-version').addEventListener('change',renderPath);
renderSmallOutlook=function(){
 const rows=CURRENT.rows.slice(0,6),start=CURRENT.realised.at(-1),last=rows.at(-1).target;
 chart('outlook-chart',[{name:'Fresh September-origin path',color:COLORS.core,points:[start,...rows.map(r=>[r.target,r.yy_exante])]},{name:'Original July-origin path',color:'#8b9ea9',dash:'5 4',points:DATA.archive_path.filter(([m])=>m>=start[0]&&m<=last)}],{height:260,target:true,label:'Fresh path alongside the dated July-origin archive'});
 const dec=CURRENT.ledger.find(r=>r.month.endsWith('-12'));
 if(dec){const used=CURRENT.ledger.filter(r=>r.month<=dec.month),base=used.reduce((a,r)=>a+r.base_effect_pp,0),fresh=used.reduce((a,r)=>a+r.new_price_pp,0);text('base-story','By '+month(dec.month)+', the path reaches '+fmt(dec.yy,2)+'% y/y. From August, old prints leaving contribute '+signed(base,2)+' pp and new monthly prints '+signed(fresh,2)+' pp. New prints include seasonality.');}
};
renderCurrentForecast=function(){
 const live=DATA.live;const card=document.querySelector('.next-card');
 text('freshness-badge','Nowcast and path current · detail dated');
 card.querySelector('.badge').textContent='Recorded forecast';card.querySelector('.badge').classList.remove('amber');
 card.querySelector('.unavailable').innerHTML=fmt(live.point,2)+' <small>% m/m</small>';
 card.querySelector('.unavailable').style.color='var(--blue)';
 card.querySelector('p').textContent='BASE · '+clockLabel(live.as_of)+'. The September-origin path has now also been re-estimated.';
 $('current-forecast-panel').innerHTML='<div class="panel-heading"><h2>'+month(live.target)+' nowcast</h2><span class="badge">Recorded prospective run</span></div><p class="caption">BASE <b>'+fmt(live.point,3)+'% m/m</b> · '+esc(clockLabel(live.as_of))+'. No current consensus loaded.</p><div class="table-wrap"><table><thead><tr><th>Component</th><th>Contribution, pp</th></tr></thead><tbody>'+Object.entries(live.components).map(([k,v])=>'<tr><td>'+componentNames[k]+'</td><td>'+signed(v,3)+'</td></tr>').join('')+'</tbody></table></div><p class="footnote">Bloomberg is the default source. The missing August core and regulated observations are sourced from CNB ARAD. These are observations; no CNB forecast enters the model. The fresh path retains this recorded h0 exactly.</p>';
};
function renderSeasonal(){
 const s=CONTEXT.seasonal;
 text('seasonal-summary',s.status==='available'?'The '+fmt(s.point_mm,2)+'% m/m call compares with a historical September mean of '+fmt(s.baseline_total_pp,2)+'%. It is '+fmt(Math.abs(s.deviation_total_pp),2)+' pp '+(s.deviation_total_pp<0?'below':'above')+' that descriptive seasonal benchmark.':'The same-month seasonal benchmark is unavailable.');
 $('seasonal-table').innerHTML='<table><thead><tr><th>Component</th><th>Historical September contribution</th><th>Recorded forecast</th><th>Forecast minus benchmark</th></tr></thead><tbody>'+s.components.map(r=>'<tr><td>'+componentNames[r.component]+'</td><td>'+signed(r.baseline_contribution_pp,3)+'</td><td>'+signed(r.recorded_contribution_pp,3)+'</td><td>'+signed(Math.abs(r.deviation_pp)<0.0005?0:r.deviation_pp,3)+'</td></tr>').join('')+'<tr class="seasonal-total"><td>Headline total</td><td>'+signed(s.baseline_total_pp,3)+'</td><td>'+signed(s.point_mm,3)+'</td><td>'+signed(s.deviation_total_pp,3)+'</td></tr></tbody></table>';
 text('seasonal-note',s.sample.n+' complete Septembers, '+s.sample.start+' to '+s.sample.end+'. Historical component m/m means use today’s recorded weights; the wedge reconciles to headline. This is a descriptive benchmark, not the model’s fitted seasonal decomposition. A negative unadjusted September core print does not by itself mean underlying disinflation.');
}
function renderForecastSummary(){
 const dec=CURRENT.rows.find(r=>r.target.endsWith('-12')),last=CURRENT.rows.at(-1),q=CURRENT.gaps.find(r=>r.quarter==='2026Q4');
 $('forecast-summary').innerHTML=[['December outlook',fmt(dec.yy_exante,2)+'% y/y','Fresh model run · '+month(CURRENT.meta.origin)+' origin'],['2026 Q4 versus CNB',q&&q.complete?signed(q.gap,2)+' pp':'Unavailable','Quarterly mean · CNB report '+CURRENT.latest_cnb.report_date],[month(last.target)+' outlook',fmt(last.yy_exante,2)+'% y/y','h12 · inspect historical error sizes below']].map(([label,value,note])=>'<div><span>'+label+'</span><strong>'+value+'</strong><small>'+note+'</small></div>').join('');
}
function historicalRange(row,point){return row.status==='available'?fmt(point+row.lower_offset_pp,2)+' to '+fmt(point+row.upper_offset_pp,2):'Not enough history';}
function renderUncertainty(){
 const ranges=rangeRows(),sample=$('uncertainty-sample').value;
 text('uncertainty-caption',(sample==='full'?'Full historical support':'Origins since 2024')+'. Error = actual minus forecast. The range adds the fixed 10th and 90th percentiles of those errors to the current forecast.');
 $('uncertainty-summary').innerHTML=[0,6,12].map(h=>{const r=ranges[String(h)],point=h===0?DATA.live.point:CURRENT.rows.find(x=>x.h===h).yy_exante;return '<div><span>'+(h===0?'September nowcast · m/m':'h'+h+' · '+month(CURRENT.rows.find(x=>x.h===h).target)+' y/y')+'</span><strong>'+historicalRange(r,point)+(r.status==='available'?'%':'')+'</strong><small>Historical central 80% error range · n='+r.n+'<br>Origins '+r.origin_start+' → '+r.origin_end+'</small></div>';}).join('');
 const future=CURRENT.rows.filter(r=>r.h>0),base=future.map(r=>[r.target,r.yy_exante]);
 const bound=key=>future.map(r=>[r.target,ranges[String(r.h)].status==='available'?r.yy_exante+ranges[String(r.h)][key]:null]);
 chart('uncertainty-chart',[{name:'Current path',color:COLORS.core,points:base},{name:'10th historical error offset',color:'#9cabb7',dash:'4 4',points:bound('lower_offset_pp')},{name:'90th historical error offset',color:'#9cabb7',dash:'4 4',points:bound('upper_offset_pp')}],{height:300,target:true,label:'Current path and historical error-offset ranges, not calibrated probabilities'});
 $('uncertainty-table').innerHTML='<table><thead><tr><th>Forecast</th><th>Point</th><th>Historical error range</th><th>Sample</th></tr></thead><tbody>'+[0,3,6,12].map(h=>{const r=ranges[String(h)],p=CURRENT.rows.find(x=>x.h===h),point=h===0?DATA.live.point:p.yy_exante;return '<tr><td>'+month(p.target)+'<small>h'+h+' · '+(h===0?'m/m':'y/y')+'</small></td><td>'+fmt(point,2)+'%</td><td>'+historicalRange(r,point)+(r.status==='available'?'%':'')+'</td><td>n='+r.n+'<small>'+r.origin_start+' → '+r.origin_end+'</small></td></tr>';}).join('')+'</tbody></table>';
 const points=CONTEXT.seasonal.recorded_alternative_points_mm;
 $('model-disagreement').innerHTML='<p>September nowcast: '+Object.entries(points).map(([k,v])=>'<b>'+k.replace('HARD_','')+'</b> '+fmt(v,3)+'%').join(' · ')+'. Spread '+fmt(Math.max(...Object.values(points))-Math.min(...Object.values(points)),3)+' pp. BASE remains the operating model.</p>';
 renderSensitivity();
}
function renderSensitivity(){chart('sensitivity-chart',Object.entries(CURRENT.models).map(([id,rows])=>({name:pathNames[id],color:pathColors[id],dash:id==='ROSTER_R27'?null:'6 3',points:rows.map(r=>[r.target,r.yy_exante])})),{height:260,target:true,label:'Alternative core recipes with identical food path, model sensitivity only'});}
const r34OldScenario=renderScenario;
['food','core','energy'].forEach(k=>$('scenario-'+k).removeEventListener('input',r34OldScenario));
scenarioRows=function(food,core,energy){
 const factors=[];return CURRENT.rows.map((r,i)=>{const increment=(i<3?food:0)+(i<6?core:0)+(r.target.endsWith('-01')?energy:0),factor=(1+(r.mm_forecast+increment)/100)/(1+r.mm_forecast/100);factors.push([r.target,factor]);const product=factors.filter(([m])=>mnum(m)>=mnum(r.target)-11).reduce((a,[,f])=>a*f,1);return {month:r.target,baseline_yy:r.yy_exante,scenario_yy:increment||product!==1?(100+r.yy_exante)*product-100:r.yy_exante,baseline_mm:r.mm_forecast,scenario_mm:r.mm_forecast+increment,headline_mm_increment:increment};});
};
renderScenario=function(){
 const amounts=['food','core','energy'].map(k=>+$('scenario-'+k).value),rows=scenarioRows(...amounts);
 ['food','core','energy'].forEach((k,i)=>text(k+'-value',signed(amounts[i],2)+(k==='energy'?' pp in January':' pp / month')));
 const base=rows.map(r=>[r.month,r.baseline_yy]),sc=rows.map(r=>[r.month,r.scenario_yy]);
 chart('scenario-chart',[{name:'Fresh September-origin path',color:COLORS.core,points:base},{name:'Your scenario',color:'#aa7330',dash:'6 3',points:sc}],{height:290,target:true,label:'User assumptions around the fresh September path'});
 const last=rows.at(-1);text('scenario-summary',amounts.every(v=>v===0)?'Neutral assumptions: the scenario exactly matches the fresh September-origin path.':month(last.month)+': '+fmt(last.scenario_yy,2)+'% y/y, '+signed(last.scenario_yy-last.baseline_yy,2)+' pp versus the current baseline. No probability is assigned.');
 const quarters=[...new Set(rows.map(r=>r.month.slice(0,4)+'Q'+Math.ceil(+r.month.slice(5)/3)))].filter(q=>qmean(base,q)!=null);
 $('scenario-table').innerHTML='<table><thead><tr><th>Full forecast quarter</th><th>Current baseline</th><th>Your scenario</th><th>Difference</th></tr></thead><tbody>'+quarters.map(q=>'<tr><td>'+q+'</td><td>'+fmt(qmean(base,q),2)+'%</td><td>'+fmt(qmean(sc,q),2)+'%</td><td>'+signed(qmean(sc,q)-qmean(base,q),2)+' pp</td></tr>').join('')+'</tbody></table>';
};
['food','core','energy'].forEach(k=>$('scenario-'+k).addEventListener('input',renderScenario));
const r34OldTrend=renderTrend;
$('trend-range').removeEventListener('change',r34OldTrend);
renderTrend=function(){
 const n=+$('trend-range').value,h=M.history,keys=['headline','core','services','goods'],labels=['Headline','Core','Non-tradable prices*','Other tradable prices*'],definitions=['Headline','Core','Non-tradable prices excluding regulated prices (ARAD)','Other tradable prices excluding food and fuel (ARAD)'];
 $('trend-legend').innerHTML=keys.map((k,i)=>'<span title="'+esc(definitions[i])+'"><i style="background:'+COLORS[k]+'"></i>'+labels[i]+'</span>').join('');
 chart('trend-chart',keys.map((k,i)=>({name:definitions[i],color:COLORS[k],points:h.months.map((m,j)=>[m,h[k][j]]).slice(-n)})),{height:310,target:true,label:'Headline, core and distinct ARAD tradable/non-tradable price indexes'});
};
$('trend-range').addEventListener('change',renderTrend);
const r34OldStatic=renderStatic;
renderStatic=function(){
 r34OldStatic();
 text('story-intro','August headline inflation is 1.9%. Services eased to 4.5%, while rent inflation remains elevated. The September nowcast and September-origin path are now recorded separately; the detailed 37-group analysis remains dated July.');
 $('vintage-strip').innerHTML='<span><b>Snapshot</b> '+DATA.snapshot_date+'</span><span><b>Official detail</b> Aug 2026</span><span><b>37-group panel</b> Jul 2026</span><span class="current-status"><b>Path re-estimated</b> '+month(CURRENT.meta.origin)+'</span>';
 $('source-issues').innerHTML=$('source-issues').innerHTML.replace('The July 37-group panel and model origin are unchanged.','The 37-group panel remains July; the model path has been re-estimated at a September origin.');
 $('bridge-table').innerHTML=CURRENT.ledger.map(r=>'<tr><td>'+month(r.month)+'</td><td>'+signed(r.dropout_mm,3)+'</td><td>'+signed(r.mm,3)+'</td><td>'+signed(r.base_effect_pp,3)+'</td><td>'+signed(r.new_price_pp,3)+'</td><td>'+signed(r.change_pp,3)+'</td><td>'+fmt(r.yy,2)+'%</td></tr>').join('');
 $('current-gap-quarter').innerHTML=CURRENT.gaps.map(r=>'<option value="'+r.quarter+'">'+r.quarter+'</option>').join('');
 if(CURRENT.gaps.some(r=>r.quarter==='2026Q4'))$('current-gap-quarter').value='2026Q4';
 renderSeasonal();renderForecastSummary();renderUncertainty();
};
const r34OldRedraw=redraw;
redraw=function(){r34OldRedraw();if(view==='forecasts'&&forecastMode==='outlook')renderUncertainty();};
$('uncertainty-sample').addEventListener('change',renderUncertainty);
$('current-gap-quarter').addEventListener('change',renderCurrentGap);
document.querySelector('#uncertainty-panel details').addEventListener('toggle',renderSensitivity);
renderStatic();reportOptions();renderModelToggles();renderScores();navigate(location.hash.slice(1)||'overview',false);visitMessage();
