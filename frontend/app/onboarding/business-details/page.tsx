"use client"

import { useEffect, useState, useRef, useCallback } from "react"
import { useRouter } from "next/navigation"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { apiClient } from "@/lib/api"
import { useToast } from "@/components/ui/use-toast"
import { FileText, Upload, Trash2, CheckCircle2, Plus, X, ArrowRight, Loader2 } from "lucide-react"
import { Progress } from "@/components/ui/progress"

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

  useEffect(() => {
    loadDocuments()
  }, [loadDocuments])

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

  const requiredDocuments = documents.filter(
    (doc) => doc.meta_data?.document_category === "required" || doc.meta_data?.required_type
  )

  const uploadedRequiredTypes = new Set(
    requiredDocuments
      .map((doc) => doc.meta_data?.required_type)
      .filter((type): type is string => !!type)
  )

  const requiredProgress = (uploadedRequiredTypes.size / REQUIRED_DOCUMENT_TYPES.length) * 100

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold">Business Details</h2>
        <p className="text-muted-foreground">
          Upload these documents to help our AI understand your company better. 
          The more information you provide, the better the results.
        </p>
      </div>

      <div className="space-y-6">
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
                          <FileText className="h-4 w-4 text-slate-400" />
                          <span className="flex-1 truncate">{uploadedDoc.filename}</span>
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
      </div>

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
