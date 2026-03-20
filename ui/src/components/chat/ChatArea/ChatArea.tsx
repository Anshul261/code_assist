'use client'

import ChatInput from './ChatInput'
import MessageArea from './MessageArea'
import ChatHeader from '@/components/chat-header/ChatHeader'

const ChatArea = () => {
  return (
    <main className="relative flex flex-grow flex-col bg-background">
      <ChatHeader />
      <MessageArea />
      <div className="sticky bottom-0 px-4 pb-3">
        <ChatInput />
      </div>
    </main>
  )
}

export default ChatArea
