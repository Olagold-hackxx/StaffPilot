"use client"

import { useEffect, useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { apiClient, Capability as ApiCapability, AgentExecution } from "@/lib/api"
import { useToast } from "@/components/ui/use-toast"
import { 
  FileText, Plus, Loader2, CheckCircle2, Clock, 
  Facebook, Instagram, Linkedin, Twitter, Music,
  Sparkles, Image, Video, Calendar, Trash2, Pause, Play,
  Send, Eye, Filter, Search, X
} from "lucide-react"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Badge } from "@/components/ui/badge"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Switch } from "@/components/ui/switch"
import { Label } from "@/components/ui/label"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

type Capability = ApiCapability & {
  integrations_connected?: number
  integrations_required?: string[]
}


interface PublishedPost {
  id: string
  platform: string
  content: string
  status: "published" | "failed" | "skipped"
  post_id?: string
  published_at?: string
  created_at: string
  execution_id: string
  images?: string[]
  error?: string
}

interface ScheduledPost {
  id: string
  name: string
  schedule_type: "one_time" | "daily" | "weekly" | "monthly"
  schedule_config: any
  request: string
  platforms: string[]
  include_images: boolean
  include_video: boolean
  next_run_at: string
  last_run_at?: string
  is_active: boolean
  status: string
  total_runs: number
  successful_runs: number
  failed_runs: number
  start_date: string
  end_date?: string
  created_at: string
}

type Execution = AgentExecution

const platformIcons: Record<string, any> = {
  facebook: Facebook,
  instagram: Instagram,
  linkedin: Linkedin,
  twitter: Twitter,
  tiktok: Music,
}

export default function ContentPage() {
  const { toast } = useToast()
  const [capability, setCapability] = useState<Capability | null>(null)
  const [loading, setLoading] = useState(true)
  // Submission state for the create dialog; we do not block other executions with it
  const [submitting, setSubmitting] = useState(false)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [activeTab, setActiveTab] = useState("published")
  
  // Form state
  const [request, setRequest] = useState("")
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>([])
  const [includeImages, setIncludeImages] = useState(false)
  const [includeVideo, setIncludeVideo] = useState(false)
  const [isScheduled, setIsScheduled] = useState(false)
  const [scheduleName, setScheduleName] = useState("")
  const [scheduleType, setScheduleType] = useState<"one_time" | "daily" | "weekly" | "monthly">("daily")
  const [scheduleHour, setScheduleHour] = useState(9)
  const [scheduleMinute, setScheduleMinute] = useState(0)
  const [startDate, setStartDate] = useState("")
  const [endDate, setEndDate] = useState("")
  
  // Data state
  const [publishedPosts, setPublishedPosts] = useState<PublishedPost[]>([])
  const [scheduledPosts, setScheduledPosts] = useState<ScheduledPost[]>([])
  const [executions, setExecutions] = useState<Execution[]>([])
  const [currentExecution, setCurrentExecution] = useState<Execution | null>(null)
  
  // Filter state
  const [searchQuery, setSearchQuery] = useState("")
  const [platformFilter, setPlatformFilter] = useState<string>("all")
  const [statusFilter, setStatusFilter] = useState<string>("all")


  useEffect(() => {
    loadData()
  }, [])

  async function loadData() {
    try {
      setLoading(true)
      // Get active assistant
      const assistants = await apiClient.listAssistants()
      const digitalMarketer = assistants.assistants?.find(
        (a: any) => a.assistant_type === "digital_marketer" && a.is_active
      )

      if (!digitalMarketer) {
        toast({
          title: "Assistant Required",
          description: "Please activate the Digital Marketer assistant first",
          variant: "destructive",
        })
        return
      }

      // Get content creation capability
      const capabilities = await apiClient.getCapabilities(digitalMarketer.id)
      const contentCapability = capabilities.capabilities?.find(
        (c: any) => c.capability_type === "content_creation"
      )

      if (contentCapability) {
        setCapability(contentCapability)
        
        // Load all executions
        const allExecutions = await apiClient.listAgentExecutions(
            digitalMarketer.id,
            contentCapability.id,
          undefined,
          100,
          0
        )
        setExecutions(allExecutions.executions || [])
        
        // Extract published posts from completed executions
        const posts: PublishedPost[] = []
        for (const exec of allExecutions.executions || []) {
          if (exec.status === "completed" && exec.result?.content_items) {
            for (const item of exec.result.content_items || []) {
              posts.push({
                id: item.id || `${exec.id}-${item.platform}`,
                platform: item.platform || "unknown",
                content: item.content || exec.result?.content || "",
                status: item.status === "published" ? "published" : item.status === "failed" ? "failed" : "skipped",
                post_id: item.post_id,
                    published_at: exec.completed_at,
                    created_at: exec.created_at || new Date().toISOString(),
                execution_id: exec.id,
                images: item.images,
                error: typeof item.error === 'string' ? item.error : item.error?.error || item.error?.message || (typeof item.error === 'object' ? JSON.stringify(item.error) : String(item.error || ''))
                  })
                }
              }
            }
        setPublishedPosts(posts.sort((a, b) => 
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        ))

        // Load scheduled posts
        const scheduled = await apiClient.listScheduledPosts(digitalMarketer.id, undefined)
        setScheduledPosts((scheduled.scheduled_posts || []).sort((a: ScheduledPost, b: ScheduledPost) => 
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        ))
      }
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to load data",
        variant: "destructive",
      })
    } finally {
      setLoading(false)
    }
  }


  async function handleCreateContent() {
    if (!capability || !request.trim()) return

    setSubmitting(true)
    try {
      const assistants = await apiClient.listAssistants()
      const digitalMarketer = assistants.assistants?.find(
        (a: any) => a.assistant_type === "digital_marketer" && a.is_active
      )

      if (!digitalMarketer) {
        throw new Error("Digital Marketer assistant not found")
      }

      if (isScheduled) {
        if (!scheduleName.trim() || !startDate) {
          throw new Error("Schedule name and start date are required")
        }

        const scheduleConfig: any = {
          hour: scheduleHour,
          minute: scheduleMinute,
        }

        if (scheduleType === "weekly") {
          scheduleConfig.days_of_week = [0, 1, 2, 3, 4, 5, 6]
        } else if (scheduleType === "monthly") {
          scheduleConfig.days_of_month = [1]
        }

        await apiClient.createScheduledPost({
          name: scheduleName.trim(),
          assistant_id: digitalMarketer.id,
          capability_id: capability.id,
          schedule_type: scheduleType,
          schedule_config: scheduleConfig,
          request: request.trim(),
          platforms: selectedPlatforms,
          include_images: includeImages,
          include_video: includeVideo,
          start_date: new Date(startDate).toISOString(),
          end_date: endDate ? new Date(endDate).toISOString() : undefined,
        })

        setSubmitting(false)
        setShowCreateDialog(false)
        resetForm()
        loadData()
        toast({
          title: "Success",
          description: "Scheduled post created successfully!",
        })
      } else {
        const execution = await apiClient.executeAgent({
          assistant_id: digitalMarketer.id,
          capability_id: capability.id,
          request_type: "create_content",
          request_data: {
            request: request.trim(),
            platforms: selectedPlatforms,
            include_images: includeImages,
            include_video: includeVideo,
          },
        })

        setCurrentExecution(execution.execution || null)
        if (execution.execution) {
          // Prepend to local list so we can show status immediately
          setExecutions((prev) => [execution.execution as Execution, ...prev])
        }
        
        if (execution.execution?.id) {
          pollExecutionStatus(execution.execution.id)
        }

        // Allow users to queue another action right away
        setSubmitting(false)
        setShowCreateDialog(false)
        resetForm()
      }
    } catch (error: any) {
      setSubmitting(false)
      toast({
        title: "Error",
        description: error.message || "Failed to create content",
        variant: "destructive",
      })
    }
  }

  function resetForm() {
    setRequest("")
    setScheduleName("")
    setIsScheduled(false)
    setStartDate("")
    setEndDate("")
    setSelectedPlatforms([])
    setIncludeImages(false)
    setIncludeVideo(false)
    setScheduleType("daily")
    setScheduleHour(9)
    setScheduleMinute(0)
  }

  async function pollExecutionStatus(executionId: string) {
    const maxAttempts = 300
    let attempts = 0
    let pollInterval: NodeJS.Timeout | null = null

    const poll = async () => {
      try {
        attempts++
        const result = await apiClient.getAgentExecution(executionId)
        const execution = result.execution

        if (execution) {
          setCurrentExecution(execution)
          // Keep execution list in sync so each action shows its own status
          setExecutions((prev) => {
            const existingIndex = prev.findIndex((e) => e.id === execution.id)
            if (existingIndex >= 0) {
              const updated = [...prev]
              updated[existingIndex] = execution as Execution
              return updated
            }
            return [execution as Execution, ...prev]
          })

          if (execution.status === "completed") {
            if (pollInterval) clearInterval(pollInterval)
            setSubmitting(false)
            loadData()
            toast({
              title: "Success",
              description: "Content created and published successfully!",
            })
            return
          }

          if (execution.status === "failed") {
            if (pollInterval) clearInterval(pollInterval)
            setSubmitting(false)
            toast({
              title: "Error",
              description: execution.error_message || "Content creation failed",
              variant: "destructive",
            })
            return
          }

          if (attempts >= maxAttempts) {
            if (pollInterval) clearInterval(pollInterval)
            setSubmitting(false)
            toast({
              title: "Timeout",
              description: "Content creation is taking longer than expected. Please check back later.",
              variant: "destructive",
            })
            return
          }
        }
      } catch (error: any) {
        console.error("Error polling execution status:", error)
      }
    }

    await poll()
    pollInterval = setInterval(poll, 1000)
  }

  async function handleDeleteScheduledPost(id: string) {
    try {
      await apiClient.deleteScheduledPost(id)
      loadData()
      toast({
        title: "Success",
        description: "Scheduled post deleted",
      })
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to delete scheduled post",
        variant: "destructive",
      })
    }
  }

  async function handleToggleScheduledPost(id: string, isActive: boolean) {
    try {
      await apiClient.updateScheduledPost(id, { is_active: !isActive })
      loadData()
      toast({
        title: "Success",
        description: `Scheduled post ${!isActive ? "activated" : "paused"}`,
      })
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to update scheduled post",
        variant: "destructive",
      })
    }
  }

  // Filter functions
  const filteredPublishedPosts = publishedPosts.filter(post => {
    const matchesSearch = !searchQuery || 
      post.content.toLowerCase().includes(searchQuery.toLowerCase()) ||
      post.platform.toLowerCase().includes(searchQuery.toLowerCase())
    const matchesPlatform = platformFilter === "all" || post.platform === platformFilter
    const matchesStatus = statusFilter === "all" || post.status === statusFilter
    return matchesSearch && matchesPlatform && matchesStatus
  })

  const filteredScheduledPosts = scheduledPosts.filter(post => {
    const matchesSearch = !searchQuery || 
      post.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      post.request.toLowerCase().includes(searchQuery.toLowerCase())
    return matchesSearch
  })

  const filteredExecutions = executions.filter(exec => {
    const matchesSearch = !searchQuery || 
      (exec.result?.content || "").toLowerCase().includes(searchQuery.toLowerCase())
    return matchesSearch && exec.request_type === "create_content"
  })

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!capability) {
    return (
      <Card>
        <CardContent className="p-6">
          <p className="text-muted-foreground">Content Creation capability not set up. Please configure it first.</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Content Creation</h1>
          <p className="text-muted-foreground">Create, schedule, and manage your social media content</p>
        </div>
        <Button onClick={() => setShowCreateDialog(true)} size="lg">
          <Plus className="h-4 w-4 mr-2" />
          Create Content
        </Button>
      </div>

      {/* Execution Status */}
      {currentExecution && currentExecution.status !== "completed" && currentExecution.status !== "failed" && (
        <Card className="border-primary">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              {currentExecution.status === "running" ? (
                <Loader2 className="h-5 w-5 animate-spin" />
              ) : (
                <Clock className="h-5 w-5" />
              )}
              {currentExecution.status === "running" ? "Creating Content..." : "Queued for Processing"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">
                Status: <span className="capitalize font-medium">{currentExecution.status}</span>
                </p>
                {currentExecution.steps_executed && currentExecution.steps_executed.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-3">
                    {currentExecution.steps_executed.map((step: any, idx: number) => (
                    <Badge key={idx} variant="secondary" className="text-xs">
                      <CheckCircle2 className="h-3 w-3 mr-1" />
                      {typeof step === 'string' ? step : step.task || step}
                        </Badge>
                      ))}
                  </div>
                )}
                  </div>
          </CardContent>
        </Card>
      )}

      {/* Main Content Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList>
          <TabsTrigger value="published">
            <Send className="h-4 w-4 mr-2" />
            Published Posts
            {publishedPosts.length > 0 && (
              <Badge variant="secondary" className="ml-2">{publishedPosts.length}</Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="scheduled">
            <Calendar className="h-4 w-4 mr-2" />
            Scheduled Posts
            {scheduledPosts.length > 0 && (
              <Badge variant="secondary" className="ml-2">{scheduledPosts.length}</Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="history">
            <FileText className="h-4 w-4 mr-2" />
            History
      {executions.length > 0 && (
              <Badge variant="secondary" className="ml-2">{executions.length}</Badge>
            )}
          </TabsTrigger>
        </TabsList>

        {/* Published Posts Tab */}
        <TabsContent value="published" className="space-y-4">
          {/* Filters */}
        <Card>
            <CardContent className="p-4">
              <div className="flex flex-col sm:flex-row gap-4">
                <div className="flex-1 relative">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Search posts..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-9"
                  />
                  {searchQuery && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="absolute right-2 top-1/2 transform -translate-y-1/2 h-6 w-6 p-0"
                      onClick={() => setSearchQuery("")}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                )}
              </div>
                <Select value={platformFilter} onValueChange={setPlatformFilter}>
                  <SelectTrigger className="w-[180px]">
                    <SelectValue placeholder="Platform" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Platforms</SelectItem>
                    <SelectItem value="facebook">Facebook</SelectItem>
                    <SelectItem value="instagram">Instagram</SelectItem>
                    <SelectItem value="linkedin">LinkedIn</SelectItem>
                    <SelectItem value="twitter">Twitter</SelectItem>
                    <SelectItem value="tiktok">TikTok</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={statusFilter} onValueChange={setStatusFilter}>
                  <SelectTrigger className="w-[180px]">
                    <SelectValue placeholder="Status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Status</SelectItem>
                    <SelectItem value="published">Published</SelectItem>
                    <SelectItem value="failed">Failed</SelectItem>
                    <SelectItem value="skipped">Skipped</SelectItem>
                  </SelectContent>
                </Select>
            </div>
          </CardContent>
        </Card>

          {/* Posts Grid */}
          {filteredPublishedPosts.length === 0 ? (
        <Card>
              <CardContent className="p-12 text-center">
                <Send className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                <h3 className="text-lg font-semibold mb-2">No Published Posts</h3>
                <p className="text-muted-foreground mb-4">
                  {publishedPosts.length === 0 
                    ? "Create your first content to see it here"
                    : "No posts match your filters"}
                </p>
                {publishedPosts.length === 0 && (
                  <Button onClick={() => setShowCreateDialog(true)}>
                    <Plus className="h-4 w-4 mr-2" />
                    Create Content
                  </Button>
                )}
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {filteredPublishedPosts.map((post) => {
                const PlatformIcon = platformIcons[post.platform] || FileText
                return (
                  <Card key={post.id} className="hover:shadow-md transition-shadow">
          <CardHeader>
                      <div className="flex items-start justify-between">
                        <div className="flex items-center gap-2">
                          <PlatformIcon className="h-5 w-5" />
                          <div>
                            <CardTitle className="text-base capitalize">{post.platform}</CardTitle>
                            <CardDescription className="text-xs">
                              {post.published_at 
                                ? new Date(post.published_at).toLocaleString()
                                : new Date(post.created_at).toLocaleString()}
                            </CardDescription>
                      </div>
                    </div>
                        <Badge 
                          variant={
                            post.status === "published" ? "default" :
                            post.status === "failed" ? "destructive" : "secondary"
                          }
                        >
                          {post.status}
                    </Badge>
                  </div>
          </CardHeader>
          <CardContent>
                      <p className="text-sm line-clamp-4 mb-4">{post.content}</p>
                      {post.post_id && (
                        <p className="text-xs text-muted-foreground mb-2">
                          Post ID: {post.post_id.substring(0, 20)}...
                        </p>
                      )}
                      {post.error && (
                        <p className="text-xs text-destructive mt-2">
                          {typeof post.error === 'string' 
                            ? post.error 
                            : typeof post.error === 'object' && post.error !== null
                              ? ((post.error as any).error || (post.error as any).message || JSON.stringify(post.error))
                              : String(post.error || '')}
                          </p>
                        )}
                      {post.images && post.images.length > 0 && (
                        <div className="flex gap-2 mt-3">
                          <Badge variant="outline" className="text-xs">
                            <Image className="h-3 w-3 mr-1" />
                            {post.images.length} image{post.images.length > 1 ? 's' : ''}
                    </Badge>
                  </div>
                      )}
          </CardContent>
        </Card>
                )
              })}
            </div>
      )}
        </TabsContent>

        {/* Scheduled Posts Tab */}
        <TabsContent value="scheduled" className="space-y-4">
          {/* Search */}
        <Card>
            <CardContent className="p-4">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search scheduled posts..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-9"
                />
                {searchQuery && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="absolute right-2 top-1/2 transform -translate-y-1/2 h-6 w-6 p-0"
                    onClick={() => setSearchQuery("")}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Scheduled Posts List */}
          {filteredScheduledPosts.length === 0 ? (
            <Card>
              <CardContent className="p-12 text-center">
                <Calendar className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                <h3 className="text-lg font-semibold mb-2">No Scheduled Posts</h3>
                <p className="text-muted-foreground mb-4">
                  {scheduledPosts.length === 0
                    ? "Create a scheduled post to automate your content publishing"
                    : "No scheduled posts match your search"}
                </p>
                {scheduledPosts.length === 0 && (
                  <Button onClick={() => {
                    setIsScheduled(true)
                    setShowCreateDialog(true)
                  }}>
                    <Plus className="h-4 w-4 mr-2" />
                    Create Scheduled Post
                  </Button>
                )}
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {filteredScheduledPosts.map((sp) => (
                <Card key={sp.id}>
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between">
                      <div className="flex-1 space-y-2">
                        <div className="flex items-center gap-2">
                          <Calendar className="h-4 w-4 text-muted-foreground" />
                          <h3 className="font-semibold">{sp.name}</h3>
                          <Badge variant={sp.is_active ? "default" : "secondary"}>
                            {sp.is_active ? "Active" : "Paused"}
                          </Badge>
                    </div>
                        <p className="text-sm text-muted-foreground line-clamp-2">{sp.request}</p>
                        <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                          <span className="capitalize">{sp.schedule_type} schedule</span>
                          <span>•</span>
                          <span>Next: {new Date(sp.next_run_at).toLocaleString()}</span>
                          {sp.last_run_at && (
                            <>
                              <span>•</span>
                              <span>Last: {new Date(sp.last_run_at).toLocaleString()}</span>
                            </>
                          )}
                          <span>•</span>
                          <span>{sp.successful_runs} successful, {sp.failed_runs} failed</span>
                  </div>
                        <div className="flex flex-wrap gap-2 mt-2">
                          {sp.platforms.map((platform) => {
                            const Icon = platformIcons[platform] || FileText
                            return (
                              <Badge key={platform} variant="outline" className="text-xs">
                                <Icon className="h-3 w-3 mr-1" />
                                {platform}
                              </Badge>
                            )
                          })}
                          {sp.include_images && (
                            <Badge variant="outline" className="text-xs">
                              <Image className="h-3 w-3 mr-1" />
                              Images
                            </Badge>
                          )}
                          {sp.include_video && (
                            <Badge variant="outline" className="text-xs">
                              <Video className="h-3 w-3 mr-1" />
                              Video
                            </Badge>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2 ml-4">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleToggleScheduledPost(sp.id, sp.is_active)}
                    >
                      {sp.is_active ? (
                        <Pause className="h-4 w-4" />
                      ) : (
                        <Play className="h-4 w-4" />
                      )}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDeleteScheduledPost(sp.id)}
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* History Tab */}
        <TabsContent value="history" className="space-y-4">
          {/* Search */}
          <Card>
            <CardContent className="p-4">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search execution history..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-9"
                />
                {searchQuery && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="absolute right-2 top-1/2 transform -translate-y-1/2 h-6 w-6 p-0"
                    onClick={() => setSearchQuery("")}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                )}
            </div>
          </CardContent>
        </Card>

          {/* Executions List */}
          {filteredExecutions.length === 0 ? (
            <Card>
              <CardContent className="p-12 text-center">
                <FileText className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                <h3 className="text-lg font-semibold mb-2">No Execution History</h3>
                <p className="text-muted-foreground">
                  {executions.length === 0
                    ? "Your content creation history will appear here"
                    : "No executions match your search"}
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {filteredExecutions.map((execution) => (
                <Card key={execution.id}>
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between">
                      <div className="flex-1 space-y-2">
                        <div className="flex items-center gap-2">
                          {execution.status === "running" ? (
                            <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                          ) : execution.status === "completed" ? (
                            <CheckCircle2 className="h-4 w-4 text-green-500" />
                          ) : execution.status === "failed" ? (
                            <X className="h-4 w-4 text-red-500" />
                          ) : (
                            <Clock className="h-4 w-4 text-muted-foreground" />
                          )}
                          <span className="font-medium capitalize">{execution.status}</span>
                          <Badge variant={
                            execution.status === "completed" ? "default" :
                            execution.status === "running" ? "secondary" :
                            execution.status === "failed" ? "destructive" : "outline"
                          }>
                            {execution.status}
                          </Badge>
                    </div>
                        <p className="text-sm text-muted-foreground line-clamp-2">
                          {(() => {
                            const content = execution.result?.content
                            const request = (execution as any).request_data?.request
                            if (typeof content === 'string') return content
                            if (typeof request === 'string') return request
                            return "Content Creation"
                          })()}
                        </p>
                        <div className="flex items-center gap-3 text-xs text-muted-foreground">
                          <span>{execution.created_at ? new Date(execution.created_at).toLocaleString() : 'N/A'}</span>
                          {execution.completed_at && (
                            <>
                              <span>•</span>
                              <span>Completed: {new Date(execution.completed_at).toLocaleString()}</span>
                            </>
                          )}
                          {(execution as any).execution_time_ms && (
                            <>
                              <span>•</span>
                              <span>Duration: {((execution as any).execution_time_ms / 1000).toFixed(1)}s</span>
                            </>
                          )}
                  </div>
                        {execution.result?.platform_contents && (
                          <div className="flex flex-wrap gap-2 mt-2">
                            {Object.keys(execution.result.platform_contents).map((platform) => {
                              const Icon = platformIcons[platform] || FileText
                              return (
                                <Badge key={platform} variant="outline" className="text-xs">
                                  <Icon className="h-3 w-3 mr-1" />
                                  {platform}
                  </Badge>
                              )
                            })}
                    </div>
                  )}
                    </div>
                      {execution.result && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            // Could open a detail modal here
                            toast({
                              title: "Execution Details",
                              description: `Status: ${execution.status}. Check the Published Posts tab to see results.`,
                            })
                          }}
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                  )}
                </div>
              </CardContent>
            </Card>
              ))}
      </div>
          )}
        </TabsContent>

        {/* Assets Tab */}
        </Tabs>

      {/* Create Content Dialog */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Create New Content</DialogTitle>
            <DialogDescription>
              The AI will create content based on your company information from uploaded documents. Add any additional context, tone preferences, or specific instructions below.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label htmlFor="content-request" className="text-sm font-medium mb-2 block">
                Additional Context & Instructions (Optional)
              </Label>
              <p className="text-xs text-muted-foreground mb-2">
                The AI already knows about your company from your uploaded documents. Use this field to provide:
              </p>
              <ul className="text-xs text-muted-foreground mb-3 list-disc list-inside space-y-1">
                <li>Additional context or specific information for this content</li>
                <li>Tone, style, or flavor preferences</li>
                <li>Rules or guidelines to follow</li>
                <li>Fine-tuning details or particular focus areas</li>
              </ul>
              <Textarea
                id="content-request"
                placeholder="Example: Make it more casual and friendly, focus on the healthcare benefits, include a call-to-action for a free consultation"
                value={request}
                onChange={(e) => setRequest(e.target.value)}
                rows={4}
              />
            </div>
            <div>
              <Label htmlFor="platforms" className="text-sm font-medium mb-2 block">
                Platforms (Optional)
              </Label>
              <div id="platforms" className="flex flex-wrap gap-2">
                {["facebook", "instagram", "linkedin", "twitter", "tiktok"].map((platform) => {
                  const Icon = platformIcons[platform]
                  return (
                    <Button
                      key={platform}
                      type="button"
                      variant={selectedPlatforms.includes(platform) ? "default" : "outline"}
                      size="sm"
                      onClick={() => {
                        if (selectedPlatforms.includes(platform)) {
                          setSelectedPlatforms(selectedPlatforms.filter(p => p !== platform))
                        } else {
                          setSelectedPlatforms([...selectedPlatforms, platform])
                        }
                      }}
                    >
                      <Icon className="h-4 w-4 mr-1" />
                      {platform.charAt(0).toUpperCase() + platform.slice(1)}
                    </Button>
                  )
                })}
              </div>
            </div>
            <div className="flex flex-col gap-4 pt-2 border-t">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Calendar className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <Label htmlFor="is-scheduled" className="text-sm font-medium cursor-pointer">
                      Schedule as Recurring Post
                    </Label>
                    <p className="text-xs text-muted-foreground">
                      Set up automatic posting on a schedule
                    </p>
                  </div>
                </div>
                <Switch
                  id="is-scheduled"
                  checked={isScheduled}
                  onCheckedChange={setIsScheduled}
                />
              </div>
              {isScheduled && (
                <div className="space-y-4 pt-2 border-t">
                  <div>
                    <Label htmlFor="schedule-name" className="text-sm font-medium mb-2 block">
                      Schedule Name *
                    </Label>
                    <Input
                      id="schedule-name"
                      placeholder="e.g., Daily Morning Posts"
                      value={scheduleName}
                      onChange={(e) => setScheduleName(e.target.value)}
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label htmlFor="schedule-type" className="text-sm font-medium mb-2 block">
                        Schedule Type
                      </Label>
                      <Select value={scheduleType} onValueChange={(v: any) => setScheduleType(v)}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="one_time">One Time</SelectItem>
                          <SelectItem value="daily">Daily</SelectItem>
                          <SelectItem value="weekly">Weekly</SelectItem>
                          <SelectItem value="monthly">Monthly</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label htmlFor="start-date" className="text-sm font-medium mb-2 block">
                        Start Date *
                      </Label>
                      <Input
                        id="start-date"
                        type="datetime-local"
                        value={startDate}
                        onChange={(e) => setStartDate(e.target.value)}
                      />
                    </div>
                  </div>
                  {scheduleType !== "one_time" && (
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label htmlFor="schedule-hour" className="text-sm font-medium mb-2 block">
                          Hour (0-23)
                        </Label>
                        <Input
                          id="schedule-hour"
                          type="number"
                          min="0"
                          max="23"
                          value={scheduleHour}
                          onChange={(e) => setScheduleHour(parseInt(e.target.value) || 9)}
                        />
                      </div>
                      <div>
                        <Label htmlFor="schedule-minute" className="text-sm font-medium mb-2 block">
                          Minute (0-59)
                        </Label>
                        <Input
                          id="schedule-minute"
                          type="number"
                          min="0"
                          max="59"
                          value={scheduleMinute}
                          onChange={(e) => setScheduleMinute(parseInt(e.target.value) || 0)}
                        />
                      </div>
                    </div>
                  )}
                  <div>
                    <Label htmlFor="end-date" className="text-sm font-medium mb-2 block">
                      End Date (Optional)
                    </Label>
                    <Input
                      id="end-date"
                      type="datetime-local"
                      value={endDate}
                      onChange={(e) => setEndDate(e.target.value)}
                    />
                  </div>
                </div>
              )}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Image className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <Label htmlFor="include-images" className="text-sm font-medium cursor-pointer">
                      Include Images
                    </Label>
                    <p className="text-xs text-muted-foreground">
                      Generate AI images for your content
                    </p>
                  </div>
                </div>
                <Switch
                  id="include-images"
                  checked={includeImages}
                  onCheckedChange={setIncludeImages}
                />
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Video className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <Label htmlFor="include-video" className="text-sm font-medium cursor-pointer">
                      Include Video
                    </Label>
                    <p className="text-xs text-muted-foreground">
                      Generate AI video content
                    </p>
                  </div>
                </div>
                <Switch
                  id="include-video"
                  checked={includeVideo}
                  onCheckedChange={setIncludeVideo}
                />
              </div>
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-4">
            <Button variant="outline" onClick={() => {
              setShowCreateDialog(false)
              resetForm()
            }}>
              Cancel
            </Button>
            <Button 
              onClick={handleCreateContent} 
              disabled={submitting || (isScheduled && (!scheduleName.trim() || !startDate))}
            >
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  {isScheduled ? "Creating Schedule..." : "Creating..."}
                </>
              ) : (
                <>
                  {isScheduled ? (
                    <>
                      <Calendar className="h-4 w-4 mr-2" />
                      Schedule Post
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-4 w-4 mr-2" />
                      Create with AI
                    </>
                  )}
                </>
              )}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
