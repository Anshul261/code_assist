'use client'

import { useStore } from '@/store'
import Icon from '@/components/ui/icon'

const ChatHeader = () => {
  const {
    sidebarCollapsed,
    setSidebarCollapsed,
    selectedModel,
    isEndpointActive,
    setSettingsOpen
  } = useStore()

  return (
    <div className="flex h-12 shrink-0 items-center justify-between border-b border-border px-4">
      <div className="flex items-center gap-3">
        {/* Sidebar toggle (visible when collapsed) */}
        {sidebarCollapsed && (
          <button
            onClick={() => setSidebarCollapsed(false)}
            className="rounded p-1 text-muted transition-colors hover:text-primary"
          >
            <Icon type="menu" size="xs" />
          </button>
        )}
        <span className="text-sm font-medium text-primary">Assistant</span>
      </div>

      <div className="flex items-center gap-3">
        {/* Model name */}
        {selectedModel && (
          <span className="font-mono text-xs text-muted">{selectedModel}</span>
        )}

        {/* Connection status dot */}
        <div
          className={`size-2 rounded-full ${isEndpointActive ? 'bg-positive' : 'bg-destructive'}`}
          title={isEndpointActive ? 'Connected' : 'Disconnected'}
        />

        {/* Settings menu */}
        <button
          onClick={() => setSettingsOpen(true)}
          className="rounded p-1 text-muted transition-colors hover:text-primary"
        >
          <Icon type="settings" size="xs" />
        </button>
      </div>
    </div>
  )
}

export default ChatHeader
