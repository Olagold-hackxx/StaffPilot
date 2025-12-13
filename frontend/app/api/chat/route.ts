import { GoogleGenerativeAI } from '@google/generative-ai'
import { STAFFPILOT_KNOWLEDGE_BASE } from '@/lib/knowledge-base'

export const maxDuration = 30

export async function POST(req: Request) {
  try {
    // Check if API key is available at runtime
    const apiKey = process.env.GOOGLE_AI_API_KEY
    
    if (!apiKey) {
      console.error('GOOGLE_AI_API_KEY environment variable is not set')
      return Response.json({ 
        error: 'AI service is not configured. Please set GOOGLE_AI_API_KEY environment variable.' 
      }, { status: 500 })
    }

    // Initialize Google AI with the API key
    const genAI = new GoogleGenerativeAI(apiKey)

    // Parse and validate request body
    const { messages } = await req.json()

    if (!messages || !Array.isArray(messages) || messages.length === 0) {
      return Response.json({ 
        error: 'Invalid request: messages array is required' 
      }, { status: 400 })
    }

    // Get the latest user message
    const lastMessage = messages.at(-1)
    if (!lastMessage?.role || lastMessage.role !== 'user') {
      return Response.json({ 
        error: 'No user message found' 
      }, { status: 400 })
    }

    // Create the system prompt with knowledge base
    const systemPrompt = `You are StaffPilot's AI assistant - a knowledgeable, friendly, and professional guide that helps visitors understand our AI employees, pricing, and how to get started.

${STAFFPILOT_KNOWLEDGE_BASE}

Instructions:
- Always be helpful, accurate, and professional
- Use the knowledge base above to answer questions about StaffPilot
- If you don't find specific information, politely suggest contacting our sales team
- Keep responses concise but informative
- Focus on how StaffPilot can solve the user's specific needs
- Use a conversational, approachable tone
- Emphasize cost savings, 24/7 coverage, and flexible plans (Self-Setup, Managed, Dedicated Manager)
- Format your responses using Markdown for better readability (use **bold**, *italic*, lists, code blocks, etc.)
- Use bullet points and numbered lists to organize information clearly
- Use code blocks for technical examples or API endpoints

Remember: You're representing StaffPilot, so be enthusiastic about our AI employees while remaining professional.`

    // Initialize the model
    const model = genAI.getGenerativeModel({ 
      model: 'gemini-2.5-flash',
      generationConfig: {
        temperature: 0.7,
        maxOutputTokens: 1000,
      }
    })

    // Create the full conversation context
    const conversationHistory = messages
      .map((msg: { role: string; content: string }) => 
        `${msg.role === 'user' ? 'User' : 'Assistant'}: ${msg.content}`
      )
      .join('\n')

    const prompt = `${systemPrompt}

Conversation History:
${conversationHistory}

Please respond to the user's latest message based on the StaffPilot knowledge base and conversation context.`

    // Generate response
    console.log('Generating content with Google AI...')
    const result = await model.generateContent(prompt)
    const response = result.response
    const text = response.text()

    console.log('Successfully generated response from Google AI')
    
    // Return the response in the format expected by the AI SDK
    return Response.json({
      id: `msg_${Date.now()}`,
      role: 'assistant',
      content: text,
      createdAt: new Date().toISOString(),
    })

  } catch (error) {
    console.error('Error generating response:', error)
    
    // Provide more specific error messages
    let errorMessage = 'Failed to generate response'
    let statusCode = 500
    
    if (error instanceof Error) {
      // Network errors
      if (error.message.includes('fetch failed') || error.message.includes('network')) {
        errorMessage = 'Network error: Unable to connect to Google AI service. Please check your internet connection.'
        statusCode = 503
      } 
      // API key errors
      else if (error.message.includes('API key') || error.message.includes('authentication')) {
        errorMessage = 'Invalid API key. Please check your Google AI API key configuration.'
        statusCode = 401
      } 
      // Quota errors
      else if (error.message.includes('quota') || error.message.includes('rate limit')) {
        errorMessage = 'API quota exceeded. Please try again later.'
        statusCode = 429
      }
      // Safety/blocked content errors
      else if (error.message.includes('blocked') || error.message.includes('safety')) {
        errorMessage = 'Content was blocked by safety filters. Please rephrase your message.'
        statusCode = 400
      }
      // Generic errors with message
      else {
        errorMessage = `AI service error: ${error.message}`
      }
    }
    
    return new Response(JSON.stringify({ 
      error: errorMessage,
      details: process.env.NODE_ENV === 'development' ? String(error) : undefined
    }), { 
      status: statusCode,
      headers: { 'Content-Type': 'application/json' }
    })
  }
}