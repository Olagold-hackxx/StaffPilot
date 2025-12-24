"use client"

import { useEffect, useState } from "react"
import { useSearchParams } from "next/navigation"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { apiClient } from "@/lib/api"
import { useToast } from "@/components/ui/use-toast"
import { 
  Share2, CheckCircle2, ExternalLink, Bot, 
  Facebook, Instagram, Linkedin, Twitter, Music,
  Mail, Calendar, Video, FileText, BarChart3,
  MessageSquare, Users, Settings, Calendar as CalendarIcon, X, AlertCircle, Building2
} from "lucide-react"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Badge } from "@/components/ui/badge"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Separator } from "@/components/ui/separator"

interface Assistant {
  id: string
  assistant_type: string
  type?: string  // Legacy field, use assistant_type instead
  name: string
  description: string
  is_active: boolean
}

interface IntegrationStatus {
  platform: string
  is_connected: boolean
  integration_id?: string
  platform_username?: string
  platform_name?: string
  connected_at?: string
  is_active: boolean
}

interface IntegrationDetails {
  id: string
  platform: string
  platform_username?: string
  platform_name?: string
  profile_data?: Record<string, unknown>
  pages?: Array<Record<string, unknown>>
  organizations?: Array<Record<string, unknown>>
  default_page_id?: string
  oauth1_configured?: boolean  // For Twitter: whether OAuth 1.0a is configured for media uploads
  is_active: boolean
  is_verified: boolean
  created_at: string
  updated_at?: string
  last_used_at?: string
}

interface IntegrationConfig {
  id: string
  name: string
  description: string
  icon: React.ComponentType<{ className?: string }>
  category: string
  required: boolean
  platforms: string[]
}

// Integration configurations for each assistant type
const integrationConfigs: Record<string, IntegrationConfig[]> = {
  digital_marketer: [
    {
      id: "social_media",
      name: "Social Media",
      description: "Connect social media accounts for content creation and management",
      icon: Share2,
      category: "Content Creation",
      required: false,
      platforms: ["facebook", "instagram", "linkedin", "twitter", "tiktok"],
    },
    {
      id: "meta_ads",
      name: "Meta Ads",
      description: "Manage Facebook and Instagram advertising campaigns",
      icon: BarChart3,
      category: "Advertising",
      required: false,
      platforms: ["meta_ads"],
    },
    {
      id: "google_ads",
      name: "Google Ads",
      description: "Manage Google advertising campaigns",
      icon: BarChart3,
      category: "Advertising",
      required: false,
      platforms: ["google_ads"],
    },
    {
      id: "analytics",
      name: "Google Analytics",
      description: "Track performance metrics and insights",
      icon: BarChart3,
      category: "Analytics",
      required: false,
      platforms: ["google_analytics"],
    },
    {
      id: "youtube",
      name: "YouTube",
      description: "Connect YouTube for video content and advertising",
      icon: Video,
      category: "Video",
      required: false,
      platforms: ["youtube"],
    },
    {
      id: "brand_assets",
      name: "Brand Assets Storage",
      description: "Connect cloud storage for brand assets and media files",
      icon: FileText,
      category: "Storage",
      required: false,
      platforms: ["google_drive"],
    },
  ],
  customer_support: [
    {
      id: "social_media",
      name: "Social Media",
      description: "Connect social media for customer support",
      icon: Share2,
      category: "Communication",
      required: false,
      platforms: ["facebook", "instagram", "twitter"],
    },
    {
      id: "email",
      name: "Email",
      description: "Connect email for support ticket management",
      icon: Mail,
      category: "Communication",
      required: false,
      platforms: ["gmail", "outlook"],
    },
    {
      id: "messaging",
      name: "Messaging Platforms",
      description: "Connect messaging platforms for customer support",
      icon: MessageSquare,
      category: "Communication",
      required: false,
      platforms: ["whatsapp", "telegram"],
    },
    {
      id: "crm",
      name: "CRM Integration",
      description: "Connect CRM systems for customer management",
      icon: Users,
      category: "Management",
      required: false,
      platforms: ["salesforce", "hubspot"],
    },
  ],
  executive_assistant: [
    {
      id: "email",
      name: "Email",
      description: "Connect email accounts for management",
      icon: Mail,
      category: "Communication",
      required: true,
      platforms: ["gmail", "outlook"],
    },
    {
      id: "calendar",
      name: "Calendar",
      description: "Connect calendar for schedule management",
      icon: Calendar,
      category: "Scheduling",
      required: true,
      platforms: ["google_calendar", "outlook_calendar"],
    },
    {
      id: "meetings",
      name: "Video Conferencing",
      description: "Connect meeting platforms for scheduling",
      icon: Video,
      category: "Scheduling",
      required: false,
      platforms: ["zoom", "teams", "google_meet"],
    },
    {
      id: "documents",
      name: "Document Storage",
      description: "Connect cloud storage for document management",
      icon: FileText,
      category: "Storage",
      required: false,
      platforms: ["google_drive", "onedrive", "dropbox"],
    },
    {
      id: "tasks",
      name: "Task Management",
      description: "Connect task management tools",
      icon: Settings,
      category: "Productivity",
      required: false,
      platforms: ["asana", "trello", "notion"],
    },
  ],
}

// Platform icons mapping with colorful styling
const platformIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  facebook: Facebook,
  instagram: Instagram,
  linkedin: Linkedin,
  twitter: Twitter,
  tiktok: Music,
  google_ads: BarChart3,
  google_analytics: BarChart3,
  youtube: Video,
  meta_ads: Facebook,
  gmail: Mail,
  outlook: Mail,
  google: BarChart3,
  google_calendar: Calendar,
  outlook_calendar: Calendar,
  zoom: Video,
  teams: Video,
  google_meet: Video,
  google_drive: FileText,
  onedrive: FileText,
  dropbox: FileText,
  whatsapp: MessageSquare,
  telegram: MessageSquare,
  salesforce: Users,
  hubspot: Users,
  asana: Settings,
  trello: Settings,
  notion: Settings,
}

// Platform colors for icons
const platformColors: Record<string, string> = {
  facebook: "text-[#1877F2]",
  instagram: "text-[#E4405F]",
  linkedin: "text-[#0A66C2]",
  twitter: "text-[#1DA1F2]",
  tiktok: "text-black dark:text-white",
  google_ads: "text-[#4285F4]",
  google_analytics: "text-[#F4B400]",
  youtube: "text-[#FF0000]",
  meta_ads: "text-[#1877F2]",
}

// Platform display names
const platformNames: Record<string, string> = {
  facebook: "Facebook",
  instagram: "Instagram",
  linkedin: "LinkedIn",
  twitter: "Twitter/X",
  tiktok: "TikTok",
  google_ads: "Google Ads",
  google_analytics: "Google Analytics",
  youtube: "YouTube",
  meta_ads: "Meta Ads",
  gmail: "Gmail",
  outlook: "Outlook",
  google: "Google",
  google_calendar: "Google Calendar",
  outlook_calendar: "Outlook Calendar",
  zoom: "Zoom",
  teams: "Microsoft Teams",
  google_meet: "Google Meet",
  google_drive: "Google Drive",
  onedrive: "OneDrive",
  dropbox: "Dropbox",
  whatsapp: "WhatsApp",
  telegram: "Telegram",
  salesforce: "Salesforce",
  hubspot: "HubSpot",
  asana: "Asana",
  trello: "Trello",
  notion: "Notion",
}

export default function IntegrationsPage() {
  const { toast } = useToast()
  const searchParams = useSearchParams()
  const capabilityId = searchParams.get("capability")
  
  const [assistants, setAssistants] = useState<Assistant[]>([])
  const [selectedAssistant, setSelectedAssistant] = useState<string>("")
  const [statuses, setStatuses] = useState<IntegrationStatus[]>([])
  const [requiredPlatforms, setRequiredPlatforms] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedIntegration, setSelectedIntegration] = useState<IntegrationDetails | null>(null)
  const [integrationDetails, setIntegrationDetails] = useState<IntegrationDetails | null>(null)
  const [loadingDetails, setLoadingDetails] = useState(false)
  const [oauth1Status, setOauth1Status] = useState<{ oauth1_configured: boolean; init_url?: string; message: string } | null>(null)
  const [loadingOAuth1, setLoadingOAuth1] = useState(false)

  useEffect(() => {
    loadAssistants()
    if (capabilityId) {
      loadCapabilityRequirements()
    }
  }, [capabilityId])

  useEffect(() => {
    // Check for OAuth callback
    const success = searchParams.get('success')
    const oauth1 = searchParams.get('oauth1')
    const platform = searchParams.get('platform')
    const error = searchParams.get('error')
    const code = searchParams.get('code')  // Google Drive OAuth callback
    
    // Handle Google Drive OAuth callback
    if (code && !success && !error) {
      const redirectUri = `${window.location.origin}/dashboard/integrations`
      apiClient.connectGoogleDrive(code, redirectUri)
        .then(() => {
          toast({
            title: "Success",
            description: "Google Drive connected successfully!",
          })
          // Clear URL parameters
          window.history.replaceState({}, '', window.location.pathname)
          if (selectedAssistant) {
            loadStatuses()
          }
        })
        .catch((err) => {
          toast({
            title: "Error",
            description: err.message || "Failed to connect Google Drive",
            variant: "destructive",
          })
          window.history.replaceState({}, '', window.location.pathname)
        })
      return  // Exit early, we're handling this
    }
    
    // Handle OAuth 1.0 Twitter callback
    if (success === 'true' && oauth1 === 'complete' && platform === 'twitter') {
      toast({
        title: "Success",
        description: "Twitter media upload authorization completed! You can now upload images with your posts.",
      })
      // Reload statuses to update integration
      if (selectedAssistant) {
        loadStatuses()
      }
      // Reload integration details if modal is open
      if (integrationDetails?.id && integrationDetails.platform === 'twitter') {
        // Reload the integration details
        apiClient.getIntegration(integrationDetails.id).then((details) => {
          setIntegrationDetails(details as IntegrationDetails)
          // Reload OAuth 1.0 status
          apiClient.getOAuth1InitUrl(integrationDetails.id).then((oauth1Data) => {
            setOauth1Status(oauth1Data)
          }).catch(() => {
            setOauth1Status(null)
          })
        }).catch(() => {
          // Silently fail
        })
      }
      // Clear URL parameters
      window.history.replaceState({}, '', window.location.pathname)
    } 
    // Handle general OAuth success (YouTube, Google Ads, etc.)
    else if (success === 'true' && platform) {
      const platformName = platformNames[platform] || platform
      toast({
        title: "Success",
        description: `${platformName} connected successfully!`,
      })
      // Reload statuses to update integration
      if (selectedAssistant) {
        loadStatuses()
      }
      // Clear URL parameters
      window.history.replaceState({}, '', window.location.pathname)
    }
    // Handle error
    else if (success === 'false' || error) {
      const errorMsg = error || 'Authorization failed'
      toast({
        title: "Authorization Failed",
        description: decodeURIComponent(errorMsg),
        variant: "destructive",
      })
      // Clear URL parameters
      window.history.replaceState({}, '', window.location.pathname)
    }
  }, [searchParams, selectedAssistant, integrationDetails])

  useEffect(() => {
    if (selectedAssistant) {
      loadStatuses()
    }
  }, [selectedAssistant])

  async function loadCapabilityRequirements() {
    if (!capabilityId) return
    
    try {
      const capability = await apiClient.getCapability(capabilityId) as {
        integrations_required?: string[]
      }
      setRequiredPlatforms(capability.integrations_required || [])
    } catch (error: unknown) {
      // Silently fail - capability might not exist
      console.error("Failed to load capability requirements:", error)
    }
  }

  async function loadAssistants() {
    try {
      const response = await apiClient.listAssistants() as {
        assistants?: Assistant[]
      }
      const activeAssistants = (response.assistants || []).filter((a: Assistant) => a.is_active)
      setAssistants(activeAssistants)
      if (activeAssistants.length > 0 && !selectedAssistant) {
        setSelectedAssistant(activeAssistants[0].id)
      }
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : "Failed to load assistants"
      toast({
        title: "Error",
        description: errorMessage,
        variant: "destructive",
      })
    } finally {
      setLoading(false)
    }
  }

  async function loadStatuses() {
    try {
      const response = await apiClient.getIntegrationStatus(selectedAssistant) as {
        platforms?: IntegrationStatus[]
      }
      setStatuses(response.platforms || [])
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : "Failed to load integration statuses"
      toast({
        title: "Error",
        description: errorMessage,
        variant: "destructive",
      })
    }
  }

  async function handleConnect(platform: string) {
    try {
      // Special handling for Google Drive - uses separate OAuth flow
      if (platform === 'google_drive') {
        const redirectUri = `${window.location.origin}/dashboard/integrations`
        const response = await apiClient.getGoogleDriveAuthUrl(redirectUri)
        globalThis.window.location.href = response.auth_url
        return
      }
      
      const url = await apiClient.getOAuthInitUrl(platform, selectedAssistant)
      globalThis.window.location.href = url
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : "Failed to initiate OAuth"
      toast({
        title: "Error",
        description: errorMessage,
        variant: "destructive",
      })
    }
  }

  async function handleDisconnect(integrationId: string) {
    if (!confirm("Are you sure you want to disconnect this integration?")) return

    try {
      await apiClient.disconnectIntegration(integrationId)
      toast({
        title: "Success",
        description: "Integration disconnected",
      })
      loadStatuses()
      if (selectedIntegration?.id === integrationId) {
        setSelectedIntegration(null)
        setIntegrationDetails(null)
      }
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : "Failed to disconnect integration"
      toast({
        title: "Error",
        description: errorMessage,
        variant: "destructive",
      })
    }
  }

  async function handleSetDefaultPage(integrationId: string, pageId: string) {
    try {
      if (!apiClient || typeof apiClient.setDefaultPage !== 'function') {
        throw new Error('API client is not available')
      }
      await apiClient.setDefaultPage(integrationId, pageId)
      toast({
        title: "Success",
        description: "Default page updated successfully",
      })
      // Reload integration details to show updated default
      if (integrationDetails?.id === integrationId) {
        const updated = await apiClient.getIntegration(integrationId) as IntegrationDetails
        setIntegrationDetails(updated)
      }
      // Also reload statuses to reflect changes
      await loadStatuses()
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : "Failed to set default page"
      toast({
        title: "Error",
        description: errorMessage,
        variant: "destructive",
      })
    }
  }

  async function handleViewDetails(status: IntegrationStatus) {
    if (!status.integration_id) return

    setSelectedIntegration({
      id: status.integration_id,
      platform: status.platform,
      platform_username: status.platform_username,
      platform_name: status.platform_name,
      is_active: status.is_active,
      is_verified: false,
      created_at: status.connected_at || new Date().toISOString(),
    })
    setLoadingDetails(true)

    try {
      const details = await apiClient.getIntegration(status.integration_id) as IntegrationDetails
      setIntegrationDetails(details)
      
      // Check OAuth 1.0 status for Twitter integrations
      if (details.platform === "twitter") {
        try {
          const oauth1Data = await apiClient.getOAuth1InitUrl(status.integration_id)
          setOauth1Status(oauth1Data)
        } catch (error) {
          console.error("Failed to load OAuth 1.0 status:", error)
          setOauth1Status(null)
        }
      } else {
        setOauth1Status(null)
      }
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : "Failed to load integration details"
      toast({
        title: "Error",
        description: errorMessage,
        variant: "destructive",
      })
      setIntegrationDetails(null)
    } finally {
      setLoadingDetails(false)
    }
  }

  async function handleOAuth1Init() {
    if (!integrationDetails?.id) return

    setLoadingOAuth1(true)
    try {
      // Get OAuth 1.0 authorization URL via authenticated API call
      const authUrl = await apiClient.getOAuth1AuthorizationUrl()
      // Redirect to Twitter authorization page
      window.location.href = authUrl
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : "Failed to initiate OAuth 1.0"
      toast({
        title: "Error",
        description: errorMessage,
        variant: "destructive",
      })
      setLoadingOAuth1(false)
    }
  }

  function formatDate(dateString?: string): string {
    if (!dateString) return "N/A"
    try {
      return new Date(dateString).toLocaleDateString("en-US", {
        year: "numeric",
        month: "long",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    } catch {
      return dateString
    }
  }

  function getStatus(platform: string): IntegrationStatus | undefined {
    return statuses.find((s) => s.platform === platform)
  }

  function isPlatformConnected(platform: string): boolean {
    return getStatus(platform)?.is_connected || false
  }

  const selectedAssistantData = assistants.find((a) => a.id === selectedAssistant)
  const assistantType = selectedAssistantData?.assistant_type || selectedAssistantData?.type || ""
  const configs = integrationConfigs[assistantType] || []
  const configsByCategory = configs.reduce((acc, config) => {
    if (!acc[config.category]) {
      acc[config.category] = []
    }
    acc[config.category].push(config)
    return acc
  }, {} as Record<string, IntegrationConfig[]>)

  if (loading) {
    return <div>Loading...</div>
  }

  if (assistants.length === 0) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold">Integrations</h1>
          <p className="text-muted-foreground">Connect services to enhance your AI assistants</p>
        </div>
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Bot className="h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-muted-foreground">No active assistants found</p>
            <p className="text-sm text-muted-foreground mt-2">
              Activate an assistant first to configure integrations
            </p>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6 w-full">
      <div>
        <h1 className="text-3xl font-bold">Integrations</h1>
        <p className="text-muted-foreground">
          Connect services and platforms to enhance your AI assistant capabilities
        </p>
      </div>

      <Card className="w-full">
        <CardHeader>
          <CardTitle>Select Assistant</CardTitle>
          <CardDescription>Choose an assistant to configure integrations for</CardDescription>
        </CardHeader>
        <CardContent>
          <Select value={selectedAssistant} onValueChange={setSelectedAssistant}>
            <SelectTrigger className="w-full max-w-md">
              <SelectValue placeholder="Select an assistant" />
            </SelectTrigger>
            <SelectContent>
              {assistants.map((assistant) => (
                <SelectItem key={assistant.id} value={assistant.id}>
                  <div className="flex items-center gap-2">
                    <Bot className="h-4 w-4" />
                    {assistant.name}
                  </div>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardContent>
      </Card>

      {capabilityId && requiredPlatforms.length > 0 && (
        <Card className="border-orange-500/50 bg-orange-500/5 w-full">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5 text-orange-500" />
              Capability Setup Required
            </CardTitle>
            <CardDescription>
              Connect the following integrations to complete capability setup:
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {requiredPlatforms.map((platform) => {
                const isConnected = statuses.some(s => s.platform === platform && s.is_connected)
                return (
                  <Badge
                    key={platform}
                    variant={isConnected ? "default" : "destructive"}
                    className="text-sm"
                  >
                    {platformNames[platform] || platform}
                    {isConnected && <CheckCircle2 className="h-3 w-3 ml-1" />}
                  </Badge>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {selectedAssistant && configs.length > 0 && (
        <div className="space-y-6">
          {Object.entries(configsByCategory).map(([category, categoryConfigs]) => (
            <div key={category}>
              <h2 className="text-xl font-semibold mb-4">{category}</h2>
              <div className="flex flex-col lg:flex-row gap-6">
                {categoryConfigs.map((config) => {
                  const ConfigIcon = config.icon
                  const connectedPlatforms = config.platforms.filter((p) =>
                    isPlatformConnected(p)
                  )
                  const allConnected = connectedPlatforms.length === config.platforms.length

                  return (
                    <Card key={config.id} className="flex-1 min-w-0">
                      <CardHeader>
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <ConfigIcon className="h-5 w-5" />
                            <CardTitle className="text-base">{config.name}</CardTitle>
                          </div>
                          {allConnected ? (
                            <CheckCircle2 className="h-5 w-5 text-green-500" />
                          ) : connectedPlatforms.length > 0 ? (
                            <Badge variant="outline" className="text-xs">
                              {connectedPlatforms.length}/{config.platforms.length}
                            </Badge>
                          ) : null}
                        </div>
                        <CardDescription className="text-sm">
                          {config.description}
                        </CardDescription>
                      </CardHeader>
                      <CardContent>
                        <div className="flex flex-col gap-2">
                          {config.platforms.map((platform) => {
                            const PlatformIcon = platformIcons[platform] || Share2
                            const status = getStatus(platform)
                            const isConnected = status?.is_connected || false
                            const iconColor = platformColors[platform] || "text-foreground"
                            const isRequired = requiredPlatforms.length > 0 && requiredPlatforms.includes(platform)

                            return (
                              <div
                                key={platform}
                                className={`group relative flex items-center justify-between p-3 rounded-lg border transition-all ${
                                  isConnected
                                    ? "border-green-500/50 bg-green-500/5 hover:bg-green-500/10 cursor-pointer"
                                    : isRequired
                                      ? "border-orange-500/50 bg-orange-500/5 hover:bg-orange-500/10 border-2"
                                      : "border-border hover:border-primary/50"
                                }`}
                                onClick={() => {
                                  if (isConnected && status) {
                                    handleViewDetails(status)
                                  }
                                }}
                              >
                                <div className="flex items-center gap-3 flex-1 min-w-0">
                                  <div className={`p-2 rounded-lg ${isConnected ? "bg-green-500/10" : "bg-muted"}`}>
                                    <PlatformIcon className={`h-5 w-5 ${iconColor}`} />
                                  </div>
                                  <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2">
                                      <span className="text-sm font-medium">
                                        {platformNames[platform] || platform}
                                      </span>
                                      {(config.required || isRequired) && (
                                        <Badge variant={isRequired && !isConnected ? "destructive" : "secondary"} className="text-xs">
                                          Required
                                        </Badge>
                                      )}
                                    </div>
                                    {isConnected && status?.platform_username && (
                                      <p className="text-xs text-muted-foreground truncate">
                                        @{status.platform_username}
                                      </p>
                                    )}
                                  </div>
                                </div>
                                <div className="flex items-center gap-2">
                                  {isConnected && status ? (
                                    <>
                                      <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-green-500/10">
                                        <CheckCircle2 className="h-4 w-4 text-green-500" />
                                        <span className="text-xs font-medium text-green-600 dark:text-green-400">
                                          Connected
                                        </span>
                                      </div>
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        className="opacity-0 group-hover:opacity-100 transition-opacity"
                                        onClick={(e) => {
                                          e.stopPropagation()
                                          if (status.integration_id) {
                                            handleDisconnect(status.integration_id)
                                          }
                                        }}
                                      >
                                        <X className="h-4 w-4" />
                                      </Button>
                                    </>
                                  ) : (
                                    <Button
                                      variant="outline"
                                      size="sm"
                                      onClick={(e) => {
                                        e.stopPropagation()
                                        handleConnect(platform)
                                      }}
                                    >
                                      <ExternalLink className="h-3 w-3 mr-1" />
                                      Connect
                                    </Button>
                                  )}
                                </div>
                              </div>
                            )
                          })}
                        </div>
                      </CardContent>
                    </Card>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {selectedAssistant && configs.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Settings className="h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-muted-foreground">
              No integration configurations available for this assistant type
            </p>
          </CardContent>
        </Card>
      )}

      {/* Integration Details Modal */}
      <Dialog open={!!selectedIntegration} onOpenChange={(open) => {
        if (!open) {
          setSelectedIntegration(null)
          setIntegrationDetails(null)
        }
      }}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {selectedIntegration && (
                <>
                  {(() => {
                    const PlatformIcon = platformIcons[selectedIntegration.platform] || Share2
                    const iconColor = platformColors[selectedIntegration.platform] || "text-foreground"
                    return <PlatformIcon className={`h-5 w-5 ${iconColor}`} />
                  })()}
                  <span>{platformNames[selectedIntegration.platform] || selectedIntegration.platform}</span>
                  {selectedIntegration.is_active && (
                    <Badge variant="outline" className="ml-2">
                      <CheckCircle2 className="h-3 w-3 mr-1 text-green-500" />
                      Active
                    </Badge>
                  )}
                </>
              )}
            </DialogTitle>
            <DialogDescription>
              Integration details and connection information
            </DialogDescription>
          </DialogHeader>

          {loadingDetails ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
            </div>
          ) : integrationDetails ? (
            <div className="space-y-4">
              {/* Account Information */}
              <div className="space-y-3">
                <h3 className="font-semibold text-sm uppercase tracking-wide text-muted-foreground">
                  Account Information
                </h3>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <p className="text-xs text-muted-foreground">Username</p>
                    <p className="text-sm font-medium">
                      {integrationDetails.platform_username ? `@${integrationDetails.platform_username}` : "N/A"}
                    </p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-xs text-muted-foreground">Display Name</p>
                    <p className="text-sm font-medium">
                      {integrationDetails.platform_name || "N/A"}
                    </p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-xs text-muted-foreground">Status</p>
                    <div className="flex items-center gap-2">
                      <Badge variant={integrationDetails.is_active ? "default" : "secondary"}>
                        {integrationDetails.is_active ? "Active" : "Inactive"}
                      </Badge>
                      {integrationDetails.is_verified && (
                        <Badge variant="outline">Verified</Badge>
                      )}
                    </div>
                  </div>
                  <div className="space-y-1">
                    <p className="text-xs text-muted-foreground">Platform</p>
                    <p className="text-sm font-medium">
                      {platformNames[integrationDetails.platform] || integrationDetails.platform}
                    </p>
                  </div>
                </div>
              </div>

              <Separator />

              {/* OAuth 1.0 Status for Twitter */}
              {integrationDetails.platform === "twitter" && (
                <>
                  <div className="space-y-3">
                    <h3 className="font-semibold text-sm uppercase tracking-wide text-muted-foreground">
                      Media Upload Authorization
                    </h3>
                    {loadingOAuth1 ? (
                      <div className="flex items-center justify-center py-4">
                        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
                      </div>
                    ) : oauth1Status && !oauth1Status.oauth1_configured ? (
                      <div className="p-4 rounded-lg border border-orange-500/50 bg-orange-500/5">
                        <div className="flex items-start gap-3">
                          <AlertCircle className="h-5 w-5 text-orange-500 flex-shrink-0 mt-0.5" />
                          <div className="flex-1 space-y-2">
                            <div>
                              <p className="text-sm font-medium text-orange-600 dark:text-orange-400">
                                Media Upload Authorization Required
                              </p>
                              <p className="text-xs text-muted-foreground mt-1">
                                To upload images with your Twitter posts, you need to complete an additional authorization step.
                                This is required because Twitter's media upload endpoints use OAuth 1.0a authentication.
                              </p>
                            </div>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={handleOAuth1Init}
                              className="mt-2"
                            >
                              <ExternalLink className="h-3 w-3 mr-2" />
                              Authorize Media Uploads
                            </Button>
                          </div>
                        </div>
                      </div>
                    ) : integrationDetails.oauth1_configured ? (
                      <div className="p-4 rounded-lg border border-green-500/50 bg-green-500/5">
                        <div className="flex items-center gap-3">
                          <CheckCircle2 className="h-5 w-5 text-green-500" />
                          <div>
                            <p className="text-sm font-medium text-green-600 dark:text-green-400">
                              Media Uploads Enabled
                            </p>
                            <p className="text-xs text-muted-foreground mt-1">
                              You can upload images with your Twitter posts.
                            </p>
                          </div>
                        </div>
                      </div>
                    ) : null}
                  </div>
                  <Separator />
                </>
              )}

              {/* Connection Details */}
              <div className="space-y-3">
                <h3 className="font-semibold text-sm uppercase tracking-wide text-muted-foreground">
                  Connection Details
                </h3>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <p className="text-xs text-muted-foreground flex items-center gap-1">
                      <CalendarIcon className="h-3 w-3" />
                      Connected At
                    </p>
                    <p className="text-sm font-medium">
                      {formatDate(integrationDetails.created_at)}
                    </p>
                  </div>
                  {integrationDetails.updated_at && (
                    <div className="space-y-1">
                      <p className="text-xs text-muted-foreground flex items-center gap-1">
                        <CalendarIcon className="h-3 w-3" />
                        Last Updated
                      </p>
                      <p className="text-sm font-medium">
                        {formatDate(integrationDetails.updated_at)}
                      </p>
                    </div>
                  )}
                  {integrationDetails.last_used_at && (
                    <div className="space-y-1">
                      <p className="text-xs text-muted-foreground flex items-center gap-1">
                        <CalendarIcon className="h-3 w-3" />
                        Last Used
                      </p>
                      <p className="text-sm font-medium">
                        {formatDate(integrationDetails.last_used_at)}
                      </p>
                    </div>
                  )}
                </div>
              </div>

              {/* Pages (for Facebook/Instagram) - Hide for Meta Ads */}
              {integrationDetails.pages && integrationDetails.pages.length > 0 && integrationDetails.platform !== "meta_ads" && (
                <>
                  <Separator />
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="font-semibold text-sm uppercase tracking-wide text-muted-foreground">
                        Connected Pages ({integrationDetails.pages.length})
                      </h3>
                    </div>
                    <div className="space-y-2">
                      <div className="space-y-1">
                        <label htmlFor="default-page-select" className="text-xs text-muted-foreground">Default Page</label>
                        <Select
                          value={integrationDetails.default_page_id ? String(integrationDetails.default_page_id) : undefined}
                          onValueChange={(value) => {
                            if (integrationDetails.id && value && value.trim() !== "") {
                              handleSetDefaultPage(integrationDetails.id, value)
                            }
                          }}
                        >
                          <SelectTrigger id="default-page-select">
                            <SelectValue placeholder="Select default page" />
                          </SelectTrigger>
                          <SelectContent>
                            {integrationDetails.pages
                              .filter((page: Record<string, unknown>) => {
                                // Filter out pages without valid IDs
                                return page.id != null || page.page_id != null
                              })
                              .map((page: Record<string, unknown>) => {
                                const pageId = String(page.id || page.page_id)
                                const pageName = String(page.name || "Unnamed Page")
                                const isDefault = integrationDetails.default_page_id === pageId
                                return (
                                  <SelectItem key={pageId} value={pageId}>
                                    <div className="flex items-center gap-2">
                                      <span>{pageName}</span>
                                      {isDefault && (
                                        <Badge variant="secondary" className="text-xs">Default</Badge>
                                      )}
                                    </div>
                                  </SelectItem>
                                )
                              })}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-2 max-h-48 overflow-y-auto">
                        {integrationDetails.pages.map((page: Record<string, unknown>) => {
                          const pageId = String(page.id || Math.random())
                          const isDefault = integrationDetails.default_page_id === pageId
                          return (
                            <div
                              key={pageId}
                              className={`p-3 rounded-lg border ${
                                isDefault
                                  ? "border-primary bg-primary/5"
                                  : "bg-muted/50"
                              }`}
                            >
                              <div className="flex items-center justify-between">
                                <div>
                                  <p className="text-sm font-medium">
                                    {String(page.name || "Unnamed Page")}
                                  </p>
                                  {page.id != null && (
                                    <p className="text-xs text-muted-foreground">ID: {String(page.id)}</p>
                                  )}
                                </div>
                                {isDefault && (
                                  <Badge variant="default" className="text-xs">
                                    Default
                                  </Badge>
                                )}
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  </div>
                </>
              )}

              {/* Organizations/Ad Accounts (for LinkedIn, Google Ads, Meta Ads, etc.) */}
              {integrationDetails.organizations && integrationDetails.organizations.length > 0 && (
                <>
                  <Separator />
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="font-semibold text-sm uppercase tracking-wide text-muted-foreground">
                        {integrationDetails.platform === "meta_ads" 
                          ? `Ad Accounts (${integrationDetails.organizations.length})`
                          : integrationDetails.platform === "google_ads" || integrationDetails.platform === "google_analytics"
                          ? `Accounts (${integrationDetails.organizations.length})`
                          : `Organizations (${integrationDetails.organizations.length})`}
                      </h3>
                    </div>
                    <div className="space-y-2">
                      {/* For Google Ads: Show client accounts selection if manager account has client_ids */}
                      {integrationDetails.platform === "google_ads" && (() => {
                        // Debug: Log organizations to see what we're getting
                        console.log("Google Ads organizations:", integrationDetails.organizations)
                        
                        const managerAccount = integrationDetails.organizations.find(
                          (org: Record<string, unknown>) => org.type === "manager"
                        )
                        
                        console.log("Manager account found:", managerAccount)
                        
                        const clientIds = managerAccount?.client_ids as string[] | undefined
                        console.log("Client IDs:", clientIds)
                        
                        const hasClientAccounts = clientIds && Array.isArray(clientIds) && clientIds.length > 0
                        
                        if (hasClientAccounts && managerAccount) {
                          const managerId = String(managerAccount.customer_id || "")
                          return (
                            <div className="space-y-1">
                              <label htmlFor="default-client-select" className="text-xs text-muted-foreground">
                                Default Client Account (for campaign creation)
                              </label>
                              <Select
                                value={integrationDetails.default_page_id ? String(integrationDetails.default_page_id) : undefined}
                                onValueChange={(value) => {
                                  if (integrationDetails.id && value && value.trim() !== "") {
                                    handleSetDefaultPage(integrationDetails.id, value)
                                  }
                                }}
                              >
                                <SelectTrigger id="default-client-select">
                                  <SelectValue placeholder="Select default client account" />
                                </SelectTrigger>
                                <SelectContent>
                                  {clientIds
                                    .filter((clientId: string) => {
                                      const idStr = String(clientId).trim()
                                      return idStr && idStr.length === 10 && /^\d+$/.test(idStr)
                                    })
                                    .map((clientId: string) => {
                                      const clientIdStr = String(clientId).trim()
                                      const isDefault = String(integrationDetails.default_page_id || "") === clientIdStr
                                      return (
                                        <SelectItem key={clientIdStr} value={clientIdStr}>
                                          <div className="flex items-center gap-2">
                                            <span>Customer {clientIdStr}</span>
                                            {isDefault && (
                                              <Badge variant="secondary" className="text-xs">Default</Badge>
                                            )}
                                          </div>
                                        </SelectItem>
                                      )
                                    })}
                                </SelectContent>
                              </Select>
                              <p className="text-xs text-muted-foreground mt-1">
                                Manager Account: {managerId} ({clientIds.length} client accounts)
                              </p>
                            </div>
                          )
                        }
                        return null
                      })()}
                      
                      {/* Default organization/account selector for other platforms */}
                      {!(integrationDetails.platform === "google_ads" && (() => {
                        const managerAccount = integrationDetails.organizations.find(
                          (org: Record<string, unknown>) => org.type === "manager"
                        )
                        return managerAccount?.client_ids && Array.isArray(managerAccount.client_ids) && managerAccount.client_ids.length > 0
                      })()) && (
                        <div className="space-y-1">
                          <label htmlFor="default-org-select" className="text-xs text-muted-foreground">
                            {integrationDetails.platform === "meta_ads" 
                              ? "Default Ad Account"
                              : integrationDetails.platform === "google_ads" || integrationDetails.platform === "google_analytics"
                              ? "Default Account"
                              : "Default Organization"}
                          </label>
                          <Select
                            value={integrationDetails.default_page_id ? String(integrationDetails.default_page_id) : undefined}
                            onValueChange={(value) => {
                              if (integrationDetails.id && value && value.trim() !== "") {
                                handleSetDefaultPage(integrationDetails.id, value)
                              }
                            }}
                          >
                            <SelectTrigger id="default-org-select">
                              <SelectValue placeholder="Select default organization" />
                            </SelectTrigger>
                            <SelectContent>
                              {integrationDetails.organizations
                                .filter((org: Record<string, unknown>) => {
                                  // Filter out organizations without valid IDs
                                  // Support multiple ID fields for different platforms:
                                  // LinkedIn: id, entity_id, organization_id
                                  // Google Ads: customer_id
                                  // Google Analytics: account_id
                                  // Meta Ads: ad_account_id
                                  const rawId = org.id || org.entity_id || org.organization_id || org.customer_id || org.account_id || org.ad_account_id
                                  return rawId != null && String(rawId).trim() !== ""
                                })
                                .map((org: Record<string, unknown>) => {
                                  // Extract org ID, handling URN format and multiple ID fields
                                  let orgId = String(org.id || org.entity_id || org.organization_id || org.customer_id || org.account_id || org.ad_account_id || "")
                                  
                                  // Clean URN format: "urn:li:organization:123456" -> "123456"
                                  if (orgId.includes("urn:li:organization:")) {
                                    orgId = orgId.split("urn:li:organization:")[1] || orgId
                                  } else if (orgId.includes("urn:li:")) {
                                    // Handle other URN formats
                                    const parts = orgId.split(":")
                                    orgId = parts[parts.length - 1] || orgId
                                  }
                                  
                                  // Clean default_page_id for comparison
                                  let defaultPageId = String(integrationDetails.default_page_id || "")
                                  if (defaultPageId.includes("urn:li:organization:")) {
                                    defaultPageId = defaultPageId.split("urn:li:organization:")[1] || defaultPageId
                                  } else if (defaultPageId.includes("urn:li:")) {
                                    const parts = defaultPageId.split(":")
                                    defaultPageId = parts[parts.length - 1] || defaultPageId
                                  }
                                  
                                  // Try multiple name fields: name, localizedName, vanityName
                                  // For Google Ads, use customer_id as name if no name available
                                  const orgName = String(
                                    org.name || 
                                    org.localizedName || 
                                    org.vanityName || 
                                    (org.customer_id ? `Customer ${org.customer_id}` : null) ||
                                    (org.account_id ? `Account ${org.account_id}` : null) ||
                                    (org.ad_account_id ? `Ad Account ${org.ad_account_id}` : null) ||
                                    "Unnamed Organization"
                                  )
                                  const isDefault = defaultPageId === orgId
                                  return (
                                    <SelectItem key={orgId} value={orgId}>
                                      <div className="flex items-center gap-2">
                                        <span>{orgName}</span>
                                        {isDefault && (
                                          <Badge variant="secondary" className="text-xs">Default</Badge>
                                        )}
                                      </div>
                                    </SelectItem>
                                  )
                                })}
                            </SelectContent>
                          </Select>
                        </div>
                      )}
                      <div className="space-y-2 max-h-48 overflow-y-auto">
                        {integrationDetails.organizations.map((org: Record<string, unknown>) => {
                          // Extract org ID, handling URN format and multiple ID fields
                          // Support: id, entity_id, organization_id (LinkedIn), customer_id (Google Ads), account_id (Google Analytics), ad_account_id (Meta Ads)
                          const rawId = org.id || org.entity_id || org.organization_id || org.customer_id || org.account_id || org.ad_account_id
                          let orgId = String(rawId || Math.random())
                          let orgIdStr = rawId != null ? String(rawId) : ""
                          
                          // Clean URN format: "urn:li:organization:123456" -> "123456"
                          if (orgId.includes("urn:li:organization:")) {
                            orgId = orgId.split("urn:li:organization:")[1] || orgId
                          } else if (orgId.includes("urn:li:")) {
                            // Handle other URN formats
                            const parts = orgId.split(":")
                            orgId = parts[parts.length - 1] || orgId
                          }
                          
                          // Clean orgIdStr for display
                          if (orgIdStr.includes("urn:li:organization:")) {
                            orgIdStr = orgIdStr.split("urn:li:organization:")[1] || orgIdStr
                          } else if (orgIdStr.includes("urn:li:")) {
                            const parts = orgIdStr.split(":")
                            orgIdStr = parts[parts.length - 1] || orgIdStr
                          }
                          
                          // Clean default_page_id for comparison
                          let defaultPageId = String(integrationDetails.default_page_id || "")
                          if (defaultPageId.includes("urn:li:organization:")) {
                            defaultPageId = defaultPageId.split("urn:li:organization:")[1] || defaultPageId
                          } else if (defaultPageId.includes("urn:li:")) {
                            const parts = defaultPageId.split(":")
                            defaultPageId = parts[parts.length - 1] || defaultPageId
                          }
                          
                          const isDefault = defaultPageId === orgId
                          return (
                            <div
                              key={orgId}
                              className={`p-3 rounded-lg border ${
                                isDefault
                                  ? "border-primary bg-primary/5"
                                  : "bg-muted/50"
                              }`}
                            >
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-3 flex-1 min-w-0">
                                  <div className="relative h-10 w-10 flex-shrink-0">
                                    {org.logo_url ? (
                                      <img 
                                        src={String(org.logo_url)} 
                                        alt="Organization logo"
                                        className="h-10 w-10 rounded-full object-cover"
                                        onError={(e) => {
                                          // Hide image if it fails to load, show placeholder
                                          e.currentTarget.style.display = 'none'
                                          const placeholder = e.currentTarget.parentElement?.querySelector('.logo-placeholder') as HTMLElement
                                          if (placeholder) {
                                            placeholder.style.display = 'flex'
                                          }
                                        }}
                                      />
                                    ) : null}
                                    <div 
                                      className="logo-placeholder h-10 w-10 rounded-full flex items-center justify-center bg-muted"
                                      style={{ display: org.logo_url ? 'none' : 'flex' }}
                                    >
                                      <Building2 className="h-5 w-5 text-muted-foreground" />
                                    </div>
                                  </div>
                                  <div className="flex-1 min-w-0">
                                    <p className="text-sm font-medium truncate">
                                      {String(
                                        org.name || 
                                        org.localizedName || 
                                        org.vanityName ||
                                        // For Google Ads, use customer_id as name if no name available
                                        (org.customer_id ? `Customer ${org.customer_id}` : null) || 
                                        "Unnamed Organization"
                                      )}
                                    </p>
                                    {orgIdStr && (
                                      <p className="text-xs text-muted-foreground">ID: {String(orgIdStr)}</p>
                                    )}
                                    {(() => {
                                      const vanityName = org.vanityName ? String(org.vanityName) : ""
                                      const orgName = org.name ? String(org.name) : ""
                                      return vanityName && vanityName !== orgName ? (
                                        <p className="text-xs text-muted-foreground">@{vanityName}</p>
                                      ) : null
                                    })()}
                                  </div>
                                </div>
                                {isDefault && (
                                  <Badge variant="default" className="text-xs flex-shrink-0">
                                    Default
                                  </Badge>
                                )}
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  </div>
                </>
              )}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-8">
              <AlertCircle className="h-8 w-8 text-muted-foreground mb-2" />
              <p className="text-sm text-muted-foreground">Failed to load integration details</p>
            </div>
          )}

          <DialogFooter>
            {integrationDetails && (
              <Button
                variant="destructive"
                onClick={() => {
                  if (integrationDetails.id) {
                    handleDisconnect(integrationDetails.id)
                    setSelectedIntegration(null)
                    setIntegrationDetails(null)
                  }
                }}
              >
                Disconnect
              </Button>
            )}
            <Button variant="outline" onClick={() => {
              setSelectedIntegration(null)
              setIntegrationDetails(null)
            }}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
