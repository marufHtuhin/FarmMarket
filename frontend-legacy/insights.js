const $=id=>document.getElementById(id),API="/api/v1";
let lang=localStorage.getItem("fm_lang")||"bn",activeTab="forecast";
let forecastChart=null,hubMap=null,routeMap=null,routeLayer=null,lastScenario=null;
const HUBS=[{name:"Dhaka",lat:23.8103,lon:90.4125},{name:"Chattogram",lat:22.3569,lon:91.7832},{name:"Rajshahi",lat:24.3745,lon:88.6042},{name:"Khulna",lat:22.8456,lon:89.5403},{name:"Sylhet",lat:24.8949,lon:91.8687}];
const OSM_URL="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",OSM_ATTR='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const TI={
bn:{brandTag:"মার্কেট ইন্টেলিজেন্স",backMarketplace:"← মার্কেটপ্লেস",pageKicker:"সিদ্ধান্ত সহায়তা",pageTitle:"মার্কেট ইন্টেলিজেন্স",pageSub:"দামের পূর্বাভাস, ফসলের গ্রেডিং, পরামর্শ, ডেলিভারি পরিকল্পনা ও ব্যাচের উৎস যাচাই। প্রতিটি ফলাফলে বলা থাকে এটি কীসের ভিত্তিতে এবং কতটা নির্ভরযোগ্য।",authNote:'গ্রেডিং, পরামর্শ ও ডেলিভারি পরিকল্পনার জন্য লগইন প্রয়োজন — প্রথমে <a class="font-bold underline" href="/">মূল পাতা</a> থেকে সাইন ইন করুন।',tabForecast:"দামের পূর্বাভাস",tabVision:"ছবি গ্রেডিং",tabAdvisor:"পরামর্শ",tabLogistics:"ডেলিভারি",tabTwin:"ব্যাচ টুইন",
forecastTitle:"দামের পূর্বাভাস",modelLabel:"মডেল",forecastBtn:"পূর্বাভাস দেখুন",fitting:"মডেল তৈরি হচ্ছে…",modelUsed:"ব্যবহৃত মডেল",signal:"সংকেত",reliable:"নির্ভরযোগ্য",reliableYes:"হ্যাঁ — সাধারণ পূর্বাভাসের চেয়ে ভালো",reliableNo:"না",skill:"বেসলাইনের চেয়ে দক্ষতা",smape:"ব্যাক-টেস্ট sMAPE",coverage:"ইন্টারভাল কভারেজ",historyPoints:"ইতিহাসের ডেটা পয়েন্ট",currencyUnit:"মুদ্রা / একক",week:"সপ্তাহ",forecast:"পূর্বাভাস",low:"সর্বনিম্ন",high:"সর্বোচ্চ",sources:"উৎস",history:"ইতিহাস",intervalBand:"৮০% ইন্টারভাল",hubsMapTitle:"ট্রেডিং হাবের মানচিত্র",hubsMapHint:"বাংলাদেশের প্রধান বাজার কেন্দ্রগুলো।",hubCountry:"বাংলাদেশ",
visionTitle:"পাকা ও রোগ গ্রেডিং",visionNote:"এখনো কোনো প্রশিক্ষিত রোগ শনাক্তকরণ মডেল নেই — মডেল প্রশিক্ষিত না হওয়া পর্যন্ত API 503 দেবে।",cropPh:"ফসল (যেমন: টমেটো)",refPricePh:"প্রতি কেজি রেফারেন্স দাম (ঐচ্ছিক)",assessBtn:"ছবি বিশ্লেষণ করুন",choosePhoto:"প্রথমে একটি ছবি বেছে নিন",analysing:"বিশ্লেষণ চলছে…",grade:"গ্রেড",ripeness:"পাকার মাত্রা",disease:"রোগ",confidence:"আত্মবিশ্বাস",priceMultiplier:"দামের গুণক",suggestedPrice:"প্রস্তাবিত দাম",manualReview:"ম্যানুয়াল রিভিউ",manualReviewNote:"দাম নির্ধারণের আগে ম্যানুয়াল যাচাই প্রয়োজন।",
advisorTitle:"আঞ্চলিক ভাষায় চাষ পরামর্শ",adviceBtn:"পরামর্শ নিন",preparing:"পরামর্শ তৈরি হচ্ছে…",mode:"মোড",fidelity:"প্রত্যাশিত ভাষাগত নির্ভুলতা",risks:"ঝুঁকি",noHub:"কোনো হাব নেই (শুধু রিপোর্ট)",reportPh:"বাজার / পণ্য রিপোর্ট এখানে পেস্ট করুন (ইংরেজি)। ঐচ্ছিক: শুধু দামের পূর্বাভাস থেকেও পরামর্শ তৈরি করা যায়।",humanReviewNote:"শেয়ার করার আগে একজন স্থানীয় ভাষাভাষী / সম্প্রসারণ কর্মকর্তার পর্যালোচনা প্রয়োজন",truncatedNote:"রিপোর্ট কাটা হয়েছে",readingsWord:"টি রিডিং",
logisticsTitle:"ডেলিভারি পরিকল্পনা (সময় + কার্বন + তাজা)",logisticsHint:"সিনারিও JSON সম্পাদনা করুন (স্টপ, যানবাহন, সময়সীমা, তাজা থাকার বাজেট), তারপর পরিকল্পনা করুন।",planBtn:"রুট পরিকল্পনা করুন",optimising:"অপ্টিমাইজ হচ্ছে…",vehicles:"যানবাহন",distanceKm:"দূরত্ব (কিমি)",minutes:"মিনিট",co2:"CO₂e (কেজি)",lateMin:"দেরি (মিনিট)",spoilage:"নষ্টের ঝুঁকি (মিনিট)",stop:"স্টপ",arriveMin:"পৌঁছানোর সময় (মিনিট)",late:"দেরি",tradeoff:"সময় বনাম কার্বন ট্রেড-অফ",co2Weight:"CO₂ ওজন",km:"কিমি",routeMapTitle:"পরিকল্পিত রুটের মানচিত্র",straightLine:"সরলরেখা অনুমান",osrm:"সড়ক নেটওয়ার্ক (OSRM, কনফিগার করা থাকলে)",baselineVs:"nearest-neighbour বেসলাইনের তুলনায়",objective:"উদ্দেশ্য",timeWord:"সময়",negativeWorse:"(ঋণাত্মক = সেই মাপে খারাপ)",depot:"ডিপো",
twinTitle:"ব্যাচ ডিজিটাল টুইন — উৎস যাচাই",lookupBtn:"খুঁজুন",batchPh:"ব্যাচ কোড, যেমন FM-1A2B3C4D5E6F",crop:"ফসল",origin:"উৎস জেলা",harvested:"সংগ্রহের তারিখ",chainIntact:"চেইন অক্ষত",coldChain:"কোল্ড চেইন",sensorReadings:"সেন্সর রিডিং",headHash:"হেড হ্যাশ",yes:"হ্যাঁ",no:"না",tamper:"না — কারসাজি ধরা পড়েছে",na:"প্রযোজ্য নয়",networkError:"সার্ভারের সঙ্গে যোগাযোগ করা যায়নি।",footerText:"কৃষকের ন্যায্য আয়, ক্রেতার সঠিক বাজার।",footerNote:"Hackathon MVP · তথ্য যাচাই করে লেনদেন করুন",builtWith:"যা দিয়ে তৈরি",stackCredits:"FastAPI · MySQL · scikit-learn · OpenStreetMap"},
en:{brandTag:"Market intelligence",backMarketplace:"← Marketplace",pageKicker:"Decision support",pageTitle:"Market intelligence",pageSub:"Forecasts, produce grading, advice, dispatch planning and batch provenance. Each result says what it is based on and how far to trust it.",authNote:'Grading, advice and dispatch planning need a login — sign in on the <a class="font-bold underline" href="/">main page</a> first.',tabForecast:"Price forecast",tabVision:"Photo grading",tabAdvisor:"Advisor",tabLogistics:"Dispatch",tabTwin:"Batch twin",
forecastTitle:"Price forecast",modelLabel:"Model",forecastBtn:"Forecast",fitting:"Fitting model…",modelUsed:"Model used",signal:"Signal",reliable:"Reliable",reliableYes:"yes — beats naive",reliableNo:"NO",skill:"Skill vs baseline",smape:"Back-test sMAPE",coverage:"Interval coverage",historyPoints:"History points",currencyUnit:"Currency / unit",week:"Week",forecast:"Forecast",low:"Low",high:"High",sources:"Sources",history:"History",intervalBand:"80% interval",hubsMapTitle:"Trading hubs map",hubsMapHint:"Main trading hubs in Bangladesh.",hubCountry:"Bangladesh",
visionTitle:"Ripeness & disease grading",visionNote:"No trained disease model ships yet — the API returns 503 until one is trained.",cropPh:"Crop (e.g. tomato)",refPricePh:"Reference price per kg (optional)",assessBtn:"Assess photo",choosePhoto:"Choose a photo first",analysing:"Analysing…",grade:"Grade",ripeness:"Ripeness",disease:"Disease",confidence:"Confidence",priceMultiplier:"Price multiplier",suggestedPrice:"Suggested price",manualReview:"manual review",manualReviewNote:"Needs a manual check before any price is set.",
advisorTitle:"Regional-language planting advisor",adviceBtn:"Get advice",preparing:"Preparing advice…",mode:"Mode",fidelity:"expected language fidelity",risks:"Risks",noHub:"No hub (report only)",reportPh:"Paste a market / commodity report (English). Optional: advice can also be built from the price forecast alone.",humanReviewNote:"review by a native speaker/extension officer before sharing",truncatedNote:"report was truncated",readingsWord:"readings",
logisticsTitle:"Dispatch planner (time + carbon + freshness)",logisticsHint:"Edit the scenario JSON (stops, vehicles, time windows, freshness budgets), then plan.",planBtn:"Plan routes",optimising:"Optimising…",vehicles:"Vehicles",distanceKm:"Distance km",minutes:"Minutes",co2:"CO₂e kg",lateMin:"Late min",spoilage:"Spoilage-risk min",stop:"Stop",arriveMin:"Arrive (min)",late:"Late",tradeoff:"Time vs carbon trade-off",co2Weight:"CO₂ weight",km:"Km",routeMapTitle:"Planned route map",straightLine:"Straight-line estimate",osrm:"Road network (OSRM, if configured)",baselineVs:"vs. nearest-neighbour baseline",objective:"objective",timeWord:"time",negativeWorse:"(negative = worse on that measure)",depot:"Depot",
twinTitle:"Batch Digital Twin — verify provenance",lookupBtn:"Look up",batchPh:"Batch code, e.g. FM-1A2B3C4D5E6F",crop:"Crop",origin:"Origin district",harvested:"Harvested",chainIntact:"Chain intact",coldChain:"Cold chain",sensorReadings:"Sensor readings",headHash:"Head hash",yes:"yes",no:"NO",tamper:"NO — tampering detected",na:"n/a",networkError:"Could not connect to the server.",footerText:"Fair income for farmers. Better access for buyers.",footerNote:"Hackathon MVP · Verify information before trading",builtWith:"Built with",stackCredits:"FastAPI · MySQL · scikit-learn · OpenStreetMap"}
};
function tr(k){return (TI[lang]&&TI[lang][k])||TI.en[k]||k}
function applyLanguage(){document.documentElement.lang=lang;document.querySelectorAll("[data-i18n]").forEach(el=>{const k=el.dataset.i18n;if(TI[lang][k])el.innerHTML=TI[lang][k]});document.querySelectorAll("[data-ph]").forEach(el=>el.placeholder=tr(el.dataset.ph));$("langBtn").textContent=lang==="bn"?"EN":"বাংলা";renderTabs()}
function toggleLanguage(){lang=lang==="bn"?"en":"bn";localStorage.setItem("fm_lang",lang);applyLanguage()}
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const tok=()=>localStorage.getItem("fm_token");
async function req(path,opts={}){const h={...(opts.headers||{})};if(opts.body&&!(opts.body instanceof FormData))h["Content-Type"]="application/json";if(tok())h.Authorization="Bearer "+tok();
 let r;try{r=await fetch(API+path,{...opts,headers:h})}catch(e){throw Error(tr("networkError"))}const d=await r.json().catch(()=>({}));
 if(!r.ok){let m=d.detail;if(Array.isArray(m))m=m.map(x=>x.msg).join(", ");throw Error(m||("Request failed ("+r.status+")"))}return d}
const err=e=>`<div class="bg-[#fceaea] border border-[#f1c4c4] text-[#a53f3f] rounded-2xl px-4 py-3 text-[13px] my-2">${esc(e.message)}</div>`;
const warns=a=>(a||[]).map(w=>`<div class="bg-[#fff8e9] border border-[#f4e4bf] text-[#80632d] rounded-2xl px-4 py-3 text-[13px] my-2">${esc(w)}</div>`).join("");
const kv=o=>`<div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2.5 my-3">${o.map(([k,v])=>`<div class="bg-mint rounded-2xl px-3.5 py-3 text-[13px] text-muted">${esc(k)}<b class="block text-brand-700 text-lg font-extrabold">${esc(v)}</b></div>`).join("")}</div>`;
const fill=(sel,items,val,txt)=>{sel.innerHTML=items.map(i=>`<option value="${esc(val(i))}">${esc(txt(i))}</option>`).join("")};
const TH="text-left px-2 py-2 border-b border-line font-bold",TD="text-left px-2 py-2 border-b border-line";
const TABS=[["forecast","tabForecast"],["vision","tabVision"],["advisor","tabAdvisor"],["logistics","tabLogistics"],["twin","tabTwin"]];
function tabCls(on){return "rounded-full px-4 py-2.5 font-bold text-sm transition shadow-sm "+(on?"bg-brand-700 text-white":"bg-white text-[#506057] border border-line hover:border-brand-300 hover:text-brand-700")}
function renderTabs(){$("tabs").innerHTML=TABS.map(([k,l])=>`<button data-k="${k}" class="${tabCls(k===activeTab)}">${tr(l)}</button>`).join("")}
function pick(k){activeTab=k;document.querySelectorAll("#tabs button").forEach(b=>{b.className=tabCls(b.dataset.k===k)});document.querySelectorAll(".pane").forEach(p=>p.classList.toggle("hidden",p.id!=="p-"+k));if(k==="forecast")setTimeout(initHubMap,30);if(k==="logistics"&&routeMap)setTimeout(()=>routeMap.invalidateSize(),30)}
$("tabs").onclick=e=>{if(e.target.dataset.k){pick(e.target.dataset.k);location.hash=e.target.dataset.k}};
if(!tok())$("authNote").classList.remove("hidden");

// ---- hubs map (Leaflet + OpenStreetMap) on the forecast tab ----
function initHubMap(){if(!window.L)return;if(hubMap){setTimeout(()=>hubMap.invalidateSize(),60);return}try{hubMap=L.map("fMap").setView([23.9,90.4],7);L.tileLayer(OSM_URL,{attribution:OSM_ATTR}).addTo(hubMap);HUBS.forEach(h=>L.marker([h.lat,h.lon]).addTo(hubMap).bindPopup(`<b>${esc(h.name)}</b><br>${tr("hubCountry")}`));setTimeout(()=>hubMap.invalidateSize(),60)}catch(e){/* map stays empty if Leaflet failed to load */}}

// ---- forecast chart (Chart.js): history + dashed forecast + 80% band ----
function drawForecastChart(h,f){if(!window.Chart||!h.length||!f.length)return;const c=$("fChart");if(!c)return;Chart.defaults.font.family='"Hind Siliguri",Inter,sans-serif';
 const labels=[...h.map(p=>p.ds),...f.map(p=>p.ds)],o=h.length;
 const hist=h.map(p=>p.y).concat(new Array(f.length).fill(null));
 const fc=new Array(o-1).fill(null).concat([h[o-1].y,...f.map(p=>p.yhat)]);
 const lo=new Array(o).fill(null).concat(f.map(p=>p.lower));
 const hi=new Array(o).fill(null).concat(f.map(p=>p.upper));
 if(forecastChart)forecastChart.destroy();
 forecastChart=new Chart(c,{type:"line",data:{labels,datasets:[
  {label:"",data:lo,borderColor:"transparent",backgroundColor:"transparent",pointRadius:0,fill:false},
  {label:tr("intervalBand"),data:hi,borderColor:"transparent",backgroundColor:"rgba(242,163,60,.20)",pointRadius:0,fill:"-1"},
  {label:tr("history"),data:hist,borderColor:"#1E7A4C",backgroundColor:"#1E7A4C",pointRadius:2,tension:.1,fill:false},
  {label:tr("forecast"),data:fc,borderColor:"#F2A33C",backgroundColor:"#F2A33C",borderDash:[6,4],borderWidth:2.5,pointRadius:2,tension:.1,fill:false}]},
 options:{responsive:true,maintainAspectRatio:false,interaction:{mode:"index",intersect:false},plugins:{legend:{labels:{filter:i=>!!i.text}}},scales:{y:{beginAtZero:false}}}})}
$("fGo").onclick=async()=>{const model=$("fModel").value;$("fOut").innerHTML=tr("fitting");try{const path=model==="sklearn"?"/forecast/sklearn":"/forecast";const r=await req(`${path}?hub=${$("fHub").value}&crop=${$("fCrop").value}&horizon=${$("fH").value}`);const v=r.validation||{};
 $("fOut").innerHTML=warns(r.warnings)+kv([[tr("modelUsed"),r.model||model],[tr("signal"),`${r.signal.direction} (${r.signal.expected_change_pct}%)`],[tr("reliable"),r.reliable?tr("reliableYes"):tr("reliableNo")],[tr("skill"),v.skill_vs_baseline??tr("na")],[tr("smape"),(v.smape_pct??tr("na"))+"%"],[tr("coverage"),v.interval_coverage??tr("na")],[tr("historyPoints"),r.series.points],[tr("currencyUnit"),`${r.hub.currency}/${r.unit}`]])+
 `<div class="relative h-72 my-3"><canvas id="fChart"></canvas></div>`+
 `<table class="w-full border-collapse text-[13px]"><tr><th class="${TH}">${tr("week")}</th><th class="${TH}">${tr("forecast")}</th><th class="${TH}">${tr("low")}</th><th class="${TH}">${tr("high")}</th></tr>${r.forecast.map(p=>`<tr><td class="${TD}">${esc(p.ds)}</td><td class="${TD}">${p.yhat}</td><td class="${TD}">${p.lower}</td><td class="${TD}">${p.upper}</td></tr>`).join("")}</table>
 <p class="text-muted text-[13px] mt-2">${tr("sources")}: ${esc((r.series.sources||[]).join(", "))}</p>`;drawForecastChart(r.history,r.forecast)}catch(e){$("fOut").innerHTML=err(e)}};

// ---- vision ----
$("vGo").onclick=async()=>{const f=$("vFile").files[0];if(!f)return $("vOut").innerHTML=err(Error(tr("choosePhoto")));
 const fd=new FormData();fd.append("image",f);fd.append("crop",$("vCrop").value.trim());if($("vPrice").value)fd.append("reference_price",$("vPrice").value);
 $("vOut").innerHTML=tr("analysing");try{const r=await req("/vision/assess",{method:"POST",body:fd});
 $("vOut").innerHTML=kv([[tr("grade"),r.grade],[tr("ripeness"),r.ripeness||tr("na")],[tr("disease"),(r.disease||tr("na")).replace(/___/g," – ").replace(/_/g," ")],[tr("confidence"),Math.round(r.confidence*100)+"%"],[tr("priceMultiplier"),r.price_multiplier??tr("manualReview")],[tr("suggestedPrice"),r.suggested_price??"—"]])+
 (r.needs_manual_review?`<div class="bg-[#fff8e9] border border-[#f4e4bf] text-[#80632d] rounded-2xl px-4 py-3 text-[13px] my-2">${tr("manualReviewNote")}</div>`:"")+`<p class="text-muted text-[13px] mt-2">${r.reasons.map(esc).join(" · ")}</p>`+warns(r.warnings)}catch(e){$("vOut").innerHTML=err(e)}};

// ---- advisor ----
$("aGo").onclick=async()=>{$("aOut").innerHTML=tr("preparing");try{const r=await req("/advisor/advice",{method:"POST",body:JSON.stringify({crop:$("aCrop").value,hub_id:$("aHub").value||null,language:$("aLang").value,report:$("aReport").value})});
 $("aOut").innerHTML=`<div class="bg-[#fff8e9] border border-[#f4e4bf] text-[#80632d] rounded-2xl px-4 py-3 text-[13px] my-2">${tr("mode")}: <b>${esc(r.mode)}</b> · ${tr("fidelity")}: <b>${esc(r.expected_fidelity)}</b>${r.requires_human_review?" · "+tr("humanReviewNote"):""}${r.truncated?" · "+tr("truncatedNote"):""}</div>
 <h4 class="text-lg font-extrabold my-3">${esc(r.summary)}</h4><ul class="list-disc pl-5 text-sm space-y-2">${r.actions.map(a=>`<li><b>${esc(a.action)}</b> ${a.timing?`<i>(${esc(a.timing)})</i>`:""}<br><span class="text-muted text-[13px]">${esc(a.reason)}</span></li>`).join("")}</ul>
 <p class="font-bold mt-4">${tr("risks")}:</p><ul class="list-disc pl-5 text-sm space-y-1 mt-1">${r.risks.map(x=>`<li>${esc(x)}</li>`).join("")}</ul><p class="text-muted text-[13px] mt-3">${esc(r.uncertainty_note)} ${esc(r.dialect_fidelity_note||"")}</p>`}catch(e){$("aOut").innerHTML=err(e)}};

// ---- logistics (Dhaka-area default scenario) ----
$("lJson").value=JSON.stringify({depot:{lat:23.8103,lon:90.4125},mode:"delivery",
 stops:[{id:"Gazipur",lat:23.9999,lon:90.4203,load_kg:120,max_transit_min:240},{id:"Savar",lat:23.8583,lon:90.2629,load_kg:200,window_start_min:30,window_end_min:180},{id:"Narayanganj",lat:23.6238,lon:90.5,load_kg:150},{id:"Tongi",lat:23.8905,lon:90.4013,load_kg:90,max_transit_min:150},{id:"Keraniganj",lat:23.7,lon:90.45,load_kg:110}],
 vehicles:[{id:"truck-1",capacity_kg:400},{id:"reefer-1",capacity_kg:500,refrigerated:true,shelf_life_factor:2}],carbon_tradeoff:[0,4,20]},null,1);
function drawRouteMap(r){if(!window.L||!lastScenario)return;$("lMapWrap").classList.remove("hidden");
 const coords={};(lastScenario.stops||[]).forEach(s=>{coords[s.id]=[s.lat,s.lon]});const depot=lastScenario.depot?[lastScenario.depot.lat,lastScenario.depot.lon]:null;
 if(!routeMap){try{routeMap=L.map("lMap").setView(depot||[23.8103,90.4125],11);L.tileLayer(OSM_URL,{attribution:OSM_ATTR}).addTo(routeMap);routeLayer=L.layerGroup().addTo(routeMap)}catch(e){return}}
 routeLayer.clearLayers();const colors=["#1E7A4C","#F2A33C","#2563eb","#9333ea","#dc2626"],bounds=[];
 r.routes.forEach((rt,i)=>{const pts=[];if(depot)pts.push(depot);rt.stops.forEach(s=>{if(coords[s.stop_id])pts.push(coords[s.stop_id])});
  if(pts.length>1){L.polyline(pts,{color:colors[i%colors.length],weight:4}).addTo(routeLayer);pts.forEach(p=>bounds.push(p))}
  rt.stops.forEach((s,j)=>{const c=coords[s.stop_id];if(!c)return;L.marker(c,{icon:L.divIcon({className:"",html:`<div class="route-num">${j+1}</div>`,iconSize:[26,26],iconAnchor:[13,13]})}).bindPopup(`<b>${esc(s.stop_id)}</b><br>${esc(rt.vehicle_id)} · ${tr("arriveMin")}: ${s.arrive_min}`).addTo(routeLayer)})});
 if(depot){L.marker(depot,{icon:L.divIcon({className:"",html:'<div class="route-num route-depot">🏠</div>',iconSize:[26,26],iconAnchor:[13,13]})}).bindPopup(`<b>${tr("depot")}</b>`).addTo(routeLayer);bounds.push(depot)}
 if(bounds.length)routeMap.fitBounds(bounds,{padding:[30,30]});setTimeout(()=>routeMap.invalidateSize(),60)}
$("lGo").onclick=async()=>{$("lOut").innerHTML=tr("optimising");try{const body=JSON.parse($("lJson").value);body.road_provider=$("lProv").value;lastScenario=body;const r=await req("/logistics/plan",{method:"POST",body:JSON.stringify(body)});const t=r.totals,i=r.improvement_vs_baseline;
 $("lOut").innerHTML=kv([[tr("vehicles"),t.vehicles_used],[tr("distanceKm"),t.distance_km],[tr("minutes"),t.minutes],[tr("co2"),t.co2_kg],[tr("lateMin"),t.late_min],[tr("spoilage"),t.spoilage_risk_min]])+
 (i?`<p class="text-muted text-[13px]">${tr("baselineVs")}: ${tr("objective")} ${i.objective_pct}% · CO₂ ${i.co2_pct}% · ${tr("timeWord")} ${i.minutes_pct}% ${tr("negativeWorse")}</p>`:"")+
 r.routes.map(x=>`<h4 class="text-base font-extrabold mt-4 mb-2">${esc(x.vehicle_id)} ${x.refrigerated?"❄":""} — ${x.load_kg}/${x.capacity_kg} kg · ${x.distance_km} km · ${x.co2_kg} kg CO₂e</h4><table class="w-full border-collapse text-[13px]"><tr><th class="${TH}">${tr("stop")}</th><th class="${TH}">${tr("arriveMin")}</th><th class="${TH}">${tr("late")}</th></tr>${x.stops.map(s=>`<tr><td class="${TD}">${esc(s.stop_id)}</td><td class="${TD}">${s.arrive_min}</td><td class="${TD}">${s.late_min}</td></tr>`).join("")}</table>`).join("")+
 (r.carbon_tradeoff?`<h4 class="text-base font-extrabold mt-4 mb-2">${tr("tradeoff")}</h4><table class="w-full border-collapse text-[13px]"><tr><th class="${TH}">${tr("co2Weight")}</th><th class="${TH}">${tr("minutes")}</th><th class="${TH}">${tr("co2")}</th><th class="${TH}">${tr("km")}</th></tr>${r.carbon_tradeoff.map(x=>`<tr><td class="${TD}">${x.co2_per_kg_weight}</td><td class="${TD}">${x.minutes}</td><td class="${TD}">${x.co2_kg}</td><td class="${TD}">${x.distance_km}</td></tr>`).join("")}</table>`:"")+warns(r.notes);drawRouteMap(r)}catch(e){$("lOut").innerHTML=err(e)}};

// ---- twin ----
$("tGo").onclick=async()=>{const c=$("tCode").value.trim();if(!c)return;try{const r=await req("/twin/public/"+encodeURIComponent(c)),i=r.integrity,cc=r.cold_chain;
 $("tOut").innerHTML=kv([[tr("crop"),r.crop],[tr("origin"),r.origin_district],[tr("harvested"),r.harvested_at||tr("na")],[tr("chainIntact"),i.chain_valid?tr("yes"):tr("tamper")],[tr("coldChain"),cc.status||tr("na")],[tr("sensorReadings"),cc.n_readings]])+
 `<div class="bg-[#fff8e9] border border-[#f4e4bf] text-[#80632d] rounded-2xl px-4 py-3 text-[13px] my-2">${esc(i.note)}</div><div class="border-l-[3px] border-mint ml-1.5 pl-3.5 my-2.5">${r.timeline.map(t=>`<div class="my-2 text-[13px]"><b>${esc(t.event.replace(/_/g," "))}</b> <span class="text-muted">${esc(t.time)}</span>${t.status?` — ${esc(t.status)}, ${t.readings} ${tr("readingsWord")}`:""}</div>`).join("")}</div>
 <p class="text-muted text-[13px]">${tr("headHash")}: ${esc(i.head_hash)}</p>`}catch(e){$("tOut").innerHTML=err(e)}};

// ---- bootstrap lists ----
(async()=>{try{const [h,l]=await Promise.all([req("/forecast/hubs"),req("/advisor/languages")]);
 fill($("fHub"),h.hubs,x=>x.id,x=>`${x.name}, ${x.country}`);fill($("fCrop"),h.crops,x=>x.id,x=>x.name);fill($("aCrop"),h.crops,x=>x.id,x=>x.name);
 $("aHub").innerHTML=`<option value="">${tr("noHub")}</option>`+h.hubs.map(x=>`<option value="${esc(x.id)}">${esc(x.name)}</option>`).join("");
 fill($("aLang"),l,x=>x.code,x=>`${x.name} (${x.expected_fidelity})`)}catch(e){$("fOut").innerHTML=err(e)}})();
applyLanguage();
const _h=location.hash.slice(1);pick(TABS.some(([k])=>k===_h)?_h:"forecast");
