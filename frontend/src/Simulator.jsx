import { useMemo, useState } from 'react';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export default function Simulator({ models }) {
  const [requests, setRequests] = useState(10000);
  const [inputTokens, setInputTokens] = useState(500);
  const [outputTokens, setOutputTokens] = useState(300);
  const [quality, setQuality] = useState(80);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const localRows = useMemo(() => models.filter(m => m.input_price_per_1k && m.output_price_per_1k).map(m => ({
    ...m,
    cost: ((inputTokens / 1000) * Number(m.input_price_per_1k) + (outputTokens / 1000) * Number(m.output_price_per_1k)) * requests
  })).sort((a,b) => a.cost - b.cost), [models, requests, inputTokens, outputTokens]);

  async function simulate() {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/simulator/monthly`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({requests_per_month:Number(requests), input_tokens_per_request:Number(inputTokens), output_tokens_per_request:Number(outputTokens), min_quality:Number(quality)}) });
      if (r.ok) setData(await r.json());
    } finally { setLoading(false); }
  }

  const rows = data?.projections?.sort((a,b)=>Number(a.monthly_cost_usd)-Number(b.monthly_cost_usd)) || localRows;
  const eligible = rows.filter(r => Number(r.estimated_quality) >= Number(quality));
  const best = eligible[0];
  const premium = rows.reduce((a,b)=>Number(b.monthly_cost_usd) > Number(a.monthly_cost_usd) ? b : a, rows[0]);
  const savings = best && premium && Number(premium.monthly_cost_usd) > 0 ? ((Number(premium.monthly_cost_usd)-Number(best.monthly_cost_usd))/Number(premium.monthly_cost_usd))*100 : 0;

  return <section className="panel simulator"><div className="panel-head"><h2>What-if cost simulator</h2><span>Projected monthly spend</span></div>
    <div className="grid"><label>Requests / month<input type="number" min="1" value={requests} onChange={e=>setRequests(e.target.value)}/></label><label>Input tokens / request<input type="number" min="0" value={inputTokens} onChange={e=>setInputTokens(e.target.value)}/></label><label>Output tokens / request<input type="number" min="0" value={outputTokens} onChange={e=>setOutputTokens(e.target.value)}/></label><label>Minimum quality<input type="number" min="0" max="100" value={quality} onChange={e=>setQuality(e.target.value)}/></label></div>
    <button onClick={simulate} disabled={loading}>{loading ? 'Calculating…' : 'Calculate projection'}</button>
    {rows.length > 0 && <div className="simulation-results"><div className="decision"><div><small>CHEAPEST ELIGIBLE</small><strong>{best ? `${best.provider_name} · ${best.model_name}` : 'No model meets the quality threshold'}</strong></div><div className="cost"><small>PROJECTED SAVINGS VS MOST EXPENSIVE</small><strong>{best ? `${savings.toFixed(1)}%` : '—'}</strong></div></div>{rows.map(r=><div className="simulation-row" key={r.model_id}><span>{r.provider_name} · {r.model_name}</span><b>${Number(r.monthly_cost_usd ?? r.cost).toFixed(4)} / month</b><small>{r.estimated_quality}/100 quality</small></div>)}</div>}
  </section>;
}
