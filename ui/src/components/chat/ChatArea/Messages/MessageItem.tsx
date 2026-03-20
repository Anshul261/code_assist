import MarkdownRenderer from '@/components/ui/typography/MarkdownRenderer'
import { useStore } from '@/store'
import type { ChatMessage } from '@/types/os'
import Videos from './Multimedia/Videos'
import Images from './Multimedia/Images'
import Audios from './Multimedia/Audios'
import { memo } from 'react'
import AgentThinkingLoader from './AgentThinkingLoader'

interface MessageProps {
  message: ChatMessage
}

export const MessageLabel = ({ label }: { label: string }) => (
  <p className="mb-2 text-xs font-medium uppercase tracking-widest text-muted">{label}</p>
)

const AgentMessage = ({ message }: MessageProps) => {
  const { streamingErrorMessage } = useStore()
  let messageContent
  if (message.streamingError) {
    messageContent = (
      <p className="text-sm text-destructive">
        Something went wrong.{' '}
        {streamingErrorMessage || 'Please try again.'}
      </p>
    )
  } else if (message.content) {
    messageContent = (
      <div className="flex w-full flex-col gap-4">
        <MarkdownRenderer>{message.content}</MarkdownRenderer>
        {message.videos && message.videos.length > 0 && (
          <Videos videos={message.videos} />
        )}
        {message.images && message.images.length > 0 && (
          <Images images={message.images} />
        )}
        {message.audio && message.audio.length > 0 && (
          <Audios audio={message.audio} />
        )}
      </div>
    )
  } else if (message.response_audio) {
    if (!message.response_audio.transcript) {
      messageContent = <AgentThinkingLoader />
    } else {
      messageContent = (
        <div className="flex w-full flex-col gap-4">
          <MarkdownRenderer>
            {message.response_audio.transcript}
          </MarkdownRenderer>
          {message.response_audio.content && message.response_audio && (
            <Audios audio={[message.response_audio]} />
          )}
        </div>
      )
    }
  } else {
    messageContent = <AgentThinkingLoader />
  }

  return (
    <div className="border-l-2 border-border pl-4 text-sm text-primary">
      <MessageLabel label="Assistant" />
      {messageContent}
    </div>
  )
}

const UserMessage = memo(({ message }: MessageProps) => {
  return (
    <div className="flex flex-col items-end">
      <MessageLabel label="You" />
      <div className="max-w-[80%] rounded-xl bg-surface px-4 py-2.5 text-sm text-primary">
        {message.content}
      </div>
    </div>
  )
})

AgentMessage.displayName = 'AgentMessage'
UserMessage.displayName = 'UserMessage'
export { AgentMessage, UserMessage }
