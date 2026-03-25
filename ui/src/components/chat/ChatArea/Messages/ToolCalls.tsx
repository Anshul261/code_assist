'use client'

import { useState } from 'react'
import type { ToolCall } from '@/types/os'

// ─── helpers ────────────────────────────────────────────────────────────────

type Category = 'file' | 'bash' | 'search' | 'other'

function getCategory(name: string): Category {
  if (['read', 'write', 'edit', 'glob', 'grep', 'ls'].includes(name)) return 'file'
  if (name === 'bash') return 'bash'
  if (name.startsWith('duckduckgo')) return 'search'
  return 'other'
}

const LABEL: Record<string, string> = {
  read: 'READ',
  write: 'WRITE',
  edit: 'EDIT',
  glob: 'GLOB',
  grep: 'GREP',
  ls: 'LS',
  bash: 'BASH',
  duckduckgo_search: 'SEARCH',
  duckduckgo_news: 'NEWS',
}

const DOT: Record<Category, string> = {
  file:   'bg-blue-400/70',
  bash:   'bg-amber-400/70',
  search: 'bg-emerald-400/70',
  other:  'bg-muted/40',
}

function primaryArg(args: Record<string, string>): string {
  const order = ['path', 'cmd', 'query', 'pat', 'q']
  for (const key of order) {
    if (args[key]) {
      const val = String(args[key])
      // Show just the basename for paths
      if (key === 'path') return val.split('/').pop() ?? val
      return val.length > 32 ? val.slice(0, 32) + '…' : val
    }
  }
  const first = Object.values(args)[0]
  if (!first) return ''
  const s = String(first)
  return s.length > 32 ? s.slice(0, 32) + '…' : s
}

// ─── chip ────────────────────────────────────────────────────────────────────

interface ChipProps {
  tc: ToolCall
  active: boolean
  onClick: () => void
}

const Chip = ({ tc, active, onClick }: ChipProps) => {
  const cat = getCategory(tc.tool_name)
  const label = LABEL[tc.tool_name] ?? tc.tool_name.toUpperCase()
  const arg = primaryArg(tc.tool_args ?? {})

  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded border px-2 py-1 font-mono text-[10px] transition-all ${
        active
          ? 'border-border/80 bg-surface text-primary'
          : 'border-border/40 bg-background text-muted hover:border-border/60 hover:text-primary'
      } ${tc.tool_call_error ? 'border-destructive/50 text-destructive' : ''}`}
    >
      {/* category dot */}
      <span className={`size-1.5 shrink-0 rounded-full ${tc.tool_call_error ? 'bg-destructive' : DOT[cat]}`} />
      <span className="font-semibold tracking-wider">{label}</span>
      {arg && (
        <span className="max-w-[120px] truncate opacity-60">{arg}</span>
      )}
      {tc.metrics?.time != null && (
        <span className="opacity-40">{tc.metrics.time.toFixed(2)}s</span>
      )}
    </button>
  )
}

// ─── detail panel ─────────────────────────────────────────────────────────────

const DetailPanel = ({ tc }: { tc: ToolCall }) => {
  const args = tc.tool_args ?? {}
  const hasArgs = Object.keys(args).length > 0
  const content = typeof tc.content === 'string' ? tc.content : null

  return (
    <div className="mt-1 rounded-lg border border-border/60 bg-background text-xs">
      {/* args */}
      {hasArgs && (
        <div className="border-b border-border/40 px-3 py-2">
          <p className="mb-1.5 font-mono text-[10px] uppercase tracking-widest text-muted/50">
            Input
          </p>
          <div className="space-y-0.5">
            {Object.entries(args).map(([k, v]) => (
              <div key={k} className="flex gap-2 font-mono">
                <span className="shrink-0 text-muted/60">{k}</span>
                <span className="truncate text-primary/80">{String(v)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* result */}
      {content != null && (
        <div className="px-3 py-2">
          <p className="mb-1.5 font-mono text-[10px] uppercase tracking-widest text-muted/50">
            {tc.tool_call_error ? 'Error' : 'Output'}
          </p>
          <pre
            className={`max-h-48 overflow-y-auto whitespace-pre-wrap break-all font-mono text-[11px] leading-relaxed ${
              tc.tool_call_error ? 'text-destructive' : 'text-primary/70'
            }`}
          >
            {content}
          </pre>
        </div>
      )}
    </div>
  )
}

// ─── main export ─────────────────────────────────────────────────────────────

const ToolCalls = ({ toolCalls }: { toolCalls: ToolCall[] }) => {
  const [activeIdx, setActiveIdx] = useState<number | null>(null)

  if (!toolCalls || toolCalls.length === 0) return null

  const toggle = (i: number) => setActiveIdx(activeIdx === i ? null : i)

  return (
    <div className="mb-3">
      {/* chip row */}
      <div className="flex flex-wrap gap-1.5">
        {toolCalls.map((tc, i) => (
          <Chip
            key={tc.tool_call_id ?? i}
            tc={tc}
            active={activeIdx === i}
            onClick={() => toggle(i)}
          />
        ))}
      </div>

      {/* detail panel */}
      {activeIdx !== null && toolCalls[activeIdx] && (
        <DetailPanel tc={toolCalls[activeIdx]} />
      )}
    </div>
  )
}

export default ToolCalls
