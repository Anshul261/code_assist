'use client'

import { useEffect, useState } from 'react'
import { useStore } from '@/store'
import { toast } from 'sonner'
import Icon from '@/components/ui/icon'

interface ModelInfo {
  id: string
  name: string
  provider: string
}

interface WorkspaceConfig {
  knowledge_dirs: string[]
  output_dir: string
}

const PROVIDERS = [
  { id: 'ollama', name: 'Ollama', status: 'active' },
  { id: 'vllm', name: 'vLLM', status: 'coming_soon' },
  { id: 'sglang', name: 'SGLang', status: 'coming_soon' }
]

type Tab = 'model' | 'workspace'

const Settings = () => {
  const { settingsOpen, setSettingsOpen, selectedEndpoint, selectedModel, setSelectedModel } = useStore()

  const [tab, setTab] = useState<Tab>('model')

  // Model tab state
  const [provider, setProvider] = useState('ollama')
  const [host, setHost] = useState('')
  const [models, setModels] = useState<ModelInfo[]>([])
  const [model, setModel] = useState('')
  const [isLoadingModels, setIsLoadingModels] = useState(false)

  // Workspace tab state
  const [workspace, setWorkspace] = useState<WorkspaceConfig>({ knowledge_dirs: [], output_dir: '' })
  const [newKnowledgeDir, setNewKnowledgeDir] = useState('')
  const [newOutputDir, setNewOutputDir] = useState('')
  const [isLoadingWorkspace, setIsLoadingWorkspace] = useState(false)

  const endpoint = selectedEndpoint || 'http://localhost:7777'

  // Init from localStorage
  useEffect(() => {
    setHost(localStorage.getItem('settings_host') || 'http://localhost:11434')
    setProvider(localStorage.getItem('settings_provider') || 'ollama')
  }, [])

  // Fetch models when model tab is open
  useEffect(() => {
    if (settingsOpen && tab === 'model' && provider === 'ollama') {
      fetchModels()
    }
  }, [settingsOpen, tab, provider])

  // Sync selectedModel into local state
  useEffect(() => {
    if (selectedModel) setModel(selectedModel)
  }, [selectedModel])

  // Fetch workspace when workspace tab opens
  useEffect(() => {
    if (settingsOpen && tab === 'workspace') {
      fetchWorkspace()
    }
  }, [settingsOpen, tab])

  const fetchModels = async () => {
    setIsLoadingModels(true)
    try {
      const resp = await fetch(`${endpoint}/api/available-models`)
      if (resp.ok) {
        const data = await resp.json()
        setModels(data.models || [])
        if (data.current) setModel(data.current)
      }
    } catch {
      setModels([])
    } finally {
      setIsLoadingModels(false)
    }
  }

  const fetchWorkspace = async () => {
    setIsLoadingWorkspace(true)
    try {
      const resp = await fetch(`${endpoint}/api/workspace`)
      if (resp.ok) {
        const data = await resp.json()
        setWorkspace(data)
        setNewOutputDir(data.output_dir || '')
      }
    } catch {
      toast.error('Failed to load workspace config')
    } finally {
      setIsLoadingWorkspace(false)
    }
  }

  const handleSaveModel = async () => {
    localStorage.setItem('settings_host', host)
    localStorage.setItem('settings_provider', provider)

    if (model && model !== selectedModel) {
      try {
        const resp = await fetch(`${endpoint}/api/switch-model`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model_id: model })
        })
        if (resp.ok) {
          setSelectedModel(model)
          toast.success(`Model switched to ${model}`)
        } else {
          toast.error('Failed to switch model')
        }
      } catch {
        toast.error('Failed to connect to server')
      }
    }
    setSettingsOpen(false)
  }

  const handleAddKnowledgeDir = async () => {
    const path = newKnowledgeDir.trim()
    if (!path) return
    try {
      const resp = await fetch(`${endpoint}/api/workspace/knowledge`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path })
      })
      const data = await resp.json()
      if (data.error) {
        toast.error(data.error)
      } else {
        setWorkspace(data)
        setNewKnowledgeDir('')
        toast.success('Knowledge dir added')
      }
    } catch {
      toast.error('Failed to add directory')
    }
  }

  const handleRemoveKnowledgeDir = async (dir: string) => {
    try {
      const resp = await fetch(`${endpoint}/api/workspace/knowledge`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: dir })
      })
      const data = await resp.json()
      if (data.error) {
        toast.error(data.error)
      } else {
        setWorkspace(data)
        toast.success('Removed')
      }
    } catch {
      toast.error('Failed to remove directory')
    }
  }

  const handleSetOutputDir = async () => {
    const path = newOutputDir.trim()
    if (!path) return
    try {
      const resp = await fetch(`${endpoint}/api/workspace/output`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path })
      })
      const data = await resp.json()
      if (data.error) {
        toast.error(data.error)
      } else {
        setWorkspace(data)
        toast.success('Output dir updated')
      }
    } catch {
      toast.error('Failed to update output dir')
    }
  }

  if (!settingsOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-md rounded-xl border border-border bg-surface p-6">
        {/* Header */}
        <div className="mb-5 flex items-center justify-between">
          <h2 className="text-base font-medium text-primary">Settings</h2>
          <button
            onClick={() => setSettingsOpen(false)}
            className="rounded p-1 text-muted transition-colors hover:text-primary"
          >
            <Icon type="x" size="xs" />
          </button>
        </div>

        {/* Tabs */}
        <div className="mb-5 flex gap-1 rounded-lg border border-border bg-background p-1">
          {(['model', 'workspace'] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`flex-1 rounded-md py-1.5 text-xs font-medium capitalize transition-colors ${
                tab === t
                  ? 'bg-surface text-primary'
                  : 'text-muted hover:text-primary'
              }`}
            >
              {t}
            </button>
          ))}
        </div>

        {/* Model Tab */}
        {tab === 'model' && (
          <div className="space-y-4">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted">Provider</label>
              <select
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                className="h-9 w-full rounded-lg border border-border bg-background px-3 text-sm text-primary outline-none"
              >
                {PROVIDERS.map((p) => (
                  <option key={p.id} value={p.id} disabled={p.status !== 'active'}>
                    {p.name}{p.status === 'coming_soon' ? ' (coming soon)' : ''}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted">Model</label>
              <select
                value={model}
                onChange={(e) => setModel(e.target.value)}
                disabled={isLoadingModels || models.length === 0}
                className="h-9 w-full rounded-lg border border-border bg-background px-3 text-sm text-primary outline-none disabled:opacity-50"
              >
                {isLoadingModels ? (
                  <option>Loading...</option>
                ) : models.length === 0 ? (
                  <option>No models found</option>
                ) : (
                  models.map((m) => (
                    <option key={m.id} value={m.id}>{m.name}</option>
                  ))
                )}
              </select>
            </div>

            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted">Host</label>
              <input
                type="text"
                value={host}
                onChange={(e) => setHost(e.target.value)}
                className="h-9 w-full rounded-lg border border-border bg-background px-3 text-sm text-primary outline-none"
                placeholder="http://localhost:11434"
              />
            </div>

            <button
              onClick={handleSaveModel}
              className="h-9 w-full rounded-lg bg-primary text-sm font-medium text-background transition-colors hover:bg-primary/80"
            >
              Save Changes
            </button>
          </div>
        )}

        {/* Workspace Tab */}
        {tab === 'workspace' && (
          <div className="space-y-5">
            {isLoadingWorkspace ? (
              <p className="text-center text-xs text-muted">Loading...</p>
            ) : (
              <>
                {/* Knowledge dirs */}
                <div>
                  <label className="mb-2 block text-xs font-medium text-muted">
                    Knowledge Directories <span className="text-muted/60">(agent reads from these)</span>
                  </label>
                  <div className="mb-2 space-y-1">
                    {workspace.knowledge_dirs.length === 0 ? (
                      <p className="text-xs text-muted/60">No directories added</p>
                    ) : (
                      workspace.knowledge_dirs.map((dir) => (
                        <div key={dir} className="flex items-center gap-2 rounded-lg border border-border bg-background px-3 py-2">
                          <span className="flex-1 truncate font-mono text-xs text-primary" title={dir}>{dir}</span>
                          <button
                            onClick={() => handleRemoveKnowledgeDir(dir)}
                            className="shrink-0 text-muted transition-colors hover:text-destructive"
                          >
                            <Icon type="x" size="xs" />
                          </button>
                        </div>
                      ))
                    )}
                  </div>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={newKnowledgeDir}
                      onChange={(e) => setNewKnowledgeDir(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleAddKnowledgeDir()}
                      placeholder="/path/to/folder"
                      className="h-8 flex-1 rounded-lg border border-border bg-background px-3 font-mono text-xs text-primary outline-none placeholder:text-muted/40"
                    />
                    <button
                      onClick={handleAddKnowledgeDir}
                      className="h-8 rounded-lg border border-border bg-background px-3 text-xs text-muted transition-colors hover:text-primary"
                    >
                      Add
                    </button>
                  </div>
                </div>

                {/* Output dir */}
                <div>
                  <label className="mb-2 block text-xs font-medium text-muted">
                    Output Directory <span className="text-muted/60">(agent writes here)</span>
                  </label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={newOutputDir}
                      onChange={(e) => setNewOutputDir(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleSetOutputDir()}
                      placeholder="/path/to/output"
                      className="h-8 flex-1 rounded-lg border border-border bg-background px-3 font-mono text-xs text-primary outline-none placeholder:text-muted/40"
                    />
                    <button
                      onClick={handleSetOutputDir}
                      className="h-8 rounded-lg border border-border bg-background px-3 text-xs text-muted transition-colors hover:text-primary"
                    >
                      Set
                    </button>
                  </div>
                  {workspace.output_dir && (
                    <p className="mt-1.5 truncate font-mono text-xs text-muted/60" title={workspace.output_dir}>
                      Current: {workspace.output_dir}
                    </p>
                  )}
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default Settings
