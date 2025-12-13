"use client"

import { useEffect, useState, useCallback, useRef } from "react"
import { useParams, useRouter } from "next/navigation"
import ReactMarkdown from 'react-markdown';
import { cn } from "@/lib/utils"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { ScrollArea } from "@/components/ui/scroll-area"
import { apiClient } from "@/lib/api"
import { useToast } from "@/components/ui/use-toast"
import { 
  ArrowLeft, CheckCircle2, Loader2, DollarSign, Calendar, 
  Target, ChevronDown, ChevronRight, Clock, Play, Send,
  MessageSquare, RefreshCw, Sparkles, Image as ImageIcon, Video, Wand2,
  Bot, ThumbsUp, ThumbsDown, Download
} from "lucide-react"

interface StepResult {
  content?: string
  image_urls?: string[]
  video_urls?: string[]
  research_data?: any
  executed_at?: string
  error?: string
}

interface PlanStep {
  id: string
  title: string
  description: string
  actions: string[]
  time_estimate?: string
  status: "pending" | "in_progress" | "completed" | "failed"
  task_type?: string
  result?: StepResult
  execution_id?: string
}

interface AdSet {
  name: string
  audience_type: string
  description: string
  budget_percentage: number
}

interface CampaignPlan {
  overview: string
  steps: PlanStep[]
  recommended_ad_sets: AdSet[]
  priority_metrics: string[]
  research_insights?: string[]
}

interface Campaign {
  id: string
  name: string
  description?: string
  objective_type?: string
  campaign_type?: string
  channels: string[]
  status: string
  total_budget?: number
  currency?: string
  start_date?: string
  end_date?: string
  plan?: CampaignPlan
  product_brief?: string
  creative_preference?: string
  target_audience?: Record<string, any>
  metrics?: Record<string, any>
  created_at: string
}

interface ChatMessage {
  id: string
  role: "user" | "assistant"
  content: string
  timestamp: Date
  isPinned?: boolean
}

export default function CampaignWorkspacePage() {
  const params = useParams()
  const router = useRouter()
  const { toast } = useToast()
  
  const [campaign, setCampaign] = useState<Campaign | null>(null)
  const [loading, setLoading] = useState(true)
  const [expandedSteps, setExpandedSteps] = useState<Set<string>>(new Set())
  const [updatingStep, setUpdatingStep] = useState<string | null>(null)
  const [regeneratingPlan, setRegeneratingPlan] = useState(false)
  
  // Chat state
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [chatInput, setChatInput] = useState("")
  const [sendingMessage, setSendingMessage] = useState(false)
  
  // Selected step for main canvas
  const [selectedStep, setSelectedStep] = useState<PlanStep | null>(null)
  
  // Step execution state
  const [executingStep, setExecutingStep] = useState<string | null>(null)
  const executingStepsRef = useRef<Set<string>>(new Set())

  const loadCampaign = useCallback(async () => {
    try {
      const response = await apiClient.getCampaign(params.id as string) as Campaign
      setCampaign(response)
      
      // Auto-select first step if plan exists
      if (response.plan?.steps?.length && !selectedStep) {
        setSelectedStep(response.plan.steps[0])
      }
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to load campaign",
        variant: "destructive",
      })
    } finally {
      setLoading(false)
    }
  }, [params.id, toast, selectedStep])

  useEffect(() => {
    loadCampaign()
  }, [loadCampaign])

  // Poll for updates when campaign is in an active state or processing
  useEffect(() => {
    if (!campaign) return

    // Statuses that require polling
    const activeStatuses = ["processing", "creating", "generating", "pending", "running"]
    const shouldPoll = activeStatuses.includes(campaign.status.toLowerCase()) 
      || (campaign.status === "draft" && !campaign.plan) // Poll if plan is missing (potentially being generated)

    if (shouldPoll) {
      const intervalId = setInterval(() => {
        loadCampaign()
      }, 5000) // Poll every 5 seconds

      return () => clearInterval(intervalId)
    }
  }, [campaign?.status, campaign?.plan, loadCampaign])

  const toggleStepExpansion = (stepId: string) => {
    const newExpanded = new Set(expandedSteps)
    if (newExpanded.has(stepId)) {
      newExpanded.delete(stepId)
    } else {
      newExpanded.add(stepId)
    }
    setExpandedSteps(newExpanded)
  }

  const updateStepStatus = async (stepId: string, newStatus: "pending" | "in_progress" | "completed") => {
    if (!campaign) return
    
    setUpdatingStep(stepId)
    try {
      await apiClient.updatePlanStepStatus(campaign.id, stepId, newStatus)
      
      // Update local state
      setCampaign(prev => {
        if (!prev?.plan) return prev
        return {
          ...prev,
          plan: {
            ...prev.plan,
            steps: prev.plan.steps.map(step => 
              step.id === stepId ? { ...step, status: newStatus } : step
            )
          }
        }
      })
      
      toast({
        title: "Updated",
        description: `Step status changed to ${newStatus.replace('_', ' ')}`,
      })
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to update step",
        variant: "destructive",
      })
    } finally {
      setUpdatingStep(null)
    }
  }

  const executeStepAI = async (stepId: string) => {
    if (!campaign) return
    
    console.log('[ExecuteStepAI] Starting execution for step:', stepId)
    setExecutingStep(stepId)
    executingStepsRef.current.add(stepId)
    
    try {
      // Trigger execution
      console.log('[ExecuteStepAI] Calling API:', `/campaigns/${campaign.id}/steps/${stepId}/execute`)
      const response = await apiClient.executeStep(campaign.id, stepId)
      console.log('[ExecuteStepAI] API Response:', response)
      
      toast({
        title: "Execution Started",
        description: `${response.task_type.replace('_', ' ')} task started`,
      })
      
      // Update local state to show in_progress
      setCampaign(prev => {
        if (!prev?.plan) return prev
        return {
          ...prev,
          plan: {
            ...prev.plan,
            steps: prev.plan.steps.map(step => 
              step.id === stepId ? { ...step, status: "in_progress" as const, task_type: response.task_type, execution_id: response.execution_id } : step
            )
          }
        }
      })
      
      // Poll for completion
      const pollInterval = setInterval(async () => {
        try {
          console.log('[Poll] Checking step result for:', stepId)
          const result = await apiClient.getStepResult(campaign.id, stepId)
          console.log('[Poll] Result:', result)
          
          if (result.status === "completed" || result.status === "failed") {
            console.log('[Poll] Step finished with status:', result.status)
            clearInterval(pollInterval)
            executingStepsRef.current.delete(stepId)
            
            // Reload the full campaign to get updated data
            try {
              const updatedCampaign = await apiClient.getCampaign(campaign.id) as Campaign
              setCampaign(updatedCampaign)
              
              // Update selectedStep from the reloaded campaign
              const updatedStep = updatedCampaign.plan?.steps.find(s => s.id === stepId)
              if (updatedStep) {
                setSelectedStep(updatedStep)
              }
            } catch (reloadError) {
              console.error('[Poll] Failed to reload campaign:', reloadError)
              // Fallback: update local state
              setCampaign(prev => {
                if (!prev?.plan) return prev
                return {
                  ...prev,
                  plan: {
                    ...prev.plan,
                    steps: prev.plan.steps.map(step => 
                      step.id === stepId ? { ...step, status: result.status as any, result: result.result } : step
                    )
                  }
                }
              })
              setSelectedStep(prev => prev?.id === stepId ? { ...prev, status: result.status as any, result: result.result } : prev)
            }
            
            if (result.status === "completed") {
              toast({
                title: "Step Completed",
                description: "AI execution finished successfully",
              })
            } else {
              toast({
                title: "Execution Failed",
                description: result.error || "Step execution failed",
                variant: "destructive",
              })
            }
            
            if (executingStepsRef.current.size === 0) {
              setExecutingStep(null)
            }
          }
        } catch (e) {
          console.error("Poll error:", e)
        }
      }, 3000) // Poll every 3 seconds
      
      // Clean up after 10 minutes max
      setTimeout(() => {
        clearInterval(pollInterval)
        executingStepsRef.current.delete(stepId)
        if (executingStepsRef.current.size === 0) {
          setExecutingStep(null)
        }
      }, 600000)
      
    } catch (error: any) {
      executingStepsRef.current.delete(stepId)
      setExecutingStep(null)
      toast({
        title: "Error",
        description: error.message || "Failed to execute step",
        variant: "destructive",
      })
    }
  }

  const regeneratePlan = async () => {
    if (!campaign) return
    
    setRegeneratingPlan(true)
    try {
      const response = await apiClient.generateCampaignPlan(campaign.id, true) as { plan: CampaignPlan }
      
      setCampaign(prev => prev ? { ...prev, plan: response.plan } : prev)
      
      toast({
        title: "Plan Regenerated",
        description: "AI has created a new campaign plan",
      })
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to regenerate plan",
        variant: "destructive",
      })
    } finally {
      setRegeneratingPlan(false)
    }
  }

  const sendChatMessage = async () => {
    if (!chatInput.trim() || !campaign) return
    
    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: "user",
      content: chatInput.trim(),
      timestamp: new Date()
    }
    
    setChatMessages(prev => [...prev, userMessage])
    setChatInput("")
    setSendingMessage(true)
    
    try {
      setSendingMessage(true)
      const response = await apiClient.campaignChat(campaign.id, chatInput.trim(), chatMessages)
      
      const aiMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: "assistant", // Fixed: role should be "assistant" not "AI" based on ChatMessage type
        content: response.response,
        timestamp: new Date()
      }
      setChatMessages(prev => [...prev, aiMessage])
    } catch (error) {
      console.error("Failed to send chat message:", error)
      toast({
        title: "Error",
        description: "Failed to send message. Please try again.",
        variant: "destructive"
      })
    } finally {
      setSendingMessage(false)
    }
  }

  const getStepStatusIcon = (status: string) => {
    switch (status) {
      case "completed":
        return <CheckCircle2 className="h-5 w-5 text-green-500" />
      case "in_progress":
        return <Play className="h-5 w-5 text-blue-500" />
      default:
        return <Clock className="h-5 w-5 text-muted-foreground" />
    }
  }

  const getStepStatusBadge = (status: string) => {
    switch (status) {
      case "completed":
        return <Badge className="bg-green-500/10 text-green-600 border-green-500/20">Completed</Badge>
      case "in_progress":
        return <Badge className="bg-blue-500/10 text-blue-600 border-blue-500/20">In Progress</Badge>
      default:
        return <Badge variant="outline">Pending</Badge>
    }
  }

  const calculateProgress = () => {
    if (!campaign?.plan?.steps?.length) return 0
    const completed = campaign.plan.steps.filter(s => s.status === "completed").length
    return Math.round((completed / campaign.plan.steps.length) * 100)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-200px)]">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!campaign) {
    return (
      <Card>
        <CardContent className="p-6">
          <p className="text-muted-foreground">Campaign not found</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="h-[calc(100vh-6rem)] flex flex-col gap-4">
      {/* Header */}
      {/* Premium Header */}
      <header className="flex items-center justify-between px-1 flex-shrink-0 mb-2">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" className="h-10 w-10 rounded-full hover:bg-white/5" onClick={() => router.back()}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold tracking-tight bg-gradient-to-r from-white to-white/70 bg-clip-text text-transparent">{campaign.name}</h1>
              <Badge variant={campaign.status === "draft" ? "secondary" : "default"} className="uppercase text-[10px] tracking-wider px-2 py-0.5 h-5">
                {campaign.status}
              </Badge>
            </div>
            <p className="text-sm text-muted-foreground/80">Campaign Workspace</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
           {campaign.status === "draft" && (
            <Button 
               onClick={() => router.push(`/dashboard/campaigns/${campaign.id}`)} 
               size="sm" 
               className="h-9 px-4 bg-primary hover:bg-primary/90 shadow-lg shadow-primary/20 rounded-lg"
            >
              <CheckCircle2 className="h-4 w-4 mr-2" />
              Review & Deploy
            </Button>
          )}
        </div>
      </header>

      {/* Main Content Grid */}
      <div className="flex-1 grid grid-cols-12 gap-6 min-h-0">
        
        {/* Left Column - Plan & Progress */}
        <section className="col-span-3 flex flex-col min-h-0 glass-panel rounded-2xl overflow-hidden border-white/5 shadow-2xl shadow-black/20">
          <div className="p-4 border-b bg-muted/20">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold text-sm flex items-center gap-2">
                <Target className="h-4 w-4 text-primary" />
                Campaign Plan
              </h2>
              <Button 
                variant="ghost" 
                size="icon"
                className="h-6 w-6"
                onClick={regeneratePlan}
                disabled={regeneratingPlan}
              >
                {regeneratingPlan ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <RefreshCw className="h-3 w-3" />
                )}
              </Button>
            </div>
            {/* Progress Bar */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                <span>Progress</span>
                <span>{calculateProgress()}%</span>
              </div>
              <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                <div 
                  className="h-full bg-primary transition-all duration-500 ease-out"
                  style={{ width: `${calculateProgress()}%` }}
                />
              </div>
            </div>
          </div>

          <ScrollArea className="flex-1">
            <div className="p-4 space-y-4">
              {campaign.plan ? (
                <>
                  {/* Overview */}
                  <div className="p-3 bg-primary/5 rounded-lg border border-primary/10">
                    <p className="text-xs leading-relaxed text-muted-foreground">{campaign.plan.overview}</p>
                  </div>

                  {/* Research Insights */}
                  {campaign.plan.research_insights && campaign.plan.research_insights.length > 0 && (
                    <div className="p-3 bg-blue-50/50 dark:bg-blue-900/10 rounded-lg border border-blue-100 dark:border-blue-900/20">
                      <p className="text-[10px] font-semibold text-blue-600 dark:text-blue-400 uppercase tracking-wider mb-2 flex items-center gap-1">
                        <Sparkles className="h-3 w-3" />
                        Research Insights
                      </p>
                      <ul className="space-y-1.5">
                        {campaign.plan.research_insights.map((insight: string, i: number) => (
                          <li key={i} className="text-xs text-muted-foreground flex items-start gap-2">
                            <span className="mt-1.5 h-1 w-1 rounded-full bg-blue-400 shrink-0" />
                            {insight}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  
                  {/* Steps */}
                  <div className="space-y-3">
                    {campaign.plan.steps.map((step, index) => (
                      <div 
                        key={step.id}
                        className={`group relative rounded-xl transition-all duration-300 backdrop-blur-sm ${
                          selectedStep?.id === step.id 
                            ? 'border border-primary/50 bg-primary/10 ring-1 ring-primary/20 shadow-lg shadow-primary/5' 
                            : 'border border-white/5 bg-white/5 hover:bg-white/10 hover:border-white/10'
                        }`}
                      >
                         {/* Connection Line (visual only) */}
                         {index < campaign.plan!.steps.length - 1 && (
                            <div className="absolute left-[19px] bottom-[-14px] w-[2px] h-[14px] bg-border" />
                         )}

                        <div 
                          className="p-3 cursor-pointer"
                          onClick={() => {
                            setSelectedStep(step)
                            toggleStepExpansion(step.id)
                          }}
                        >
                          <div className="flex items-start gap-3">
                            <div className="flex-shrink-0 mt-0.5">
                              {getStepStatusIcon(step.status)}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center justify-between gap-2">
                                <span className={cn(
                                  "text-sm font-medium leading-none transition-colors",
                                  selectedStep?.id === step.id ? "text-primary" : "text-foreground"
                                )}>
                                  {step.title}
                                </span>
                              </div>
                               <div className="flex items-center gap-2 mt-1.5">
                                  {step.time_estimate && (
                                    <span className="text-[10px] text-muted-foreground flex items-center gap-1 bg-muted px-1.5 py-0.5 rounded">
                                      <Clock className="h-3 w-3" />
                                      {step.time_estimate}
                                    </span>
                                  )}
                               </div>
                            </div>
                             {expandedSteps.has(step.id) ? (
                                <ChevronDown className="h-4 w-4 text-muted-foreground/50" />
                              ) : (
                                <ChevronRight className="h-4 w-4 text-muted-foreground/50" />
                              )}
                          </div>
                        </div>
                        
                        {expandedSteps.has(step.id) && (
                          <div className="px-3 pb-3 pt-1 border-t border-dashed mx-3 mt-1">
                            <p className="text-xs text-muted-foreground leading-relaxed">{step.description}</p>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>

                   {/* Priority Metrics */}
                    {campaign.plan.priority_metrics.length > 0 && (
                      <div className="mt-6">
                        <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">Key Metrics</p>
                        <div className="flex flex-wrap gap-1.5">
                          {campaign.plan.priority_metrics.map(metric => (
                            <Badge key={metric} variant="outline" className="text-[10px] font-normal border-dashed">{metric}</Badge>
                          ))}
                        </div>
                      </div>
                    )}

                </>
              ) : (
                 <div className="flex flex-col items-center justify-center h-48 text-center">
                    <div className="h-12 w-12 rounded-full bg-muted flex items-center justify-center mb-3">
                       <Sparkles className="h-6 w-6 text-muted-foreground" />
                    </div>
                    <p className="text-sm font-medium mb-1">No Plan Yet</p>
                    <p className="text-xs text-muted-foreground mb-4 max-w-[180px]">Generate a data-driven plan for your campaign</p>
                    <Button size="sm" onClick={regeneratePlan} disabled={regeneratingPlan}>
                      {regeneratingPlan ? <Loader2 className="h-3 w-3 mr-2 animate-spin" /> : <Wand2 className="h-3 w-3 mr-2" />}
                      Generate
                    </Button>
                  </div>
              )}
            </div>
          </ScrollArea>
        </section>

        {/* Center Column - Main Canvas */}
        <main className="col-span-6 flex flex-col min-h-0 glass-panel rounded-2xl overflow-hidden border-white/5 shadow-2xl shadow-black/20 relative">
          {/* Subtle glow behind canvas */}
          <div className="absolute top-0 inset-x-0 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent opacity-50" />
          {selectedStep ? (
             <div className="flex flex-col h-full">
                <div className="p-6 border-b">
                   <div className="flex items-start justify-between mb-2">
                      <div className="space-y-1">
                         <h2 className="text-lg font-semibold">{selectedStep.title}</h2>
                         <div className="flex items-center gap-2">
                            {getStepStatusBadge(selectedStep.status)}
                            {selectedStep.time_estimate && (
                               <span className="text-xs text-muted-foreground flex items-center gap-1">
                                  <Clock className="h-3 w-3" />
                                  {selectedStep.time_estimate}
                               </span>
                            )}
                         </div>
                      </div>
                      <div className="flex gap-2">
                        {/* Execute AI Button */}
                        {selectedStep.status !== "in_progress" && (
                          <Button 
                            size="sm"
                            className="h-8 bg-gradient-to-r from-purple-500 to-blue-500 hover:from-purple-600 hover:to-blue-600 text-white"
                            onClick={() => executeStepAI(selectedStep.id)}
                            disabled={executingStep === selectedStep.id}
                          >
                            {executingStep === selectedStep.id ? (
                              <>
                                <Loader2 className="h-3.5 w-3.5 mr-2 animate-spin"/>
                                Executing...
                              </>
                            ) : (
                              <>
                                <Sparkles className="h-3.5 w-3.5 mr-2"/>
                                {selectedStep.status === "completed" || selectedStep.status === "failed" ? "Re-Execute AI" : "Execute AI"}
                              </>
                            )}
                          </Button>
                        )}
                        {selectedStep.status === "in_progress" && (
                          <div className="flex items-center gap-2 h-8 px-3 rounded-md bg-blue-50 text-blue-600 text-sm">
                            <Loader2 className="h-3.5 w-3.5 animate-spin"/>
                            <span>AI is working...</span>
                          </div>
                        )}
                        {/* Contextual Top Actions */}
                         {selectedStep.title.toLowerCase().includes("creative") && (
                            <Button variant="outline" size="sm" className="h-8">
                               <Sparkles className="h-3.5 w-3.5 mr-2" />
                               Creative Assistant
                            </Button>
                         )}
                      </div>
                   </div>
                   <p className="text-sm text-muted-foreground leading-relaxed">
                      {selectedStep.description}
                   </p>
                </div>
                
                <ScrollArea className="flex-1 p-6">
                   <div className="space-y-8">
                      {/* Check-list style Actions */}
                       {selectedStep.actions.length > 0 && (
                        <div className="space-y-4">
                           <h3 className="text-sm font-medium flex items-center gap-2 text-foreground/80">
                              <CheckCircle2 className="h-4 w-4" />
                              Action Items
                           </h3>
                           <div className="grid gap-3">
                              {selectedStep.actions.map((action, i) => (
                                 <div key={i} className="flex items-start gap-3 p-4 rounded-lg border bg-card/50 hover:bg-accent/50 transition-colors">
                                    <div className="h-5 w-5 rounded-full border-2 border-muted-foreground/30 flex-shrink-0 mt-0.5 hover:border-primary cursor-pointer transition-colors" />
                                    <span className="text-sm leading-snug">{action}</span>
                                 </div>
                              ))}
                           </div>
                        </div>
                       )}

                       {/* Step Execution Result */}
                       {selectedStep.result && (
                         <div className="space-y-4">
                           <h3 className="text-sm font-medium flex items-center gap-2 text-foreground/80">
                              <Sparkles className="h-4 w-4 text-purple-500" />
                              AI Generated Result
                              {selectedStep.result.executed_at && (
                                <span className="text-xs font-normal text-muted-foreground ml-2">
                                  {new Date(selectedStep.result.executed_at).toLocaleString()}
                                </span>
                              )}
                           </h3>
                           
                           {/* Error Display */}
                           {selectedStep.result.error && (
                             <div className="p-4 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">
                               <strong>Error:</strong> {selectedStep.result.error}
                             </div>
                           )}
                           
                           {/* Text Content */}
                           {selectedStep.result.content && !selectedStep.result.error && (
                             <div className="p-5 rounded-lg glass-card border-white/5 shadow-inner">
                               <div className="prose prose-sm max-w-none dark:prose-invert prose-headings:font-semibold prose-a:text-primary">
                                 <ReactMarkdown>{selectedStep.result.content}</ReactMarkdown>
                               </div>
                             </div>
                           )}
                           
                           {/* Generated Images */}
                           {selectedStep.result.image_urls && selectedStep.result.image_urls.length > 0 && (
                             <div className="space-y-3">
                               <h4 className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
                                 <ImageIcon className="h-3.5 w-3.5" />
                                 Generated Images ({selectedStep.result.image_urls.length})
                               </h4>
                               <div className="grid grid-cols-2 gap-4">
                                 {selectedStep.result.image_urls.map((url, i) => (
                                   <div key={i} className="relative group rounded-lg overflow-hidden border">
                                     <img 
                                       src={url} 
                                       alt={`Generated image ${i + 1}`} 
                                       className="w-full h-48 object-cover"
                                     />
                                     <a 
                                       href={url} 
                                       download 
                                       target="_blank"
                                       className="absolute bottom-2 right-2 p-2 rounded-lg bg-black/50 text-white opacity-0 group-hover:opacity-100 transition-opacity"
                                     >
                                       <Download className="h-4 w-4" />
                                     </a>
                                   </div>
                                 ))}
                               </div>
                             </div>
                           )}
                           
                           {/* Generated Videos */}
                           {selectedStep.result.video_urls && selectedStep.result.video_urls.length > 0 && (
                             <div className="space-y-3">
                               <h4 className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
                                 <Video className="h-3.5 w-3.5" />
                                 Generated Videos ({selectedStep.result.video_urls.length})
                               </h4>
                               <div className="grid gap-4">
                                 {selectedStep.result.video_urls.map((url, i) => (
                                   <div key={i} className="rounded-lg overflow-hidden border">
                                     <video 
                                       src={url} 
                                       controls 
                                       className="w-full"
                                     />
                                   </div>
                                 ))}
                               </div>
                             </div>
                           )}
                           
                           {/* Research Data */}
                           {selectedStep.result.research_data && (
                             <div className="space-y-3">
                               <h4 className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
                                 <Target className="h-3.5 w-3.5" />
                                 Research Insights
                               </h4>
                               
                               {/* Web Search Sources */}
                               {selectedStep.result.research_data.grounding_sources?.length > 0 && (
                                 <div className="p-3 rounded-lg bg-blue-50/50 border border-blue-100">
                                   <p className="text-xs font-medium text-blue-700 mb-2">Web Sources ({selectedStep.result.research_data.grounding_sources.length})</p>
                                   <div className="space-y-1.5">
                                     {selectedStep.result.research_data.grounding_sources.slice(0, 5).map((source: any, i: number) => (
                                       <a 
                                         key={i} 
                                         href={source.uri} 
                                         target="_blank" 
                                         rel="noopener noreferrer"
                                         className="block text-xs text-blue-600 hover:underline truncate"
                                       >
                                         {source.title || source.uri}
                                       </a>
                                     ))}
                                   </div>
                                 </div>
                               )}
                               
                               {/* Legacy SERP keywords support */}
                               {selectedStep.result.research_data.serp_keywords?.length > 0 && (
                                 <div className="p-3 rounded-lg bg-muted/30">
                                   <p className="text-xs font-medium text-muted-foreground mb-2">Top Keywords</p>
                                   <div className="flex flex-wrap gap-1.5">
                                     {selectedStep.result.research_data.serp_keywords.slice(0, 10).map((kw: any, i: number) => (
                                       <Badge key={i} variant="outline" className="text-xs">
                                         {typeof kw === 'string' ? kw : kw.keyword}
                                       </Badge>
                                     ))}
                                   </div>
                                 </div>
                               )}
                             </div>
                           )}
                         </div>
                       )}


                       {/* Context Info Grid */}
                       <div className="grid grid-cols-2 gap-4">
                          <div className="p-4 rounded-lg bg-muted/30 border border-transparent hover:border-border transition-colors">
                             <h4 className="text-xs font-medium text-muted-foreground mb-2 flex items-center gap-1.5">
                                <DollarSign className="h-3.5 w-3.5" /> Budget Allocation
                             </h4>
                             <p className="text-lg font-semibold">
                                {campaign.total_budget 
                                   ? `${campaign.currency} ${campaign.total_budget.toLocaleString()}` 
                                   : "Not Set"}
                             </p>
                          </div>
                           <div className="p-4 rounded-lg bg-muted/30 border border-transparent hover:border-border transition-colors">
                             <h4 className="text-xs font-medium text-muted-foreground mb-2 flex items-center gap-1.5">
                                <Target className="h-3.5 w-3.5" /> Objective
                             </h4>
                             <p className="text-lg font-semibold capitalize">
                                {campaign.objective_type?.replace('_', ' ') || "TBD"}
                             </p>
                          </div>
                       </div>
                   </div>
                </ScrollArea>
             </div>
          ) : (
             <div className="flex flex-col items-center justify-center h-full text-center p-8">
                <div className="h-16 w-16 rounded-2xl bg-primary/5 flex items-center justify-center mb-6">
                   <Target className="h-8 w-8 text-primary" />
                </div>
                <h3 className="text-lg font-semibold mb-2">Select a Step</h3>
                <p className="text-sm text-muted-foreground max-w-sm mb-6">
                   Review the campaign plan on the left and select a step to view details, take actions, or use AI tools.
                </p>
             </div>
          )}
        </main>

        {/* Right Column - Chat Assistant */}
        <aside className="col-span-3 flex flex-col min-h-0 glass-panel rounded-2xl overflow-hidden border-white/5 shadow-2xl shadow-black/20">
           <div className="p-4 border-b bg-muted/20">
              <h2 className="font-semibold text-sm flex items-center gap-2">
                 <Bot className="h-4 w-4 text-purple-500" />
                 AI Companion
              </h2>
           </div>
           
           <ScrollArea className="flex-1 p-4">
              <div className="space-y-4">
                 {chatMessages.length === 0 ? (
                    <div className="text-center py-12 px-4">
                       <div className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-purple-100 dark:bg-purple-900/20 mb-3">
                          <Sparkles className="h-5 w-5 text-purple-600 dark:text-purple-400" />
                       </div>
                       <p className="text-sm font-medium mb-1">How can I help?</p>
                       <p className="text-xs text-muted-foreground">
                          Ask about audience targeting, ad copy, or budget strategy.
                       </p>
                    </div>
                 ) : (
                    chatMessages.map(msg => (
                       <div 
                          key={msg.id} 
                          className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                       >
                        <div
                          className={cn(
                            "rounded-lg px-4 py-2 max-w-[85%] text-sm shadow-sm",
                            msg.role === "user"
                              ? "bg-primary text-primary-foreground ml-auto shadow-md shadow-primary/20"
                              : "glass-card border-white/10 mr-auto text-foreground/90 backdrop-blur-md"
                          )}
                        >
                          {msg.role === "user" ? (
                            <p>{msg.content}</p>
                          ) : (
                            <div className="prose dark:prose-invert prose-sm max-w-none">
                              <ReactMarkdown>{msg.content}</ReactMarkdown>
                            </div>
                          )}
                          <span className="text-[10px] opacity-70 mt-1 block">
                            {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </span>
                        </div>
                       </div>
                    ))
                 )}
                 {sendingMessage && (
                    <div className="flex justify-start">
                       <div className="bg-muted px-4 py-2 rounded-2xl rounded-bl-none">
                          <div className="flex gap-1">
                             <span className="w-1.5 h-1.5 bg-foreground/30 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                             <span className="w-1.5 h-1.5 bg-foreground/30 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                             <span className="w-1.5 h-1.5 bg-foreground/30 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                          </div>
                       </div>
                    </div>
                 )}
              </div>
           </ScrollArea>

           <div className="p-4 border-t bg-background">
              {/* Context Prompt Chips */}
              {chatMessages.length === 0 && (
                 <div className="flex gap-2 mb-3 overflow-x-auto pb-1 scrollbar-hide">
                    {["Target Audience", "Ad Headlines", "Budget"].map(suggestion => (
                       <button 
                          key={suggestion}
                          onClick={() => setChatInput(`Help me with ${suggestion}`)}
                          className="flex-shrink-0 text-[10px] font-medium px-2 py-1 rounded-full bg-muted hover:bg-muted/80 transition-colors border"
                       >
                          {suggestion}
                       </button>
                    ))}
                 </div>
              )}
              
              <div className="relative">
                 <Textarea
                    placeholder="Message AI..."
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => {
                       if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault()
                          sendChatMessage()
                       }
                    }}
                    className="min-h-[44px] max-h-[120px] pr-10 py-3 rounded-xl resize-none shadow-sm focus-visible:ring-offset-0 focus-visible:ring-1"
                    rows={1}
                 />
                 <Button 
                    size="icon" 
                    className="absolute right-1 top-1 h-8 w-8 rounded-lg" // smaller and inside
                    onClick={sendChatMessage}
                    disabled={!chatInput.trim() || sendingMessage}
                 >
                    <Send className="h-3.5 w-3.5" />
                 </Button>
              </div>
           </div>
        </aside>

      </div>
    </div>
  )
}
