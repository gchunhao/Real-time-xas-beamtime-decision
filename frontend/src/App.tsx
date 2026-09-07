import { useEffect, useMemo, useState } from 'react'
import {
  Activity, AlertTriangle, Check, ChevronDown, ChevronRight, CircleHelp, Database,
  Eye, FileChartColumn, FolderOpen, Gauge, Layers, RefreshCw, Save, Settings,
  SlidersHorizontal, Timer, X,
} from 'lucide-react'
import { Chart } from './Chart'
import type { Anomaly, AppState, Result, Sample } from './types'

const colors = ['#1677a6', '#c27a14', '#7658b5', '#238a65', '#c94f64', '#806f00', '#3d6fc5']
const pct = (value: number | null, digits = 3) => value == null ? '—' : `${(value * 100).toFixed(digits)}%`
const num = (value: number | null, digits = 2) => value == null ? '—' : value.toFixed(digits)
type SessionMode = 'live' | 'offline'
type DockTab = 'review' | 'quality' | 'log'

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
  const [glitches, setGlitches] = useState<Record<string, string>>({})
  const [saved, setSaved] = useState(false)
  const [sessionMode, setSessionMode] = useState<SessionMode>('live')
  const [dockTab, setDockTab] = useState<DockTab>('review')
  const [advanced, setAdvanced] = useState(false)
  const [setupOpen, setSetupOpen] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)

  const refresh = async () => {
    try {
      const response = await fetch('/api/state')
      if (!response.ok) throw new Error(await response.text())
      setState(await response.json())
      setError('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    }
  }

  useEffect(() => {
    refresh()
    const timer = window.setInterval(refresh, 1500)
    return () => clearInterval(timer)
  }, [])
  useEffect(() => {
    if (!sampleId && state?.samples[0]) setSampleId(state.samples[0].sample_id)
  }, [state, sampleId])

  const sample = state?.samples.find(item => item.sample_id === sampleId) || state?.samples[0]
  useEffect(() => {
    if (sample) {
      setIncluded(sample.scans.map(scan => scan.id))
      setAveraging(sample.latest?.averaging_mode || 'equal')
    }
  }, [sample?.sample_id, sample?.scan_count])
  const latest = sample?.latest

  const displayed = useMemo(() => {
    if (!sample) return []
    if (selected.startsWith('scan:')) {
      const scan = sample.scans.find(item => item.id === selected.slice(5))
      return scan ? [{ x: scan.energy, y: rawMode ? scan.raw : scan.normalized, label: scan.label }] : []
    }
    const count = selected.startsWith('avg:') ? Number(selected.slice(4)) : sample.scan_count
    const average = sample.averages.find(item => item.scan_count === count) || latest
    if (!average) return []
    const base = [{ x: average.energy, y: rawMode ? average.raw_average : average.normalized_average, label: `Avg 1–${average.scan_count}` }]
    if (!overlay) return base
    return [...sample.scans.filter(scan => included.includes(scan.id)).map(scan => ({ x: scan.energy, y: rawMode ? scan.raw : scan.normalized, label: scan.label })), ...base]
  }, [sample, selected, rawMode, overlay, included, latest])

  const spectrumSeries = displayed.map((series, index) => ({ ...series, color: index === displayed.length - 1 ? '#111d29' : colors[index % colors.length], width: index === displayed.length - 1 ? 2.8 : 1.05 }))
  const bands = showRegions && latest ? latest.regions.map(region => ({ start: region.start, end: region.end, color: region.protected ? '#cf465f' : '#168bc0', label: region.name })) : []
  const markers = showE0 && latest?.metrics.e0 ? [{ x: latest.metrics.e0, color: '#b98200', label: 'E0' }] : []
  const qSeries = sample ? [
    { x: sample.history.map(item => item.scan_count), y: sample.history.map(item => item.metrics.q_hf ?? NaN), color: '#1677a6', label: 'Q_HF', width: 2.6 },
    { x: [1, Math.max(sample.scan_count, 2)], y: [.0045, .0045], color: '#238a65', label: 'Route A', dashed: true },
    { x: [1, Math.max(sample.scan_count, 2)], y: [.007, .007], color: '#c27a14', label: 'Route B', dashed: true },
  ] : []

  const reanalyze = async () => {
    if (!sample) return
    const parseAnchor = (value: string) => value.split(',').map(Number)
    const response = await fetch('/api/reanalyze', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sample_id: sample.sample_id, averaging_mode: averaging, included_scan_ids: included, anchors: { pre: parseAnchor(pre), post: parseAnchor(post) } }) })
    if (!response.ok) setError(await response.text())
    else { setSelected('latest'); await refresh() }
  }

  const saveReview = async () => {
    if (!sample || !latest) return
    const decisions = latest.anomalies.map((anomaly, index) => ({ energy: anomaly.energy, region: anomaly.region, status: glitches[`${anomaly.energy}:${index}`] || 'unreviewed' }))
    const response = await fetch('/api/reviews', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ analysis_id: latest.analysis_id, sample_id: sample.sample_id, rating, override_recommendation: override || null, averaging_mode: averaging, included_scans: included, excluded_scans: sample.scans.filter(scan => !included.includes(scan.id)).map(scan => scan.id), glitch_decisions: decisions, local_normalization_anchors: { pre: pre.split(',').map(Number), post: post.split(',').map(Number) }, notes, reviewer_role: reviewerRole }) })
    if (!response.ok) setError(await response.text())
    else { setSaved(true); window.setTimeout(() => setSaved(false), 2200); await refresh() }
  }

  if (!state) return <main className="loading"><Activity className="spin" /> Connecting to the local analysis service…{error && <span>{error}</span>}</main>

  return <div className="app-shell">
    <header className="app-header">
      <div className="menu-row">
        <div className="app-brand"><div className="app-mark"><Activity size={19} /></div><div><strong>XAS Decision Workbench</strong><span>v{state.framework_version}</span></div></div>
        <nav aria-label="Application menu"><button onClick={() => setSetupOpen(true)}>File</button><button onClick={() => setDockTab('quality')}>View</button><button onClick={() => setSetupOpen(true)}>Session</button><button onClick={() => setHelpOpen(true)}>Help</button></nav>
        <div className="mode-switch" aria-label="Workflow mode"><button className={sessionMode === 'live' ? 'active' : ''} onClick={() => setSessionMode('live')}><span className={`status-dot ${state.watching ? 'on' : ''}`} />Live beamtime</button><button className={sessionMode === 'offline' ? 'active' : ''} onClick={() => setSessionMode('offline')}><Database size={14} />Offline review</button></div>
        <button className="icon-button" title="Session setup" onClick={() => setSetupOpen(true)}><Settings size={18} /></button><button className="icon-button" title="Beginner help" onClick={() => setHelpOpen(true)}><CircleHelp size={18} /></button>
      </div>
      <div className="context-row"><div><strong>{sessionMode === 'live' ? 'Real-time decision support' : 'Offline spectrum review'}</strong><span>{state.watch_folder}</span></div><div className="safety-banner"><AlertTriangle size={15} />Advisory only — this software never controls acquisition</div></div>
    </header>
    {error && <div className="error-banner"><AlertTriangle size={17} /><span>{error}</span><button onClick={() => setError('')}><X size={16} /></button></div>}
    <main className="workbench">
      <ProjectPane state={state} sample={sample} sampleId={sampleId} setSampleId={setSampleId} selected={selected} setSelected={setSelected} included={included} setIncluded={setIncluded} qualitySeries={qSeries} latest={latest} onSetup={() => setSetupOpen(true)} />
      <section className="plot-pane">
        <div className="pane-titlebar"><div><FileChartColumn size={17} /><strong>{sample ? `${sample.sample_id} — cumulative spectrum` : 'Spectrum workspace'}</strong></div><div className="plot-actions"><Segment active={!rawMode} onClick={() => setRawMode(false)}>Normalized</Segment><Segment active={rawMode} onClick={() => setRawMode(true)}>Raw</Segment><ToolbarCheck checked={overlay} onChange={setOverlay} label="Overlay" /><ToolbarCheck checked={showE0} onChange={setShowE0} label="E0" /><ToolbarCheck checked={showRegions} onChange={setShowRegions} label="Regions" /><button className="icon-button compact" title="Refresh data" onClick={refresh}><RefreshCw size={15} /></button></div></div>
        <div className="plot-canvas">{sample ? <><Chart series={spectrumSeries} bands={bands} markers={markers} /><div className="axis-label y">μ(E)</div><div className="axis-label x">Energy (eV)</div><div className="plot-legend">{displayed.map((series, index) => <span key={series.label}><i style={{ background: spectrumSeries[index].color }} />{series.label}</span>)}</div></> : <WelcomePanel onSetup={() => setSetupOpen(true)} />}</div>
        <div className="plot-status"><span><i className="swatch protected" />Protected XANES feature region</span><span><i className="swatch safe" />Safe mask zone</span><span>E0 {latest?.metrics.e0 ? `${latest.metrics.e0.toFixed(2)} eV` : '—'}</span><span>{rawMode ? 'Raw μ(E)' : `${latest?.metrics.normalization_mode || 'Normalized'} μ(E)`}</span></div>
      </section>
      <DecisionInspector result={latest} />
      <section className="review-dock"><div className="dock-tabs"><button className={dockTab === 'review' ? 'active' : ''} onClick={() => setDockTab('review')}><Check size={15} />Human validation</button><button className={dockTab === 'quality' ? 'active' : ''} onClick={() => setDockTab('quality')}><Gauge size={15} />Quality vs. scan number</button><button className={dockTab === 'log' ? 'active' : ''} onClick={() => setDockTab('log')}><Database size={15} />Session log</button><div className="dock-spacer" /><button onClick={() => setAdvanced(!advanced)}><SlidersHorizontal size={15} />{advanced ? 'Hide advanced' : 'Show advanced'}</button></div>
        {dockTab === 'review' && <HumanWorkflow sample={sample} latest={latest} averaging={averaging} setAveraging={setAveraging} included={included} setIncluded={setIncluded} pre={pre} setPre={setPre} post={post} setPost={setPost} glitches={glitches} setGlitches={setGlitches} rating={rating} setRating={setRating} override={override} setOverride={setOverride} notes={notes} setNotes={setNotes} reviewerRole={reviewerRole} setReviewerRole={setReviewerRole} reanalyze={reanalyze} saveReview={saveReview} saved={saved} advanced={advanced} />}
        {dockTab === 'quality' && <QualityDock sample={sample} latest={latest} series={qSeries} />}{dockTab === 'log' && <SessionLog events={state.events} />}
      </section>
    </main>
    <footer className="status-bar"><span><i className={`status-dot ${state.watching ? 'on' : ''}`} />{state.watching ? 'Folder monitor active' : 'Folder monitor paused'}</span><span>Profile: P K-edge XANES v1.2</span><span>Average: {state.averaging_mode.replace('_', ' ')}</span><span>{Object.values(state.database_counts).reduce((sum, count) => sum + count, 0)} provenance records</span><span className="push-right">Algorithm prediction ↔ human decision retained</span></footer>
    {setupOpen && <SessionSetup state={state} mode={sessionMode} setMode={setSessionMode} onClose={() => setSetupOpen(false)} onUpdated={refresh} setError={setError} />}{helpOpen && <HelpDialog onClose={() => setHelpOpen(false)} />}
  </div>
}

function ProjectPane({ state, sample, sampleId, setSampleId, selected, setSelected, included, setIncluded, qualitySeries, latest, onSetup }: { state: AppState; sample?: Sample; sampleId: string; setSampleId: (value: string) => void; selected: string; setSelected: (value: string) => void; included: string[]; setIncluded: (value: string[]) => void; qualitySeries: Array<{ x: number[]; y: number[]; color: string; label: string; width?: number; dashed?: boolean }>; latest?: Result | null; onSetup: () => void }) {
  const [open, setOpen] = useState<Record<string, boolean>>({ samples: true, averages: true })
  const toggleOpen = (key: string) => setOpen({ ...open, [key]: !open[key] })
  return <aside className="project-pane"><div className="pane-titlebar"><div><Layers size={17} /><strong>Data & scans</strong></div></div><div className="project-actions"><button className="primary-button" onClick={onSetup}><FolderOpen size={16} />Choose data folder</button></div><div className="folder-summary"><span>Current folder</span><strong title={state.watch_folder}>{state.watch_folder.split(/[\\/]/).pop() || state.watch_folder}</strong><small>{state.watching ? 'Monitoring completed files' : 'Not monitoring'}</small></div><div className="tree-scroll">
    <div className="tree-section"><button className="tree-heading" onClick={() => toggleOpen('samples')}>{open.samples ? <ChevronDown size={15} /> : <ChevronRight size={15} />}Samples <span>{state.samples.length}</span></button>{open.samples && <div className="tree-list">{state.samples.length === 0 ? <p>No spectra loaded</p> : state.samples.map(item => <button key={item.sample_id} className={item.sample_id === (sample?.sample_id || sampleId) ? 'active' : ''} onClick={() => { setSampleId(item.sample_id); setSelected('latest') }}><FileChartColumn size={15} /><span>{item.sample_id}<small>{item.scan_count} scan{item.scan_count === 1 ? '' : 's'}</small></span></button>)}</div>}</div>
    {sample && <><div className="tree-section"><div className="tree-heading static"><ChevronDown size={15} />Individual scans <span>{sample.scan_count}</span></div><div className="scan-tree">{sample.scans.map((scan, index) => <div key={scan.id} className={selected === `scan:${scan.id}` ? 'active' : ''}><input title="Include this scan in the cumulative average" type="checkbox" checked={included.includes(scan.id)} onChange={event => setIncluded(event.target.checked ? [...included, scan.id] : included.filter(id => id !== scan.id))} /><button onClick={() => setSelected(`scan:${scan.id}`)}><span className="line-color" style={{ background: colors[index % colors.length] }} />{scan.label}</button></div>)}</div></div><div className="tree-section"><button className="tree-heading" onClick={() => toggleOpen('averages')}>{open.averages ? <ChevronDown size={15} /> : <ChevronRight size={15} />}Cumulative averages <span>{sample.averages.length}</span></button>{open.averages && <div className="tree-list averages">{sample.averages.map(average => <button key={average.scan_count} className={(selected === `avg:${average.scan_count}` || (selected === 'latest' && average.scan_count === sample.scan_count)) ? 'active' : ''} onClick={() => setSelected(`avg:${average.scan_count}`)}><Layers size={14} /><span>Avg 1–{average.scan_count}<small>{average.recommendation}</small></span></button>)}</div>}</div></>}
    <div className="profile-card"><span>Active profile</span><strong>P_K_XANES v1.2</strong><small>Profile rules are frozen and external to the framework.</small></div></div><div className="quality-mini"><div><strong>Quality vs. scan number</strong><span>Q_HF {pct(latest?.metrics.q_hf ?? null)}</span></div><Chart series={qualitySeries} yPercent /></div></aside>
}

function DecisionInspector({ result }: { result: Result | null | undefined }) {
  const decision = result?.recommendation || 'CONTINUE'; const tone = decision === 'STOP RECOMMENDED' ? 'stop' : decision === 'QL ONLY' ? 'ql' : 'continue'
  return <aside className="decision-inspector"><div className="pane-titlebar"><div><Gauge size={17} /><strong>Decision inspector</strong></div><span className="advisory-tag">ADVISORY</span></div><div className={`decision-card ${tone}`}><span>Software recommendation</span><strong><i />{decision}</strong><p>{result?.recommendation_reason || 'Waiting for the first completed scan.'}</p></div><div className="inspector-section"><h3>Decision basis</h3><dl className="property-list"><div><dt>Route</dt><dd>{result?.metrics.route || '—'}</dd></div><div><dt>N_quant</dt><dd>{result?.n_quant || result?.predicted_n_quant || '—'}</dd></div><div><dt>Normalization</dt><dd>{result?.metrics.normalization_mode || '—'}</dd></div><div><dt>Measured time</dt><dd>{result ? `${num(result.total_measured_seconds, 0)} s` : '—'}</dd></div></dl></div><div className="inspector-section"><h3>Marginal gain</h3><div className="gain-row"><strong>{result?.marginal_gain == null ? 'Learning…' : `${(result.marginal_gain * 100).toFixed(1)}%`}</strong><span>{result?.marginal_gain == null ? 'More scans needed' : result.marginal_gain > .12 ? 'Another scan may help' : 'Diminishing return'}</span></div><div className="gain-track"><i style={{ width: `${Math.min(Math.max((result?.marginal_gain || 0) * 350, 4), 100)}%` }} /></div></div><div className="inspector-section"><h3>Quality metrics</h3><dl className="property-list metrics"><div><dt>Q_HF</dt><dd>{pct(result?.metrics.q_hf ?? null)}</dd></div><div><dt>Q_pre</dt><dd>{pct(result?.metrics.q_pre ?? null)}</dd></div><div><dt>Q_post</dt><dd>{pct(result?.metrics.q_post ?? null)}</dd></div><div><dt>A_spike</dt><dd>{num(result?.metrics.a_spike ?? null)}</dd></div></dl></div><div className="inspector-section"><h3>Limits</h3><div className="limit-line"><Timer size={17} /><div><strong>Strictest constraint applies</strong><span>{result?.remaining_scan_budget ?? '∞'} scans · {result?.remaining_time_seconds == null ? '∞' : `${Math.floor(result.remaining_time_seconds)} s`} remaining</span></div></div></div>{result?.uncertainty?.q_hf_interval_95 && <div className="inspector-section"><h3>Uncertainty</h3><p className="small-copy">Q_HF scan-bootstrap 95% band</p><strong className="range">{pct(result.uncertainty.q_hf_interval_95[0])} – {pct(result.uncertainty.q_hf_interval_95[1])}</strong></div>}{!!result?.metrics.diagnostics.length && <div className="diagnostic-note"><Eye size={16} /><span><strong>Diagnostic</strong>{result.metrics.diagnostics[0]}</span></div>}<div className="human-gate"><AlertTriangle size={18} /><span><strong>Human decision required</strong>A beamline user, beamline scientist, or other authorized reviewer makes the final decision.</span></div></aside>
}

type HumanProps = { sample?: Sample; latest?: Result | null; averaging: string; setAveraging: (value: string) => void; included: string[]; setIncluded: (value: string[]) => void; pre: string; setPre: (value: string) => void; post: string; setPost: (value: string) => void; glitches: Record<string, string>; setGlitches: (value: Record<string, string>) => void; rating: string; setRating: (value: string) => void; override: string; setOverride: (value: string) => void; notes: string; setNotes: (value: string) => void; reviewerRole: string; setReviewerRole: (value: string) => void; reanalyze: () => void; saveReview: () => void; saved: boolean; advanced: boolean }
function HumanWorkflow(props: HumanProps) {
  return <div className="review-workflow"><section className="workflow-step"><div className="step-number">1</div><div className="step-content"><h3>Review included scans</h3><p>Clear a checkbox to exclude a poor scan, then update the average.</p><div className="scan-checks">{props.sample?.scans.map(scan => <label key={scan.id}><input type="checkbox" checked={props.included.includes(scan.id)} onChange={event => props.setIncluded(event.target.checked ? [...props.included, scan.id] : props.included.filter(id => id !== scan.id))} />{scan.label}</label>) || <span className="empty-copy">Load a folder to begin.</span>}</div><div className="inline-controls"><label>Averaging<select value={props.averaging} onChange={event => props.setAveraging(event.target.value)}><option value="equal">Equal-weight</option><option value="noise_weighted">Noise-weighted</option></select></label><button className="secondary-button" onClick={props.reanalyze} disabled={!props.sample}><RefreshCw size={15} />Update average</button></div>{props.advanced && <div className="advanced-box"><strong>Local normalization anchors</strong><div><label>Pre offsets (eV)<input value={props.pre} onChange={event => props.setPre(event.target.value)} /></label><label>Post offsets (eV)<input value={props.post} onChange={event => props.setPost(event.target.value)} /></label></div><button className="secondary-button" onClick={props.reanalyze}><SlidersHorizontal size={15} />Apply anchors</button></div>}</div></section><section className="workflow-step"><div className="step-number">2</div><div className="step-content"><h3>Check artifact flags</h3><p>Protected-region anomalies are never removed automatically.</p><div className="artifact-list">{!props.latest?.anomalies.length && <span className="empty-copy">No flags in the current average.</span>}{props.latest?.anomalies.slice(0, 7).map((anomaly: Anomaly, index) => { const key = `${anomaly.energy}:${index}`; return <div className="artifact-row" key={key}><div><strong>{anomaly.energy.toFixed(2)} eV</strong><span className={anomaly.protected ? 'flag protected' : 'flag safe'}>{anomaly.protected ? 'Protected anomaly' : 'Safe-zone glitch'}</span></div><div><button className={props.glitches[key] === 'confirmed' ? 'chosen' : ''} onClick={() => props.setGlitches({ ...props.glitches, [key]: 'confirmed' })}><Check size={14} />Confirm</button><button className={props.glitches[key] === 'rejected' ? 'chosen' : ''} onClick={() => props.setGlitches({ ...props.glitches, [key]: 'rejected' })}><X size={14} />Reject</button></div></div> })}</div></div></section><section className="workflow-step final-step"><div className="step-number">3</div><div className="step-content"><h3>Record the human decision</h3><p>This becomes calibration data; it does not stop the scanner.</p><div className="readiness">{['Q-ready', 'QL-ready', 'Below-QL'].map(value => <Segment key={value} active={props.rating === value} onClick={() => props.setRating(value)}>{value}</Segment>)}</div><div className="form-grid"><label>Reviewer role<select value={props.reviewerRole} onChange={event => props.setReviewerRole(event.target.value)}><option value="beamline_user">Beamline user</option><option value="beamline_scientist">Beamline scientist</option><option value="pi_experiment_lead">PI / experiment lead</option><option value="other">Other authorized reviewer</option></select></label><label>Manual override<select value={props.override} onChange={event => props.setOverride(event.target.value)}><option value="">No override</option><option>CONTINUE</option><option>QL ONLY</option><option>STOP RECOMMENDED</option></select></label></div><label>Review notes<textarea value={props.notes} onChange={event => props.setNotes(event.target.value)} placeholder="What did you observe, and why did you make this decision?" /></label><button className="save-button" onClick={props.saveReview} disabled={!props.latest}><Save size={16} />{props.saved ? 'Human review saved' : 'Save human review'}</button></div></section></div>
}

function QualityDock({ sample, latest, series }: { sample?: Sample; latest?: Result | null; series: Array<{ x: number[]; y: number[]; color: string; label: string; width?: number; dashed?: boolean }> }) { return <div className="quality-dock"><div className="quality-chart"><Chart series={series} yPercent /></div><div className="quality-summary"><h3>Noise convergence</h3><p>Lower Q values indicate better repeatability. The profile checks Route A first, then Route B.</p><dl className="property-list metrics"><div><dt>Current scans</dt><dd>{sample?.scan_count || 0}</dd></div><div><dt>Q_HF</dt><dd>{pct(latest?.metrics.q_hf ?? null)}</dd></div><div><dt>Route A threshold</dt><dd>≤ 0.450%</dd></div><div><dt>Route B threshold</dt><dd>≤ 0.700%</dd></div></dl></div></div> }
function SessionLog({ events }: { events: Array<Record<string, unknown>> }) { return <div className="session-log"><div className="log-header"><span>Time</span><span>Event</span><span>Details</span></div>{events.length === 0 ? <p>No session events yet.</p> : events.map((event, index) => <div className="log-row" key={`${event.time}-${index}`}><span>{String(event.time || '').replace('T', ' ').slice(0, 19)}</span><strong>{String(event.kind || '')}</strong><span>{String(event.message || event.error || '')}</span></div>)}</div> }
function WelcomePanel({ onSetup }: { onSetup: () => void }) { return <div className="welcome-panel"><div className="welcome-icon"><FileChartColumn size={30} /></div><h2>Start an XAS review session</h2><p>Choose the folder where completed scan files are written. Existing files are loaded for offline review; new completed files appear automatically during beamtime.</p><button className="primary-button large" onClick={onSetup}><FolderOpen size={18} />Choose data folder</button><div className="welcome-steps"><span><strong>1</strong>Choose folder</span><i /><span><strong>2</strong>Review spectrum</span><i /><span><strong>3</strong>Save human decision</span></div></div> }

function SessionSetup({ state, mode, setMode, onClose, onUpdated, setError }: { state: AppState; mode: SessionMode; setMode: (value: SessionMode) => void; onClose: () => void; onUpdated: () => void; setError: (value: string) => void }) {
  const [folder, setFolder] = useState(state.watch_folder); const [scans, setScans] = useState(String(state.limits.maximum_scans || '')); const [seconds, setSeconds] = useState(String(state.limits.maximum_time_seconds || '')); const [busy, setBusy] = useState(false)
  const chooseFolder = async () => { setBusy(true); try { const response = await fetch('/api/select-folder', { method: 'POST', headers: { 'X-XAS-Local': '1' } }); const payload = await response.json(); if (!response.ok) throw new Error(payload.detail || 'Folder picker unavailable'); if (payload.folder) setFolder(payload.folder) } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)) } finally { setBusy(false) } }
  const start = async () => { setBusy(true); try { const response = await fetch('/api/watch', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ folder, maximum_scans: scans ? Number(scans) : null, maximum_time_seconds: seconds ? Number(seconds) : null, averaging_mode: state.averaging_mode }) }); if (!response.ok) throw new Error(await response.text()); await onUpdated(); onClose() } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)) } finally { setBusy(false) } }
  return <Modal title="Session setup" onClose={onClose}><div className="mode-cards"><button className={mode === 'live' ? 'active' : ''} onClick={() => setMode('live')}><Activity size={20} /><span><strong>Live beamtime</strong><small>Analyze new completed files immediately</small></span></button><button className={mode === 'offline' ? 'active' : ''} onClick={() => setMode('offline')}><Database size={20} /><span><strong>Offline review</strong><small>Load and revisit an existing folder</small></span></button></div><label className="form-field">XAS data folder<div className="folder-input"><input value={folder} onChange={event => setFolder(event.target.value)} /><button className="secondary-button" onClick={chooseFolder} disabled={busy}><FolderOpen size={15} />Browse…</button></div><small>You can paste a Windows folder path if the native window is unavailable.</small></label><div className="limit-fields"><label className="form-field">Maximum scans<input type="number" min="1" value={scans} onChange={event => setScans(event.target.value)} placeholder="No limit" /></label><label className="form-field">Maximum time per sample (seconds)<input type="number" min="1" value={seconds} onChange={event => setSeconds(event.target.value)} placeholder="No limit" /></label></div><div className="info-box"><Timer size={17} /><span>If both limits are supplied, the stricter one applies. Time remaining uses the actual measured scan duration dynamically.</span></div><div className="modal-actions"><button className="secondary-button" onClick={onClose}>Cancel</button><button className="primary-button" disabled={!folder || busy} onClick={start}>{busy ? <Activity className="spin" size={16} /> : <FolderOpen size={16} />}{mode === 'live' ? 'Start monitoring' : 'Load folder'}</button></div></Modal>
}
function HelpDialog({ onClose }: { onClose: () => void }) { return <Modal title="Quick start for new users" onClose={onClose}><div className="help-content"><div><strong>1. Choose a data folder</strong><p>Use Live beamtime for a folder receiving new files, or Offline review for previously collected scans.</p></div><div><strong>2. Inspect the spectrum</strong><p>Select individual scans or cumulative averages in the left tree. Use Overlay, E0, and Regions above the plot.</p></div><div><strong>3. Check automatic flags</strong><p>Confirm or reject artifact suggestions. Protected-feature anomalies are always left for a person to judge.</p></div><div><strong>4. Record your assessment</strong><p>Beamline users as well as beamline scientists can save a review. The software recommendation remains advisory.</p></div><div className="warning-help"><AlertTriangle size={18} /><p><strong>CONTINUE / QL ONLY / STOP RECOMMENDED never controls the scanner.</strong> An authorized member of the beamtime team makes the operational decision.</p></div></div><div className="modal-actions"><button className="primary-button" onClick={onClose}>Got it</button></div></Modal> }
function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) { return <div className="modal-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}><section className="modal" role="dialog" aria-modal="true" aria-label={title}><div className="modal-header"><h2>{title}</h2><button className="icon-button" onClick={onClose}><X size={18} /></button></div><div className="modal-body">{children}</div></section></div> }
function Segment({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) { return <button className={`segment ${active ? 'active' : ''}`} onClick={onClick}>{children}</button> }
function ToolbarCheck({ checked, onChange, label }: { checked: boolean; onChange: (value: boolean) => void; label: string }) { return <label className="toolbar-check"><input type="checkbox" checked={checked} onChange={event => onChange(event.target.checked)} />{label}</label> }
