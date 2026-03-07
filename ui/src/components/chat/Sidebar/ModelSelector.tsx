'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select'
import { useStore } from '@/store'
import { toast } from 'sonner'
import { constructEndpointUrl } from '@/lib/constructEndpointUrl'

interface AvailableModel {
  id: string
  name: string
}

const ModelSelector = () => {
  const { selectedEndpoint, setSelectedModel } = useStore()
  const [models, setModels] = useState<AvailableModel[]>([])
  const [currentModelId, setCurrentModelId] = useState<string>('')

  const fetchModels = useCallback(async () => {
    try {
      const url = constructEndpointUrl(selectedEndpoint)
      const res = await fetch(`${url}/api/available-models`)
      if (!res.ok) return
      const data = await res.json()
      setModels(data.models || [])
      setCurrentModelId(data.current || '')
    } catch {
      // silently fail — models endpoint may not exist
    }
  }, [selectedEndpoint])

  useEffect(() => {
    fetchModels()
  }, [fetchModels])

  const handleSwitch = async (value: string) => {
    const model = models.find((m) => m.id === value)
    if (!model) return

    try {
      const url = constructEndpointUrl(selectedEndpoint)
      const res = await fetch(`${url}/api/switch-model`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_id: model.id })
      })
      if (!res.ok) {
        toast.error('Failed to switch model')
        return
      }
      setCurrentModelId(model.id)
      setSelectedModel(model.name)
      toast.success(`Switched to ${model.name}`)
    } catch {
      toast.error('Failed to switch model')
    }
  }

  if (models.length === 0) return null

  return (
    <div className="flex w-full flex-col items-start gap-2">
      <div className="text-xs font-medium uppercase text-primary">Model</div>
      <Select value={currentModelId} onValueChange={handleSwitch}>
        <SelectTrigger className="h-9 w-full rounded-xl border border-primary/15 bg-primaryAccent text-xs font-medium uppercase">
          <SelectValue placeholder="Select model" />
        </SelectTrigger>
        <SelectContent className="border-none bg-primaryAccent font-dmmono shadow-lg">
          {models.map((model) => (
            <SelectItem
              key={model.id}
              value={model.id}
              className="cursor-pointer"
            >
              <span className="text-xs font-medium uppercase">
                {model.name}
              </span>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

export default ModelSelector
