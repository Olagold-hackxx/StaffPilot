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
  
  // Creative preference
  const [creativePreference, setCreativePreference] = useState<"image" | "video" | "both">("both")

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
          campaign_type: "brand_awareness",
          // Creative preference - company context comes from uploaded documents
          creative_preference: creativePreference
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
    setCreativePreference("both")
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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Campaigns</h1>
          <p className="text-muted-foreground">Create and manage marketing campaigns</p>
        </div>
        <div className="flex gap-2">
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-40">
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
          <Button onClick={() => setShowCreateDialog(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Create Campaign
          </Button>
        </div>
      </div>

      {/* Executions List */}
      {executions.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Recent Campaign Executions</CardTitle>
            <CardDescription>AI-generated campaigns in progress</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {executions.slice(0, 5).map((execution) => {
                const campaign = campaigns.find(c => c.execution_id === execution.id)
                return (
                  <div
                    key={execution.id}
                    className="flex items-center justify-between p-3 border rounded-lg"
                  >
                    <div className="flex items-center gap-3">
                      {execution.status === "running" ? (
                        <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                      ) : execution.status === "completed" ? (
                        <CheckCircle2 className="h-4 w-4 text-green-500" />
                      ) : execution.status === "failed" ? (
                        <Clock className="h-4 w-4 text-red-500" />
                      ) : (
                        <Clock className="h-4 w-4 text-muted-foreground" />
                      )}
                      <div>
                        <p className="text-sm font-medium">
                          {campaign?.name || "Campaign Creation"}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {execution.status} • {new Date(execution.created_at).toLocaleString()}
                        </p>
                      </div>
                    </div>
                    <Badge variant={getStatusColor(execution.status)}>
                      {execution.status}
                    </Badge>
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Campaigns List */}
      {campaigns.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center">
            <Target className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <h3 className="text-lg font-semibold mb-2">No campaigns yet</h3>
            <p className="text-muted-foreground mb-4">
              Create your first marketing campaign and let AI generate a comprehensive strategy
            </p>
            <Button onClick={() => setShowCreateDialog(true)}>
              <Plus className="h-4 w-4 mr-2" />
              Create Campaign
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4">
          {campaigns.map((campaign) => (
            <Card key={campaign.id}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <CardTitle>{campaign.name}</CardTitle>
                    <CardDescription>{campaign.description || "No description"}</CardDescription>
                  </div>
                  <Badge variant={getStatusColor(campaign.status)}>
                    {campaign.status}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                  <div>
                    <p className="text-sm text-muted-foreground flex items-center gap-1">
                      <Target className="h-3 w-3" />
                      Channels
                    </p>
                    <p className="font-medium">{campaign.channels.length}</p>
                    <p className="text-xs text-muted-foreground">
                      {campaign.channels.map(c => c.replace("_", " ")).join(", ")}
                    </p>
                  </div>
                  {campaign.total_budget && (
                    <div>
                      <p className="text-sm text-muted-foreground flex items-center gap-1">
                        <DollarSign className="h-3 w-3" />
                        Budget
                      </p>
                      <p className="font-medium">${campaign.total_budget.toLocaleString()}</p>
                    </div>
                  )}
                  {campaign.start_date && (
                    <div>
                      <p className="text-sm text-muted-foreground flex items-center gap-1">
                        <Calendar className="h-3 w-3" />
                        Duration
                      </p>
                      <p className="font-medium text-sm">
                        {new Date(campaign.start_date).toLocaleDateString()} - {campaign.end_date ? new Date(campaign.end_date).toLocaleDateString() : "Ongoing"}
                      </p>
                    </div>
                  )}
                  {campaign.metrics && Object.keys(campaign.metrics).length > 0 && (
                    <div>
                      <p className="text-sm text-muted-foreground flex items-center gap-1">
                        <TrendingUp className="h-3 w-3" />
                        Performance
                      </p>
                      <p className="font-medium text-sm">
                        {campaign.metrics.impressions ? `${campaign.metrics.impressions.toLocaleString()} impressions` : "N/A"}
                      </p>
                    </div>
                  )}
                </div>
                <div className="flex gap-2">
                  {campaign.status === "draft" && (
                    <>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => router.push(`/dashboard/campaigns/${campaign.id}/workspace`)}
                      >
                        <LayoutDashboard className="h-4 w-4 mr-1" />
                        Workspace
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => router.push(`/dashboard/campaigns/${campaign.id}`)}
                      >
                        <Eye className="h-4 w-4 mr-1" />
                        Review
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => openFeedbackDialog(campaign)}
                      >
                        <MessageSquare className="h-4 w-4 mr-1" />
                        Provide Feedback
                      </Button>
                      <Button
                        size="sm"
                        onClick={() => openApproveDialog(campaign)}
                      >
                        <CheckCircle2 className="h-4 w-4 mr-1" />
                        Approve & Launch
                      </Button>
                    </>
                  )}
                  {campaign.status === "active" && (
                    <Button size="sm" variant="outline">
                      <Pause className="h-4 w-4 mr-1" />
                      Pause
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
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
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label htmlFor="budget" className="text-sm font-medium mb-2 block">
                  Total Budget ($)
                </label>
                <Input
                  id="budget"
                  type="number"
                  placeholder="5000"
                  value={budget}
                  onChange={(e) => setBudget(e.target.value)}
                />
              </div>
              <div>
                <label htmlFor="creative-preference" className="text-sm font-medium mb-2 block">
                  Creative Preference
                </label>
                <Select value={creativePreference} onValueChange={(value: "image" | "video" | "both") => setCreativePreference(value)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="both">Both (Image & Video)</SelectItem>
                    <SelectItem value="image">Image Only</SelectItem>
                    <SelectItem value="video">Video Only</SelectItem>
                  </SelectContent>
                </Select>
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
