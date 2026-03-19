# Local AI Code Assistant - Implementation Plan

## Overview

A local-first AI coding assistant with:
- **Backend**: AgentOS server with Ollama, SQLite for sessions, context compression
- **Frontend**: Notion-style minimal web UI with IBM Plex fonts, Shiki syntax highlighting

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (Next.js 15)                 │
│  ┌────────────┬──────────────────────────────────────────┐  │
│  │            │  [☰]  Assistant │ qwen3.5:9b │ ● │ ⋮   │  │
│  │  Sidebar   ├──────────────────────────────────────────┤  │
│  │            │                                           │  │
│  │ + New Chat │           Chat Messages Area              │  │
│  │            │                                           │  │
│  │ ○ Chat 1   │           (or Welcome Message)            │  │
│  │ ● Chat 2   │                                           │  │
│  │   Chat 3   │                                           │  │
│  │            │                                           │  │
│  │            ├──────────────────────────────────────────┤  │
│  │ ⚙ Settings │  [ Message Assistant...               ]  │  │
│  └────────────┴──────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP/SSE (port 7777)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                     Backend (AgentOS)                       │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              AgentOS Server                          │   │
│  │                                                       │   │
│  │  - Ollama Model (qwen3.5:9b, llama3.1, etc.)        │   │
│  │  - FileToolkit (read, write, edit, glob, grep)      │   │
│  │  - BashToolkit (shell commands)                     │   │
│  │  - DuckDuckGoTools (web search)                      │   │
│  │  - Context Compression                               │   │
│  │  - Session History (10 runs)                         │   │
│  │                                                       │   │
│  │  ┌─────────────────────────────────────────────┐    │   │
│  │  │  SQLite Database (agent_os.db)               │    │   │
│  │  │  - Sessions table                            │    │   │
│  │  │  - Runs table                                │    │   │
│  │  │  - Messages table                             │    │   │
│  │  └─────────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Provider Abstraction                                │   │
│  │                                                       │   │
│  │  Supported:                                          │   │
│  │  - Ollama (active)                                   │   │
│  │  - vLLM (coming soon)                                │   │
│  │  - SGLang (coming soon)                              │   │
│  │                                                       │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Part 1: Backend - AgentOS Server

### File: `agent_os_server.py`

**Core Features:**
- Wrap FileToolkit + BashToolkit as agent tools
- DuckDuckGo search tools (web search + news)
- Configure Ollama model with dynamic switching
- SQLite database for session persistence
- Context compression (compress after 5 tool calls)
- Chat history (10 previous runs)
- REST API on port `7777`
- CORS enabled for localhost development

**Provider Abstraction:**
```python
PROVIDERS = {
    "ollama": {
        "name": "Ollama",
        "status": "active",
        "models_endpoint": "{host}/api/tags",
    },
    "vllm": {
        "name": "vLLM",
        "status": "coming_soon",
        "models_endpoint": "{host}/v1/models",
    },
    "sglang": {
        "name": "SGLang",
        "status": "coming_soon",
        "models_endpoint": "{host}/v1/models",
    },
}
```

**API Endpoints:**
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/agents/assistant/runs` | POST | Run agent with message (streaming supported) |
| `/providers` | GET | List available providers |
| `/providers/{provider}/models` | GET | List models for provider |
| `/sessions` | GET | List all sessions |
| `/sessions/{id}` | GET/DELETE | Get or delete session |

**Agent Configuration:**
```python
agent = Agent(
    name="Assistant",
    model=Ollama(id="qwen3.5:9b"),
    tools=[
        FileToolkit(),      # File operations (read, write, edit, glob, grep)
        BashToolkit(),      # Shell commands
        DuckDuckGoTools(),  # Web search and news
    ],
    instructions=CODE_ASSISTANT_INSTRUCTIONS,
    markdown=True,
    compress_tool_results=True,
    compress_tool_results_limit=5,
    add_history_to_context=True,
    num_history_runs=10,
    read_chat_history=True,
)
```

**DuckDuckGo Tools:**
```python
from agno.tools.duckduckgo import DuckDuckGoTools

# Available functions:
# - duckduckgo_search: Search the web for information
# - duckduckgo_news: Search for recent news

DuckDuckGoTools(
    enable_search=True,  # Enable web search
    enable_news=True,    # Enable news search
)
```

**Agent Instructions:**
```
You help with coding tasks - reading, writing, editing files and running commands.

## Capabilities
- Read any file in the project
- Write new files or edit existing ones
- Search files by name pattern (glob) or content (grep)
- Run shell commands
- Search the web for information using DuckDuckGo

## Best Practices
- Always read a file before editing it
- Use glob to find files: `**/*.py`, `**/*.js`
- Use grep to search content
- Use DuckDuckGo search when you need up-to-date information or answers from the web
- Explain what you're doing
```

---

## Part 2: Frontend - UI Design

### Color Palette

| Element | Color | Usage |
|---------|-------|-------|
| Background | `#000000` | Main background (pure black) |
| Surface | `#0A0A0A` | Sidebar, cards, modals (near black) |
| Border | `rgba(255,255,255,0.06)` | Subtle borders |
| Text Primary | `#FFFFFF` | Main text (pure white) |
| Text Secondary | `#6B6B6B` | Muted text, placeholders |
| Hover | `rgba(255,255,255,0.04)` | Hover states |

### Typography

| Element | Font | Size |
|---------|------|------|
| Body | IBM Plex Sans | 14px |
| Code | IBM Plex Mono | 13px |
| Headings | IBM Plex Sans | 16px (medium) |

**Font Loading:**
```typescript
import { IBM_Plex_Sans, IBM_Plex_Mono } from 'next/font/google'

const ibmPlexSans = IBM_Plex_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-sans',
})

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ['latin'],
  weight: ['400'],
  variable: '--font-mono',
})
```

### Tailwind Configuration

```typescript
// tailwind.config.ts
colors: {
  background: '#000000',
  surface: '#0A0A0A',
  border: 'rgba(255,255,255,0.06)',
  text: {
    primary: '#FFFFFF',
    secondary: '#6B6B6B',
  },
  hover: 'rgba(255,255,255,0.04)',
}
fontFamily: {
  sans: ['IBM Plex Sans', 'sans-serif'],
  mono: ['IBM Plex Mono', 'monospace'],
}
```

### Layout Structure

```
┌────────────┬─────────────────────────────────────────────────┐
│            │  [☰]  Assistant    │ qwen3.5:9b │ ● │ [...] │  ← Chat Header
│  Sidebar   ├─────────────────────────────────────────────────┤
│            │                                                  │
│ + New Chat │           Chat Messages Area                     │
│            │                                                  │
│ ○ Mar 19   │                                                  │
│ ● Mar 19   │           (or Welcome Message)                  │
│   Mar 18   │                                                  │
│            │                                                  │
│            ├─────────────────────────────────────────────────┤
│ ⚙ Settings │  [ Message Assistant...                    ]  │  ← Input
└────────────┴─────────────────────────────────────────────────┘
```

---

## Part 3: Sidebar Component

### Sidebar Structure

**Expanded State (280px):**
```
┌─────────────────────┐
│ ≡  Assistant        │ ← Header with collapse toggle
├─────────────────────┤
│ + New Chat          │ ← Top: Always visible
├─────────────────────┤
│ ○ Mar 19, 14:30    │ ← Session items (timestamp naming)
│ ● Mar 19, 14:25    │ ← Active session (dot indicator)
│   Mar 18, 16:45    │
├─────────────────────┤
│                     │ ← Empty space
│                     │
│                     │
├─────────────────────┤
│ ⚙ Settings         │ ← Bottom
│ [Collapse ←]        │
└─────────────────────┘
```

**Collapsed State (64px):**
```
┌─────────┐
│    ≡    │ ← Toggle to expand
├─────────┤
│    +    │
├─────────┤
│    ○    │ ← Session count badge
│   [3]   │
├─────────┤
│         │
│         │
│         │
├─────────┤
│    ⚙    │
└─────────┘
```

**Session Count Badge:** Shows total number of sessions when collapsed

### Session Naming

Format: `MMM D, H:MM` (e.g., "Mar 19, 14:30")
- Auto-generated from creation timestamp
- First 20 characters displayed

### Animation

- Transition: Framer Motion `spring` (damping: 25, stiffness: 200)
- Duration: ~300ms
- Easing: Smooth slide in/out

---

## Part 4: Chat Header Bar

```
┌────────────────────────────────────────────────────────────────┐
│ [☰]  Assistant        │  qwen3.5:9b  │  ● Connected  │  ⋮   │
└────────────────────────────────────────────────────────────────┘
   │          │              │              │         │
   │          │              │              │         └── Settings menu
   │          │              │              └── Status dot (green/red)
   │          │              └── Model name (from settings)
   │          └── Agent name (fixed: "Assistant")
   └── Toggle sidebar
```

**Status Dot:**
- Green (#22C55E): Connected to AgentOS
- Red (#E53935): Disconnected/Error

---

## Part 5: Settings Modal

Simple overlay modal with the following fields:

```
┌─────────────────────────────────────┐
│  Settings                       ✕   │
├─────────────────────────────────────┤
│                                     │
│  Provider                          │
│  ┌───────────────────────────────┐  │
│  │ Ollama                      ▼ │  │
│  │ vLLM (coming soon)            │  │
│  │ SGLang (coming soon)          │  │
│  └───────────────────────────────┘  │
│                                     │
│  Model                             │
│  ┌───────────────────────────────┐  │
│  │ qwen3.5:9b                  ▼ │  │
│  └───────────────────────────────┘  │
│                                     │
│  Host                              │
│  ┌───────────────────────────────┐  │
│  │ http://localhost:11434        │  │
│  └───────────────────────────────┘  │
│                                     │
│           [ Save Changes ]           │
│                                     │
└─────────────────────────────────────┘
```

**Behavior:**
- vLLM/SGLang shown but disabled with "(coming soon)" label
- Save triggers app state refresh
- Settings persist to localStorage

---

## Part 6: Chat Messages

### User Message
```
┌─────────────────────────────────────────┐
│ Message content here                     │
└─────────────────────────────────────────┘
```
- No bubble, no background
- White text (#FFFFFF), 14px
- Left-aligned, full width
- Slight top margin between messages

### Assistant Message
```
┌─────────────────────────────────────────┐
│ Message content with **markdown**        │
│ support and code blocks:                │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ const x = 1;                        │ │  ← Shiki syntax highlighting
│ │ console.log(x);                     │ │  ← One Dark theme
│ └─────────────────────────────────────┘ │
└─────────────────────────────────────────┘
```
- Full markdown rendering
- Code blocks with Shiki (One Dark theme)
- Inline code with gray background

### Code Block Styling
- Background: `#1e1e1e` (VS Code dark)
- Border: `rgba(255,255,255,0.06)`
- Border radius: 8px
- Padding: 16px
- Font: IBM Plex Mono, 13px
- Copy button on hover

---

## Part 7: Welcome Message

Minimal, centered:

```
┌────────────────────────────────────────┐
│                                        │
│                                        │
│              Ask me anything           │
│                                        │
│                                        │
└────────────────────────────────────────┘
```

- Text color: `#6B6B6B` (text-secondary)
- Font size: 14px
- No icons, no cards, no suggestions

---

## Part 8: Chat Input

```
┌─────────────────────────────────────────────────────────────────┐
│ Message Assistant...                                             │
└─────────────────────────────────────────────────────────────────┘
```

- Border-top: `rgba(255,255,255,0.06)`
- Background: transparent
- Placeholder: "Message Assistant..." in `#6B6B6B`
- Text: `#FFFFFF`, 14px
- Auto-resize height (max 200px)
- Enter to send, Shift+Enter for newline

---

## Part 9: Dependencies

### Backend (pyproject.toml)
```
agno>=2.0.0
agno[sqlite]       # SQLite support
duckduckgo-search  # DuckDuckGo web search
pypdf              # PDF reading
```

### Frontend (package.json)
```json
{
  "dependencies": {
    "@shikijs/react": "latest",
    "framer-motion": "^11.0.0",
    "lucide-react": "latest",
    "next": "^15.0.0",
    "react": "^18.0.0",
    "tailwindcss": "^3.4.0"
  }
}
```

---

## Part 10: File Structure

```
/home/anshul/projects/code_assist/
├── agent.py                    # Original CLI agent (keep for reference)
├── agent_os_server.py          # NEW: AgentOS backend
├── pyproject.toml              # Updated with agno deps
├── uv.lock                     # Lock file
│
└── ui/                         # Frontend (Next.js 15)
    ├── package.json
    ├── tailwind.config.ts     # UPDATED: New color palette
    ├── src/
    │   ├── app/
    │   │   ├── globals.css    # UPDATED: CSS variables
    │   │   ├── layout.tsx     # UPDATED: IBM Plex fonts
    │   │   └── page.tsx
    │   │
    │   ├── components/
    │   │   ├── chat/
    │   │   │   ├── ChatArea/
    │   │   │   │   ├── ChatArea.tsx
    │   │   │   │   └── ChatInput.tsx    # UPDATED: Minimal styling
    │   │   │   └── Messages/
    │   │   │       ├── Messages.tsx
    │   │   │       ├── MessageItem.tsx  # UPDATED: Minimal styling
    │   │   │       └── ChatBlankState.tsx # UPDATED: Welcome msg
    │   │   │
    │   │   ├── sidebar/
    │   │   │   ├── Sidebar.tsx        # UPDATED: Animated expand/collapse
    │   │   │   ├── SessionList.tsx     # UPDATED: Session management
    │   │   │   └── Settings.tsx        # NEW: Settings modal
    │   │   │
    │   │   ├── chat-header/
    │   │   │   └── ChatHeader.tsx      # NEW: Header bar above chat
    │   │   │
    │   │   └── ui/                     # shadcn/ui components
    │   │       ├── button.tsx
    │   │       ├── dialog.tsx
    │   │       ├── select.tsx
    │   │       ├── textarea.tsx
    │   │       └── ...
    │   │
    │   ├── hooks/
    │   │   ├── useProviders.ts         # NEW: Fetch providers/models
    │   │   ├── useAIStreamHandler.tsx   # UPDATED: AgentOS streaming
    │   │   └── useSettings.ts           # NEW: Settings state
    │   │
    │   ├── lib/
    │   │   ├── api/
    │   │   │   ├── routes.ts           # UPDATED: AgentOS endpoints
    │   │   │   └── os.ts
    │   │   └── utils.ts
    │   │
    │   ├── store.ts                    # Zustand state
    │   └── types/
    │       └── os.ts                   # AgentOS types
    │
    └── public/
```

---

## Part 11: Implementation Order

### Phase 1: Backend
1. Create `agent_os_server.py`
2. Test with curl
3. Verify sessions persist

### Phase 2: Frontend Setup
1. Install Shiki for syntax highlighting
2. Update Tailwind config (colors, fonts)
3. Update fonts in layout.tsx

### Phase 3: Sidebar
1. Implement expand/collapse animation
2. Add New Chat button at top
3. Session list with timestamp naming
4. Session count badge when collapsed
5. Settings button at bottom

### Phase 4: Chat Header
1. Create ChatHeader component
2. Add sidebar toggle
3. Show model name and connection status

### Phase 5: Chat Messages
1. Minimal message styling (no bubbles)
2. Welcome message
3. Markdown + Shiki code highlighting

### Phase 6: Chat Input
1. Minimal input styling
2. Enter to send behavior

### Phase 7: Settings Modal
1. Provider selector (Ollama active, others disabled)
2. Model selector (fetch from API)
3. Host URL input
4. Save to localStorage

### Phase 8: Integration
1. Connect UI to AgentOS API
2. Test streaming
3. Test session switching
4. Test settings persistence

---

## Part 12: Testing Checklist

- [ ] Agent memory (conversation continuity)
- [ ] Context compression (verbose tool output)
- [ ] File operations (read/write/edit)
- [ ] Bash commands
- [ ] DuckDuckGo web search
- [ ] Sidebar expand/collapse animation
- [ ] Session switching
- [ ] Settings modal opens/saves
- [ ] Model refresh on settings change
- [ ] Markdown rendering
- [ ] Code syntax highlighting
- [ ] Streaming responses

---

## Configuration Defaults

| Setting | Default |
|---------|---------|
| Ollama Host | `http://localhost:11434` |
| Default Model | `qwen3.5:9b` |
| Default Provider | `ollama` |
| Max Sessions in Sidebar | 20 (most recent) |
| Session Naming | Timestamp (MMM D, H:MM) |

---

## Environment Variables

### Backend (.env)
```
OLLAMA_HOST=http://localhost:11434
MODEL=qwen3.5:9b
```

### Frontend (.env.local)
```
NEXT_PUBLIC_AGNO_OS_URL=http://localhost:7777
```

---

## Notes

- Provider abstraction ready for future vLLM and SGLang integration
- Model list fetched dynamically from provider's API
- Settings persist to localStorage (lost on browser clear)
- AgentOS handles session persistence in SQLite
