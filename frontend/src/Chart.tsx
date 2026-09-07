import { useId } from 'react'

type Series = { x: number[]; y: number[]; color: string; label: string; width?: number; dashed?: boolean }
type Band = { start: number; end: number; color: string; label: string }

export function Chart({ series, bands = [], markers = [], yPercent = false }: {
  series: Series[]; bands?: Band[]; markers?: Array<{ x: number; color: string; label: string }>; yPercent?: boolean
}) {
  const clipId = useId().replaceAll(':', '')
  const points = series.flatMap(s => s.x.map((x, i) => [x, s.y[i]] as const)).filter(p => Number.isFinite(p[0]) && Number.isFinite(p[1]))
  if (!points.length) return <div className="empty-chart">Waiting for a complete spectrum…</div>
  const xs = points.map(p => p[0]), ys = points.map(p => p[1])
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  let minY = Math.min(...ys), maxY = Math.max(...ys)
  const padY = Math.max((maxY - minY) * .1, 1e-8); minY -= padY; maxY += padY
  const W = 720, H = 360, left = 64, right = 20, top = 20, bottom = 42
  const sx = (x: number) => left + (x - minX) / (maxX - minX || 1) * (W - left - right)
  const sy = (y: number) => top + (maxY - y) / (maxY - minY || 1) * (H - top - bottom)
  const path = (s: Series) => s.x.map((x, i) => `${i ? 'L' : 'M'}${sx(x).toFixed(1)},${sy(s.y[i]).toFixed(1)}`).join(' ')
  const ticks = Array.from({ length: 5 }, (_, i) => i / 4)
  return <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="XAS analysis chart">
    <defs><clipPath id={clipId}><rect x={left} y={top} width={W-left-right} height={H-top-bottom}/></clipPath></defs>
    {ticks.map(t => { const y = minY + t * (maxY-minY); return <g key={`y${t}`}>
      <line x1={left} x2={W-right} y1={sy(y)} y2={sy(y)} className="grid"/>
      <text x={left-9} y={sy(y)+4} textAnchor="end" className="tick">{yPercent ? `${(y*100).toFixed(2)}%` : y.toPrecision(4)}</text>
    </g> })}
    {ticks.map(t => { const x = minX + t * (maxX-minX); return <text key={`x${t}`} x={sx(x)} y={H-14} textAnchor="middle" className="tick">{Number.isInteger(x) ? x : x.toFixed(1)}</text> })}
    <g clipPath={`url(#${clipId})`}>
      {bands.map(b => <rect key={b.label} x={sx(b.start)} y={top} width={Math.max(sx(b.end)-sx(b.start),1)} height={H-top-bottom} fill={b.color} opacity=".13"/>) }
      {markers.map(m => <line key={`${m.label}${m.x}`} x1={sx(m.x)} x2={sx(m.x)} y1={top} y2={H-bottom} stroke={m.color} strokeWidth="1.5" strokeDasharray="5 5"/>) }
      {series.map(s => <path key={s.label} d={path(s)} fill="none" stroke={s.color} strokeWidth={s.width || 2} strokeDasharray={s.dashed ? '7 5' : undefined} vectorEffect="non-scaling-stroke"/>) }
    </g>
    <line x1={left} x2={W-right} y1={H-bottom} y2={H-bottom} className="axis"/>
    <line x1={left} x2={left} y1={top} y2={H-bottom} className="axis"/>
  </svg>
}
