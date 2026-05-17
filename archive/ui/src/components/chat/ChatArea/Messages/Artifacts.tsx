'use client'

import Icon from '@/components/ui/icon'
import { constructEndpointUrl } from '@/lib/constructEndpointUrl'
import { useStore } from '@/store'
import type { ToolCall } from '@/types/os'

interface ExcelPptArtifact {
  status: string
  workbook?: string
  profile_md?: string
  profile_json?: string
  report_md?: string
  charts?: {
    title?: string
    path?: string
  }[]
  deck?: string
  slides?: number
}

const parseExcelPptArtifact = (toolCall: ToolCall): ExcelPptArtifact | null => {
  const content =
    toolCall.content ??
    (toolCall as ToolCall & { result?: string | null }).result

  if (toolCall.tool_name !== 'create_excel_analysis_ppt' || !content) {
    return null
  }

  try {
    const parsed = JSON.parse(content) as ExcelPptArtifact
    if (parsed.status !== 'success') return null
    if (!parsed.deck && !parsed.report_md && !parsed.profile_md) return null
    return parsed
  } catch {
    return null
  }
}

const fileName = (path?: string) => {
  if (!path) return ''
  return path.split('/').pop() || path
}

const artifactUrl = (endpoint: string, path?: string) => {
  if (!path) return ''
  return `${endpoint}/api/artifacts?path=${encodeURIComponent(path)}`
}

const ArtifactLink = ({
  label,
  path,
  endpoint,
  primary = false
}: {
  label: string
  path?: string
  endpoint: string
  primary?: boolean
}) => {
  if (!path) return null

  return (
    <a
      href={artifactUrl(endpoint, path)}
      target="_blank"
      rel="noreferrer"
      className={`flex min-w-0 items-center gap-2 rounded border px-3 py-2 text-xs transition-colors ${
        primary
          ? 'border-primary/30 bg-primary/10 text-primary hover:bg-primary/15'
          : 'border-border bg-background text-muted hover:text-primary'
      }`}
      title={path}
    >
      <Icon type="download" size="xs" className="shrink-0" />
      <span className="shrink-0 font-medium">{label}</span>
      <span className="truncate font-mono opacity-70">{fileName(path)}</span>
    </a>
  )
}

const ExcelPptArtifactCard = ({ artifact }: { artifact: ExcelPptArtifact }) => {
  const selectedEndpoint = useStore((state) => state.selectedEndpoint)
  const endpoint = constructEndpointUrl(selectedEndpoint || 'http://localhost:7777')
  const charts = artifact.charts?.filter((chart) => chart.path) ?? []

  return (
    <div className="mb-3 rounded-lg border border-border/70 bg-background p-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-primary">
            Excel Analysis Artifacts
          </p>
          <p className="mt-1 text-xs text-muted">
            {artifact.slides ? `${artifact.slides} slides generated` : 'Generated report and deck'}
          </p>
        </div>
        {artifact.status === 'success' && (
          <span className="rounded border border-emerald-400/30 bg-emerald-400/10 px-2 py-1 text-[10px] font-medium uppercase text-emerald-300">
            Ready
          </span>
        )}
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        <ArtifactLink label="PPTX" path={artifact.deck} endpoint={endpoint} primary />
        <ArtifactLink label="Report" path={artifact.report_md} endpoint={endpoint} />
        <ArtifactLink label="Profile" path={artifact.profile_md} endpoint={endpoint} />
        <ArtifactLink label="JSON" path={artifact.profile_json} endpoint={endpoint} />
      </div>

      {charts.length > 0 && (
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {charts.slice(0, 4).map((chart) => (
            <a
              key={chart.path}
              href={artifactUrl(endpoint, chart.path)}
              target="_blank"
              rel="noreferrer"
              className="group overflow-hidden rounded border border-border bg-surface"
              title={chart.path}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={artifactUrl(endpoint, chart.path)}
                alt={chart.title || 'Generated chart'}
                className="h-40 w-full object-contain p-2"
              />
              <div className="border-t border-border px-3 py-2 text-xs text-muted group-hover:text-primary">
                <span className="truncate">{chart.title || fileName(chart.path)}</span>
              </div>
            </a>
          ))}
        </div>
      )}
    </div>
  )
}

const Artifacts = ({ toolCalls }: { toolCalls?: ToolCall[] }) => {
  const artifacts = toolCalls?.map(parseExcelPptArtifact).filter(Boolean) as
    | ExcelPptArtifact[]
    | undefined

  if (!artifacts || artifacts.length === 0) return null

  return (
    <div className="flex flex-col gap-2">
      {artifacts.map((artifact, index) => (
        <ExcelPptArtifactCard key={`${artifact.deck ?? artifact.report_md}-${index}`} artifact={artifact} />
      ))}
    </div>
  )
}

export default Artifacts
