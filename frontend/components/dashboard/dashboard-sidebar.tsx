"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { cn } from "@/lib/utils"
import { 
  LayoutDashboard, 
  Bot, 
  MessageSquare, 
  FileText, 
  Share2, 
  Settings, 
  LogOut, 
  FileText as ContentIcon, 
  Target, 
  BarChart3,
  ChevronLeft,
  ChevronRight,
  Zap
} from "lucide-react"
import { useRouter } from "next/navigation"
import { authService } from "@/lib/auth"
import { useToast } from "@/components/ui/use-toast"
import { Button } from "@/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"

const navigation = [
  { name: "Overview", href: "/dashboard", icon: LayoutDashboard },
  { name: "Assistants", href: "/dashboard/assistants", icon: Bot },
  { name: "Content", href: "/dashboard/content", icon: ContentIcon },
  { name: "Campaigns", href: "/dashboard/campaigns", icon: Target },
  { name: "Analytics", href: "/dashboard/analytics", icon: BarChart3 },
  { name: "Chat", href: "/dashboard/chat", icon: MessageSquare },
  { name: "Documents", href: "/dashboard/documents", icon: FileText },
  { name: "Integrations", href: "/dashboard/integrations", icon: Share2 },
  { name: "Settings", href: "/dashboard/settings", icon: Settings },
]

export function DashboardSidebar() {
  const pathname = usePathname()
  const router = useRouter()
  const { toast } = useToast()
  const [isCollapsed, setIsCollapsed] = useState(false)

  // Optional: Persist collapsed state
  useEffect(() => {
    const saved = localStorage.getItem("sidebar-collapsed")
    if (saved) setIsCollapsed(JSON.parse(saved))
  }, [])

  const toggleCollapse = () => {
    const newState = !isCollapsed
    setIsCollapsed(newState)
    localStorage.setItem("sidebar-collapsed", JSON.stringify(newState))
  }

  const handleLogout = () => {
    authService.logout()
    toast({
      title: "Logged out",
      description: "You have been logged out successfully",
    })
    router.push("/login")
  }

  return (
    <TooltipProvider>
      <aside 
        className={cn(
          "relative flex flex-col border-r bg-card transition-all duration-300 ease-in-out",
          isCollapsed ? "w-[70px]" : "w-64"
        )}
      >
        <div className={cn(
          "flex h-16 items-center border-b transition-all duration-300",
          isCollapsed ? "justify-center px-2" : "px-6"
        )}>
          <Link href="/" className="flex items-center gap-2 overflow-hidden">
             <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                <Zap className="h-5 w-5 fill-current" />
             </div>
            {!isCollapsed && (
              <span className="text-xl font-bold bg-clip-text text-primary truncate animate-in fade-in slide-in-from-left-2">
                StaffPilot
              </span>
            )}
          </Link>
        </div>

        <nav className="space-y-1 p-2 flex-1 mt-4">
          {navigation.map((item) => {
            const isActive = pathname === item.href
            
            if (isCollapsed) {
              return (
                <Tooltip key={item.name} delayDuration={0}>
                  <TooltipTrigger asChild>
                    <Link
                      href={item.href}
                      className={cn(
                        "flex h-10 w-10 items-center justify-center rounded-lg transition-colors mx-auto",
                        isActive
                          ? "bg-primary text-primary-foreground"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground",
                      )}
                    >
                      <item.icon className="h-5 w-5" />
                      <span className="sr-only">{item.name}</span>
                    </Link>
                  </TooltipTrigger>
                  <TooltipContent side="right">
                    {item.name}
                  </TooltipContent>
                </Tooltip>
              )
            }

            return (
              <Link
                key={item.name}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                <item.icon className="h-5 w-5 shrink-0" />
                <span className="truncate">{item.name}</span>
              </Link>
            )
          })}
        </nav>

        <div className="p-2 border-t">
          {isCollapsed ? (
             <Tooltip delayDuration={0}>
               <TooltipTrigger asChild>
                 <button
                   onClick={handleLogout}
                   className="flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors mx-auto"
                 >
                   <LogOut className="h-5 w-5" />
                   <span className="sr-only">Logout</span>
                 </button>
               </TooltipTrigger>
               <TooltipContent side="right">Logout</TooltipContent>
             </Tooltip>
          ) : (
            <button
              onClick={handleLogout}
              className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
            >
              <LogOut className="h-5 w-5 shrink-0" />
              <span className="truncate">Logout</span>
            </button>
          )}
        </div>

        {/* Collapse Toggle Button */}
        <div className="absolute -right-3 top-20 z-10">
          <Button
            variant="outline"
            size="icon"
            className="h-6 w-6 rounded-full border shadow-sm bg-background text-foreground hover:bg-muted"
            onClick={toggleCollapse}
          >
            {isCollapsed ? (
              <ChevronRight className="h-3 w-3" />
            ) : (
              <ChevronLeft className="h-3 w-3" />
            )}
          </Button>
        </div>
      </aside>
    </TooltipProvider>
  )
}
