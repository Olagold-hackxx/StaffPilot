"use client"

import { useEffect, useState, useCallback } from "react"
import { useParams, useRouter } from "next/navigation"
import { cn } from "@/lib/utils"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { apiClient } from "@/lib/api"
import { useToast } from "@/components/ui/use-toast"
import { 
  ArrowLeft, CheckCircle2, Loader2, Plus, X, Sparkles, 
  Image as ImageIcon, Video, Type, FileText, BarChart3,
  Link as LinkIcon, Building2, MousePointerClick, RefreshCw,
  Youtube, ChevronRight, AlertCircle, Trash2, Download,
  Wand2, Send, MessageSquare
} from "lucide-react"
import ReactMarkdown from "react-markdown"

// Types
interface Headline {
  id: string
  text: string
  type: "short" | "long"
}

interface Description {
  id: string
  text: string
}

interface CampaignAsset {
  id: string
  asset_type: string
  url?: string
  status: string
  platform?: string
}

interface Campaign {
  id: string
  name: string
  description?: string
  status: string
  channels: string[]
  total_budget?: number
  final_url?: string
  business_name?: string
  call_to_action?: string
  headlines?: Headline[]
  descriptions?: Description[]
  ad_strength?: string
  plan?: any
  created_at: string
}

interface ChatMessage {
  id: string
  role: "user" | "assistant"
  content: string
  timestamp: Date
}

// Ad Strength Component
function AdStrengthIndicator({ strength }: { strength: string }) {
  const getStrengthConfig = (s: string) => {
    switch (s) {
      case "excellent":
        return { color: "bg-green-500", text: "Excellent", width: "100%", textColor: "text-green-600" }
      case "good":
        return { color: "bg-blue-500", text: "Good", width: "75%", textColor: "text-blue-600" }
      case "average":
        return { color: "bg-yellow-500", text: "Average", width: "50%", textColor: "text-yellow-600" }
      case "poor":
        return { color: "bg-orange-500", text: "Poor", width: "25%", textColor: "text-orange-600" }
      default:
        return { color: "bg-gray-400", text: "Incomplete", width: "10%", textColor: "text-gray-500" }
    }
  }
  
  const config = getStrengthConfig(strength)
  
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">Ad Strength</span>
        <span className={cn("text-sm font-semibold", config.textColor)}>{config.text}</span>
      </div>
      <div className="h-2 bg-muted rounded-full overflow-hidden">
        <div 
          className={cn("h-full transition-all duration-500", config.color)}
          style={{ width: config.width }}
        />
      </div>
    </div>
  )
}

export default function CampaignWorkspacePage() {
  const params = useParams()
  const router = useRouter()
  const { toast } = useToast()
  
  const [campaign, setCampaign] = useState<Campaign | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  
  // Headlines state
  const [headlines, setHeadlines] = useState<Headline[]>([])
  const [newShortHeadline, setNewShortHeadline] = useState("")
  const [newLongHeadline, setNewLongHeadline] = useState("")
  
  // Descriptions state
  const [descriptions, setDescriptions] = useState<Description[]>([])
  const [newDescription, setNewDescription] = useState("")
  
  // Assets state
  const [images, setImages] = useState<CampaignAsset[]>([])
  const [videos, setVideos] = useState<CampaignAsset[]>([])
  const [generatingImages, setGeneratingImages] = useState(false)
  const [generatingVideo, setGeneratingVideo] = useState(false)
  
  // Text generation states
  const [generatingShortHeadlines, setGeneratingShortHeadlines] = useState(false)
  const [generatingLongHeadlines, setGeneratingLongHeadlines] = useState(false)
  const [generatingDescriptions, setGeneratingDescriptions] = useState(false)
  
  // Chat state
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [chatInput, setChatInput] = useState("")
  const [sendingMessage, setSendingMessage] = useState(false)
  
  // YouTube connection state
  const [youtubeConnected, setYoutubeConnected] = useState(false)

  const loadCampaign = useCallback(async () => {
    try {
      const response = await apiClient.getCampaign(params.id as string) as Campaign
      setCampaign(response)
      
      // Initialize from campaign data
      setHeadlines(response.headlines || [])
      setDescriptions(response.descriptions || [])
      
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to load campaign",
        variant: "destructive",
      })
    } finally {
      setLoading(false)
    }
  }, [params.id, toast])

  useEffect(() => {
    loadCampaign()
  }, [loadCampaign])

  // Check YouTube connection status
  useEffect(() => {
    async function checkYoutubeStatus() {
      try {
        const response = await apiClient.getIntegrationStatus() as { platforms?: Array<{ platform: string; is_connected: boolean }> }
        const youtube = response.platforms?.find(p => p.platform === 'youtube')
        setYoutubeConnected(youtube?.is_connected || false)
      } catch (error) {
        // Silently fail - not critical
      }
    }
    checkYoutubeStatus()
  }, [])

  // Calculate ad strength based on assets
  const calculateAdStrength = useCallback(() => {
    const shortHeadlines = headlines.filter(h => h.type === "short").length
    const longHeadlines = headlines.filter(h => h.type === "long").length
    const descCount = descriptions.length
    const imageCount = images.length
    const videoCount = videos.length
    
    // Performance Max requirements
    // Short headlines: 3-15, Long headlines: 1-5, Descriptions: 1-5
    // Images: 3+, Videos: 1+
    
    let score = 0
    if (shortHeadlines >= 3) score += 20
    if (shortHeadlines >= 10) score += 10
    if (longHeadlines >= 1) score += 15
    if (longHeadlines >= 3) score += 5
    if (descCount >= 1) score += 15
    if (descCount >= 4) score += 5
    if (imageCount >= 3) score += 20
    if (imageCount >= 5) score += 5
    if (videoCount >= 1) score += 5
    
    if (score >= 90) return "excellent"
    if (score >= 70) return "good"
    if (score >= 40) return "average"
    if (score >= 20) return "poor"
    return "incomplete"
  }, [headlines, descriptions, images, videos])

  // Add headline
  const addHeadline = (type: "short" | "long") => {
    const text = type === "short" ? newShortHeadline : newLongHeadline
    if (!text.trim()) return
    
    const maxLength = type === "short" ? 30 : 90
    if (text.length > maxLength) {
      toast({
        title: "Too long",
        description: `${type === "short" ? "Short" : "Long"} headlines must be ${maxLength} characters or less`,
        variant: "destructive",
      })
      return
    }
    
    const newHeadline: Headline = {
      id: Date.now().toString(),
      text: text.trim(),
      type
    }
    
    setHeadlines(prev => [...prev, newHeadline])
    type === "short" ? setNewShortHeadline("") : setNewLongHeadline("")
  }

  // Remove headline
  const removeHeadline = (id: string) => {
    setHeadlines(prev => prev.filter(h => h.id !== id))
  }

  // Add description
  const addDescription = () => {
    if (!newDescription.trim()) return
    
    if (newDescription.length > 90) {
      toast({
        title: "Too long",
        description: "Descriptions must be 90 characters or less",
        variant: "destructive",
      })
      return
    }
    
    const desc: Description = {
      id: Date.now().toString(),
      text: newDescription.trim()
    }
    
    setDescriptions(prev => [...prev, desc])
    setNewDescription("")
  }

  // Remove description
  const removeDescription = (id: string) => {
    setDescriptions(prev => prev.filter(d => d.id !== id))
  }

  // Generate headlines/descriptions with AI
  const generateShortHeadlines = async () => {
    if (!campaign) return
    
    setGeneratingShortHeadlines(true)
    try {
      const response = await apiClient.generateAdText(campaign.id, 'short_headlines', 5)
      
      const newHeadlines: Headline[] = response.generated.map((text, i) => ({
        id: `gen-short-${Date.now()}-${i}`,
        text,
        type: 'short' as const
      }))
      
      setHeadlines(prev => [...prev, ...newHeadlines])
      
      toast({
        title: "Headlines Generated",
        description: `Added ${newHeadlines.length} short headlines`,
      })
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to generate headlines",
        variant: "destructive",
      })
    } finally {
      setGeneratingShortHeadlines(false)
    }
  }

  const generateLongHeadlines = async () => {
    if (!campaign) return
    
    setGeneratingLongHeadlines(true)
    try {
      const response = await apiClient.generateAdText(campaign.id, 'long_headlines', 3)
      
      const newHeadlines: Headline[] = response.generated.map((text, i) => ({
        id: `gen-long-${Date.now()}-${i}`,
        text,
        type: 'long' as const
      }))
      
      setHeadlines(prev => [...prev, ...newHeadlines])
      
      toast({
        title: "Headlines Generated",
        description: `Added ${newHeadlines.length} long headlines`,
      })
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to generate headlines",
        variant: "destructive",
      })
    } finally {
      setGeneratingLongHeadlines(false)
    }
  }

  const generateDescriptionsAI = async () => {
    if (!campaign) return
    
    setGeneratingDescriptions(true)
    try {
      const response = await apiClient.generateAdText(campaign.id, 'descriptions', 3)
      
      const newDescriptions: Description[] = response.generated.map((text, i) => ({
        id: `gen-desc-${Date.now()}-${i}`,
        text
      }))
      
      setDescriptions(prev => [...prev, ...newDescriptions])
      
      toast({
        title: "Descriptions Generated",
        description: `Added ${newDescriptions.length} descriptions`,
      })
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to generate descriptions",
        variant: "destructive",
      })
    } finally {
      setGeneratingDescriptions(false)
    }
  }

  // Save campaign data
  const saveCampaign = async () => {
    if (!campaign) return
    
    setSaving(true)
    try {
      // TODO: Implement API endpoint for updating campaign assets
      await new Promise(resolve => setTimeout(resolve, 500)) // Simulated save
      
      toast({
        title: "Saved",
        description: "Campaign assets updated",
      })
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to save",
        variant: "destructive",
      })
    } finally {
      setSaving(false)
    }
  }

  // Generate images with AI
  const generateImages = async () => {
    if (!campaign) return
    
    setGeneratingImages(true)
    try {
      toast({
        title: "Generating Images",
        description: "AI is creating images for your campaign...",
      })
      
      // TODO: Call actual image generation API
      await new Promise(resolve => setTimeout(resolve, 3000))
      
      // Mock response
      const newImages: CampaignAsset[] = [
        { id: Date.now().toString(), asset_type: "image", url: "https://via.placeholder.com/400x300/3b82f6/ffffff?text=Generated+1", status: "completed" },
        { id: (Date.now() + 1).toString(), asset_type: "image", url: "https://via.placeholder.com/400x300/8b5cf6/ffffff?text=Generated+2", status: "completed" },
        { id: (Date.now() + 2).toString(), asset_type: "image", url: "https://via.placeholder.com/400x300/ec4899/ffffff?text=Generated+3", status: "completed" },
      ]
      
      setImages(prev => [...prev, ...newImages])
      
      toast({
        title: "Images Generated",
        description: `Created ${newImages.length} new images`,
      })
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to generate images",
        variant: "destructive",
      })
    } finally {
      setGeneratingImages(false)
    }
  }

  // AI Chat
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
      const response = await apiClient.campaignChat(campaign.id, chatInput.trim(), chatMessages)
      
      const aiMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: response.response,
        timestamp: new Date()
      }
      setChatMessages(prev => [...prev, aiMessage])
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to send message",
        variant: "destructive",
      })
    } finally {
      setSendingMessage(false)
    }
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

  const adStrength = calculateAdStrength()
  const shortHeadlineCount = headlines.filter(h => h.type === "short").length
  const longHeadlineCount = headlines.filter(h => h.type === "long").length

  return (
    <div className="h-[calc(100vh-6rem)] flex flex-col gap-4">
      {/* Header */}
      <header className="flex items-center justify-between px-1 flex-shrink-0">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" className="h-10 w-10 rounded-full" onClick={() => router.back()}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold tracking-tight">{campaign.name}</h1>
              <Badge variant="secondary" className="uppercase text-[10px]">
                Performance Max
              </Badge>
            </div>
            <p className="text-sm text-muted-foreground">Build your campaign assets</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Button 
            variant="outline" 
            size="sm" 
            onClick={saveCampaign}
            disabled={saving}
          >
            {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <CheckCircle2 className="h-4 w-4 mr-2" />}
            Save
          </Button>
          <Button 
            size="sm" 
            className="bg-primary"
            onClick={() => router.push(`/dashboard/campaigns/${campaign.id}`)}
          >
            Review & Launch
            <ChevronRight className="h-4 w-4 ml-1" />
          </Button>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 grid grid-cols-12 gap-4 min-h-0">
        
        {/* Left Panel - Text Assets */}
        <div className="col-span-4 flex flex-col gap-4 min-h-0">
          
          {/* Ad Strength Card */}
          <Card className="flex-shrink-0">
            <CardContent className="p-4">
              <AdStrengthIndicator strength={adStrength} />
              <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
                <div className="p-2 rounded bg-muted/50">
                  <div className="font-semibold">{shortHeadlineCount}/15</div>
                  <div className="text-muted-foreground">Headlines</div>
                </div>
                <div className="p-2 rounded bg-muted/50">
                  <div className="font-semibold">{descriptions.length}/5</div>
                  <div className="text-muted-foreground">Descriptions</div>
                </div>
                <div className="p-2 rounded bg-muted/50">
                  <div className="font-semibold">{images.length}</div>
                  <div className="text-muted-foreground">Images</div>
                </div>
              </div>
            </CardContent>
          </Card>
          
          {/* Campaign Settings */}
          <Card className="flex-shrink-0">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm flex items-center gap-2">
                <Building2 className="h-4 w-4" />
                Campaign Settings
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center gap-2 text-sm">
                <LinkIcon className="h-4 w-4 text-muted-foreground" />
                <span className="text-muted-foreground">URL:</span>
                <span className="truncate flex-1">{campaign.final_url || "Not set"}</span>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <Building2 className="h-4 w-4 text-muted-foreground" />
                <span className="text-muted-foreground">Business:</span>
                <span>{campaign.business_name || "Not set"}</span>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <MousePointerClick className="h-4 w-4 text-muted-foreground" />
                <span className="text-muted-foreground">CTA:</span>
                <Badge variant="outline" className="capitalize">
                  {campaign.call_to_action?.replace("_", " ") || "Learn More"}
                </Badge>
              </div>
            </CardContent>
          </Card>
          
          {/* Headlines */}
          <Card className="flex-1 min-h-0 flex flex-col">
            <CardHeader className="pb-3 flex-shrink-0">
              <CardTitle className="text-sm flex items-center justify-between">
                <span className="flex items-center gap-2">
                  <Type className="h-4 w-4" />
                  Headlines
                </span>
                <span className="text-xs font-normal text-muted-foreground">
                  {shortHeadlineCount} short, {longHeadlineCount} long
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="flex-1 overflow-hidden flex flex-col gap-3">
              {/* Short headlines */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-xs font-medium text-muted-foreground">
                    Short Headlines (30 chars max) — min 3
                  </label>
                  <Button 
                    size="sm" 
                    variant="ghost" 
                    className="h-6 text-xs px-2"
                    onClick={generateShortHeadlines}
                    disabled={generatingShortHeadlines}
                  >
                    {generatingShortHeadlines ? (
                      <><Loader2 className="h-3 w-3 mr-1 animate-spin" />Generating...</>
                    ) : (
                      <><Wand2 className="h-3 w-3 mr-1" />Generate</>
                    )}
                  </Button>
                </div>
                <div className="flex gap-2">
                  <Input 
                    placeholder="Add a headline..."
                    value={newShortHeadline}
                    onChange={(e) => setNewShortHeadline(e.target.value)}
                    maxLength={30}
                    onKeyDown={(e) => e.key === "Enter" && addHeadline("short")}
                    className="h-8 text-sm"
                  />
                  <Button size="sm" variant="secondary" onClick={() => addHeadline("short")} className="h-8 px-2">
                    <Plus className="h-4 w-4" />
                  </Button>
                </div>
                <div className="text-right text-[10px] text-muted-foreground">{newShortHeadline.length}/30</div>
              </div>
              
              {/* Long headlines */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-xs font-medium text-muted-foreground">
                    Long Headlines (90 chars max) — min 1
                  </label>
                  <Button 
                    size="sm" 
                    variant="ghost" 
                    className="h-6 text-xs px-2"
                    onClick={generateLongHeadlines}
                    disabled={generatingLongHeadlines}
                  >
                    {generatingLongHeadlines ? (
                      <><Loader2 className="h-3 w-3 mr-1 animate-spin" />Generating...</>
                    ) : (
                      <><Wand2 className="h-3 w-3 mr-1" />Generate</>
                    )}
                  </Button>
                </div>
                <div className="flex gap-2">
                  <Input 
                    placeholder="Add a long headline..."
                    value={newLongHeadline}
                    onChange={(e) => setNewLongHeadline(e.target.value)}
                    maxLength={90}
                    onKeyDown={(e) => e.key === "Enter" && addHeadline("long")}
                    className="h-8 text-sm"
                  />
                  <Button size="sm" variant="secondary" onClick={() => addHeadline("long")} className="h-8 px-2">
                    <Plus className="h-4 w-4" />
                  </Button>
                </div>
                <div className="text-right text-[10px] text-muted-foreground">{newLongHeadline.length}/90</div>
              </div>
              
              {/* Headlines list */}
              <ScrollArea className="flex-1">
                <div className="space-y-1.5 pr-2">
                  {headlines.map((h) => (
                    <div 
                      key={h.id} 
                      className={cn(
                        "flex items-center gap-2 p-2 rounded-md text-sm group",
                        h.type === "long" ? "bg-purple-500/10" : "bg-muted/50"
                      )}
                    >
                      <Badge variant="outline" className="text-[10px] shrink-0">
                        {h.type === "short" ? "S" : "L"}
                      </Badge>
                      <span className="flex-1 truncate">{h.text}</span>
                      <Button 
                        variant="ghost" 
                        size="icon" 
                        className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity"
                        onClick={() => removeHeadline(h.id)}
                      >
                        <X className="h-3 w-3" />
                      </Button>
                    </div>
                  ))}
                  {headlines.length === 0 && (
                    <p className="text-xs text-muted-foreground text-center py-4">
                      Add at least 3 short headlines and 1 long headline
                    </p>
                  )}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>
        </div>

        {/* Center Panel - Visual Assets */}
        <div className="col-span-5 flex flex-col gap-4 min-h-0">
          
          {/* Images */}
          <Card className="flex-1 min-h-0 flex flex-col">
            <CardHeader className="pb-3 flex-shrink-0">
              <CardTitle className="text-sm flex items-center justify-between">
                <span className="flex items-center gap-2">
                  <ImageIcon className="h-4 w-4" />
                  Images
                </span>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-normal text-muted-foreground">{images.length} images</span>
                  <Button 
                    size="sm" 
                    variant="default"
                    onClick={generateImages}
                    disabled={generatingImages}
                    className="h-7 text-xs"
                  >
                    {generatingImages ? (
                      <><Loader2 className="h-3 w-3 mr-1 animate-spin" />Generating...</>
                    ) : (
                      <><Wand2 className="h-3 w-3 mr-1" />Generate</>
                    )}
                  </Button>
                </div>
              </CardTitle>
            </CardHeader>
            <CardContent className="flex-1 overflow-hidden">
              <ScrollArea className="h-full">
                {images.length > 0 ? (
                  <div className="grid grid-cols-3 gap-3 pr-2">
                    {images.map((img) => (
                      <div key={img.id} className="relative group rounded-lg overflow-hidden border aspect-square">
                        <img 
                          src={img.url} 
                          alt="Campaign image" 
                          className="w-full h-full object-cover"
                        />
                        <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                          <Button size="icon" variant="secondary" className="h-8 w-8">
                            <Download className="h-4 w-4" />
                          </Button>
                          <Button 
                            size="icon" 
                            variant="destructive" 
                            className="h-8 w-8"
                            onClick={() => setImages(prev => prev.filter(i => i.id !== img.id))}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center h-48 text-center">
                    <ImageIcon className="h-12 w-12 text-muted-foreground/30 mb-3" />
                    <p className="text-sm text-muted-foreground mb-3">No images yet</p>
                    <Button 
                      size="sm" 
                      onClick={generateImages}
                      disabled={generatingImages}
                    >
                      <Wand2 className="h-4 w-4 mr-2" />
                      Generate with AI
                    </Button>
                  </div>
                )}
              </ScrollArea>
            </CardContent>
          </Card>
          
          {/* Videos */}
          <Card className="flex-shrink-0">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm flex items-center justify-between">
                <span className="flex items-center gap-2">
                  <Video className="h-4 w-4" />
                  Videos
                </span>
                <div className="flex items-center gap-2">
                  {!youtubeConnected ? (
                    <Button 
                      size="sm" 
                      variant="outline" 
                      className="h-7 text-xs"
                      onClick={async () => {
                        try {
                          // Get OAuth URL using authenticated API client
                          const url = await apiClient.getOAuthInitUrl('youtube')
                          window.location.href = url
                        } catch (error: any) {
                          toast({
                            title: "Error",
                            description: error.message || "Failed to initiate YouTube connection",
                            variant: "destructive",
                          })
                        }
                      }}
                    >
                      <Youtube className="h-3 w-3 mr-1 text-red-500" />
                      Connect YouTube
                    </Button>
                  ) : (
                    <span className="text-xs text-green-600 flex items-center gap-1">
                      <Youtube className="h-3 w-3 text-red-500" />
                      YouTube Connected
                    </span>
                  )}
                  <Button size="sm" variant="default" className="h-7 text-xs" disabled={generatingVideo}>
                    <Wand2 className="h-3 w-3 mr-1" />
                    Generate
                  </Button>
                </div>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {videos.length > 0 ? (
                <div className="grid gap-3">
                  {videos.map((vid) => (
                    <div key={vid.id} className="rounded-lg border overflow-hidden">
                      <video src={vid.url} controls className="w-full" />
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex items-center gap-4 p-4 border border-dashed rounded-lg">
                  <div className="h-12 w-12 rounded-full bg-muted flex items-center justify-center">
                    <Video className="h-6 w-6 text-muted-foreground" />
                  </div>
                  <div className="flex-1">
                    <p className="text-sm font-medium">Add videos to your campaign</p>
                    <p className="text-xs text-muted-foreground">
                      Generate AI videos or connect YouTube to link existing ones
                    </p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
          
          {/* Descriptions */}
          <Card className="flex-shrink-0">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm flex items-center justify-between">
                <span className="flex items-center gap-2">
                  <FileText className="h-4 w-4" />
                  Descriptions
                </span>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-normal text-muted-foreground">{descriptions.length}/5</span>
                  <Button 
                    size="sm" 
                    variant="ghost" 
                    className="h-6 text-xs px-2"
                    onClick={generateDescriptionsAI}
                    disabled={generatingDescriptions}
                  >
                    {generatingDescriptions ? (
                      <><Loader2 className="h-3 w-3 mr-1 animate-spin" />Generating...</>
                    ) : (
                      <><Wand2 className="h-3 w-3 mr-1" />Generate</>
                    )}
                  </Button>
                </div>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex gap-2">
                <Textarea 
                  placeholder="Add a description (90 chars max)..."
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  maxLength={90}
                  className="min-h-[60px] text-sm resize-none"
                />
                <Button size="sm" variant="secondary" onClick={addDescription} className="h-[60px] px-3">
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
              <div className="text-right text-[10px] text-muted-foreground">{newDescription.length}/90</div>
              
              {descriptions.length > 0 && (
                <div className="space-y-2">
                  {descriptions.map((d) => (
                    <div key={d.id} className="flex items-start gap-2 p-2 rounded-md bg-muted/50 text-sm group">
                      <span className="flex-1">{d.text}</span>
                      <Button 
                        variant="ghost" 
                        size="icon" 
                        className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                        onClick={() => removeDescription(d.id)}
                      >
                        <X className="h-3 w-3" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right Panel - AI Chat */}
        <div className="col-span-3 flex flex-col min-h-0">
          <Card className="flex-1 flex flex-col min-h-0">
            <CardHeader className="pb-3 flex-shrink-0">
              <CardTitle className="text-sm flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-primary" />
                AI Assistant
              </CardTitle>
            </CardHeader>
            <CardContent className="flex-1 flex flex-col min-h-0 gap-3">
              <ScrollArea className="flex-1">
                <div className="space-y-3 pr-2">
                  {chatMessages.length === 0 ? (
                    <div className="text-center py-8">
                      <MessageSquare className="h-10 w-10 text-muted-foreground/30 mx-auto mb-3" />
                      <p className="text-sm text-muted-foreground">
                        Ask for help with headlines, descriptions, or creative direction
                      </p>
                      <div className="mt-4 space-y-2">
                        <Button 
                          variant="outline" 
                          size="sm" 
                          className="w-full text-xs justify-start"
                          onClick={() => setChatInput("Generate 5 compelling headlines for my campaign")}
                        >
                          <Wand2 className="h-3 w-3 mr-2" />
                          Generate headlines
                        </Button>
                        <Button 
                          variant="outline" 
                          size="sm" 
                          className="w-full text-xs justify-start"
                          onClick={() => setChatInput("Suggest descriptions that highlight urgency")}
                        >
                          <Wand2 className="h-3 w-3 mr-2" />
                          Suggest descriptions
                        </Button>
                      </div>
                    </div>
                  ) : (
                    chatMessages.map((msg) => (
                      <div 
                        key={msg.id}
                        className={cn(
                          "p-3 rounded-lg text-sm",
                          msg.role === "user" 
                            ? "bg-primary text-primary-foreground ml-4" 
                            : "bg-muted mr-4 prose prose-sm dark:prose-invert max-w-none"
                        )}
                      >
                        {msg.role === "user" ? (
                          msg.content
                        ) : (
                          <ReactMarkdown
                            components={{
                              strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
                              p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                              ul: ({ children }) => <ul className="list-disc list-inside mb-2 space-y-1">{children}</ul>,
                              ol: ({ children }) => <ol className="list-decimal list-inside mb-2 space-y-1">{children}</ol>,
                              li: ({ children }) => <li>{children}</li>,
                            }}
                          >
                            {msg.content}
                          </ReactMarkdown>
                        )}
                      </div>
                    ))
                  )}
                  {sendingMessage && (
                    <div className="flex items-center gap-2 p-3 bg-muted rounded-lg mr-4">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      <span className="text-sm text-muted-foreground">Thinking...</span>
                    </div>
                  )}
                </div>
              </ScrollArea>
              
              <div className="flex gap-2 flex-shrink-0">
                <Input 
                  placeholder="Ask for help..."
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && sendChatMessage()}
                  className="h-9"
                />
                <Button 
                  size="icon" 
                  onClick={sendChatMessage}
                  disabled={sendingMessage || !chatInput.trim()}
                  className="h-9 w-9"
                >
                  <Send className="h-4 w-4" />
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
