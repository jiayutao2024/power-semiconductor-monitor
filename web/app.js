const $ = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => [...root.querySelectorAll(s)];
let DATA = null;
let companyRegion = 'A股';
let marketRegion = 'A股';

const fmt = (v, digits=1) => v == null ? '—' : Number(v).toLocaleString('zh-CN',{maximumFractionDigits:digits});
const pct = v => v == null ? '—' : `${v>0?'+':''}${fmt(v,2)}%`;
const cls = v => v == null ? '' : v >= 0 ? 'positive' : 'negative';
const dateText = iso => iso ? iso.replace('T',' ').slice(0,16) : '—';

function setTabs(){
  $$('.tab').forEach(btn => btn.addEventListener('click', () => {
    $$('.tab,.panel').forEach(x=>x.classList.remove('active'));
    btn.classList.add('active');
    $(`#${btn.dataset.tab}`).classList.add('active');
    history.replaceState(null,'',`#${btn.dataset.tab}`);
  }));
  const hash=location.hash.slice(1);
  if(hash && $(`.tab[data-tab="${hash}"]`)) $(`.tab[data-tab="${hash}"]`).click();
}

function renderHeader(){
  $('#generated-at').textContent=dateText(DATA.meta.generated_at);
  $('#health-line').textContent=`行情 ${DATA.health.market_success}/${DATA.health.market_total} · SKU ${DATA.health.sku_observed}/${DATA.health.sku_target}`;
}

function renderOverview(){
  const c=DATA.cycle;
  $('#stage-label').textContent=c.label;
  $('#stage-reason').textContent=c.reason;
  $('#coverage-row').innerHTML=`<span>供给 ${c.coverage.supply}/${c.thresholds.stage_min_supply}</span><span>需求 ${c.coverage.demand}/${c.thresholds.stage_min_demand}</span><span>盈利 ${c.coverage.profit}/${c.thresholds.stage_min_profit}</span>`;
  const matrix=$('#cycle-matrix');
  matrix.innerHTML='<span class="matrix-zone" style="left:7%;bottom:8%">去库存</span><span class="matrix-zone" style="right:5%;bottom:8%">需求复苏</span><span class="matrix-zone" style="left:7%;top:8%">供给趋紧</span><span class="matrix-zone" style="right:5%;top:8%">盈利兑现</span>';
  if(c.supply_tightness==null){matrix.insertAdjacentHTML('beforeend','<div class="matrix-missing"><div><b>暂不落点</b>供给侧可比历史不足，避免伪精确</div></div>')}
  else matrix.insertAdjacentHTML('beforeend',`<i class="matrix-dot" style="left:${c.demand_breadth}%;bottom:${c.supply_tightness}%"></i>`);
  const kpis=[
    ['需求扩散度',c.demand_breadth==null?'—':`${fmt(c.demand_breadth)}%`,`${c.coverage.demand} 项有效`,''],
    ['需求强度',c.demand_strength==null?'—':`${fmt(c.demand_strength)}分`,'方向技术评分','gold'],
    ['供给紧张度',c.supply_tightness==null?'待积累':'可计算',`SKU ${DATA.health.sku_observed}/${DATA.health.sku_target}`,'gray'],
    ['20日市场上涨广度',c.market_breadth_20d==null?'—':`${fmt(c.market_breadth_20d)}%`,'不进入产业得分','gray']
  ];
  $('#kpi-strip').innerHTML=kpis.map(x=>`<div class="kpi-card ${x[3]}"><span>${x[0]}</span><strong>${x[1]}</strong><small>${x[2]}</small></div>`).join('');
  $('#metric-heatmap').innerHTML=DATA.metrics.slice(0,8).map(m=>`<div class="metric-cell ${m.status}"><b>${m.name}</b><span>${m.frequency} · ${m.tier}</span><small>${m.status==='active'?'已接入':m.status==='partial'?'部分接入':'历史积累中'}</small></div>`).join('');
  const obs=DATA.observations.filter(x=>['nev_output_yoy','solar_capacity_yoy','industrial_equip_yoy'].includes(x.metric_id));
  $('#daily-signals').innerHTML=obs.map(x=>`<div class="signal"><b>${x.note} <span class="positive">${pct(x.value)}</span></b><p>${x.period} · <a href="${x.source_url}" target="_blank" rel="noopener">${x.source_name}</a></p></div>`).join('')+`<div class="signal"><b>供给侧仍在建立基准</b><p>没有可比 SKU 历史前，不把涨价新闻直接转成行业得分。</p></div>`;
  $('#industry-chain').innerHTML=DATA.methodology.chain.map((x,i)=>`<div>${x}</div>${i<DATA.methodology.chain.length-1?'<i>→</i>':''}`).join('');
}

function renderPrices(){
  $('#sku-count').textContent=`${DATA.health.sku_observed}/${DATA.health.sku_target}`;
  const cards=[['价格指数','待积累','共同有效日=100'],['涨价广度','待积累','上涨SKU/可比SKU'],['缺货广度','待积累','无库存SKU/有效SKU'],['交期中位数','待积累','按规格单元分组']];
  $('#supply-cards').innerHTML=cards.map(x=>`<div class="kpi-card gray"><span>${x[0]}</span><strong>${x[1]}</strong><small>${x[2]}</small></div>`).join('');
  $('#sku-cells').innerHTML=DATA.sku.cells.map(x=>`<div class="bar-row"><span>${x.product} ${x.voltage_v}V</span><div class="bar-track"><div class="bar-fill" style="width:${x.target/DATA.sku.target_count*800}%"></div></div><b>${x.target}</b></div>`).join('');
  const rows=DATA.sku.rows;
  $('#sku-table').innerHTML=rows.length?rows.map(x=>`<tr><td>${x.cell}</td><td>${x.manufacturer}</td><td>${x.mpn}</td><td>${x.voltage_v}V</td><td>${x.quantity}</td><td>${x.price} ${x.currency}</td><td>${x.stock}</td><td>${x.lead_time_weeks??'—'}</td><td>${x.observed_at}</td><td><a href="${x.source_url}">原文</a></td></tr>`).join(''):'<tr class="empty-row"><td colspan="10">固定篮子正在逐项核验料号与公开页面；上线后从第一个共同有效日开始计算。</td></tr>';
}

function renderDemand(){
  const map={nev_output_yoy:['新能源汽车','主驱/OBC/DC-DC'],solar_capacity_yoy:['光伏与电网','逆变器/功率模块'],industrial_equip_yoy:['工业控制','变频器/伺服'],ai_power_confirmation:['AI数据中心','PSU/BBU/SST']};
  const obsBy=Object.fromEntries(DATA.observations.map(x=>[x.metric_id,x]));
  $('#application-grid').innerHTML=Object.entries(map).map(([id,v])=>{const x=obsBy[id];return `<div class="application-card"><span class="section-kicker">${v[1]}</span><h3>${v[0]}</h3><div class="app-value">${x?pct(x.value):'待财报扩散'}</div><p>${x?`${x.period} · ${x.note}`:'按公开AI电源收入/指引公司数计算'}</p>${x?`<a class="source-link" href="${x.source_url}" target="_blank">原始来源 →</a>`:''}</div>`}).join('');
  const names=Object.fromEntries(DATA.metrics.map(x=>[x.id,x.name]));
  $('#demand-bars').innerHTML=DATA.cycle.demand_components.map(x=>`<div class="bar-row"><span>${names[x.metric_id]}</span><div class="bar-track"><div class="bar-fill ${x.direction_points<3?'gold':''}" style="width:${x.direction_points/3*100}%"></div></div><b>${x.direction_points}/3</b></div>`).join('');
  const rows=[['AI数据中心','强','中','强','强'],['新能源汽车','中','强','强','弱'],['光伏/储能','弱','强','强','弱'],['工业控制','中','强','中','弱']];
  $('#application-matrix').innerHTML=['应用','低压MOS','IGBT','SiC','GaN',...rows.flat()].map((x,i)=>`<div class="${i<5||i%5===0?'head':x==='强'?'strong':x==='中'?'medium':''}">${x}</div>`).join('');
}

function renderTechnology(){
  const mats=[['Silicon','30–1700V','成熟成本曲线',['MOSFET、IGBT','关注价格与稼动率']],['SiC','650–3300V','高压高效率',['汽车、光储、AI机房','关注有效产能与量产']],['GaN','40–650V','高频小型化',['快充、服务器PSU','关注客户验证与出货']]];
  $('#material-cards').innerHTML=mats.map(x=>`<article class="card material-card"><span class="section-kicker">MATERIAL</span><h3>${x[0]}</h3><div class="voltage">${x[1]}</div><p>${x[2]}</p><ul>${x[3].map(y=>`<li>${y}</li>`).join('')}</ul></article>`).join('');
  const stages=['传闻','官方发布/路线图','展示/点亮','送样','客户验证','合同/定点','量产','出货/收入'];
  $('#evidence-stages').innerHTML=stages.map((x,i)=>`<div><b>${i+1}</b> ${x}</div>`).join('');
}

function allCompanies(){return DATA.market.filter(x=>x.kind==='company')}
function renderCompanies(){
  const rows=allCompanies().filter(x=>x.region===companyRegion);
  const q=$('#company-search').value.trim().toLowerCase();
  const filtered=rows.filter(x=>!q||[x.name,x.segment,(x.materials||[]).join(' '),(x.applications||[]).join(' ')].join(' ').toLowerCase().includes(q));
  const core=rows.filter(x=>x.purity==='核心').length;
  const segments=new Set(rows.map(x=>x.segment)).size;
  const positive=rows.filter(x=>x.relative_return_20d!=null&&x.relative_return_20d>0).length;
  $('#company-summary').innerHTML=[['样本公司',rows.length,'固定研究池'],['核心纯度',core,'其余为产业相关'],['覆盖环节',segments,'按公开产品分类'],['跑赢基准',`${positive}/${rows.filter(x=>x.relative_return_20d!=null).length}`,'20日相对收益']].map(x=>`<div class="kpi-card"><span>${x[0]}</span><strong>${x[1]}</strong><small>${x[2]}</small></div>`).join('');
  $('#company-table').innerHTML=filtered.map(x=>`<tr><td><b>${x.name}</b><br><small>${x.symbol}</small></td><td>${x.region}</td><td>${x.segment}</td><td>${(x.materials||[]).join(' / ')}</td><td>${(x.applications||[]).join(' / ')}</td><td><span class="badge ${x.purity==='核心'?'neutral':'warning'}">${x.purity}</span></td><td class="${cls(x.return_20d)}">${pct(x.return_20d)}</td><td class="${cls(x.relative_return_20d)}">${pct(x.relative_return_20d)}</td><td><a href="${x.ir}" target="_blank">IR</a></td></tr>`).join('');
  const fin=DATA.observations.filter(x=>x.company);
  $('#financial-cards').innerHTML=fin.map(x=>`<div class="financial-item"><div><b>${x.company}</b><small>${x.metric_id.replaceAll('_',' ')} · ${x.period}</small></div><div><strong>${fmt(x.value)}${x.unit==='%'?'%':''}</strong><small><a href="${x.source_url}" target="_blank">${x.source_name}</a></small></div></div>`).join('');
}

function renderMarket(){
  const rows=allCompanies();
  const valid=rows.filter(x=>x.return_20d!=null);
  const median=valid.length?valid.map(x=>x.return_20d).sort((a,b)=>a-b)[Math.floor(valid.length/2)]:null;
  const best=[...valid].sort((a,b)=>b.relative_return_20d-a.relative_return_20d)[0];
  $('#market-cards').innerHTML=[['有效行情',`${valid.length}/${rows.length}`,'最近交易日'],['20日收益中位数',pct(median),'全部公司'],['上涨广度',`${fmt(DATA.cycle.market_breadth_20d)}%`,'20日收益>0'],['相对收益领先',best?best.name:'—',best?pct(best.relative_return_20d):'—']].map(x=>`<div class="kpi-card"><span>${x[0]}</span><strong>${x[1]}</strong><small>${x[2]}</small></div>`).join('');
  const rr=rows.filter(x=>x.region===marketRegion&&x.relative_return_20d!=null).sort((a,b)=>b.relative_return_20d-a.relative_return_20d).slice(0,12);
  const max=Math.max(1,...rr.map(x=>Math.abs(x.relative_return_20d)));
  $('#relative-bars').innerHTML=rr.map(x=>`<div class="bar-row"><span>${x.name}</span><div class="bar-track"><div class="bar-fill ${x.relative_return_20d<0?'gold':''}" style="width:${Math.abs(x.relative_return_20d)/max*100}%"></div></div><b class="${cls(x.relative_return_20d)}">${pct(x.relative_return_20d)}</b></div>`).join('');
  $('#events-list').innerHTML=DATA.events.length?DATA.events.map(x=>`<div class="signal"><b>${x.title}</b><p>${x.stage} · ${x.published_at}</p></div>`).join(''):'<div class="signal"><b>事件自动核验池准备中</b><p>只有官方发布、客户验证、合同、量产或收入证据才会进入正式事件流。</p></div>';
  $('#market-table').innerHTML=rows.map(x=>`<tr><td><b>${x.name}</b><br><small>${x.symbol}</small></td><td>${fmt(x.price,3)} ${x.currency||''}</td><td>${x.trade_date||'—'}</td><td class="${cls(x.return_1d)}">${pct(x.return_1d)}</td><td class="${cls(x.return_20d)}">${pct(x.return_20d)}</td><td class="${cls(x.return_60d)}">${pct(x.return_60d)}</td><td class="${cls(x.relative_return_20d)}">${pct(x.relative_return_20d)}</td><td>${x.source_url?`<a href="${x.source_url}" target="_blank">行情</a>`:'—'}</td></tr>`).join('');
}

function renderMethod(){
  $('#method-list').innerHTML=DATA.metrics.map(m=>`<div class="method-row"><b>${m.name} <span class="badge neutral">${m.tier}</span></b><p>${m.formula}</p><small>${m.source} · ${m.frequency} · ${m.status}</small></div>`).join('');
  const endpoints=['dashboard','power-overview','power-prices','power-supply','power-demand','power-materials','power-companies','power-events','power-sources','power-health','index'];
  $('#api-list').innerHTML=endpoints.map(x=>`<a href="api/${x}.json" target="_blank">/api/${x}.json</a>`).join('');
  $$('[data-open-method]').forEach(x=>x.onclick=()=>{$('#method-drawer').classList.add('open');$('#method-drawer').setAttribute('aria-hidden','false')});
  $('.drawer-close').onclick=()=>{$('#method-drawer').classList.remove('open');$('#method-drawer').setAttribute('aria-hidden','true')};
}

function bindControls(){
  $$('[data-company-region]').forEach(b=>b.onclick=()=>{$$('[data-company-region]').forEach(x=>x.classList.remove('active'));b.classList.add('active');companyRegion=b.dataset.companyRegion;renderCompanies()});
  $('#company-search').addEventListener('input',renderCompanies);
  $$('[data-market-region]').forEach(b=>b.onclick=()=>{$$('[data-market-region]').forEach(x=>x.classList.remove('active'));b.classList.add('active');marketRegion=b.dataset.marketRegion;renderMarket()});
}

async function boot(){
  setTabs();
  try{
    const res=await fetch('api/dashboard.json',{cache:'no-store'});
    if(!res.ok) throw new Error(`HTTP ${res.status}`);
    DATA=await res.json();
    renderHeader();renderOverview();renderPrices();renderDemand();renderTechnology();renderCompanies();renderMarket();renderMethod();bindControls();
  }catch(err){
    $('#generated-at').textContent='数据加载失败';
    $('#health-line').textContent=err.message;
    document.querySelector('main').insertAdjacentHTML('afterbegin',`<div class="card"><b>暂时无法读取数据接口</b><p>${err.message}</p></div>`);
  }
}
boot();
