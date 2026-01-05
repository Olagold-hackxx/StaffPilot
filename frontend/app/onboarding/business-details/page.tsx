"use client"

import { useEffect, useState, useRef, useCallback } from "react"
import { useRouter } from "next/navigation"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { apiClient } from "@/lib/api"
import { useToast } from "@/components/ui/use-toast"
import { FileText, Upload, Trash2, CheckCircle2, Plus, X, ArrowRight, Loader2, Sparkles, Globe, Pencil, Save } from "lucide-react"
import { Progress } from "@/components/ui/progress"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import ReactMarkdown from "react-markdown"

interface Document {
  id: string
  filename: string
  file_type: string
  file_size: number
  status: string
  created_at: string
  meta_data?: {
    document_category?: string
    required_type?: string
    ai_generated?: boolean
  }
}

interface RequiredDocumentType {
  id: string
  name: string
  description: string
  icon: React.ComponentType<{ className?: string }>
  acceptedTypes: string[]
}

const REQUIRED_DOCUMENT_TYPES: RequiredDocumentType[] = [
  {
    id: "company_overview",
    name: "Company Overview",
    description: "Document describing your company, mission, vision, and values",
    icon: FileText,
    acceptedTypes: ["pdf", "docx", "txt", "md"],
  },
  {
    id: "brand_guidelines",
    name: "Brand Guidelines",
    description: "Your brand voice, tone, style guide, and visual identity",
    icon: FileText,
    acceptedTypes: ["pdf", "docx", "md"],
  },
  {
    id: "product_catalog",
    name: "Product/Service Catalog",
    description: "Information about your products or services",
    icon: FileText,
    acceptedTypes: ["pdf", "docx", "txt", "md"],
  },
  {
    id: "target_audience",
    name: "Target Audience Profile",
    description: "Details about your ideal customers and target market",
    icon: FileText,
    acceptedTypes: ["pdf", "docx", "txt", "md"],
  },
]

export default function BusinessDetailsPage() {
  const router = useRouter()
  const { toast } = useToast()
  const [documents, setDocuments] = useState<Document[]>([])
  const [uploadingType, setUploadingType] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [loading, setLoading] = useState(true)
  const fileInputRef = useRef<HTMLInputElement>(null)
  
  // Quick Setup state
  const [activeTab, setActiveTab] = useState<"upload" | "quick-setup">("upload")
  const [researching, setResearching] = useState(false)
  const [aiDescription, setAiDescription] = useState("")
  const [aiSources, setAiSources] = useState<Array<{ title: string; uri: string }>>([])
  const [saving, setSaving] = useState(false)
  const [websiteUrl, setWebsiteUrl] = useState<string>("")
  const [hasResearched, setHasResearched] = useState(false)
  const [isEditing, setIsEditing] = useState(false)

  const loadDocuments = useCallback(async () => {
    try {
      const response = await apiClient.listDocuments() as { documents?: Document[] }
      setDocuments(response.documents || [])
    } catch (error: unknown) {
      console.error("Failed to load documents", error)
    } finally {
      setLoading(false)
    }
  }, [])

  const loadTenant = useCallback(async () => {
    try {
      const tenant = await apiClient.getTenant()
      if (tenant.website_url) {
        setWebsiteUrl(tenant.website_url)
      }
    } catch (error: unknown) {
      console.error("Failed to load tenant", error)
    }
  }, [])

  useEffect(() => {
    loadDocuments()
    loadTenant()
  }, [loadDocuments, loadTenant])

  async function handleFileSelect(event: React.ChangeEvent<HTMLInputElement>, requiredType: string) {
    const files = Array.from(event.target.files || [])
    if (files.length === 0) return

    const file = files[0]
    
    // Validate file type
    const allowedTypes = new Set(['text/plain', 'application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/msword'])
    const allowedExtensions = new Set(['.txt', '.md', '.markdown', '.pdf', '.docx', '.doc'])
    const extension = '.' + file.name.split('.').pop()?.toLowerCase()
    
    if (!allowedTypes.has(file.type) && !allowedExtensions.has(extension)) {
      toast({
        title: "Invalid File Type",
        description: "Only TXT, MD, PDF, and DOCX files are supported.",
        variant: "destructive",
      })
      return
    }

    setUploading(true)
    setUploadingType(requiredType)

    try {
      const newDoc = await apiClient.uploadDocument(file, undefined, requiredType) as Document
      
      // Update state immediately to reflect progress
      setDocuments((prev) => {
        // Remove potentially existing doc with same required_type if we're replacing
        // But the previous logic didn't assume replacement. The UI allows "Replace" if uploaded? 
        // Actually the UI shows "Replace" button if isUploaded.
        // If we just prepend, we might have duplicates if we don't filter.
        // Let's filter out any existing doc with the same required_type if it's a required document upload
        if (requiredType) {
           const filtered = prev.filter(d => d.meta_data?.required_type !== requiredType)
           return [newDoc, ...filtered]
        }
        return [newDoc, ...prev]
      })

      toast({
        title: "Success",
        description: "Document uploaded successfully",
      })
      
      // We can still reload to ensure consistency, but the UI should already be updated
      // await loadDocuments() 
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to upload document",
        variant: "destructive",
      })
    } finally {
      setUploading(false)
      setUploadingType(null)
      if (fileInputRef.current) {
        fileInputRef.current.value = ""
      }
    }
  }

  async function handleDelete(documentId: string) {
    if (!confirm("Are you sure you want to delete this document?")) return

    try {
      await apiClient.deleteDocument(documentId)
      setDocuments((prev) => prev.filter((doc) => doc.id !== documentId))
      toast({
        title: "Success",
        description: "Document deleted",
      })
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to delete document",
        variant: "destructive",
      })
    }
  }

  // Quick Setup handlers
  async function handleQuickSetupResearch() {
    if (!websiteUrl) {
      toast({
        title: "Website Required",
        description: "Please add your website URL in settings first, or enter it below.",
        variant: "destructive",
      })
      return
    }

    setResearching(true)
    setHasResearched(false)
    
    try {
      const result = await apiClient.quickSetupResearch(websiteUrl)
      setAiDescription(result.description)
      setAiSources(result.sources || [])
      setHasResearched(true)
      
      toast({
        title: "Research Complete",
        description: `Found information from ${result.sources?.length || 0} sources. You can now edit and save.`,
      })
    } catch (error: any) {
      toast({
        title: "Research Failed",
        description: error.message || "Failed to research website. Please try again or upload documents manually.",
        variant: "destructive",
      })
    } finally {
      setResearching(false)
    }
  }

  async function handleQuickSetupSave() {
    if (!aiDescription || aiDescription.length < 50) {
      toast({
        title: "Description Too Short",
        description: "Please provide at least 50 characters of business information.",
        variant: "destructive",
      })
      return
    }

    setSaving(true)
    
    try {
      const result = await apiClient.quickSetupSave(aiDescription, "company_overview")
      
      if (result.success) {
        toast({
          title: "Saved Successfully",
          description: result.message,
        })
        
        // Reload documents to show the new AI-generated entry
        await loadDocuments()
        
        // Reset state
        setHasResearched(false)
      } else {
        throw new Error(result.message || "Failed to save")
      }
    } catch (error: any) {
      toast({
        title: "Save Failed",
        description: error.message || "Failed to save business information.",
        variant: "destructive",
      })
    } finally {
      setSaving(false)
    }
  }

  const requiredDocuments = documents.filter(
    (doc) => doc.meta_data?.document_category === "required" || doc.meta_data?.required_type
  )

  const uploadedRequiredTypes = new Set(
    requiredDocuments
      .map((doc) => doc.meta_data?.required_type)
      .filter((type): type is string => !!type)
  )

  const requiredProgress = (uploadedRequiredTypes.size / REQUIRED_DOCUMENT_TYPES.length) * 100

  // Check if any AI-generated documents exist
  const hasAiGeneratedDocs = documents.some(doc => doc.meta_data?.ai_generated)

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold">Business Details</h2>
        <p className="text-muted-foreground">
          Help our AI understand your company better for more accurate content creation.
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as "upload" | "quick-setup")} className="w-full">
        <TabsList className="grid w-full grid-cols-2 max-w-md">
          <TabsTrigger value="upload" className="flex items-center gap-2">
            <Upload className="h-4 w-4" />
            Upload Documents
          </TabsTrigger>
          <TabsTrigger value="quick-setup" className="flex items-center gap-2">
            <Sparkles className="h-4 w-4" />
            Quick Setup
          </TabsTrigger>
        </TabsList>

        {/* Upload Documents Tab */}
        <TabsContent value="upload" className="space-y-6 mt-6">
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <div className="text-sm font-medium">Progress</div>
              <div className="text-2xl font-bold">
                {uploadedRequiredTypes.size}/{REQUIRED_DOCUMENT_TYPES.length} Completed
              </div>
            </div>
            <div className="w-1/3">
              <Progress value={requiredProgress} className="h-2" />
            </div>
          </div>

          <div className="grid gap-6 md:grid-cols-2">
            {REQUIRED_DOCUMENT_TYPES.map((docType) => {
              const isUploaded = uploadedRequiredTypes.has(docType.id)
              const uploadedDoc = requiredDocuments.find(
                (doc) => doc.meta_data?.required_type === docType.id
              )
              const DocIcon = docType.icon
              const isUploadingThis = uploading && uploadingType === docType.id
              const isAiGenerated = uploadedDoc?.meta_data?.ai_generated

              return (
                <Card
                  key={docType.id}
                  className={`transition-all duration-200 ${
                    isUploaded
                      ? "border-green-200 bg-green-50/50 dark:bg-green-900/10 dark:border-green-800"
                      : "border-slate-200 hover:border-sidebar-primary/50 dark:border-slate-800"
                  }`}
                >
                  <CardContent className="pt-6">
                    <div className="flex items-start gap-4">
                      <div className={`rounded-lg p-2 ${
                        isUploaded ? "bg-green-100 dark:bg-green-900/30" : "bg-slate-100 dark:bg-slate-800"
                      }`}>
                        <DocIcon className={`h-6 w-6 ${
                          isUploaded ? "text-green-600 dark:text-green-400" : "text-slate-500"
                        }`} />
                      </div>
                      
                      <div className="flex-1 space-y-1">
                        <div className="flex items-center justify-between">
                          <h3 className="font-semibold">{docType.name}</h3>
                          {isUploaded && (
                            <CheckCircle2 className="h-5 w-5 text-green-600 dark:text-green-400" />
                          )}
                        </div>
                        <p className="text-sm text-muted-foreground">
                          {docType.description}
                        </p>
                        
                        {uploadedDoc && (
                          <div className="mt-3 flex items-center gap-2 rounded-md bg-white px-3 py-2 text-sm border dark:bg-slate-950 dark:border-slate-800">
                            {isAiGenerated ? (
                              <Sparkles className="h-4 w-4 text-purple-500" />
                            ) : (
                              <FileText className="h-4 w-4 text-slate-400" />
                            )}
                            <span className="flex-1 truncate">{uploadedDoc.filename}</span>
                            {isAiGenerated && (
                              <Badge variant="secondary" className="text-xs">AI Generated</Badge>
                            )}
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-6 w-6 text-slate-400 hover:text-red-500"
                              onClick={() => handleDelete(uploadedDoc.id)}
                            >
                              <Trash2 className="h-3 w-3" />
                            </Button>
                          </div>
                        )}
                      </div>
                    </div>

                    {!isUploaded && (
                      <div className="mt-4">
                        <Button
                          variant="outline"
                          className="w-full"
                          disabled={uploading}
                          onClick={() => {
                            setUploadingType(docType.id)
                            fileInputRef.current?.click()
                          }}
                        >
                          {isUploadingThis ? (
                            <>
                              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                              Uploading...
                            </>
                          ) : (
                            <>
                              <Plus className="mr-2 h-4 w-4" />
                              Upload Document
                            </>
                          )}
                        </Button>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )
            })}
          </div>
        </TabsContent>

        {/* Quick Setup Tab */}
        <TabsContent value="quick-setup" className="space-y-6 mt-6">
          <Card className="border-purple-200 dark:border-purple-800">
            <CardHeader>
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-purple-100 p-2 dark:bg-purple-900/30">
                  <Sparkles className="h-6 w-6 text-purple-600 dark:text-purple-400" />
                </div>
                <div>
                  <CardTitle>AI-Powered Quick Setup</CardTitle>
                  <CardDescription>
                    Let AI research your website and generate business information automatically
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Website URL input */}
              <div className="space-y-2">
                <label className="text-sm font-medium">Website URL</label>
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <Globe className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <input
                      type="url"
                      placeholder="https://yourcompany.com"
                      value={websiteUrl}
                      onChange={(e) => setWebsiteUrl(e.target.value)}
                      className="w-full pl-10 pr-4 py-2 border rounded-md bg-background"
                    />
                  </div>
                  <Button
                    onClick={handleQuickSetupResearch}
                    disabled={researching || !websiteUrl}
                    className="bg-purple-600 hover:bg-purple-700"
                  >
                    {researching ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Researching...
                      </>
                    ) : (
                      <>
                        <Sparkles className="mr-2 h-4 w-4" />
                        Generate
                      </>
                    )}
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  We'll use AI to research your website and extract key business information.
                </p>
              </div>

              {/* AI-generated description */}
              {(hasResearched || aiDescription) && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium flex items-center gap-2">
                      <Pencil className="h-4 w-4" />
                      Generated Business Description
                    </label>
                    <div className="flex items-center gap-2">
                      {aiSources.length > 0 && (
                        <Badge variant="outline" className="text-xs">
                          {aiSources.length} sources
                        </Badge>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setIsEditing(!isEditing)}
                        className="text-xs"
                      >
                        {isEditing ? "Preview" : "Edit"}
                      </Button>
                    </div>
                  </div>
                  
                  {isEditing ? (
                    <Textarea
                      value={aiDescription}
                      onChange={(e) => setAiDescription(e.target.value)}
                      placeholder="AI-generated description will appear here. You can edit it before saving."
                      className="min-h-[400px] font-mono text-sm"
                    />
                  ) : (
                    <div className="prose prose-sm dark:prose-invert max-w-none p-4 border rounded-md bg-slate-50 dark:bg-slate-900 min-h-[300px] overflow-auto">
                      <ReactMarkdown>{aiDescription}</ReactMarkdown>
                    </div>
                  )}
                  
                  <p className="text-xs text-muted-foreground">
                    {isEditing 
                      ? "Edit the AI-generated description. Click 'Preview' to see formatted output."
                      : "Review the AI-generated description. Click 'Edit' to make changes."
                    }
                  </p>
                  
                  {/* Sources display */}
                  {aiSources.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-xs font-medium text-muted-foreground">Sources used:</p>
                      <div className="flex flex-wrap gap-2">
                        {aiSources.slice(0, 5).map((source, idx) => (
                          <a
                            key={idx}
                            href={source.uri}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-xs text-purple-600 hover:underline"
                          >
                            <Globe className="h-3 w-3" />
                            {source.title.slice(0, 30) || source.uri.slice(0, 30)}...
                          </a>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Save button */}
                  <Button
                    onClick={handleQuickSetupSave}
                    disabled={saving || !aiDescription || aiDescription.length < 50}
                    className="w-full bg-green-600 hover:bg-green-700"
                  >
                    {saving ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Saving...
                      </>
                    ) : (
                      <>
                        <Save className="mr-2 h-4 w-4" />
                        Save & Add to Knowledge Base
                      </>
                    )}
                  </Button>
                </div>
              )}

              {/* Helper text when no research done yet */}
              {!hasResearched && !aiDescription && (
                <div className="text-center py-8 text-muted-foreground">
                  <Sparkles className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p className="text-sm">
                    Enter your website URL above and click "Generate" to let AI research your business.
                  </p>
                </div>
              )}

              {/* Show existing AI-generated docs */}
              {hasAiGeneratedDocs && (
                <div className="pt-4 border-t">
                  <p className="text-sm font-medium mb-2">Previously Generated:</p>
                  <div className="space-y-2">
                    {documents
                      .filter(doc => doc.meta_data?.ai_generated)
                      .map(doc => (
                        <div key={doc.id} className="flex items-center gap-2 text-sm p-2 bg-slate-50 dark:bg-slate-900 rounded-md">
                          <Sparkles className="h-4 w-4 text-purple-500" />
                          <span className="flex-1">{doc.filename}</span>
                          <CheckCircle2 className="h-4 w-4 text-green-500" />
                        </div>
                      ))
                    }
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <div className="flex justify-end pt-4">
        <Button 
          size="lg"
          onClick={() => router.push("/onboarding/integrations")}
          className="w-full sm:w-auto"
        >
          Next Step: Integrations
          <ArrowRight className="ml-2 h-4 w-4" />
        </Button>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        accept=".txt,.md,.markdown,.pdf,.docx,.doc"
        onChange={(e) => uploadingType && handleFileSelect(e, uploadingType)}
      />
    </div>
  )
}
