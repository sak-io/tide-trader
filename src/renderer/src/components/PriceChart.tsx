import { useMemo, useRef, useState } from 'react'
import type { HistoricalBar } from '../../../shared/types'

interface Props {
  bars: HistoricalBar[]
}

const WIDTH = 640
const HEIGHT = 280
const PADDING = { top: 16, right: 8, bottom: 24, left: 56 }

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function formatPrice(value: number): string {
  return `$${value.toFixed(2)}`
}

export default function PriceChart({ bars }: Props): JSX.Element {
  const svgRef = useRef<SVGSVGElement>(null)
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)

  const plot = useMemo(() => {
    if (bars.length === 0) return null

    const innerWidth = WIDTH - PADDING.left - PADDING.right
    const innerHeight = HEIGHT - PADDING.top - PADDING.bottom

    const lows = bars.map((b) => b.low)
    const highs = bars.map((b) => b.high)
    const min = Math.min(...lows)
    const max = Math.max(...highs)
    const span = max - min || 1
    const domainMin = min - span * 0.05
    const domainMax = max + span * 0.05
    const domainSpan = domainMax - domainMin

    const x = (index: number): number =>
      bars.length === 1 ? PADDING.left : PADDING.left + (index / (bars.length - 1)) * innerWidth
    const y = (price: number): number => PADDING.top + innerHeight - ((price - domainMin) / domainSpan) * innerHeight

    const linePoints = bars.map((bar, i) => `${x(i)},${y(bar.close)}`).join(' ')
    const areaPoints = `${PADDING.left},${PADDING.top + innerHeight} ${linePoints} ${x(bars.length - 1)},${PADDING.top + innerHeight}`

    const gridSteps = 4
    const gridLines = Array.from({ length: gridSteps + 1 }, (_, i) => {
      const price = domainMin + (domainSpan * i) / gridSteps
      return { price, y: y(price) }
    })

    return { x, y, linePoints, areaPoints, gridLines, innerWidth, innerHeight }
  }, [bars])

  if (!plot || bars.length === 0) {
    return <div className="chart-empty">No historical data available.</div>
  }

  const hoverBar = hoverIndex !== null ? bars[hoverIndex] : null

  function handleMouseMove(event: React.MouseEvent<SVGSVGElement>): void {
    const svg = svgRef.current
    if (!svg || !plot) return
    const rect = svg.getBoundingClientRect()
    const ratio = (event.clientX - rect.left) / rect.width
    const fractionalIndex = ratio * (bars.length - 1)
    const index = Math.min(bars.length - 1, Math.max(0, Math.round(fractionalIndex)))
    setHoverIndex(index)
  }

  const firstClose = bars[0].close
  const lastClose = bars[bars.length - 1].close
  const trendUp = lastClose >= firstClose

  return (
    <div className="price-chart">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        preserveAspectRatio="none"
        className="price-chart-svg"
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHoverIndex(null)}
      >
        <defs>
          <linearGradient id="price-area-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--chart-line)" stopOpacity="0.28" />
            <stop offset="100%" stopColor="var(--chart-line)" stopOpacity="0" />
          </linearGradient>
        </defs>

        {plot.gridLines.map((line) => (
          <g key={line.price}>
            <line
              x1={PADDING.left}
              x2={WIDTH - PADDING.right}
              y1={line.y}
              y2={line.y}
              className="chart-gridline"
            />
            <text x={PADDING.left - 8} y={line.y} className="chart-axis-label" textAnchor="end" dy="0.32em">
              {formatPrice(line.price)}
            </text>
          </g>
        ))}

        <text x={PADDING.left} y={HEIGHT - 6} className="chart-axis-label" textAnchor="start">
          {formatDate(bars[0].timestamp)}
        </text>
        <text x={WIDTH - PADDING.right} y={HEIGHT - 6} className="chart-axis-label" textAnchor="end">
          {formatDate(bars[bars.length - 1].timestamp)}
        </text>

        <polygon points={plot.areaPoints} fill="url(#price-area-fill)" stroke="none" />
        <polyline points={plot.linePoints} className="chart-line" fill="none" />

        {hoverBar && hoverIndex !== null && (
          <>
            <line
              x1={plot.x(hoverIndex)}
              x2={plot.x(hoverIndex)}
              y1={PADDING.top}
              y2={PADDING.top + plot.innerHeight}
              className="chart-crosshair"
            />
            <circle cx={plot.x(hoverIndex)} cy={plot.y(hoverBar.close)} r={4} className="chart-dot" />
          </>
        )}
      </svg>

      <div className={`chart-current-price ${trendUp ? 'up' : 'down'}`}>{formatPrice(lastClose)}</div>

      {hoverBar && (
        <div className="chart-tooltip">
          <div className="chart-tooltip-date">{formatDate(hoverBar.timestamp)}</div>
          <div className="chart-tooltip-grid">
            <span>Open</span>
            <span>{formatPrice(hoverBar.open)}</span>
            <span>High</span>
            <span>{formatPrice(hoverBar.high)}</span>
            <span>Low</span>
            <span>{formatPrice(hoverBar.low)}</span>
            <span>Close</span>
            <span>{formatPrice(hoverBar.close)}</span>
            <span>Volume</span>
            <span>{Math.round(hoverBar.volume).toLocaleString()}</span>
          </div>
        </div>
      )}
    </div>
  )
}
