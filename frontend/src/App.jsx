import { useEffect, useState } from 'react';
import Simulator from './Simulator';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function Stat({ label, value }) { return <div className="stat"><span>{label}</span><strong>{value}</strong></div>; }

export default function App() {
  const [models, setModels] = useState([]), [summary, setSummary] = useState(null);
  const [prompt, setPrompt] = useState('Explain binary search in simple terms and provide a short example.'), [mode, setMode] = useState('auto');
  const [strategy, setStrategy] = useState('baseline');
  const [minQuality, setMinQuality] = useState(80), [budget, setBudget] = useState(''), [manualModel, setManualModel] = useState('');
  const [result, setResult] = useState(null), [loading, setLoading] = useState(false), [error, setError] = useState('');

  async function load() {
    try {
      const [m, s] = await Promise.all([fetch(`${API}/api/models`), fetch(`${API}/api/dashboard/summary`)]);
      if (!m.ok || !s.ok) throw new Error();
      const modelData = await m.json(); setModels(modelData); setSummary(await s.json());
      if (!manualModel && modelData.length) setManualModel(modelData[0].model_id);
    } catch { setError('Connect the FastAPI backend to load live model and dashboard data.'); }
  }
  useEffect(() => { load(); }, []);

  async function submit(e) {
    e.preventDefault(); setLoading(true); setError(''); setResult(null);
    try {
      const body = { prompt, mode, min_quality: Number(minQuality), routing_strategy: strategy };
      if (budget !== '') body.remaining_budget_usd = budget;
      if (mode === 'manual') body.manual_model_id = manualModel;
      const response = await fetch(`${API}/api/requests`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) });
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || 'Request failed');
      setResult(data); load();
    } catch (e) { setError(e.message); } finally { setLoading(false); }
  }

  return <div className="app">
    <header><div><p className="eyebrow">INTELLIGENT MULTI-LLM PLATFORM</p><h1>LLM Cost Optimizer</h1><p className="subtitle">Route every request to the lowest-cost model that satisfies your quality requirements.</p></div><span className="status">● LIVE DASHBOARD</span></header>
    {summary && <section className="stats"><Stat label="Requests" value={summary.total_requests}/><Stat label="Total cost" value={`$${summary.total_cost_usd}`}/><Stat label="Tokens" value={summary.total_tokens.toLocaleString()}/><Stat label="Avg quality" value={summary.average_quality == null ? '—' : `${summary.average_quality.toFixed(1)}/100`}/><Stat label="Avg latency" value={summary.average_latency_ms == null ? '—' : `${summary.average_latency_ms.toFixed(0)} ms`}/></section>}
    <main>
      <section className="panel request-panel"><div className="panel-head"><h2>Run an LLM task</h2><span>Cost-aware routing</span></div><form onSubmit={submit}>
        <label>Prompt<textarea value={prompt} onChange={e=>setPrompt(e.target.value)} rows="7"/></label>
        <div className="grid"><label>Mode<select value={mode} onChange={e=>setMode(e.target.value)}><option value="auto">Intelligent routing</option><option value="manual">Manual model</option></select></label>{mode === 'auto' && <label>Routing strategy<select value={strategy} onChange={e=>setStrategy(e.target.value)}><option value="baseline">Baseline — cheapest eligible</option><option value="weighted_scoring">Weighted — cost + quality + latency</option></select></label>}<label>Minimum quality<select value={minQuality} onChange={e=>setMinQuality(e.target.value)}><option value="0">No minimum</option><option value="70">70 / 100</option><option value="80">80 / 100</option><option value="90">90 / 100</option></select></label>{mode === 'manual' && <label>Model<select value={manualModel} onChange={e=>setManualModel(e.target.value)}>{models.map(m=><option key={m.model_id} value={m.model_id}>{m.provider_name} — {m.model_name}</option>)}</select></label>}<label>Remaining budget (USD)<input value={budget} onChange={e=>setBudget(e.target.value)} type="number" min="0" step="0.000001" placeholder="Optional"/></label></div>
        <button disabled={loading || !prompt.trim()}>{loading ? 'Running…' : 'Run task'}</button></form>{error && <div className="error">{error}</div>}</section>
      <section className="panel result-panel"><div className="panel-head"><h2>Result</h2>{result && <span className="pill">{result.routing_strategy}</span>}</div>{!result ? <div className="empty">Submit a task to see the selected model, response, quality and real usage cost.</div> : <><div className="decision"><div><small>SELECTED MODEL</small><strong>{result.provider_name} · {result.model_name}</strong><p>{result.routing_reason}</p></div><div className="cost"><small>ACTUAL COST</small><strong>${result.actual_cost_usd}</strong></div></div><article className="answer">{result.response_text}</article><div className="metrics"><Stat label="Input tokens" value={result.input_tokens_actual}/><Stat label="Output tokens" value={result.output_tokens_actual}/><Stat label="Quality" value={`${result.quality_score}/100`}/><Stat label="Latency" value={`${result.latency_ms} ms`}/></div><div className="candidate-list"><h3>Routing decision</h3>{result.candidates_considered.map(c=><div className="candidate" key={c.model_id}><span>{c.provider_name} · {c.model_name}</span><span>{c.eligible ? 'Eligible' : c.ineligible_reason}</span></div>)}</div></>}</section>
    </main>
    <Simulator models={models}/>
    <section className="panel models"><div className="panel-head"><h2>Model registry</h2><span>{models.length} configured models</span></div><div className="model-grid">{models.map(m=><div className="model-card" key={m.model_id}><small>{m.provider_name}</small><h3>{m.model_name}</h3><p>Quality estimate: <b>{m.estimated_quality}/100</b></p><p>Input: ${m.input_price_per_1k ?? '—'} / 1K · Output: ${m.output_price_per_1k ?? '—'} / 1K</p></div>)}</div></section>
    <footer>LLM Cost Optimizer · Experimental platform for cost/quality-aware model routing</footer>
  </div>;
}
