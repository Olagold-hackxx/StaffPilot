"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { apiClient, Assistant } from "@/lib/api"
import { useToast } from "@/components/ui/use-toast"
import { 
  CheckCircle2, ExternalLink, Bot, Loader2,
  Facebook, Instagram, Linkedin, Twitter, Music,
  BarChart3, Mail, Check
} from "lucide-react"

interface IntegrationStatus {
  platform: string
  is_connected: boolean
  integration_id?: string
  platform_username?: string
}

const platformIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  facebook: Facebook,
  instagram: Instagram,
  linkedin: Linkedin,
  twitter: Twitter,
  tiktok: Music,
  google_ads: BarChart3,
  google_analytics: BarChart3,
  meta_ads: Facebook,
  gmail: Mail,
}

const platformNames: Record<string, string> = {
  facebook: "Facebook",
  instagram: "Instagram",
  linkedin: "LinkedIn",
  twitter: "Twitter/X",
  tiktok: "TikTok",
  google_ads: "Google Ads",
  google_analytics: "Google Analytics",
  meta_ads: "Meta Ads",
}

const FEATURED_INTEGRATIONS = [
  "facebook", "instagram", "linkedin", "twitter", "google_ads", "meta_ads"
]

export default function IntegrationsPage() {
  const router = useRouter()
  const { toast } = useToast()
  const [loading, setLoading] = useState(true)
  const [assistantId, setAssistantId] = useState<string | null>(null)
  const [statuses, setStatuses] = useState<IntegrationStatus[]>([])
  const [activating, setActivating] = useState(false)

  // Initialize: Check for assistant or create one
  useEffect(() => {
    async function init() {
      try {
        setLoading(true)
        const response = await apiClient.listAssistants()
        const activeAssistants = (response.assistants || []).filter(a => a.is_active)
        
        if (activeAssistants.length > 0) {
          setAssistantId(activeAssistants[0].id)
        } else {
          // No active assistant, let's create a default one
          setActivating(true)
          const newAssistant = await apiClient.activateAssistant('digital_marketer') as Assistant
          setAssistantId(newAssistant.id)
        }
      } catch (error) {
        console.error("Failed to initialize integrations page", error)
        toast({
          title: "Error",
          description: "Failed to initialize. Please try refreshing the page.",
          variant: "destructive",
        })
      } finally {
        setLoading(false)
        setActivating(false)
      }
    }
    
    init()
  }, [toast])

  // Load statuses when assistantId is available
  useEffect(() => {
    if (!assistantId) return

    async function loadStatuses() {
      try {
        const response = await apiClient.getIntegrationStatus(assistantId!) as { platforms?: IntegrationStatus[] }
        setStatuses(response.platforms || [])
      } catch (error) {
        console.error("Failed to load statuses", error)
      }
    }

    loadStatuses()
    
    // Check for success param from redirect
    const urlParams = new URLSearchParams(window.location.search)
    if (urlParams.get('success') === 'true') {
      toast({
        title: "Success",
        description: "Integration connected successfully!",
      })
      // Clean up URL
      window.history.replaceState({}, '', window.location.pathname)
    }
  }, [assistantId, toast])

  async function handleConnect(platform: string) {
    if (!assistantId) return

    try {
      // Pass current URL as return URL so OAuth callback returns here
      const returnUrl = window.location.origin + window.location.pathname
      const url = await apiClient.getOAuthInitUrl(platform, assistantId, returnUrl)
      window.location.href = url
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to initiate connection",
        variant: "destructive",
      })
    }
  }

  function isConnected(platform: string) {
    return statuses.find(s => s.platform === platform)?.is_connected
  }

  if (loading || activating) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <Loader2 className="h-12 w-12 animate-spin text-primary" />
        <p className="mt-4 text-muted-foreground">
          {activating ? "Setting up your digital workspace..." : "Loading integrations..."}
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold">Connect Your Apps</h2>
        <p className="text-muted-foreground">
          Connect your social media and advertising accounts to let StaffPilot manage them for you.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {FEATURED_INTEGRATIONS.map(platform => {
          const PlatformIcon = platformIcons[platform] || ExternalLink
          const connected = isConnected(platform)
          const status = statuses.find(s => s.platform === platform)

          return (
            <Card key={platform} className={`transition-all ${connected ? 'border-green-200 bg-green-50/50 dark:border-green-800 dark:bg-green-900/10' : ''}`}>
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className={`p-2 rounded-lg ${connected ? 'bg-green-100 dark:bg-green-900/30' : 'bg-slate-100 dark:bg-slate-800'}`}>
                      <PlatformIcon className={`h-6 w-6 ${connected ? 'text-green-600 dark:text-green-400' : 'text-slate-600 dark:text-slate-400'}`} />
                    </div>
                    <div>
                      <h3 className="font-semibold">{platformNames[platform] || platform}</h3>
                      {connected && status?.platform_username && (
                        <p className="text-sm text-muted-foreground">@{status.platform_username}</p>
                      )}
                    </div>
                  </div>

                  {connected ? (
                    <div className="flex items-center gap-2 text-green-600 dark:text-green-400">
                      <span className="text-sm font-medium">Connected</span>
                      <CheckCircle2 className="h-5 w-5" />
                    </div>
                  ) : (
                    <Button 
                      variant="outline" 
                      onClick={() => handleConnect(platform)}
                    >
                      Connect
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>

      <div className="flex justify-end pt-8">
        <Button 
          size="lg"
          onClick={() => router.push("/dashboard")}
          className="w-full sm:w-auto"
        >
          Complete Setup
          <Check className="ml-2 h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}
