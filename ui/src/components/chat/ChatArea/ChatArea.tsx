'use client'

import ChatInput from './ChatInput'
import MessageArea from './MessageArea'
import ChatHeader from '@/components/chat-header/ChatHeader'

const ChatArea = () => {
  return (
    <main className="chat-grid-bg relative flex flex-grow flex-col bg-background">
      <ChatHeader />
      <MessageArea />
      <div className="sticky bottom-0 bg-background/80 px-4 pb-4 pt-2 backdrop-blur-sm">
        <div className="mx-auto max-w-4xl rounded-xl border border-border bg-surface shadow-lg shadow-black/40">
          <ChatInput />
        </div>
      </div>
    </main>
  )
}

export default ChatArea
