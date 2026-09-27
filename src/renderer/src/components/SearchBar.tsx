import { useEffect, useRef, useState } from 'react'
import type { AssetSummary } from '../../../shared/types'

interface Props {
  onSelect: (asset: AssetSummary) => void
}

export default function SearchBar({ onSelect }: Props): JSX.Element {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<AssetSummary[]>([])
  const [open, setOpen] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)

    const trimmed = query.trim()
    if (!trimmed) {
      setResults([])
      setOpen(false)
      return
    }

    debounceRef.current = setTimeout(async () => {
      const matches = await window.alpaca.searchAssets(trimmed)
      setResults(matches)
      setOpen(true)
    }, 200)

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [query])

  useEffect(() => {
    function handleClickOutside(event: MouseEvent): void {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  function handleSelect(asset: AssetSummary): void {
    onSelect(asset)
    setQuery('')
    setResults([])
    setOpen(false)
  }

  return (
    <div className="search-bar" ref={containerRef}>
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => results.length > 0 && setOpen(true)}
        placeholder="Search symbol or company name (e.g. AAPL, Apple)"
      />
      {open && results.length > 0 && (
        <ul className="search-results">
          {results.map((asset) => (
            <li key={asset.symbol} onClick={() => handleSelect(asset)}>
              <span className="symbol">{asset.symbol}</span>
              <span className="name">{asset.name}</span>
              <span className="exchange">{asset.exchange}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
