"use client"

import { useEffect, useState } from 'react'
import { usePathname } from "next/navigation"
import { X, Send, MessageCircle, Sparkles, Bot, User, Loader2 } from 'lucide-react'
import Markdown from 'react-markdown'
import { useChatbot } from "@/components/chatbot-context"

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  createdAt?: string
}

export function ChatbotWidget() {
  const { isOpen, closeChatbot, openChatbot } = useChatbot()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const pathname = usePathname()

  // Close chat whenever the route changes (e.g. user clicks to another page)
  // useEffect(() => {
  //   closeChatbot()
  // }, [pathname, closeChatbot])

  // Add welcome message if no messages exist
  const displayMessages = messages.length === 0 ? [
    {
      id: "welcome",
      role: "assistant" as const,
      content:
        "👋 Hi! I'm StaffPilot's AI assistant. I can help you learn about our AI employees, pricing, and how to hire your first AI team member. What would you like to know?",
    },
  ] : messages

  const sendMessage = async (text: string) => {
    if (!text.trim() || isLoading) return

    // Add user message
    const userMessage: Message = {
      id: `user_${Date.now()}`,
      role: 'user',
      content: text,
      createdAt: new Date().toISOString(),
    }
    
    setMessages(prev => [...prev, userMessage])
    setIsLoading(true)

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          messages: [...messages, userMessage],
        }),
      })

      if (!response.ok) {
        // Try to parse error response
        let errorData: { error?: string; details?: string } = {}
        try {
          errorData = await response.json()
        } catch {
          // If JSON parsing fails, use default error
          errorData = { error: 'Failed to get response' }
        }
        
        const errorMsg = errorData.error || 'Failed to get response'
        const errorDetails = errorData.details ? `\n\nDetails: ${errorData.details}` : ''
        throw new Error(`${errorMsg}${errorDetails}`)
      }

      const data = await response.json()
      
      // Add assistant message
      const assistantMessage: Message = {
        id: data.id || `assistant_${Date.now()}`,
        role: 'assistant',
        content: data.content,
        createdAt: data.createdAt || new Date().toISOString(),
      }
      
      setMessages(prev => [...prev, assistantMessage])
    } catch (error) {
      console.error('Error sending message:', error)
      // Add error message
      const errorMessage: Message = {
        id: `error_${Date.now()}`,
        role: 'assistant',
        content: `${error instanceof Error ? error.message : 'An unexpected error occurred'}. Please try again.`,
        createdAt: new Date().toISOString(),
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (input.trim()) {
      sendMessage(input)
      setInput('')
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e as any)
    }
  }

  return (
    <>
      {/* Floating Chat Button */}
      {!isOpen && (
        <button 
          onClick={(e) => {
            e.preventDefault()
            e.stopPropagation()
            openChatbot()
          }} 
          className="fixed bottom-6 right-4 sm:right-6 z-50 group cursor-pointer outline-none focus:outline-none" 
          aria-label="Open chat"
          type="button"
        >
          <div className="relative">
            {/* Animated gradient ring */}
            <div className="absolute inset-0 rounded-full bg-gradient-to-r from-ai-primary via-ai-secondary to-ai-accent animate-spin-slow blur-md opacity-75 pointer-events-none" />

            {/* Button */}
            <div className="relative flex ai-gradient items-center justify-center w-16 h-16 rounded-full bg-gradient-to-br from-ai-primary to-ai-secondary shadow-lg shadow-ai-primary/50 transition-transform group-hover:scale-110">
              <MessageCircle className="w-7 h-7 text-white pointer-events-none" />
              <Sparkles className="absolute -top-1 -right-1 w-5 h-5 text-ai-accent animate-pulse pointer-events-none" />
            </div>
          </div>
        </button>
      )}

      {/* Chat Window */}
      {isOpen && (
        <div className="fixed bottom-6 right-4 w-[calc(100vw-2rem)] sm:left-auto sm:right-6 sm:w-[380px] min-h-[65vh] max-h-[80vh] sm:max-h-[85vh] z-50 flex flex-col bg-white/95 dark:bg-gray-900/95 backdrop-blur-xl rounded-2xl shadow-2xl shadow-ai-primary/20 border border-ai-primary/20 overflow-hidden">
          {/* Header */}
          <div className="relative flex items-center justify-between p-4 bg-gradient-to-r from-ai-primary via-ai-secondary to-ai-accent">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center">
                <Sparkles className="w-5 h-5 text-white" />
              </div>
              <div>
                <h3 className="font-semibold text-white">AI Assistant</h3>
                <p className="text-xs text-white/80">Always here to help</p>
              </div>
            </div>
            <button
              onClick={closeChatbot}
              className="w-8 h-8 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center hover:bg-white/30 transition-colors"
              aria-label="Close chat"
            >
              <X className="w-4 h-4 text-white" />
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {displayMessages.map((message: any) => (
              <div key={message.id} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[80%] rounded-2xl px-4 py-2.5 ${
                    message.role === "user"
                      ? "bg-gradient-to-br from-ai-primary border border-teal-400 to-ai-secondary text-white"
                      : "bg-gradient-to-br from-teal-50 to-cyan-50 dark:from-gray-800 dark:to-gray-700 text-gray-800 dark:text-gray-100 border border-ai-primary/10 dark:border-gray-600"
                  }`}
                >
                  <div className="flex items-start space-x-2">
                    {message.role === 'assistant' && (
                      <Bot className="h-4 w-4 mt-0.5 flex-shrink-0" />
                    )}
                    {message.role === 'user' && (
                      <User className="h-4 w-4 mt-0.5 flex-shrink-0" />
                    )}
                    <div className="text-sm leading-relaxed whitespace-pre-wrap">
                      <Markdown>{message.parts?.map((part: any, partIndex: number) => {
                        if (part.type === 'text') {
                          return <span key={`text-${partIndex}`}>{part.text}</span>
                        }
                        return <span key={`content-${partIndex}`}>{part.text || part.content}</span>
                      }) || message.content}</Markdown> 
                    </div>
                  </div>
                </div>
              </div>
            ))}
            
            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-gradient-to-br from-teal-50 to-cyan-50 dark:from-gray-800 dark:to-gray-700 text-gray-800 dark:text-gray-100 border border-ai-primary/10 dark:border-gray-600 rounded-2xl px-4 py-2.5 max-w-[80%]">
                  <div className="flex items-center space-x-2">
                    <Bot className="h-4 w-4" />
                    <div className="flex items-center space-x-1">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      <span className="text-sm">Thinking...</span>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Input */}
          <div className="p-4 border-t border-ai-primary/10 dark:border-gray-600 bg-gradient-to-br from-teal-50/50 to-cyan-50/50 dark:from-gray-800/50 dark:to-gray-700/50">
            <form onSubmit={handleSubmit} className="flex items-end gap-2">
              <div className="flex-1 relative">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyPress}
                  placeholder="Ask me anything about StaffPilot ..."
                  rows={1}
                  className="w-full px-4 py-2 pr-12  rounded-md border border-ai-primary/20 dark:border-gray-600 bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm focus:outline-none focus:ring-2 focus:ring-ai-primary/50 resize-none text-sm text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 leading-tight"
                  disabled={isLoading}
                />
              </div>
              <button
                type="submit"
                disabled={isLoading || !input.trim()}
                className="w-[35px] h-[35px] self-start ai-gradient rounded-md bg-gradient-to-br from-ai-primary to-ai-secondary text-white flex items-center justify-center hover:shadow-lg hover:shadow-ai-primary/50 transition-all disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:shadow-none"
                aria-label="Send message"
              >
                <Send className="w-5 h-5" />
              </button>
            </form>
          </div>
        </div>
      )}
    </>
  )
}
