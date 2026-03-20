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

const PROVIDERS = [
  { id: 'ollama', name: 'Ollama', status: 'active' },
  { id: 'vllm', name: 'vLLM', status: 'coming_soon' },
  { id: 'sglang', name: 'SGLang', status: 'coming_soon' }
]

const Settings = () => {
  const { settingsOpen, setSettingsOpen, selectedEndpoint, setSelectedEndpoint, selectedModel, setSelectedModel } = useStore()

  const [provider, setProvider] = useState('ollama')
  const [host, setHost] = useState('')
  const [models, setModels] = useState<ModelInfo[]>([])
  const [model, setModel] = useState('')
  const [isLoadingModels, setIsLoadingModels] = useState(false)

  // Initialize from localStorage on mount
  useEffect(() => {
    const savedHost = localStorage.getItem('settings_host') || 'http://localhost:11434'
    const savedProvider = localStorage.getItem('settings_provider') || 'ollama'
    setHost(savedHost)
    setProvider(savedProvider)
  }, [])

  // Fetch models when settings open
  useEffect(() => {
    if (settingsOpen && provider === 'ollama') {
      fetchModels()
    }
  }, [settingsOpen, provider])

  // Set current model
  useEffect(() => {
    if (selectedModel) {
      setModel(selectedModel)
    }
  }, [selectedModel])

  const fetchModels = async () => {
    setIsLoadingModels(true)
    try {
      const endpoint = selectedEndpoint || 'http://localhost:7777'
      const resp = await fetch(`${endpoint}/api/available-models`)
      if (resp.ok) {
        const data = await resp.json()
        setModels(data.models || [])
        if (data.current) {
          setModel(data.current)
        }
      }
    } catch {
      setModels([])
    } finally {
      setIsLoadingModels(false)
    }
  }

  const handleSave = async () => {
    // Save to localStorage
    localStorage.setItem('settings_host', host)
    localStorage.setItem('settings_provider', provider)

    // Switch model if changed
    if (model && model !== selectedModel) {
      try {
        const endpoint = selectedEndpoint || 'http://localhost:7777'
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

  if (!settingsOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-md rounded-xl border border-border bg-surface p-6">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <h2 className="text-base font-medium text-primary">Settings</h2>
          <button
            onClick={() => setSettingsOpen(false)}
            className="rounded p-1 text-muted transition-colors hover:text-primary"
          >
            <Icon type="x" size="xs" />
          </button>
        </div>

        {/* Provider */}
        <div className="mb-4">
          <label className="mb-1.5 block text-xs font-medium text-muted">
            Provider
          </label>
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            className="h-9 w-full rounded-lg border border-border bg-background px-3 text-sm text-primary outline-none"
          >
            {PROVIDERS.map((p) => (
              <option
                key={p.id}
                value={p.id}
                disabled={p.status !== 'active'}
              >
                {p.name}{p.status === 'coming_soon' ? ' (coming soon)' : ''}
              </option>
            ))}
          </select>
        </div>

        {/* Model */}
        <div className="mb-4">
          <label className="mb-1.5 block text-xs font-medium text-muted">
            Model
          </label>
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
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))
            )}
          </select>
        </div>

        {/* Host */}
        <div className="mb-6">
          <label className="mb-1.5 block text-xs font-medium text-muted">
            Host
          </label>
          <input
            type="text"
            value={host}
            onChange={(e) => setHost(e.target.value)}
            className="h-9 w-full rounded-lg border border-border bg-background px-3 text-sm text-primary outline-none"
            placeholder="http://localhost:11434"
          />
        </div>

        {/* Save */}
        <button
          onClick={handleSave}
          className="h-9 w-full rounded-lg bg-primary text-sm font-medium text-background transition-colors hover:bg-primary/80"
        >
          Save Changes
        </button>
      </div>
    </div>
  )
}

export default Settings
