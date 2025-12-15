"use client"

import { useEffect, useState, useCallback } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { apiClient } from "@/lib/api"
import { useToast } from "@/components/ui/use-toast"
import { 
  Target, Plus, Loader2, CheckCircle2, Clock, Eye, 
  Pause, DollarSign, Calendar, TrendingUp, MessageSquare, Send, AlertTriangle, LayoutDashboard
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useRouter } from "next/navigation"
import { Alert, AlertDescription } from "@/components/ui/alert"

interface Campaign {
  id: string
  name: string
  description?: string
  campaign_type?: string
  channels: string[]
  status: string
  total_budget?: number
  budget_allocation?: Record<string, number>
  spent_to_date?: number
  start_date?: string
  end_date?: string
  plan?: Record<string, any>
  metrics?: Record<string, any>
  created_at: string
  execution_id?: string
}

interface Execution {
  id: string
  request_type: string
  status: string
  result?: any
  error_message?: string
  steps_executed?: any[]
  created_at: string
}

interface FeedbackMessage {
  id: string
  role: "user" | "assistant"
  content: string
  timestamp: Date
}

export default function CampaignsPage() {
  const { toast } = useToast()
  const router = useRouter()
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [executions, setExecutions] = useState<Execution[]>([])
  const [loading, setLoading] = useState(true)
  const [executing, setExecuting] = useState(false)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [showApproveDialog, setShowApproveDialog] = useState(false)
  const [campaignToApprove, setCampaignToApprove] = useState<Campaign | null>(null)
  const [showFeedbackDialog, setShowFeedbackDialog] = useState(false)
  const [selectedCampaign, setSelectedCampaign] = useState<Campaign | null>(null)
  const [feedbackMessages, setFeedbackMessages] = useState<FeedbackMessage[]>([])
  const [feedbackInput, setFeedbackInput] = useState("")
  const [sendingFeedback, setSendingFeedback] = useState(false)
  const [campaignName, setCampaignName] = useState("")
  const [objective, setObjective] = useState("")
  const [description, setDescription] = useState("")
  const [budget, setBudget] = useState("")
  const [startDate, setStartDate] = useState("")
  const [endDate, setEndDate] = useState("")
  const [selectedChannels, setSelectedChannels] = useState<string[]>([])
  const [statusFilter, setStatusFilter] = useState<string>("all")
  
  // Performance Max fields
  const [finalUrl, setFinalUrl] = useState("")
  const [callToAction, setCallToAction] = useState<string>("learn_more")

  const loadCampaigns = useCallback(async () => {
    try {
      const filter = statusFilter === "all" ? undefined : statusFilter
      const response = await apiClient.listCampaigns(filter) as { campaigns?: Campaign[] }
      setCampaigns(response.campaigns || [])
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to load campaigns",
        variant: "destructive",
      })
    }
  }, [statusFilter, toast])

  const loadExecutions = useCallback(async () => {
    try {
      const response = await apiClient.listAgentExecutions(undefined, undefined, undefined, 50, 0) as { executions?: Execution[] }
      const campaignExecutions = (response.executions || []).filter(
        (e: Execution) => e.request_type === "create_campaign"
      )
      setExecutions(campaignExecutions)
    } catch (error: any) {
      // Silently fail - executions are optional
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [statusFilter])

  // Poll for updates if any campaign/execution is in active state
  useEffect(() => {
    // Check if any campaigns are processing/running
    const hasActiveCampaigns = campaigns.some(c => 
      ["processing", "creating", "pending", "running", "generating"].includes(c.status.toLowerCase()) || 
      (c.status === "draft" && !c.plan)
    )
    
    // Check if any executions are running
    const hasActiveExecutions = executions.some(e => 
      ["running", "queued", "pending"].includes(e.status.toLowerCase())
    )

    if (hasActiveCampaigns || hasActiveExecutions || executing) {
      const intervalId = setInterval(() => {
        loadData(false)
      }, 5000)
      return () => clearInterval(intervalId)
    }
  }, [campaigns, executions, executing, statusFilter]) // Re-run effect when data changes to re-evaluate if polling is needed

  async function loadData(showLoading = true) {
    if (showLoading) setLoading(true)
    try {
      await Promise.all([loadCampaigns(), loadExecutions()])
    } finally {
      if (showLoading) setLoading(false)
    }
  }

  async function handleCreateCampaign() {
    if (!objective.trim()) {
      toast({
        title: "Error",
        description: "Campaign objective is required",
        variant: "destructive",
      })
      return
    }

    if (selectedChannels.length === 0) {
      toast({
        title: "Error",
        description: "Please select at least one channel",
        variant: "destructive",
      })
      return
    }

    setExecuting(true)
    try {
      // Get active assistant
      const assistants = await apiClient.listAssistants() as { assistants?: any[] }
      const digitalMarketer = assistants.assistants?.find(
        (a: any) => a.assistant_type === "digital_marketer" && a.is_active
      )

      if (!digitalMarketer) {
        toast({
          title: "Error",
          description: "Digital Marketer assistant not found. Please activate it first.",
          variant: "destructive",
        })
        return
      }

      // Get campaigns capability
      const capabilities = await apiClient.getCapabilities(digitalMarketer.id) as { capabilities?: any[] }
      const campaignsCapability = capabilities.capabilities?.find(
        (c: any) => c.capability_type === "campaigns"
      )

      if (!campaignsCapability) {
        toast({
          title: "Error",
          description: "Campaigns capability not set up. Please configure it first.",
          variant: "destructive",
        })
        return
      }

      // Execute agent to create campaign
      await apiClient.executeAgent({
        assistant_id: digitalMarketer.id,
        capability_id: campaignsCapability.id,
        request_type: "create_campaign",
        request_data: {
          name: campaignName.trim() || objective.trim(),
          objective: objective.trim(),
          description: description.trim() || undefined,
          budget: budget ? Number.parseFloat(budget) : undefined,
          start_date: startDate || undefined,
          end_date: endDate || undefined,
          channels: selectedChannels,
          campaign_type: "performance_max",
          // Performance Max fields
          final_url: finalUrl.trim() || undefined,
          call_to_action: callToAction
        }
      }) as { execution?: { id: string } }

      toast({
        title: "Success",
        description: "Campaign creation started. The AI will generate a comprehensive campaign plan.",
      })
      
      setShowCreateDialog(false)
      resetForm()
      
      // Reload data after a short delay
      setTimeout(() => {
        loadData()
      }, 2000)
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to create campaign",
        variant: "destructive",
      })
    } finally {
      setExecuting(false)
    }
  }

  async function handleApproveCampaign(campaignId: string) {
    try {
      const result = await apiClient.approveCampaign(campaignId) as { success?: boolean; errors?: string[] }
      
      if (result.success) {
        toast({
          title: "Success",
          description: "Campaign approved and launched to platforms",
        })
        setShowApproveDialog(false)
        setCampaignToApprove(null)
        loadCampaigns()
      } else {
        toast({
          title: "Error",
          description: result.errors?.join(", ") || "Failed to approve campaign",
          variant: "destructive",
        })
      }
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to approve campaign",
        variant: "destructive",
      })
    }
  }

  function openApproveDialog(campaign: Campaign) {
    setCampaignToApprove(campaign)
    setShowApproveDialog(true)
  }

  function openFeedbackDialog(campaign: Campaign) {
    setSelectedCampaign(campaign)
    setFeedbackMessages([])
    setFeedbackInput("")
    setShowFeedbackDialog(true)
  }

  async function handleSendFeedback() {
    if (!feedbackInput.trim() || !selectedCampaign) return

    const userMessage: FeedbackMessage = {
      id: Date.now().toString(),
      role: "user",
      content: feedbackInput.trim(),
      timestamp: new Date()
    }

    setFeedbackMessages(prev => [...prev, userMessage])
    setFeedbackInput("")
    setSendingFeedback(true)

    try {
      // Get active assistant
      const assistants = await apiClient.listAssistants() as { assistants?: any[] }
      const digitalMarketer = assistants.assistants?.find(
        (a: any) => a.assistant_type === "digital_marketer" && a.is_active
      )

      if (!digitalMarketer) {
        throw new Error("Digital Marketer assistant not found")
      }

      // Get campaigns capability
      const capabilities = await apiClient.getCapabilities(digitalMarketer.id) as { capabilities?: any[] }
      const campaignsCapability = capabilities.capabilities?.find(
        (c: any) => c.capability_type === "campaigns"
      )

      if (!campaignsCapability) {
        throw new Error("Campaigns capability not set up")
      }

      // Create a revision request with feedback
      await apiClient.executeAgent({
        assistant_id: digitalMarketer.id,
        capability_id: campaignsCapability.id,
        request_type: "create_campaign",
        request_data: {
          objective: selectedCampaign.plan?.objective || selectedCampaign.name,
          description: selectedCampaign.description,
          budget: selectedCampaign.total_budget,
          duration_days: selectedCampaign.start_date && selectedCampaign.end_date
            ? Math.ceil((new Date(selectedCampaign.end_date).getTime() - new Date(selectedCampaign.start_date).getTime()) / (1000 * 60 * 60 * 24))
            : 30,
          channels: selectedCampaign.channels,
          campaign_type: selectedCampaign.campaign_type || "brand_awareness",
          revision_feedback: feedbackInput.trim(),
          existing_campaign_id: selectedCampaign.id
        }
      })

      const assistantMessage: FeedbackMessage = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: "Thank you for your feedback! I'm revising the campaign based on your input. This may take a few moments...",
        timestamp: new Date()
      }

      setFeedbackMessages(prev => [...prev, assistantMessage])

      toast({
        title: "Feedback Sent",
        description: "The AI is revising the campaign based on your feedback.",
      })

      // Reload campaigns after a delay
      setTimeout(() => {
        loadCampaigns()
      }, 2000)
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to send feedback",
        variant: "destructive",
      })
    } finally {
      setSendingFeedback(false)
    }
  }

  function resetForm() {
    setCampaignName("")
    setObjective("")
    setDescription("")
    setBudget("")
    setStartDate("")
    setEndDate("")
    setSelectedChannels([])
    setFinalUrl("")
    setCallToAction("learn_more")
  }

  const channels = [
    { id: "google_ads", name: "Google Ads" },
    { id: "meta_ads", name: "Meta Ads" },
  ]

  const getStatusColor = (status: string) => {
    switch (status) {
      case "draft": return "outline"
      case "active": return "default"
      case "paused": return "secondary"
      case "completed": return "default"
      case "failed": return "destructive"
      default: return "outline"
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-6">

      {/* Premium Hero Header */}
      <div className="relative rounded-3xl overflow-hidden p-8 border border-white/10 glass-card">
         <div className="absolute inset-0 bg-gradient-to-r from-blue-600/10 via-purple-600/10 to-pink-600/10 opacity-50" />
         <div className="absolute -top-24 -right-24 w-64 h-64 bg-primary/20 rounded-full blur-[100px]" />
         
         <div className="relative z-10 flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
            <div className="space-y-2">
               <h1 className="text-4xl font-bold tracking-tight bg-gradient-to-r from-white to-white/70 bg-clip-text text-transparent">
                  Campaigns
               </h1>
               <p className="text-muted-foreground text-lg max-w-xl">
                  Manage your AI-driven marketing strategies by StaffPilot.
               </p>
            </div>
            
            <div className="flex items-center gap-3 bg-black/20 p-1.5 rounded-xl border border-white/5 backdrop-blur-md">
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="w-40 border-none bg-transparent hover:bg-white/5 transition-colors focus:ring-0">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="draft">Draft</SelectItem>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="paused">Paused</SelectItem>
                  <SelectItem value="completed">Completed</SelectItem>
                </SelectContent>
              </Select>
              
              <div className="w-px h-6 bg-white/10" />
              
              <Button 
                onClick={() => setShowCreateDialog(true)}
                className="bg-primary hover:bg-primary/90 shadow-lg shadow-primary/25 rounded-lg px-6"
              >
                <Plus className="h-4 w-4 mr-2" />
                New Campaign
              </Button>
            </div>
         </div>
      </div>

      {/* Executions List - Horizontal Scroll for "Recent Activity" feel */}
      {executions.length > 0 && (
        <div className="mb-8">
           <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <Loader2 className="h-4 w-4 text-primary animate-spin" />
              Active AI Agents
           </h2>
           <div className="flex gap-4 overflow-x-auto pb-4 scrollbar-hide">
              {executions.slice(0, 5).map((execution) => {
                const campaign = campaigns.find(c => c.execution_id === execution.id)
                return (
                  <div
                    key={execution.id}
                    className="min-w-[280px] p-4 rounded-xl bg-card/50 border border-border/50 backdrop-blur-sm shadow-sm"
                  >
                    <div className="flex items-center justify-between mb-2">
                       <Badge variant={getStatusColor(execution.status)} className="capitalize">
                          {execution.status}
                       </Badge>
                       <span className="text-xs text-muted-foreground">{new Date(execution.created_at).toLocaleTimeString()}</span>
                    </div>
                    <p className="font-medium text-sm truncate">{campaign?.name || "New Campaign Strategy"}</p>
                    <p className="text-xs text-muted-foreground mt-1">AI Agent is generating plan...</p>
                  </div>
                )
              })}
           </div>
        </div>
      )}

      {/* Campaigns Grid - Bento Style */}
      {campaigns.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-center border-2 border-dashed border-muted-foreground/10 rounded-3xl bg-muted/5">
           <div className="h-20 w-20 rounded-2xl bg-primary/10 flex items-center justify-center mb-6 animate-float">
              <Target className="h-10 w-10 text-primary" />
           </div>
           <h3 className="text-2xl font-bold mb-3 tracking-tight">No campaigns yet</h3>
           <p className="text-muted-foreground max-w-md mb-8 leading-relaxed">
             Launch your first AI-driven marketing campaign. Our digital marketer agent will build a complete strategy for you.
           </p>
           <Button 
              size="lg" 
              onClick={() => setShowCreateDialog(true)}
              className="bg-primary hover:bg-primary/90 rounded-full px-8 shadow-lg shadow-primary/20 hover:shadow-primary/30 transition-all font-medium"
           >
             <Plus className="h-5 w-5 mr-2" />
             Create First Campaign
           </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {campaigns.map((campaign, index) => {
             // Calculate Progress
             const totalSteps = campaign.plan?.steps?.length || 0
             const completedSteps = campaign.plan?.steps?.filter((s: any) => s.status === 'completed').length || 0
             const progress = totalSteps === 0 ? 0 : Math.round((completedSteps / totalSteps) * 100)
             
             return (
              <div 
                 key={campaign.id}
                 className="group relative flex flex-col glass-card-interactive rounded-2xl overflow-hidden min-h-[280px]"
                 onClick={() => router.push(`/dashboard/campaigns/${campaign.id}/workspace`)}
                 style={{ cursor: 'pointer' }}
              >
                  {/* Decorative Gradient Blob */}
                  <div className="absolute -top-20 -right-20 w-40 h-40 bg-primary/10 rounded-full blur-3xl group-hover:bg-primary/20 transition-all duration-500" />
                  
                  <div className="p-6 flex-1 flex flex-col relative z-10">
                    <div className="flex items-start justify-between mb-4">
                       <div className="p-2.5 rounded-xl bg-muted/50 border border-white/5">
                          <Target className="h-5 w-5 text-primary" />
                       </div>
                       <Badge variant={getStatusColor(campaign.status)} className="rounded-full px-3 capitalize shadow-none">
                          {campaign.status}
                       </Badge>
                    </div>
                    
                    <h3 className="text-lg font-bold mb-2 group-hover:text-primary transition-colors line-clamp-1">
                       {campaign.name}
                    </h3>
                    <p className="text-sm text-muted-foreground line-clamp-2 mb-6 flex-1">
                       {campaign.description || "No description provided."}
                    </p>
                    
                    {/* Metrics / Content */}
                    <div className="grid grid-cols-2 gap-4 mb-6">
                       <div className="space-y-1">
                          <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium">Budget</p>
                          <p className="text-sm font-semibold">{campaign.total_budget ? `$${campaign.total_budget.toLocaleString()}` : "Not Set"}</p>
                       </div>
                       <div className="space-y-1">
                          <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium">Channels</p>
                          <div className="flex gap-1.5">
                             {campaign.channels.slice(0, 3).map((c, i) => (
                                <div key={i} className="h-5 w-5 rounded-full bg-blue-500/10 flex items-center justify-center" title={c}>
                                   <span className="text-[10px] font-bold text-blue-500">{c[0].toUpperCase()}</span>
                                </div>
                             ))}
                             {campaign.channels.length > 3 && (
                                <span className="text-xs text-muted-foreground">+{campaign.channels.length - 3}</span>
                             )}
                          </div>
                       </div>
                    </div>

                    {/* Footer / Progress */}
                    <div className="pt-4 border-t border-border/50">
                       <div className="flex justify-between text-xs mb-2">
                          <span className="text-muted-foreground">{totalSteps} Steps</span>
                          <span className="font-medium text-foreground">{progress}% Complete</span>
                       </div>
                       <div className="h-1.5 w-full bg-muted/50 rounded-full overflow-hidden">
                          <div 
                             className="h-full bg-gradient-to-r from-blue-500 to-purple-500 transition-all duration-1000 ease-out" 
                             style={{ width: `${progress}%` }}
                          />
                       </div>
                    </div>
                  </div>
              </div>
            )
          })}
          
          {/* New Campaign Card (Placeholder style) */}
          <div 
             className="flex flex-col items-center justify-center p-6 border border-dashed border-border rounded-2xl hover:bg-muted/5 transition-colors cursor-pointer min-h-[280px] group"
             onClick={() => setShowCreateDialog(true)}
          >
             <div className="h-14 w-14 rounded-full bg-muted group-hover:bg-primary/10 flex items-center justify-center mb-4 transition-colors">
                <Plus className="h-6 w-6 text-muted-foreground group-hover:text-primary transition-colors" />
             </div>
             <p className="font-medium group-hover:text-primary transition-colors">Create New Campaign</p>
             <p className="text-xs text-muted-foreground mt-1">Start a new AI strategy</p>
          </div>
        </div>
      )}

      {/* Create Campaign Dialog */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Create New Campaign</DialogTitle>
            <DialogDescription>
              Describe your campaign objective and the AI will generate a comprehensive strategy with ad copy, budget allocation, and timeline
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 max-h-[70vh] overflow-y-auto pr-2">
            <div>
              <label htmlFor="campaign-name" className="text-sm font-medium mb-2 block">
                Campaign Name *
              </label>
              <Input
                id="campaign-name"
                placeholder="e.g., Summer Sale 2026"
                value={campaignName}
                onChange={(e) => setCampaignName(e.target.value)}
              />
            </div>
            <div>
              <label htmlFor="objective" className="text-sm font-medium mb-2 block">
                Campaign Objective *
              </label>
              <Input
                id="objective"
                placeholder="e.g., Product Launch, Brand Awareness, Lead Generation, Conversions"
                value={objective}
                onChange={(e) => setObjective(e.target.value)}
              />
            </div>
            <div>
              <label htmlFor="description" className="text-sm font-medium mb-2 block">
                Description / Goals
              </label>
              <Textarea
                id="description"
                placeholder="Provide details about your campaign goals, target audience, and key messaging..."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
              />
            </div>
            <div>
              <label htmlFor="final-url" className="text-sm font-medium mb-2 block">
                Landing Page URL *
              </label>
              <Input
                id="final-url"
                type="url"
                placeholder="https://yourwebsite.com/landing-page"
                value={finalUrl}
                onChange={(e) => setFinalUrl(e.target.value)}
              />
              <p className="text-xs text-muted-foreground mt-1">Where users will go when they click your ad</p>
            </div>
            <div>
              <label htmlFor="call-to-action" className="text-sm font-medium mb-2 block">
                Call to Action
              </label>
              <Select value={callToAction} onValueChange={setCallToAction}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="learn_more">Learn More</SelectItem>
                  <SelectItem value="shop_now">Shop Now</SelectItem>
                  <SelectItem value="sign_up">Sign Up</SelectItem>
                  <SelectItem value="get_quote">Get Quote</SelectItem>
                  <SelectItem value="contact_us">Contact Us</SelectItem>
                  <SelectItem value="book_now">Book Now</SelectItem>
                  <SelectItem value="download">Download</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label htmlFor="budget" className="text-sm font-medium mb-2 block">
                  Daily Budget ($)
                </label>
                <Input
                  id="budget"
                  type="number"
                  placeholder="50"
                  value={budget}
                  onChange={(e) => setBudget(e.target.value)}
                />
              </div>
              <div>
                <label className="text-sm font-medium mb-2 block">
                  Campaign Type
                </label>
                <div className="h-10 px-3 py-2 rounded-md border bg-muted/50 text-sm flex items-center">
                  <Target className="h-4 w-4 mr-2 text-primary" />
                  Performance Max
                </div>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label htmlFor="start-date" className="text-sm font-medium mb-2 block">
                  Start Date
                </label>
                <Input
                  id="start-date"
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                />
              </div>
              <div>
                <label htmlFor="end-date" className="text-sm font-medium mb-2 block">
                  End Date
                </label>
                <Input
                  id="end-date"
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                />
              </div>
            </div>
            <div>
              <label htmlFor="channels" className="text-sm font-medium mb-2 block">Channels *</label>
              <div className="flex flex-wrap gap-2">
                {channels.map((channel) => (
                  <Button
                    key={channel.id}
                    type="button"
                    variant={selectedChannels.includes(channel.id) ? "default" : "outline"}
                    size="sm"
                    onClick={() => {
                      if (selectedChannels.includes(channel.id)) {
                        setSelectedChannels(selectedChannels.filter(c => c !== channel.id))
                      } else {
                        setSelectedChannels([...selectedChannels, channel.id])
                      }
                    }}
                  >
                    {channel.name}
                  </Button>
                ))}
              </div>
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setShowCreateDialog(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreateCampaign} disabled={executing || (!campaignName.trim() && !objective.trim()) || selectedChannels.length === 0}>
              {executing ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Creating...
                </>
              ) : (
                <>
                  <Target className="h-4 w-4 mr-2" />
                  Create Campaign
                </>
              )}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Approval Dialog with Charge Warning */}
      <Dialog open={showApproveDialog} onOpenChange={setShowApproveDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-amber-500" />
              Approve & Launch Campaign
            </DialogTitle>
            <DialogDescription>
              Please review the campaign details before approving.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <Alert>
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>
                <strong>Important:</strong> Approving this campaign will create actual campaigns in your integrated advertising platforms (Google Ads, Meta Ads) and will incur charges based on your campaign budget and settings.
              </AlertDescription>
            </Alert>
            {campaignToApprove && (
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Campaign:</span>
                  <span className="font-medium">{campaignToApprove.name}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Budget:</span>
                  <span className="font-medium">
                    ${campaignToApprove.total_budget?.toLocaleString() || "Not set"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Channels:</span>
                  <span className="font-medium">
                    {campaignToApprove.channels.map(c => c.replace("_", " ")).join(", ")}
                  </span>
                </div>
              </div>
            )}
            <p className="text-xs text-muted-foreground">
              Charges will be processed by the advertising platforms according to their billing terms. Make sure you have sufficient budget and payment methods configured.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowApproveDialog(false)}>
              Cancel
            </Button>
            <Button 
              onClick={() => campaignToApprove && handleApproveCampaign(campaignToApprove.id)}
              className="bg-primary"
            >
              <CheckCircle2 className="h-4 w-4 mr-2" />
              I Understand, Approve Campaign
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Feedback Dialog */}
      <Dialog open={showFeedbackDialog} onOpenChange={setShowFeedbackDialog}>
        <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Provide Feedback & Request Revisions</DialogTitle>
            <DialogDescription>
              Share your feedback and the AI will revise the campaign accordingly. You can approve it once you're satisfied.
            </DialogDescription>
          </DialogHeader>
          <div className="flex-1 overflow-y-auto space-y-4 mb-4">
            {feedbackMessages.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <MessageSquare className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>Start a conversation about this campaign</p>
                <p className="text-sm mt-2">Share what you'd like to change or improve</p>
              </div>
            ) : (
              <div className="space-y-4">
                {feedbackMessages.map((message) => (
                  <div
                    key={message.id}
                    className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
                  >
                    <div
                      className={`max-w-[80%] rounded-lg p-3 ${
                        message.role === "user"
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted"
                      }`}
                    >
                      <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                      <p className={`text-xs mt-1 ${
                        message.role === "user" ? "text-primary-foreground/70" : "text-muted-foreground"
                      }`}>
                        {message.timestamp.toLocaleTimeString()}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="flex gap-2 border-t pt-4">
            <Textarea
              placeholder="Type your feedback here... (e.g., 'Make the budget allocation more balanced', 'Focus more on brand awareness', 'Adjust the ad copy tone')"
              value={feedbackInput}
              onChange={(e) => setFeedbackInput(e.target.value)}
              rows={3}
              onKeyDown={(e) => {
                if (e.key === "Enter" && e.ctrlKey) {
                  handleSendFeedback()
                }
              }}
            />
            <Button
              onClick={handleSendFeedback}
              disabled={!feedbackInput.trim() || sendingFeedback}
              size="icon"
              className="self-end"
            >
              {sendingFeedback ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground text-center">
            Press Ctrl+Enter to send
          </p>
        </DialogContent>
      </Dialog>
    </div>
  )
}
