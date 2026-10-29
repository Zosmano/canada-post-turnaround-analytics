"""Self-contained interactive HTML dashboard (plotly.js inlined, works offline)."""
import json
from pathlib import Path

import numpy as np
import plotly

from . import config as C
from .delivery import province_summary

PLOTLY_JS = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"


def _records(df, cols, n=None):
    d = df[cols].head(n) if n else df[cols]
    return json.loads(d.replace({np.nan: None}).to_json(orient="records"))


def build(profile, plan, summary, routes, metrics, call, oda=None):
    top = plan.sort_values("priority_rank")
    winback = plan.sort_values("est_parcel_drop_2025", ascending=False)
    data = {
        "summary": summary,
        "provinces": _records(province_summary(plan), ["province", "fsas", "delivery_points", "door_points",
                                                       "convertible_points", "annual_savings", "capex",
                                                       "cmb_sites_needed", "est_parcel_drop_2025"]),
        "top_fsas": _records(top, ["priority_rank", "fsa", "province", "door_points", "convertible_points",
                                   "accommodated_points", "annual_savings", "capex", "cmb_sites_needed",
                                   "share_65_plus", "equity_flag", "wave"]
                           + [c for c in ("dwellings_per_km2", "cp_lc_routes", "cp_depot_name") if c in top.columns], 40),
        "q2": C.Q2_2026,
        "winback": _records(winback, ["fsa", "province", "rural", "pop_2021", "parcel_demand_share",
                                      "est_parcel_drop_2025"], 25),
        "routes": routes,
        "oda": oda,
        "churn": metrics,
        "call": _records(call, list(call.columns), 40),
        "cost": {"labour": C.LOADED_LABOUR_COST_PER_HOUR, "km": C.VEHICLE_COST_PER_KM,
                 "cap": C.CMB_SITE_CAPACITY, "walk": C.CMB_MAX_WALK_M, "published": C.PUBLISHED_ANNUAL_SAVINGS,
                 "capex": C.CMB_CAPEX_PER_POINT, "target": C.NATIONAL_DOOR_POINTS_TARGET,
                 "accom_households": C.ACCOMMODATION_PROGRAM_HOUSEHOLDS, "accom_uplift": C.ACCOMMODATION_UPLIFT,
                 "propensity": C.DOOR_PROPENSITY},
    }
    # Plotly's bundle has a literal U+FFFD in a regex; the escape is equivalent and safe to publish.
    plotly = PLOTLY_JS.read_text(encoding="utf-8").replace("�", "\\uFFFD")
    html = (TEMPLATE.replace("/*__PLOTLY__*/", plotly)
            .replace("/*__DATA__*/null", json.dumps(data, default=float)))
    out = C.OUT_DIR / "dashboard.html"
    out.write_text(html, encoding="utf-8")
    return out


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Canada Post Turnaround Analytics</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,500;0,600;0,700;1,500&family=Source+Sans+3:wght@400;500;600;700&display=swap">
<style>
/* Vintage airmail: a midnight-indigo band with a faint postmark pattern and an airmail-stripe edge, cream paper,
   stamp-style dashed frames on the figures, Playfair Display for titles and figures, Source Sans 3 for text.
   Indigo carries the data; coral and gold are the accents. */
:root{color-scheme:light;--band:#1E2350;--amber:#D4603F;--gold:#B98B36;--band-muted:#C3C6E0;--page:#F7F2E7;--surface:#FFFCF5;--ink:#1D2140;--ink2:#3E4266;
--muted:#6A6C85;--grid:#EDE6D6;--axis:#D6CCB6;--border:#E0D6C1;--s1:#3B4A9C;--s2:#D4603F;--s3:#B98B36;--good:#2F7D55;--crit:#B4412C;--warn-bg:#FBEADF;
--serif:"Playfair Display","Iowan Old Style",Georgia,serif;--sans:"Source Sans 3","Segoe UI",system-ui,sans-serif}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#12142B;--surface:#1A1D3A;--ink:#F1ECE1;
--ink2:#CFCDE0;--muted:#A3A5C2;--grid:#262A4D;--axis:#353A63;--border:#2E3360;--s1:#8F9CF0;--s2:#EE8A6C;--s3:#D9B45F;--good:#5FBF8A;--crit:#E8806B;--warn-bg:#36231F}}
:root[data-theme="dark"]{color-scheme:dark;--page:#12142B;--surface:#1A1D3A;--ink:#F1ECE1;--ink2:#CFCDE0;--muted:#A3A5C2;--grid:#262A4D;
--axis:#353A63;--border:#2E3360;--s1:#8F9CF0;--s2:#EE8A6C;--s3:#D9B45F;--good:#5FBF8A;--crit:#E8806B;--warn-bg:#36231F}
*{box-sizing:border-box}body{margin:0;background:var(--page);color:var(--ink);font:400 15.5px/1.6 var(--sans);-webkit-font-smoothing:antialiased}
header{background-color:var(--band);color:#fff;padding:48px max(24px,calc((100% - 1232px)/2)) 40px;position:relative;
  background-image:repeating-radial-gradient(circle at 92% 30%,transparent 0 18px,rgba(195,198,224,.08) 18px 19px),
    repeating-linear-gradient(0deg,transparent 0 22px,rgba(195,198,224,.05) 22px 23px);
  border-bottom:10px solid transparent;
  border-image:repeating-linear-gradient(-45deg,#D4603F 0 14px,#F7F2E7 14px 22px,#3B4A9C 22px 36px,#F7F2E7 36px 44px) 10}
header .kicker{margin:0 0 12px;font:600 12.5px/1.3 var(--sans);letter-spacing:.2em;text-transform:uppercase;color:#E9A58E}
h1{font:600 clamp(38px,5.4vw,62px)/1.05 var(--serif);margin:0 0 14px;letter-spacing:-.005em;color:#FFFCF5;text-wrap:balance}
header p{margin:0;color:var(--band-muted);max-width:880px;font-size:16.5px}
nav{max-width:1280px;margin:0 auto;padding:0 24px;display:flex;gap:4px;flex-wrap:wrap;border-bottom:1px solid var(--border);background:var(--page)}
nav button{background:none;border:0;border-bottom:3px solid transparent;color:var(--muted);padding:16px 12px 13px;font:600 14.5px/1 var(--sans);cursor:pointer}
nav button:hover{color:var(--ink)}
nav button[aria-selected=true]{color:var(--ink);border-color:var(--amber)}
main{max-width:1280px;margin:auto;padding:24px 24px 56px;overflow-x:hidden}@media(max-width:600px){main,nav{padding-left:16px;padding-right:16px}header{padding:32px 16px 28px}}section{display:none}section.on{display:block}
h2{font:600 clamp(28px,3.4vw,38px)/1.12 var(--serif);margin:30px 0 10px}
h2::after{content:"";display:block;width:64px;height:4px;margin-top:10px;background:linear-gradient(90deg,var(--amber) 0 50%,var(--s1) 50% 100%)}h3{font:600 15px/1.35 var(--sans);margin:0 0 6px}.sub{color:var(--muted);margin:0 0 14px;max-width:80ch}
header p.byline{margin-top:12px;font:500 13px/1.4 var(--sans);color:var(--band-muted)}header p.byline b{color:#fff;font-weight:600}
footer{background:var(--band);color:var(--band-muted);font-size:13px;padding:24px max(24px,calc((100% - 1232px)/2)) 34px;
  border-top:6px solid transparent;border-image:repeating-linear-gradient(-45deg,#D4603F 0 14px,#F7F2E7 14px 22px,#3B4A9C 22px 36px,#F7F2E7 36px 44px) 6}
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:16px}
.tile{background:var(--surface);border:1px solid var(--border);outline:1.5px dashed var(--axis);outline-offset:-7px;padding:18px 20px;box-shadow:0 2px 0 var(--border)}
.tile .k{color:var(--muted);font-size:11.5px;font-weight:600;letter-spacing:.12em;text-transform:uppercase}.tile .v{font:600 34px/1.08 var(--serif);margin-top:8px;font-variant-numeric:lining-nums tabular-nums;color:var(--s1)}.tile .n{color:var(--muted);font-size:12.5px;margin-top:4px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px}@media(max-width:900px){.grid2{grid-template-columns:1fr}}
.card{background:var(--surface);border:1px solid var(--border);box-shadow:0 1px 0 var(--border);padding:20px 22px;margin-top:18px;min-width:0}
.chart{width:100%;max-width:100%;height:340px}.map{height:440px}
.tbl{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13.5px}th,td{padding:8px 8px;border-bottom:1px solid var(--grid);text-align:right;white-space:nowrap}
th{color:var(--muted);font-weight:600;font-size:12.5px;position:sticky;top:0;background:var(--surface);border-bottom-color:var(--border)}td:first-child,th:first-child{text-align:left}
td.l,th.l{text-align:left;white-space:normal;min-width:220px}.num{font-variant-numeric:tabular-nums}
.banner{background:var(--warn-bg);border:1px solid var(--border);border-left:6px solid var(--amber);padding:12px 16px;margin:14px 0}
.seg{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}.seg button{border:1px solid var(--border);background:var(--surface);color:var(--ink);
border-radius:999px;padding:8px 15px;font:600 13.5px/1 var(--sans);cursor:pointer}.seg button:hover{border-color:var(--s1)}.seg button[aria-pressed=true]{background:var(--band);color:#fff;border-color:var(--band)}
a{color:var(--s1)}.flag{color:var(--crit);font-weight:600}ul{padding-left:20px}li{margin:4px 0}code{font-size:12.5px}
</style></head><body>
<header><p class="kicker">Delivery network · Route optimization · Parcel win-back</p><h1>Canada Post Turnaround Analytics</h1>
<p>Cut delivery cost and win back parcel customers. The delivery network model combines Canada Post's own delivery-point, delivery-mode and address-range data (July 2017) with the 2021 Census and Statistics Canada's National Address Register (10.7M buildings, 16.2M addresses, June 2026) across all 1,646 postal Forward Sortation Areas (FSAs). The customer churn model uses simulated customers until real CRM and billing data are connected. Independent analysis, not produced by or affiliated with Canada Post.</p>
<p class="byline">Analysis and design by <b>Osman Zakaria, PMP</b></p></header>
<nav id="tabs"></nav><main>
<section id="delivery">
 <h2>Where Canada Post stands (Q2 2026)</h2>
 <p class="sub">From Canada Post's 2026 Second Quarter Financial Report (period ended July 4, 2026).</p>
 <div class="tiles" id="qTiles"></div>
 <h2>Door-to-door to community mailbox conversion</h2>
 <p class="sub">Delivery points by mode come from Canada Post's Householder data for each FSA. Which door-eligible homes are still door-to-door is estimated from census construction periods, calibrated to about 4 million door-to-door addresses nationally.</p>
 <div class="tiles" id="dTiles"></div>
 <div class="grid2"><div class="card"><h3>Annual savings by province</h3><div id="cProv" class="chart"></div></div>
 <div class="card"><h3>Rollout waves</h3><p class="sub">Each wave converts about a third of the points. Highest-priority FSAs go first; priority is savings weighted by readiness (fewer accommodation requests, no equity flag).</p><div id="cWave" class="chart" style="height:280px"></div></div></div>
 <div class="card"><h3>Top 40 FSAs to convert first</h3><div class="tbl" id="tTop"></div></div>
</section>
<section id="routes">
 <h2>Community mailbox siting and route optimization</h2>
 <p class="sub"><b>Real-address</b> cases are the results. Each runs the whole FSA on National Address Register buildings with Canada Post delivery modes, in carrier zones from the real depot, with distances along real streets. <b>Method checks</b> rerun the same FSAs on a synthetic 1,500-home street grid with the same mix of homes. That simpler method is the fallback for the 40 FSAs without enough address data, and it is shown here only to confirm it agrees with the real-address results. CMBs are sited by capacitated facility location with min-cost-flow assignment; routes come from Clarke-Wright savings plus 2-opt and relocation.</p>
 <div class="seg" id="fsaPick"></div><div class="tiles" id="rTiles"></div>
 <div class="grid2"><div class="card"><h3>Before: door-to-door walking routes</h3><div id="mBefore" class="chart map"></div></div>
 <div class="card"><h3>After: community mailboxes on a vehicle route</h3><div id="mAfter" class="chart map"></div></div></div>
 <div class="card"><h3>Daily delivery hours per 1,000 homes, before vs after</h3><p class="sub">Real bars are the results. Method-check bars rerun the same FSAs on a synthetic street grid with the same mix of homes, to confirm the simpler method used where address data is missing gives the same picture.</p><div id="cHours" class="chart" style="height:280px"></div></div>
</section>
<section id="churn">
 <h2>Business customer churn early warning</h2>
 <div class="banner"><b>Simulated customers.</b> No Canada Post customer data is public. The 8,000 business shippers here are simulated, including the 2024 and 2025 strikes and the January 2026 price increase. The model, features and call list run unchanged on real CRM and billing extracts (schema in README.md).</div>
 <div class="tiles" id="kTiles"></div>
 <div class="grid2"><div class="card"><h3>Total parcels per month (simulated customers)</h3><div id="cVol" class="chart"></div></div>
 <div class="card"><h3>On-time delivery rate</h3><div id="cOT" class="chart"></div></div>
 <div class="card"><h3>Churners caught vs share of customers contacted</h3><div id="cGain" class="chart"></div></div>
 <div class="card"><h3>Calibration: predicted vs observed churn</h3><div id="cCal" class="chart"></div></div>
 <div class="card"><h3>What drives churn (permutation importance)</h3><div id="cImp" class="chart"></div></div>
 <div class="card"><h3>Recommended retention actions</h3><div id="cAct" class="chart"></div></div></div>
 <div class="card"><h3>Sales call list, ranked by expected value of the retention action</h3><div class="tbl" id="tCall"></div></div>
</section>
<section id="winback">
 <h2>Where the parcel volume went</h2>
 <p class="sub">Canada Post's parcel volume fell by 79 million pieces (32.6%) in 2025 compared with 2024, as business customers moved shipments to other carriers during the labour disruption. The parcels were delivered by competitors, not lost in transit. This view allocates the drop to FSAs by modelled parcel demand (households, income, working from home and education) to set win-back sales targets by territory.</p>
 <div class="grid2"><div class="card"><h3>Top 25 FSAs by estimated 2025 parcel volume drop</h3><div id="cWin" class="chart" style="height:560px"></div></div>
 <div class="card"><h3>By province</h3><div class="tbl" id="tProvWin"></div></div></div>
</section>
<section id="method">
 <h2>Method and assumptions</h2>
 <div class="card" id="methodBody"></div>
</section>
</main>
<footer>© 2026 Osman Zakaria, PMP. Independent analysis; not produced by or affiliated with Canada Post.</footer>
<script>/*__PLOTLY__*/</script>
<script>
const D=/*__DATA__*/null;
const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const fmt=(v,d=0)=>v==null||isNaN(v)?'—':Number(v).toLocaleString('en-CA',{maximumFractionDigits:d,minimumFractionDigits:d});
const money=(v)=>v==null?'—':Math.abs(v)>=1e9?'$'+fmt(v/1e9,2)+'B':Math.abs(v)>=1e6?'$'+fmt(v/1e6,1)+'M':Math.abs(v)>=1e3?'$'+fmt(v/1e3,0)+'K':'$'+fmt(v,0);
const big=v=>v>=1e6?fmt(v/1e6,2)+'M':v>=1e3?fmt(v/1e3,1)+'K':fmt(v);
const pct=(v,d=1)=>v==null?'—':fmt(v*100,d)+'%';
const tiles=(id,arr)=>document.getElementById(id).innerHTML=arr.map(([k,v,n])=>`<div class="tile"><div class="k">${k}</div><div class="v">${v}</div>${n?`<div class="n">${n}</div>`:''}</div>`).join('');
function table(id,rows,cols){document.getElementById(id).innerHTML='<table><thead><tr>'+cols.map(c=>`<th class="${c.l?'l':''}">${c.h}</th>`).join('')+
 '</tr></thead><tbody>'+rows.map(r=>'<tr>'+cols.map(c=>`<td class="${c.l?'l':'num'}">${c.f?c.f(r[c.k],r):r[c.k]}</td>`).join('')+'</tr>').join('')+'</tbody></table>'}
function base(extra={}){const ink=css('--ink2'),grid=css('--grid');return Object.assign({paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',
 font:{family:'Source Sans 3,Segoe UI,system-ui,sans-serif',color:ink,size:12.5},margin:{l:56,r:16,t:8,b:40},showlegend:false,
 xaxis:{gridcolor:grid,zerolinecolor:css('--axis'),linecolor:css('--axis')},yaxis:{gridcolor:grid,zerolinecolor:css('--axis'),linecolor:css('--axis')},
 hoverlabel:{bgcolor:css('--surface'),bordercolor:css('--axis'),font:{color:css('--ink')}}},extra)}
const cfg={displayModeBar:false,responsive:true};
const REAL=r=>r.source.includes('real');
const SG=(()=>{try{const c=document.createElement('canvas');return c.getContext('webgl2')||c.getContext('webgl')?'scattergl':'scatter'}catch(e){return 'scatter'}})();
const plot=(id,tr,lay)=>Plotly.react(id,tr,base(lay),cfg);

const TABS=[['delivery','Delivery network'],['routes','Route optimizer'],['churn','Customer churn'],['winback','Parcel win-back'],['method','Method & assumptions']];
let cur=localGet('tab')||'delivery';
function localGet(k){try{return localStorage.getItem('cp_'+k)}catch(e){return null}}
function localSet(k,v){try{localStorage.setItem('cp_'+k,v)}catch(e){}}
function showTab(t){cur=t;localSet('tab',t);document.querySelectorAll('section').forEach(s=>s.classList.toggle('on',s.id===t));
 document.querySelectorAll('nav button').forEach(b=>b.setAttribute('aria-selected',b.dataset.t===t));renderAll();document.querySelectorAll('#'+t+' .chart').forEach(d=>d.data&&Plotly.Plots.resize(d))}
document.getElementById('tabs').innerHTML=TABS.map(([t,l])=>`<button data-t="${t}">${l}</button>`).join('');
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>showTab(b.dataset.t));

function renderDelivery(){const s=D.summary,q=D.q2,src=s.points_source||{};
 tiles('qTiles',[['Loss before tax, Q2 2026',money(q.segment_loss_before_tax_q2),'Canada Post segment; '+money(q.segment_loss_before_tax_h1)+' in the first half'],
 ['Government funding received',money(q.funding_received_total),money(q.funding_approved_remaining)+' more approved to March 2027'],
 ['Parcel revenue, Q2',money(q.parcel_revenue_q2),'+'+pct(q.parcel_revenue_growth_q2,1)+' revenue, +'+pct(q.parcel_volume_growth_q2,1)+' volume vs Q2 2025'],
 ['Transaction mail revenue, Q2',pct(q.transaction_mail_revenue_growth_q2,1),'vs Q2 2025'],
 ['Conversions announced',big(q.conversion_wave_late_2026.addresses+q.conversion_wave_2027.addresses),
  `${big(q.conversion_wave_late_2026.addresses)} in ${q.conversion_wave_late_2026.communities} communities (late 2026–early 2027), ${big(q.conversion_wave_2027.addresses)} in ${q.conversion_wave_2027.communities} (2027)`],
 ['Delivery Accommodation Program',fmt(q.accommodation_households),'households today']]);
 tiles('dTiles',[['Residential delivery points',big(s.delivery_points),`${fmt(src['Canada Post 2017']||0)} FSAs from Canada Post counts, ${fmt(src.census||0)} from census`],
 ['Door-to-door today',big(s.door_points),'calibrated national total'],
 ['Convertible to CMB',big(s.convertible_points),big(s.accommodated_points)+' keep door delivery (accommodation)'],
 ['Business points',big(s.business_points),'keep business delivery'],['Letter carrier routes',s.cp_lc_routes?big(s.cp_lc_routes):'—','Canada Post Householder data'],
 ['Annual savings',money(s.annual_savings),'govt. estimate ~'+money(D.cost.published)],['One-time capital',money(s.capex),'CMB units and installation'],
 ['Payback',fmt(s.payback_years,1)+' yrs',''],['New CMB sites',big(s.cmb_sites_needed),D.cost.cap+' compartments per site'],
 ['FSAs needing extra engagement',fmt(s.equity_flag_fsas),'older and lower-income']]);
 const pv=[...D.provinces].sort((a,b)=>a.annual_savings-b.annual_savings);
 plot('cProv',[{type:'bar',orientation:'h',y:pv.map(r=>r.province),x:pv.map(r=>r.annual_savings),marker:{color:css('--s1')},
  customdata:pv.map(r=>[r.convertible_points,r.cmb_sites_needed]),hovertemplate:'%{y}: $%{x:,.0f}/yr<br>%{customdata[0]:,.0f} points, %{customdata[1]:,.0f} sites<extra></extra>'}],
  {xaxis:{tickprefix:'$',gridcolor:css('--grid')},yaxis:{automargin:true},bargap:.25,margin:{l:60,r:16,t:8,b:40}});
 const w=Object.entries(s.waves);
 plot('cWave',[{type:'bar',x:w.map(([k])=>'Wave '+k),y:w.map(([,v])=>v.annual_savings),marker:{color:css('--s1')},
  text:w.map(([,v])=>fmt(v.fsas)+' FSAs'),textposition:'outside',customdata:w.map(([,v])=>v.points),
  hovertemplate:'%{x}: $%{y:,.0f}/yr<br>%{customdata:,.0f} points, %{text}<extra></extra>'}],{yaxis:{tickprefix:'$',gridcolor:css('--grid')},bargap:.5});
 table('tTop',D.top_fsas,[{h:'Rank',k:'priority_rank',f:v=>fmt(v)},{h:'FSA',k:'fsa'},{h:'Prov.',k:'province'},{h:'Door points',k:'door_points',f:v=>fmt(v)},
 {h:'Convertible',k:'convertible_points',f:v=>fmt(v)},{h:'Keep door',k:'accommodated_points',f:v=>fmt(v)},{h:'Annual savings',k:'annual_savings',f:money},
 {h:'Capital',k:'capex',f:money},{h:'CMB sites',k:'cmb_sites_needed',f:v=>fmt(v)},{h:'Homes / km²',k:'dwellings_per_km2',f:v=>fmt(v)},{h:'Age 65+',k:'share_65_plus',f:v=>pct(v)},
 {h:'Equity flag',k:'equity_flag',f:v=>v?'<span class="flag">⚑ Yes</span>':'No'},{h:'Wave',k:'wave',f:v=>fmt(v)},
 {h:'LC routes',k:'cp_lc_routes',f:v=>fmt(v)},{h:'Main depot',k:'cp_depot_name',l:1,f:v=>v||'—'}]);}

let pick=0;
function renderRoutes(){const R=D.routes;if(!R.length)return;
 document.getElementById('fsaPick').innerHTML=R.map((r,i)=>`<button aria-pressed="${i===pick}" data-i="${i}">${r.fsa} · ${r.province} · ${REAL(r)?'real addresses':'method check'}</button>`).join('');
 document.querySelectorAll('#fsaPick button').forEach(b=>b.onclick=()=>{pick=+b.dataset.i;renderRoutes()});
 const r=R[pick],b=r.before,a=r.after;
 tiles('rTiles',[['Households modelled',fmt(r.sample_households),`${r.mix.door} door, ${r.mix.existing_cmb} CMB, ${r.mix.lobby_units} apartment`],
 ['Data',REAL(r)?'Real addresses':'Method check',r.oda_coverage!=null?`${r.source.split(' ')[0]}: ${fmt(r.oda_locations)} buildings, ${pct(r.oda_coverage,0)} of homes, ${pct(r.postal_match_rate||0,0)} with a Canada Post delivery mode, ${r.zones} zones; distances: ${r.distance_model||'straight line × 1.3'}`:'Synthetic street grid, same mix of homes, scaled ×'+fmt(r.scale_factor,1)],
 ...(r.cp_routes?[['Canada Post today',`${r.cp_routes.lc} + ${r.cp_routes.ss} routes`,`letter carrier + suburban (2017); model: ${fmt(r.model_hours_per_cp_route,1)} delivery h per route`],
   ['Depot',r.depot_name||'—',r.depot_geocode||'']]:[]),
 ['CMB sites after',fmt(r.cmb_sites_after),'was '+r.cmb_sites_existing],['Average walk to CMB',fmt(r.mean_walk_to_cmb_m)+' m','max '+fmt(r.max_walk_to_cmb_m)+' m (limit '+D.cost.walk+' m)'],
 ['Routes',`${b.walk_routes+b.drive_routes} → ${a.drive_routes}`,`${b.walk_routes} walking loops + ${b.drive_routes} vehicle → vehicle only`],
 ['Daily delivery cost',`${money(b.daily_cost)} → ${money(a.daily_cost)}`,pct(1-a.daily_cost/b.daily_cost,0)+' lower'],
 ['FSA saving (route model)',money(r.annual_saving_fsa_bottom_up)+'/yr','labour and vehicle only'],['FSA saving (cost model)',money(r.annual_saving_fsa_top_down)+'/yr','all-in unit costs']]);
 const P=r.plot,mut=css('--muted');
 const pts=(k,name,sym,col,size)=>({type:SG,mode:'markers',name,x:P.points[k].map(p=>p[0]),y:P.points[k].map(p=>p[1]),
  marker:{symbol:sym,color:col,size},hovertemplate:name+'<extra></extra>'});
 const lines=(routes,col,name)=>routes.map(rt=>rt.slice(1,-1)).map((rt,i)=>({type:SG,mode:'lines',name:name+' '+(i+1),x:rt.map(p=>p[0]),y:rt.map(p=>p[1]),
  line:{color:col,width:2},opacity:.85,hovertemplate:name+' '+(i+1)+'<extra></extra>'}));
 const depot={type:'scatter',mode:'markers+text',x:[P.depot[0]],y:[P.depot[1]],text:['Depot'],textposition:'middle right',
  marker:{symbol:'diamond',size:12,color:css('--ink')},hovertemplate:'Depot<extra></extra>',textfont:{color:css('--ink2')},showlegend:false};
 const lay={xaxis:{visible:false,scaleanchor:'y'},yaxis:{visible:false},margin:{l:4,r:4,t:4,b:4},showlegend:true,
  legend:{orientation:'h',y:-.02,font:{size:11}}};
 const hide=t=>Object.assign(t,{showlegend:false});
 const wl=lines(P.routes_before_walk,css('--s1'),'Walking route');wl.forEach((t,i)=>i&&hide(t));wl[0]&&(wl[0].name='Walking route');
 plot('mBefore',[pts('cmb','Already on CMB','circle',mut,4),pts('lobby','Apartment lobby','square',css('--s3'),REAL(r)?5:9),...wl,pts('door','Door-to-door home','circle',css('--s1'),5),depot],lay);
 const al=lines(P.routes_after,css('--s2'),'Vehicle route');al.forEach((t,i)=>i&&hide(t));al[0]&&(al[0].name='Vehicle route');
 const homes=['door','cmb'].flatMap(k=>P.points[k]);
 plot('mAfter',[{type:SG,mode:'markers',name:'Home (uses CMB)',x:homes.map(p=>p[0]),y:homes.map(p=>p[1]),marker:{color:mut,size:4},hovertemplate:'Home<extra></extra>'},
  pts('lobby','Apartment lobby','square',css('--s3'),REAL(r)?5:9),...al,
  {type:'scatter',mode:'markers',name:'CMB site',x:P.sites_after.map(s=>s[0]),y:P.sites_after.map(s=>s[1]),
   marker:{color:css('--s2'),size:P.sites_after.map(s=>REAL(r)?4+s[2]/16:8+s[2]/6),line:{color:css('--surface'),width:2}},
   customdata:P.sites_after.map(s=>s[2]),hovertemplate:'CMB site: %{customdata} households<extra></extra>'},depot],lay);
 const per=r=>1000/r.sample_households,lab=R.map(r=>r.fsa+(REAL(r)?' (real)':' (method check)'));
 plot('cHours',[{type:'bar',name:'Before',x:lab,y:R.map(r=>(r.before.walk_hours+r.before.drive_hours)*per(r)),marker:{color:css('--s1')},hovertemplate:'%{x} before: %{y:.2f} h/day per 1,000 homes<extra></extra>'},
  {type:'bar',name:'After',x:lab,y:R.map(r=>r.after.drive_hours*per(r)),marker:{color:css('--s2')},hovertemplate:'%{x} after: %{y:.2f} h/day per 1,000 homes<extra></extra>'}],
  {barmode:'group',bargap:.35,bargroupgap:.08,showlegend:true,legend:{orientation:'h',y:1.12},yaxis:{title:{text:'hours / day per 1,000 homes'},gridcolor:css('--grid')}});}

function renderChurn(){const M=D.churn,g=M.gbm,lb=M.logistic_baseline,L=M.live;
 tiles('kTiles',[['Out-of-time AUC',fmt(g.auc,3),'logistic baseline '+fmt(lb.auc,3)],['Top-10% lift',fmt(g.lift_top10,1)+'×','base churn rate '+pct(g.base_rate)],
 ['Churners caught in top 10%',pct(g.recall_top10,0),'revenue captured '+pct(g.revenue_captured_top10,0)],['Customers scored (Sep 2026)',fmt(L.customers_scored),''],
 ['Expected churners, next 3 months',fmt(L.expected_churners_next_3m),''],['Revenue at risk',money(L.revenue_at_risk),'probability × annual revenue'],
 ['Call list',fmt(L.call_list_size),'expected value '+money(L.call_list_expected_value)]]);
 const mt=M.monthly_totals,strikes=['2024-11','2024-12','2025-09','2025-10'];
 const shapes=strikes.map(m=>({type:'rect',xref:'x',yref:'paper',x0:m+'-01',x1:addMonth(m),y0:0,y1:1,fillcolor:css('--grid'),opacity:.6,line:{width:0},layer:'below'}));
 const ann=[{x:'2024-12-01',y:1,yref:'paper',text:'2024 strike',showarrow:false,yanchor:'bottom',font:{size:11,color:css('--ink2')}},
  {x:'2025-10-01',y:1,yref:'paper',text:'2025 strikes',showarrow:false,yanchor:'bottom',font:{size:11,color:css('--ink2')}},
  {x:'2026-01-15',y:1,yref:'paper',text:'Price increase',showarrow:false,yanchor:'bottom',font:{size:11,color:css('--ink2')}}];
 const xs=mt.map(r=>r.month+'-15');
 plot('cVol',[{type:'scatter',mode:'lines+markers',x:xs,y:mt.map(r=>r.parcels),line:{color:css('--s1'),width:2},marker:{size:8,line:{color:css('--surface'),width:2}},hovertemplate:'%{x|%b %Y}: %{y:,.0f} parcels<extra></extra>'}],
  {shapes,annotations:ann,margin:{l:64,r:16,t:24,b:40},xaxis:{type:'date',gridcolor:css('--grid')},yaxis:{rangemode:'tozero',gridcolor:css('--grid')},hovermode:'x unified'});
 plot('cOT',[{type:'scatter',mode:'lines+markers',x:xs,y:mt.map(r=>r.on_time),line:{color:css('--s1'),width:2},marker:{size:8,line:{color:css('--surface'),width:2}},hovertemplate:'%{x|%b %Y}: %{y:.1%}<extra></extra>'}],
  {shapes,annotations:ann,margin:{l:56,r:16,t:24,b:40},xaxis:{type:'date',gridcolor:css('--grid')},yaxis:{tickformat:'.0%',gridcolor:css('--grid')},hovermode:'x unified'});
 const G=M.gains;
 plot('cGain',[{type:'scatter',mode:'lines',name:'Model',x:G.map(r=>r.pct_contacted),y:G.map(r=>r.pct_churners_caught*100),line:{color:css('--s1'),width:2},hovertemplate:'Contact %{x}% → catch %{y:.0f}% of churners<extra></extra>'},
  {type:'scatter',mode:'lines',name:'Random',x:[0,100],y:[0,100],line:{color:css('--muted'),width:2,dash:'dash'},hoverinfo:'skip'}],
  {showlegend:true,legend:{orientation:'h',y:1.12},xaxis:{title:{text:'% of customers contacted'},ticksuffix:'%',gridcolor:css('--grid')},yaxis:{title:{text:'% of churners caught'},ticksuffix:'%',gridcolor:css('--grid')}});
 const cal=M.calibration,mx=Math.max(...cal.map(c=>Math.max(c.predicted,c.observed)))*1.05;
 plot('cCal',[{type:'scatter',mode:'lines',x:[0,mx],y:[0,mx],line:{color:css('--muted'),dash:'dash',width:2},hoverinfo:'skip'},
  {type:'scatter',mode:'markers',x:cal.map(c=>c.predicted),y:cal.map(c=>c.observed),marker:{color:css('--s1'),size:10,line:{color:css('--surface'),width:2}},hovertemplate:'Predicted %{x:.1%}, observed %{y:.1%}<extra></extra>'}],
  {xaxis:{title:{text:'Predicted churn (decile mean)'},tickformat:'.0%',gridcolor:css('--grid')},yaxis:{title:{text:'Observed churn'},tickformat:'.0%',gridcolor:css('--grid')}});
 const im=M.importance.slice(0,12).reverse();
 plot('cImp',[{type:'bar',orientation:'h',y:im.map(r=>r.feature.replaceAll('_',' ')),x:im.map(r=>r.auc_drop),marker:{color:css('--s1')},hovertemplate:'%{y}: AUC drops %{x:.3f} when shuffled<extra></extra>'}],
  {yaxis:{automargin:true},xaxis:{title:{text:'AUC drop when shuffled'},gridcolor:css('--grid')},margin:{l:150,r:16,t:8,b:44}});
 const ac=Object.entries(L.actions).sort((a,b)=>a[1]-b[1]);
 plot('cAct',[{type:'bar',orientation:'h',y:ac.map(a=>a[0].replaceAll('_',' ')),x:ac.map(a=>a[1]),marker:{color:css('--s1')},hovertemplate:'%{y}: %{x} customers<extra></extra>'}],
  {yaxis:{automargin:true},xaxis:{title:{text:'customers on call list'},gridcolor:css('--grid')},margin:{l:150,r:16,t:8,b:44}});
 table('tCall',D.call,[{h:'Customer',k:'customer_id'},{h:'Segment',k:'segment',f:v=>v.replaceAll('_',' ')},{h:'FSA',k:'fsa'},{h:'Annual revenue',k:'annual_revenue',f:money},
 {h:'Churn prob.',k:'churn_prob',f:v=>pct(v,0)},{h:'At risk',k:'revenue_at_risk',f:money},{h:'Why',k:'top_reasons',l:1},
 {h:'Action',k:'recommended_action',f:v=>v.replaceAll('_',' ')},{h:'Expected value',k:'expected_value_of_action',f:money}]);}
function addMonth(m){let [y,mo]=m.split('-').map(Number);mo++;if(mo>12){mo=1;y++}return `${y}-${String(mo).padStart(2,'0')}-01`}

function renderWin(){const w=[...D.winback].reverse();
 plot('cWin',[{type:'bar',orientation:'h',y:w.map(r=>r.fsa+' ('+r.province+')'),x:w.map(r=>r.est_parcel_drop_2025),marker:{color:css('--s1')},
  customdata:w.map(r=>r.pop_2021),hovertemplate:'%{y}: %{x:,.0f} fewer parcels (est.)<br>population %{customdata:,.0f}<extra></extra>'}],
  {yaxis:{automargin:true},xaxis:{gridcolor:css('--grid')},margin:{l:90,r:16,t:8,b:40},bargap:.25});
 const pv=[...D.provinces].sort((a,b)=>b.est_parcel_drop_2025-a.est_parcel_drop_2025);
 table('tProvWin',pv,[{h:'Province',k:'province'},{h:'FSAs',k:'fsas',f:v=>fmt(v)},{h:'Volume drop (est.)',k:'est_parcel_drop_2025',f:v=>big(v)},
  {h:'Share',k:'est_parcel_drop_2025',f:v=>pct(v/79e6)}]);}

function renderMethod(){const c=D.cost,s=D.summary,u=s.unit_costs;
 document.getElementById('methodBody').innerHTML=`
 <h3>Data</h3><ul><li>Statistics Canada, 2021 Census Profile for Forward Sortation Areas (98-401-X2021013): dwelling type, construction period, age, income, work location, industry. 1,646 FSAs, 36.99M people.</li>
 <li>Confidence-interval files (98-401-X2021013CI, 98-401-X2021003CI): the width of the 95% CI on full-time employment income flags FSAs with unreliable sample estimates (${fmt(D.summary.fsas)} FSAs modelled).</li>
 <li>Land area and 2016 population are blank for FSAs in this census release. Land area and density come from the StatCan 2021 FSA Boundary File, and rurality from the Canada Post convention (0 in the second character).</li>
 <li>Canada Post data products, release effective July 17, 2017: Householder Data (points of call by FSA, route and delivery mode; ${s.cp_lc_routes?big(s.cp_lc_routes):'—'} letter carrier routes), Delivery Mode Data (mode and route of 902K postal codes), and Postal Code Address Data (1.8M civic number ranges). Door-to-door conversions were paused from 2015 to 2025, so 2017 delivery modes are close to the 2026 starting point.${D.oda&&D.oda.postal_match_rate!=null?` ${pct(D.oda.postal_match_rate,0)} of addresses matched a Canada Post postal code and route.`:''}${D.oda&&D.oda.depots?` ${fmt(D.oda.depots.address_matched)} of ${fmt(D.oda.depots.installations)} delivery installations geocoded from their street address.`:''}</li>
 <li>Canada Post 2026 Second Quarter Financial Report: financial position, conversion schedule and accommodation program size.</li>
 <li>Canada Post 2025 annual results (April 20, 2026): parcel volume down 79 million pieces (32.6%) and parcel revenue down $850 million (30.1%) from 2024. The volume drop is allocated to FSAs in proportion to modelled parcel demand. It is a territory target, not observed customer losses by area.</li></ul>
 <h3>Delivery cost model</h3><ul><li>Annual cost per point: door ${money(u.door)} and CMB ${money(u.cmb)} (Canada Post 2025 Annual Report); lobby ${money(u.lobby)} and rural ${money(u.rural)} are assumptions.</li>
 <li>Door-eligible points: Canada Post letter-carrier houses plus duplex flats (census share of letter-carrier apartments). Suburban-service, lock-box and rural points are already centralized. Which door-eligible points are still door-to-door follows census construction period (relative propensity pre-1981 1, 1981-90 ${c.propensity['1981_1990']}, post-1990 ${c.propensity.post1990}), scaled to ${big(c.target)} nationally (pre-1981 share ${pct(s.pre1981_door_share,0)}).</li>
 <li>Accommodation: today's program (${fmt(c.accom_households)} households) as a share of households already on centralized delivery (${pct(s.accommodation_base_rate,2)}), scaled by each FSA's share of maintainers aged 75+ (uplift ×${c.accom_uplift}). CMB capital ${money(c.capex)} per compartment.</li>
 <li>Sanity check: the federal government estimates close to ${money(c.published)} a year once about 4M addresses are converted; this model gives ${money(s.annual_savings)}. The door-vs-CMB cost gap is the dominant assumption.</li></ul>
 <h3>Route optimizer</h3><ul><li>Street-grid network distance (driveway + street + detour to the nearest cross street). Walking 4.5 km/h, vehicle 25 km/h, carriers driven to and from their walk.</li>
 <li>CMB siting: greedy maximum coverage → min-cost-flow capacitated assignment (≤${c.cap} households per site, ≤${c.walk} m walk) → close surplus sites → re-centre on members.</li>
 <li>Routing: Clarke-Wright savings under a shift-time limit → 2-opt → inter-route relocation → 2-opt. Labour $${c.labour}/h, vehicle $${c.km}/km, 250 days a year.</li>
 <li>Real-address cases use ${D.oda&&D.oda.source==='NAR'?`Statistics Canada's National Address Register (released June 26, 2026; ${fmt(D.oda.locations)} buildings, ${fmt(D.oda.addresses)} addresses, all 13 provinces and territories). Each NAR building is one delivery location, its addresses are its units, and the building-use code separates homes from non-residential buildings. The mailing postal code links each address directly to Canada Post's delivery mode and route; postal codes created after 2017 count as new developments already on community mailboxes`:`Statistics Canada's Open Database of Addresses (${D.oda?fmt(D.oda.locations):'—'} delivery locations). Addresses at the same coordinates count as one location`}. Matched addresses take their Canada Post delivery mode: block face = home, apartment building = lobby, suburban service = already centralized; business, PO box and rural points are left out. Unmatched locations with 5+ units are lobbies. Canada Post counts set how many homes there are and the address file sets where they are. Door-to-door delivery is assigned by whole letter-carrier route up to the modelled share, and routes start from the FSA's main Canada Post depot. Distances inside each carrier zone are shortest paths on the StatCan 2021 Road Network File (densified every 25 m, plus the walk from the sidewalk to each building); depot legs and points over 300 m from a road use straight line × 1.3.${D.oda&&D.oda.has_boundary_file?` Every address is assigned to its FSA by point-in-polygon against the StatCan 2021 FSA Boundary File; ${fmt(D.oda.fsas_usable)} FSAs have enough address coverage (≥60% of census homes) for real-address routing.`:' FSAs come from ODA postal codes, which exist only for New Brunswick, until the FSA boundary file is added.'}</li></ul>
 <h3>Churn model</h3><ul><li>Label: next-3-month parcels below 10% of the trailing 12-month average. Train on snapshots Dec 2025 to Mar 2026, test out-of-time on Jun 2026, score live at Sep 2026.</li>
 <li>Calibrated (isotonic) gradient boosting vs a logistic-regression baseline. Reason codes come from the drop in probability when each driver is reset to a healthy value; each reason maps to an action, ranked by p × revenue × save rate − cost.</li></ul>`;}

function renderAll(){({delivery:renderDelivery,routes:renderRoutes,churn:renderChurn,winback:renderWin,method:renderMethod})[cur]()}
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change',renderAll);
showTab(TABS.some(t=>t[0]===cur)?cur:'delivery');
</script></body></html>"""
