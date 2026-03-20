'use client'
import Sidebar from '@/components/chat/Sidebar/Sidebar'
import { ChatArea } from '@/components/chat/ChatArea'
import Settings from '@/components/chat/Sidebar/Settings'
import { Suspense } from 'react'

export default function Home() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <div className="flex h-screen bg-background">
        <Sidebar />
        <ChatArea />
        <Settings />
      </div>
    </Suspense>
  )
}
