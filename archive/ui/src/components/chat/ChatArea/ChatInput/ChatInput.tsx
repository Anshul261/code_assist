'use client'
import { useState } from 'react'
import { toast } from 'sonner'
import { TextArea } from '@/components/ui/textarea'
import { useStore } from '@/store'
import useAIChatStreamHandler from '@/hooks/useAIStreamHandler'
import { useQueryState } from 'nuqs'

const ChatInput = () => {
  const { chatInputRef } = useStore()
  const { handleStreamResponse } = useAIChatStreamHandler()
  const [selectedAgent] = useQueryState('agent')
  const [teamId] = useQueryState('team')
  const [inputMessage, setInputMessage] = useState('')
  const isStreaming = useStore((state) => state.isStreaming)

  const handleSubmit = async () => {
    if (!inputMessage.trim()) return
    const currentMessage = inputMessage
    setInputMessage('')
    try {
      await handleStreamResponse(currentMessage)
    } catch (error) {
      toast.error(
        `Error: ${error instanceof Error ? error.message : String(error)}`
      )
    }
  }

  return (
    <div className="w-full px-4">
      <TextArea
        placeholder="Message Assistant..."
        value={inputMessage}
        onChange={(e) => setInputMessage(e.target.value)}
        onKeyDown={(e) => {
          if (
            e.key === 'Enter' &&
            !e.nativeEvent.isComposing &&
            !e.shiftKey &&
            !isStreaming
          ) {
            e.preventDefault()
            handleSubmit()
          }
        }}
        className="w-full resize-none border-none bg-transparent px-0 py-3 text-sm text-primary placeholder:text-muted focus:border-none focus:outline-none focus:ring-0"
        style={{ maxHeight: '200px' }}
        disabled={!(selectedAgent || teamId)}
        ref={chatInputRef}
      />
    </div>
  )
}

export default ChatInput
