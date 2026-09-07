import { useEffect, useMemo, useState } from 'react'
import { Activity, AlertTriangle, Check, Database, Eye, FolderOpen, Save, SlidersHorizontal, Timer, X } from 'lucide-react'
import { Chart } from './Chart'
import type { Anomaly, AppState, Result, Sample } from './types'

const colors = ['#38bdf8','#f59e0b','#a78bfa','#34d399','#fb7185','#facc15','#60a5fa','#c084fc']
const pct = (v: number | null, digits = 3) => v == null ? '—' : `${(v*100).toFixed(digits)}%`
const num = (v: number | null, digits = 2) => v == null ? '—' : v.toFixed(digits)

export function App() {
  const [state, setState] = useState<AppState | null>(null)
  const [error, setError] = useState('')
  const [sampleId, setSampleId] = useState('')
  const [selected, setSelected] = useState('latest')
  const [rawMode, setRawMode] = useState(false)
  const [overlay, setOverlay] = useState(true)
  const [showE0, setShowE0] = useState(true)
  const [showRegions, setShowRegions] = useState(true)
  const [averaging, setAveraging] = useState('equal')
  const [included, setIncluded] = useState<string[]>([])
  const [rating, setRating] = useState('Q-ready')
  const [override, setOverride] = useState('')
  const [notes, setNotes] = useState('')
  const [reviewerRole, setReviewerRole] = useState('beamline_user')
  const [pre, setPre] = useState('-10,-4')
  const [post, setPost] = useState('27,50')
  const [glitches, setGlitches] = useState<Record<string,string>>({})
  const [saved, setSaved] = useState(false)

  const refresh = async () => {
    try { const r = await fetch('/api/state'); if (!r.ok) throw new Error(await r.text()); const next = await r.json(); setState(next); setError('') }
    catch (e) { setError(e instanceof Error ? e.message : String(e)) }
  }
  useEffect(() => { refresh(); const timer = window.setInterval(refresh, 1500); return () => clearInterval(timer) }, [])
  useEffect(() => { if (!sampleId && state?.samples[0]) setSampleId(state.samples[0].sample_id) }, [state, sampleId])
  const sample = state?.samples.find(s => s.sample_id === sampleId) || state?.samples[0]
  useEffect(() => { if (sample) { setIncluded(sample.scans.map(s => s.id)); setAveraging(sample.latest?.averaging_mode || 'equal') } }, [sample?.sample_id, sample?.scan_count])
  const latest = sample?.latest

  const displayed = useMemo(() => {
    if (!sample) return []
    if (selected.startsWith('scan:')) {
      const scan = sample.scans.find(s => s.id === selected.slice(5));
      return scan ? [{ x: scan.energy, y: rawMode ? scan.raw : scan.normalized, label: scan.label }] : []
    }
    const count = selected.startsWith('avg:') ? Number(selected.slice(4)) : sample.scan_count
    const average = sample.averages.find(a => a.scan_count === count) || latest
    if (!average) return []
    const base = [{ x: average.energy, y: rawMode ? average.raw_average : average.normalized_average, label: `Avg 1–${average.scan_count}` }]
    if (!overlay) return base
    return [...sample.scans.filter(s => included.includes(s.id)).map(s => ({ x: s.energy, y: rawMode ? s.raw : s.normalized, label: s.label })), ...base]
  }, [sample, selected, rawMode, overlay, included, latest])

  const spectrumSeries = displayed.map((s, i) => ({ ...s, color: i === displayed.length-1 ? '#eaf5ff' : colors[i % colors.length], width: i === displayed.length-1 ? 2.8 : 1.1 }))
  const bands = showRegions && latest ? latest.regions.map(r => ({ start:r.start, end:r.end, color:r.protected ? '#fb7185' : '#38bdf8', label:r.name })) : []
  const markers = showE0 && latest?.metrics.e0 ? [{ x:latest.metrics.e0, color:'#facc15', label:'E0' }] : []
  const qSeries = sample ? [
    { x:sample.history.map(h=>h.scan_count), y:sample.history.map(h=>h.metrics.q_hf ?? NaN), color:'#38bdf8', label:'Q_HF', width:2.6 },
    { x:[1,Math.max(sample.scan_count,2)], y:[.0045,.0045], color:'#34d399', label:'Route A', dashed:true },
    { x:[1,Math.max(sample.scan_count,2)], y:[.007,.007], color:'#f59e0b', label:'Route B', dashed:true },
  ] : []

  const reanalyze = async () => {
    if (!sample) return
    const parseAnchor = (value:string) => value.split(',').map(Number)
    const response = await fetch('/api/reanalyze', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({
      sample_id:sample.sample_id, averaging_mode:averaging, included_scan_ids:included,
      anchors:{pre:parseAnchor(pre), post:parseAnchor(post)},
    }) })
    if (!response.ok) setError(await response.text()); else { setSelected('latest'); await refresh() }
  }
  const saveReview = async () => {
    if (!sample || !latest) return
    const decisions = latest.anomalies.map((a, i) => ({ energy:a.energy, region:a.region, status:glitches[`${a.energy}:${i}`] || 'unreviewed' }))
    const response = await fetch('/api/reviews', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({
      analysis_id:latest.analysis_id, sample_id:sample.sample_id, rating, override_recommendation:override || null,
      averaging_mode:averaging, included_scans:included, excluded_scans:sample.scans.filter(s=>!included.includes(s.id)).map(s=>s.id),
      glitch_decisions:decisions, local_normalization_anchors:{pre:pre.split(',').map(Number),post:post.split(',').map(Number)}, notes, reviewer_role:reviewerRole,
    }) })
    if (!response.ok) setError(await response.text()); else { setSaved(true); window.setTimeout(()=>setSaved(false),2200); await refresh() }
  }

  if (!state) return <main className="loading"><Activity className="spin"/> Connecting to the local analysis service…{error && <span>{error}</span>}</main>
  return <div className="app-shell">
    <header className="topbar">
      <div className="brand"><div className="mark"><Activity size={20}/></div><div><h1>XAS Beamtime Decision Support</h1><p>P K-edge XANES · profile v1.2 frozen</p></div></div>
      <div className="session">
        <span className={`live-dot ${state.watching?'on':''}`}></span>{state.watching ? 'Watching' : 'Paused'}
        <code>{state.watch_folder}</code>
        <span className="safety">Advisory only · no acquisition control</span>
      </div>
    </header>
    {error && <div className="error"><AlertTriangle size={17}/>{error}</div>}
    <section className="toolbar">
      <label>Sample<select value={sample?.sample_id || ''} onChange={e=>{setSampleId(e.target.value);setSelected('latest')}}>{state.samples.map(s=><option key={s.sample_id}>{s.sample_id}</option>)}</select></label>
      <div className="meta"><span>{sample?.scan_count || 0} scans</span><span>{latest ? `${num(latest.total_measured_seconds,0)} s measured` : 'Waiting for data'}</span><span>{latest?.metrics.normalization_mode || '—'} normalization</span></div>
      <WatchSettings state={state} onUpdated={refresh}/>
    </section>
    <main className="workspace">
      <Panel title="Quality vs. Scan Number" eyebrow="NOISE CONVERGENCE" className="quality-panel">
        <Chart series={qSeries} yPercent/>
        <div className="legend"><span><i className="cyan"/>Q_HF</span><span><i className="green"/>Route A ≤ 0.45%</span><span><i className="amber"/>Route B ≤ 0.70%</span></div>
        <div className="metric-grid">
          <Metric label="Q_HF" value={pct(latest?.metrics.q_hf ?? null)}/><Metric label="Q_pre" value={pct(latest?.metrics.q_pre ?? null)}/>
          <Metric label="Q_post" value={pct(latest?.metrics.q_post ?? null)}/><Metric label="A_spike" value={num(latest?.metrics.a_spike ?? null)}/>
        </div>
      </Panel>
      <Panel title="Cumulative-average Spectrum" eyebrow={rawMode?'RAW μ(E)':'NORMALIZED μ(E)'} className="spectrum-panel">
        <div className="chart-controls"><Toggle active={!rawMode} onClick={()=>setRawMode(false)}>Normalized</Toggle><Toggle active={rawMode} onClick={()=>setRawMode(true)}>Raw</Toggle><Toggle active={overlay} onClick={()=>setOverlay(!overlay)}>Overlay</Toggle></div>
        <Chart series={spectrumSeries} bands={bands} markers={markers}/>
        <div className="spectrum-key"><span className="protected">Protected XANES</span><span className="safe">Safe mask zones</span>{latest?.metrics.e0 && <span>E0 {latest.metrics.e0.toFixed(2)} eV</span>}</div>
      </Panel>
      <DecisionPanel result={latest}/>
      <HumanPanel sample={sample} latest={latest} selected={selected} setSelected={setSelected} rawMode={rawMode} setRawMode={setRawMode}
        overlay={overlay} setOverlay={setOverlay} showE0={showE0} setShowE0={setShowE0} showRegions={showRegions} setShowRegions={setShowRegions}
        averaging={averaging} setAveraging={setAveraging} included={included} setIncluded={setIncluded} pre={pre} setPre={setPre} post={post} setPost={setPost}
        glitches={glitches} setGlitches={setGlitches} rating={rating} setRating={setRating} override={override} setOverride={setOverride}
        notes={notes} setNotes={setNotes} reviewerRole={reviewerRole} setReviewerRole={setReviewerRole} reanalyze={reanalyze} saveReview={saveReview} saved={saved}/>
    </main>
    <footer><Database size={14}/> {Object.values(state.database_counts).reduce((a,b)=>a+b,0)} provenance records · Algorithm ↔ human feedback retained</footer>
  </div>
}

function Panel({title,eyebrow,className='',children}:{title:string;eyebrow:string;className?:string;children:React.ReactNode}) { return <section className={`panel ${className}`}><div className="panel-head"><div><span>{eyebrow}</span><h2>{title}</h2></div></div>{children}</section> }
function Metric({label,value}:{label:string;value:string}) { return <div className="metric"><span>{label}</span><strong>{value}</strong></div> }
function Toggle({active,onClick,children}:{active:boolean;onClick:()=>void;children:React.ReactNode}) { return <button className={`toggle ${active?'active':''}`} onClick={onClick}>{children}</button> }

function DecisionPanel({result}:{result:Result|null|undefined}) {
  const decision = result?.recommendation || 'CONTINUE'; const tone = decision==='STOP RECOMMENDED'?'stop':decision==='QL ONLY'?'ql':'continue'
  return <Panel title="Automatic Decision" eyebrow="ADVISORY OUTPUT" className={`decision-panel ${tone}`}>
    <div className="decision-word"><span></span>{decision}</div>
    <p className="reason">{result?.recommendation_reason || 'Waiting for the first completed scan.'}</p>
    <div className="decision-stats"><div><span>Route</span><strong>{result?.metrics.route || '—'}</strong></div><div><span>N_quant</span><strong>{result?.n_quant || result?.predicted_n_quant || '—'}</strong></div><div><span>Marginal gain</span><strong>{result?.marginal_gain == null?'—':`${(result.marginal_gain*100).toFixed(1)}%`}</strong></div></div>
    <div className="gain"><div className="gain-label"><span>Expected value of another scan</span><span>{result?.marginal_gain == null?'learning…':result.marginal_gain>.12?'material':'diminishing'}</span></div><div className="bar"><i style={{width:`${Math.min(Math.max((result?.marginal_gain||0)*350,5),100)}%`}}/></div></div>
    {result?.uncertainty?.q_hf_interval_95 && <div className="uncertainty"><span>Q_HF scan-bootstrap 95% band</span><strong>{pct(result.uncertainty.q_hf_interval_95[0])} – {pct(result.uncertainty.q_hf_interval_95[1])}</strong></div>}
    {!!result?.metrics.diagnostics.length && <div className="diagnostic"><Eye size={15}/>{result.metrics.diagnostics[0]}</div>}
    <div className="limits"><Timer size={17}/><div><strong>Strictest limit applies</strong><span>{result?.remaining_scan_budget ?? '∞'} scans · {result?.remaining_time_seconds==null?'∞':`${Math.floor(result.remaining_time_seconds)} s`} remaining</span></div></div>
    <div className="human-gate"><AlertTriangle size={18}/><span>An authorized beamtime team member makes the final continue/stop decision.</span></div>
  </Panel>
}

type HumanProps = {
  sample?:Sample; latest?:Result|null; selected:string; setSelected:(v:string)=>void; rawMode:boolean; setRawMode:(v:boolean)=>void
  overlay:boolean; setOverlay:(v:boolean)=>void; showE0:boolean; setShowE0:(v:boolean)=>void; showRegions:boolean; setShowRegions:(v:boolean)=>void
  averaging:string; setAveraging:(v:string)=>void; included:string[]; setIncluded:(v:string[])=>void; pre:string; setPre:(v:string)=>void; post:string; setPost:(v:string)=>void
  glitches:Record<string,string>; setGlitches:(v:Record<string,string>)=>void; rating:string; setRating:(v:string)=>void; override:string; setOverride:(v:string)=>void
  notes:string; setNotes:(v:string)=>void; reviewerRole:string; setReviewerRole:(v:string)=>void; reanalyze:()=>void; saveReview:()=>void; saved:boolean
}
function HumanPanel(p:HumanProps) {
  return <Panel title="Human Validation" eyebrow="HUMAN REVIEW" className="human-panel">
    <div className="human-grid">
      <div className="review-block spectra-list"><h3>Spectrum</h3><div className="pills">{p.sample?.scans.map(s=><Toggle key={s.id} active={p.selected===`scan:${s.id}`} onClick={()=>p.setSelected(`scan:${s.id}`)}>{s.label}</Toggle>)}{p.sample?.averages.map(a=><Toggle key={a.scan_count} active={p.selected===`avg:${a.scan_count}` || (p.selected==='latest'&&a.scan_count===p.sample?.scan_count)} onClick={()=>p.setSelected(`avg:${a.scan_count}`)}>Avg 1–{a.scan_count}</Toggle>)}</div></div>
      <div className="review-block"><h3>Display</h3><label className="check"><input type="checkbox" checked={p.overlay} onChange={e=>p.setOverlay(e.target.checked)}/>Overlay</label><label className="check"><input type="checkbox" checked={p.showE0} onChange={e=>p.setShowE0(e.target.checked)}/>Show E0</label><label className="check"><input type="checkbox" checked={p.showRegions} onChange={e=>p.setShowRegions(e.target.checked)}/>Noise & protected regions</label><div className="seg"><Toggle active={!p.rawMode} onClick={()=>p.setRawMode(false)}>Norm</Toggle><Toggle active={p.rawMode} onClick={()=>p.setRawMode(true)}>Raw</Toggle></div></div>
      <div className="review-block"><h3>Averaging</h3><label className="radio"><input type="radio" checked={p.averaging==='equal'} onChange={()=>p.setAveraging('equal')}/>Equal-weight</label><label className="radio"><input type="radio" checked={p.averaging==='noise_weighted'} onChange={()=>p.setAveraging('noise_weighted')}/>Noise-weighted</label><h3 className="spaced">Include scans</h3>{p.sample?.scans.map(s=><label className="check compact" key={s.id}><input type="checkbox" checked={p.included.includes(s.id)} onChange={e=>p.setIncluded(e.target.checked?[...p.included,s.id]:p.included.filter(x=>x!==s.id))}/>{s.label}</label>)}</div>
      <div className="review-block"><h3>Local normalization anchors</h3><label className="field">Pre offsets (eV)<input value={p.pre} onChange={e=>p.setPre(e.target.value)}/></label><label className="field">Post offsets (eV)<input value={p.post} onChange={e=>p.setPost(e.target.value)}/></label><button className="secondary" onClick={p.reanalyze}><SlidersHorizontal size={15}/>Apply & reanalyze</button></div>
      <div className="review-block artifacts"><h3>Artifact review</h3>{!p.latest?.anomalies.length && <p className="muted">No flags in current cumulative average.</p>}{p.latest?.anomalies.slice(0,8).map((a:Anomaly,i)=>{const key=`${a.energy}:${i}`;return <div className="artifact" key={key}><div><strong>{a.energy.toFixed(2)} eV</strong><span className={a.protected?'tag danger':'tag'}>{a.protected?'protected anomaly':'safe-zone glitch'}</span></div><div className="artifact-actions"><button className={p.glitches[key]==='confirmed'?'chosen':''} onClick={()=>p.setGlitches({...p.glitches,[key]:'confirmed'})}><Check size={14}/>Confirm</button><button className={p.glitches[key]==='rejected'?'chosen':''} onClick={()=>p.setGlitches({...p.glitches,[key]:'rejected'})}><X size={14}/>Reject</button></div></div>})}</div>
      <div className="review-block final-review"><h3>Human assessment</h3><div className="rating">{['Q-ready','QL-ready','Below-QL'].map(r=><Toggle key={r} active={p.rating===r} onClick={()=>p.setRating(r)}>{r}</Toggle>)}</div><label className="field">Reviewer role<select value={p.reviewerRole} onChange={e=>p.setReviewerRole(e.target.value)}><option value="beamline_user">Beamline user</option><option value="beamline_scientist">Beamline scientist</option><option value="pi_experiment_lead">PI / experiment lead</option><option value="other">Other authorized reviewer</option></select></label><label className="field">Manual override<select value={p.override} onChange={e=>p.setOverride(e.target.value)}><option value="">No override</option><option>CONTINUE</option><option>QL ONLY</option><option>STOP RECOMMENDED</option></select></label><label className="field">Review notes<textarea value={p.notes} onChange={e=>p.setNotes(e.target.value)} placeholder="What drove the decision?"/></label><button className="primary" onClick={p.saveReview}><Save size={16}/>{p.saved?'Feedback saved':'Save human validation'}</button></div>
    </div>
  </Panel>
}

function WatchSettings({state,onUpdated}:{state:AppState;onUpdated:()=>void}) {
  const [open,setOpen]=useState(false), [folder,setFolder]=useState(state.watch_folder), [scans,setScans]=useState(String(state.limits.maximum_scans||'')), [seconds,setSeconds]=useState(String(state.limits.maximum_time_seconds||''))
  const save=async()=>{await fetch('/api/watch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({folder,maximum_scans:scans?Number(scans):null,maximum_time_seconds:seconds?Number(seconds):null,averaging_mode:state.averaging_mode})});setOpen(false);onUpdated()}
  return <div className="watch-settings"><button className="secondary" onClick={()=>setOpen(!open)}><FolderOpen size={16}/>Watch settings</button>{open&&<div className="popover"><label className="field">Beamline folder<input value={folder} onChange={e=>setFolder(e.target.value)}/></label><div className="split"><label className="field">Max scans<input type="number" value={scans} onChange={e=>setScans(e.target.value)}/></label><label className="field">Max seconds<input type="number" value={seconds} onChange={e=>setSeconds(e.target.value)}/></label></div><p>When both limits are set, the stricter one wins using measured scan duration.</p><button className="primary" onClick={save}>Start watching</button></div>}</div>
}
