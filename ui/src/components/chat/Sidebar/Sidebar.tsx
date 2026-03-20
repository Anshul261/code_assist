'use client'
import { Button } from '@/components/ui/button'
import useChatActions from '@/hooks/useChatActions'
import { useStore } from '@/store'
import { motion } from 'framer-motion'
import { useEffect, useState } from 'react'
import { useQueryState } from 'nuqs'
import Sessions from './Sessions'
import Icon from '@/components/ui/icon'

const Sidebar = () => {
  const {
    sidebarCollapsed,
    setSidebarCollapsed,
    setSettingsOpen,
    messages,
    selectedEndpoint,
    hydrated,
    isEndpointActive,
    mode,
    sessionsData
  } = useStore()
  const { clearChat, focusChatInput, initialize } = useChatActions()
  const [isMounted, setIsMounted] = useState(false)
  const [agentId] = useQueryState('agent')
  const [teamId] = useQueryState('team')

  useEffect(() => {
    setIsMounted(true)
    if (hydrated) initialize()
  }, [selectedEndpoint, initialize, hydrated, mode])

  const handleNewChat = () => {
    clearChat()
    focusChatInput()
  }

  const sessionCount = sessionsData?.length ?? 0

  return (
    <motion.aside
      className="relative flex h-screen shrink-0 grow-0 flex-col overflow-hidden bg-surface"
      initial={{ width: '17.5rem' }}
      animate={{ width: sidebarCollapsed ? '4rem' : '17.5rem' }}
      transition={{ type: 'spring', damping: 25, stiffness: 200 }}
    >
      {/* Expanded content */}
      <motion.div
        className="flex h-full flex-col px-3 py-3"
        animate={{
          opacity: sidebarCollapsed ? 0 : 1,
          x: sidebarCollapsed ? -20 : 0
        }}
        transition={{ duration: 0.2 }}
        style={{ pointerEvents: sidebarCollapsed ? 'none' : 'auto' }}
      >
        {/* Header */}
        <div className="mb-4 flex items-center justify-between">
          <span className="text-sm font-medium text-primary">Assistant</span>
          <button
            onClick={() => setSidebarCollapsed(true)}
            className="rounded p-1 text-muted transition-colors hover:text-primary"
          >
            <Icon type="sheet" size="xs" />
          </button>
        </div>

        {/* New Chat */}
        <Button
          onClick={handleNewChat}
          disabled={messages.length === 0}
          size="lg"
          className="mb-4 h-9 w-full rounded-lg border border-border bg-transparent text-xs font-medium text-primary hover:bg-hover"
        >
          <Icon type="plus-icon" size="xs" className="mr-1.5" />
          New Chat
        </Button>

        {/* Sessions */}
        <div className="min-h-0 flex-1 overflow-hidden">
          {isMounted && isEndpointActive && <Sessions />}
        </div>

        {/* Bottom: Settings */}
        <div className="border-t border-border pt-3">
          <button
            onClick={() => setSettingsOpen(true)}
            className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-sm text-muted transition-colors hover:bg-hover hover:text-primary"
          >
            <Icon type="settings" size="xs" />
            Settings
          </button>
        </div>
      </motion.div>

      {/* Collapsed content */}
      {sidebarCollapsed && (
        <motion.div
          className="flex h-full flex-col items-center py-3"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.1, duration: 0.2 }}
        >
          {/* Expand toggle */}
          <button
            onClick={() => setSidebarCollapsed(false)}
            className="mb-4 rounded p-1.5 text-muted transition-colors hover:text-primary"
          >
            <Icon type="sheet" size="xs" className="rotate-180" />
          </button>

          {/* New Chat */}
          <button
            onClick={handleNewChat}
            disabled={messages.length === 0}
            className="mb-4 rounded-lg p-2 text-muted transition-colors hover:bg-hover hover:text-primary disabled:opacity-30"
          >
            <Icon type="plus-icon" size="xs" />
          </button>

          {/* Session count badge */}
          {sessionCount > 0 && (
            <div className="mb-2 flex size-7 items-center justify-center rounded-full bg-hover text-xs text-muted">
              {sessionCount}
            </div>
          )}

          {/* Spacer */}
          <div className="flex-1" />

          {/* Settings */}
          <button
            onClick={() => setSettingsOpen(true)}
            className="rounded p-1.5 text-muted transition-colors hover:text-primary"
          >
            <Icon type="settings" size="xs" />
          </button>
        </motion.div>
      )}
    </motion.aside>
  )
}

export default Sidebar
