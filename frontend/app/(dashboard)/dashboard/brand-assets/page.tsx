"use client"

import { useEffect, useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { apiClient } from "@/lib/api"
import { useToast } from "@/components/ui/use-toast"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog"
import { 
  LayoutGrid, Image, Loader2, Upload, Trash2, CheckCircle2,
  FileText, FolderOpen, HardDrive, ArrowLeft, Check
} from "lucide-react"

interface BrandAsset {
  id: string
  name: string
  description?: string
  asset_type: string
  source: string
  url: string
  thumbnail_url?: string
  usage_count: number
  created_at: string
}

interface DriveFile {
  id: string
  name: string
  mime_type: string
  type: 'image' | 'video' | 'folder'
  size?: number
  thumbnail_url?: string
}

export default function BrandAssetsPage() {
  const { toast } = useToast()
  
  // Brand Asset state
  const [brandAssets, setBrandAssets] = useState<BrandAsset[]>([])
  const [loadingAssets, setLoadingAssets] = useState(false)
  const [uploadingAsset, setUploadingAsset] = useState(false)
  const [selectedAssetIds, setSelectedAssetIds] = useState<string[]>([])

  // Google Drive state
  const [driveConnected, setDriveConnected] = useState(false)
  const [driveConnecting, setDriveConnecting] = useState(false)
  const [drivePickerOpen, setDrivePickerOpen] = useState(false)
  const [driveFiles, setDriveFiles] = useState<DriveFile[]>([])
  const [driveLoading, setDriveLoading] = useState(false)
  const [driveFolderStack, setDriveFolderStack] = useState<{id: string; name: string}[]>([])
  const [selectedDriveFiles, setSelectedDriveFiles] = useState<string[]>([])
  const [importingDrive, setImportingDrive] = useState(false)

  useEffect(() => {
    loadBrandAssets()
    checkDriveStatus()
    
    // Check if returning from OAuth callback
    const urlParams = new URLSearchParams(window.location.search)
    const code = urlParams.get('code')
    if (code) {
      handleDriveCallback(code)
    }
  }, [])

  async function checkDriveStatus() {
    try {
      const status = await apiClient.getGoogleDriveStatus()
      setDriveConnected(status.is_connected)
    } catch (error) {
      console.error("Failed to check Drive status:", error)
    }
  }

  async function handleDriveConnect() {
    try {
      setDriveConnecting(true)
      const redirectUri = `${window.location.origin}/dashboard/integrations`
      const response = await apiClient.getGoogleDriveAuthUrl(redirectUri)
      window.location.href = response.auth_url
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to connect Google Drive",
        variant: "destructive",
      })
      setDriveConnecting(false)
    }
  }

  async function handleDriveCallback(code: string) {
    try {
      setDriveConnecting(true)
      const redirectUri = `${window.location.origin}/dashboard/integrations`
      await apiClient.connectGoogleDrive(code, redirectUri)
      setDriveConnected(true)
      // Remove code from URL
      window.history.replaceState({}, '', window.location.pathname)
      toast({
        title: "Connected",
        description: "Google Drive connected successfully",
      })
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to connect Google Drive",
        variant: "destructive",
      })
    } finally {
      setDriveConnecting(false)
    }
  }

  async function handleDriveDisconnect() {
    try {
      await apiClient.disconnectGoogleDrive()
      setDriveConnected(false)
      toast({
        title: "Disconnected",
        description: "Google Drive disconnected",
      })
    } catch (error: any) {
      toast({
        title: "Error", 
        description: "Failed to disconnect Google Drive",
        variant: "destructive",
      })
    }
  }

  async function openDrivePicker() {
    setDrivePickerOpen(true)
    setDriveFolderStack([])
    setSelectedDriveFiles([])
    loadDriveFiles()
  }

  async function loadDriveFiles(folderId?: string) {
    try {
      setDriveLoading(true)
      const response = await apiClient.listGoogleDriveFiles(folderId)
      setDriveFiles(response.files)
    } catch (error: any) {
      toast({
        title: "Error",
        description: "Failed to load Drive files",
        variant: "destructive",
      })
    } finally {
      setDriveLoading(false)
    }
  }

  async function navigateToFolder(folder: DriveFile) {
    setDriveFolderStack([...driveFolderStack, { id: folder.id, name: folder.name }])
    loadDriveFiles(folder.id)
  }

  async function navigateBack() {
    const newStack = [...driveFolderStack]
    newStack.pop()
    setDriveFolderStack(newStack)
    loadDriveFiles(newStack.length > 0 ? newStack[newStack.length - 1].id : undefined)
  }

  async function importSelectedDriveFiles() {
    if (selectedDriveFiles.length === 0) return
    
    try {
      setImportingDrive(true)
      const response = await apiClient.importFromGoogleDrive(selectedDriveFiles)
      
      toast({
        title: "Imported",
        description: `Imported ${response.imported_count} file(s) from Google Drive`,
      })
      
      setDrivePickerOpen(false)
      setSelectedDriveFiles([])
      loadBrandAssets()
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to import files",
        variant: "destructive",
      })
    } finally {
      setImportingDrive(false)
    }
  }

  async function loadBrandAssets() {
    try {
      setLoadingAssets(true)
      const response = await apiClient.listTenantBrandAssets()
      setBrandAssets(response.assets || [])
    } catch (error: any) {
      console.error("Failed to load brand assets:", error)
      toast({
        title: "Error",
        description: "Failed to load brand assets",
        variant: "destructive",
      })
    } finally {
      setLoadingAssets(false)
    }
  }


  async function handleAssetUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return

    if (file.size > 10 * 1024 * 1024) { // 10MB limit
      toast({
        title: "File too large",
        description: "Please upload files smaller than 10MB",
        variant: "destructive",
      })
      return
    }

    try {
      setUploadingAsset(true)
      await apiClient.uploadTenantBrandAsset(file, file.name)
      await loadBrandAssets()
      toast({
        title: "Success",
        description: "Asset uploaded successfully",
      })
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to upload asset",
        variant: "destructive",
      })
    } finally {
      setUploadingAsset(false)
      // Reset input
      e.target.value = ''
    }
  }

  async function deleteAsset(id: string) {
    try {
      await apiClient.deleteTenantBrandAsset(id)
      setBrandAssets(brandAssets.filter(a => a.id !== id))
      if (selectedAssetIds.includes(id)) {
        setSelectedAssetIds(selectedAssetIds.filter(aid => aid !== id))
      }
      toast({
        title: "Success",
        description: "Asset deleted",
      })
    } catch (error: any) {
      toast({
        title: "Error",
        description: "Failed to delete asset",
        variant: "destructive",
      })
    }
  }



  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Brand Assets Library</h1>
          <p className="text-muted-foreground">Manage reference images and videos for your AI content generation</p>
        </div>
        <div className="flex items-center gap-2">
          {driveConnected ? (
            <>
              <Button variant="outline" size="sm" onClick={openDrivePicker}>
                <HardDrive className="h-4 w-4 mr-2" />
                Import from Drive
              </Button>
              <Button variant="ghost" size="sm" onClick={handleDriveDisconnect}>
                Disconnect Drive
              </Button>
            </>
          ) : (
            <Button variant="outline" size="sm" onClick={handleDriveConnect} disabled={driveConnecting}>
              {driveConnecting ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <HardDrive className="h-4 w-4 mr-2" />
              )}
              Connect Google Drive
            </Button>
          )}
        </div>
      </div>

      <div className="grid gap-6">
        <div className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <div className="space-y-1">
                <CardTitle className="text-base">Your Assets</CardTitle>
                <CardDescription>
                  Upload images/videos or view generated content. Used as references for AI generation.
                </CardDescription>
              </div>
              <div>
                <Input
                  type="file"
                  id="asset-upload"
                  className="hidden"
                  accept="image/*,video/*"
                  onChange={handleAssetUpload}
                  disabled={uploadingAsset}
                />
                <Button disabled={uploadingAsset} variant="outline" size="sm" onClick={() => document.getElementById('asset-upload')?.click()}>
                  {uploadingAsset ? (
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  ) : (
                    <Upload className="h-4 w-4 mr-2" />
                  )}
                  Upload Asset
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {loadingAssets ? (
                <div className="flex justify-center p-8">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : brandAssets.length === 0 ? (
                <div className="text-center p-12 border-2 border-dashed rounded-lg">
                  <Image className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
                  <p className="text-sm text-muted-foreground mb-2">No brand assets yet</p>
                  <Button variant="link" onClick={() => document.getElementById('asset-upload')?.click()}>
                    Upload your first asset
                  </Button>
                </div>
              ) : (
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
                  {brandAssets.map((asset) => (
                    <div 
                      key={asset.id} 
                      className={`
                        group relative aspect-square rounded-lg border overflow-hidden cursor-pointer transition-all
                        ${selectedAssetIds.includes(asset.id) ? 'ring-2 ring-primary border-primary' : 'hover:border-primary/50'}
                      `}
                      onClick={() => {
                        if (asset.asset_type === 'image') {
                          if (selectedAssetIds.includes(asset.id)) {
                            setSelectedAssetIds(selectedAssetIds.filter(id => id !== asset.id))
                          } else {
                            if (selectedAssetIds.length >= 5) {
                              toast({
                                title: "Limit Reached",
                                description: "You can select up to 5 reference images",
                                variant: "destructive"
                              })
                              return
                            }
                            setSelectedAssetIds([...selectedAssetIds, asset.id])
                          }
                        }
                      }}
                    >
                      <img 
                        src={asset.asset_type === 'video' ? (asset.thumbnail_url || asset.url) : asset.url} 
                        alt={asset.name}
                        className="w-full h-full object-cover"
                      />
                      
                      {/* Type Badge */}
                      <div className="absolute top-2 left-2">
                          <Badge variant="secondary" className="h-5 text-[10px] px-1.5 bg-background/80 backdrop-blur-sm">
                            {asset.asset_type === 'video' ? <Video className="h-3 w-3 mr-1" /> : <Image className="h-3 w-3 mr-1" />}
                            {asset.asset_type}
                          </Badge>
                      </div>

                      {/* Selection Indicator */}
                      {selectedAssetIds.includes(asset.id) && (
                        <div className="absolute top-2 right-2 bg-primary text-primary-foreground rounded-full p-0.5">
                          <CheckCircle2 className="h-4 w-4" />
                        </div>
                      )}

                      {/* Hover Overlay */}
                      <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                        <Button
                          variant="destructive"
                          size="icon"
                          className="h-8 w-8"
                          onClick={(e) => {
                            e.stopPropagation()
                            deleteAsset(asset.id)
                          }}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                      
                      {/* Name Label */}
                      <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/80 to-transparent p-2 pt-6">
                        <p className="text-xs text-white truncate text-center">{asset.name}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Google Drive Picker Dialog */}
      <Dialog open={drivePickerOpen} onOpenChange={setDrivePickerOpen}>
        <DialogContent className="max-w-2xl max-h-[70vh]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <HardDrive className="h-5 w-5" />
              Import from Google Drive
            </DialogTitle>
            <DialogDescription>
              Select images and videos to import as brand assets
            </DialogDescription>
          </DialogHeader>

          {/* Breadcrumb */}
          {driveFolderStack.length > 0 && (
            <div className="flex items-center gap-2 text-sm">
              <Button variant="ghost" size="sm" onClick={navigateBack}>
                <ArrowLeft className="h-4 w-4 mr-1" />
                Back
              </Button>
              <span className="text-muted-foreground">
                / {driveFolderStack.map(f => f.name).join(' / ')}
              </span>
            </div>
          )}

          {/* File Grid */}
          <div className="min-h-[300px] max-h-[400px] overflow-y-auto border rounded-lg p-4">
            {driveLoading ? (
              <div className="flex items-center justify-center h-full">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </div>
            ) : driveFiles.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                <FolderOpen className="h-10 w-10 mb-2" />
                <p>No images or videos found</p>
              </div>
            ) : (
              <div className="grid grid-cols-3 sm:grid-cols-4 gap-3">
                {driveFiles.map((file) => (
                  <div
                    key={file.id}
                    className={`
                      relative aspect-square rounded-lg border cursor-pointer transition-all overflow-hidden
                      ${file.type === 'folder' ? 'bg-muted/50 hover:bg-muted' : ''}
                      ${selectedDriveFiles.includes(file.id) ? 'ring-2 ring-primary border-primary' : 'hover:border-primary/50'}
                    `}
                    onClick={() => {
                      if (file.type === 'folder') {
                        navigateToFolder(file)
                      } else {
                        if (selectedDriveFiles.includes(file.id)) {
                          setSelectedDriveFiles(selectedDriveFiles.filter(id => id !== file.id))
                        } else {
                          setSelectedDriveFiles([...selectedDriveFiles, file.id])
                        }
                      }
                    }}
                  >
                    {file.type === 'folder' ? (
                      <div className="w-full h-full flex flex-col items-center justify-center p-2">
                        <FolderOpen className="h-8 w-8 text-muted-foreground mb-1" />
                        <p className="text-xs text-center truncate w-full">{file.name}</p>
                      </div>
                    ) : (
                      <>
                        {file.thumbnail_url ? (
                          <img src={file.thumbnail_url} alt={file.name} className="w-full h-full object-cover" />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center bg-muted">
                            {file.type === 'video' ? <Video className="h-8 w-8 text-muted-foreground" /> : <Image className="h-8 w-8 text-muted-foreground" />}
                          </div>
                        )}
                        <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/70 to-transparent p-1">
                          <p className="text-[10px] text-white truncate text-center">{file.name}</p>
                        </div>
                        {selectedDriveFiles.includes(file.id) && (
                          <div className="absolute top-1 right-1 bg-primary text-primary-foreground rounded-full p-0.5">
                            <Check className="h-3 w-3" />
                          </div>
                        )}
                      </>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          <DialogFooter>
            <div className="flex items-center justify-between w-full">
              <p className="text-sm text-muted-foreground">
                {selectedDriveFiles.length} file(s) selected
              </p>
              <div className="flex gap-2">
                <Button variant="outline" onClick={() => setDrivePickerOpen(false)}>
                  Cancel
                </Button>
                <Button onClick={importSelectedDriveFiles} disabled={selectedDriveFiles.length === 0 || importingDrive}>
                  {importingDrive ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Importing...
                    </>
                  ) : (
                    <>
                      <Upload className="h-4 w-4 mr-2" />
                      Import Selected
                    </>
                  )}
                </Button>
              </div>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
