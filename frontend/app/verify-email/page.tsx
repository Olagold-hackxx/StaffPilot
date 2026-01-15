"use client"

import { useState, useEffect, Suspense } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { PageLayout } from "@/components/shared/page-layout"
import { PageHeader } from "@/components/shared/page-header"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Mail, ArrowRight, Loader2 } from "lucide-react"
import { authService } from "@/lib/auth"
import { useToast } from "@/components/ui/use-toast"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import * as z from "zod"
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form"

const verifySchema = z.object({
  code: z.string().length(6, "Verification code must be 6 digits"),
})

type VerifyFormValues = z.infer<typeof verifySchema>

function VerifyEmailContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { toast } = useToast()
  const [isLoading, setIsLoading] = useState(false)
  const [isResending, setIsResending] = useState(false)
  
  const email = searchParams.get("email")

  const form = useForm<VerifyFormValues>({
    resolver: zodResolver(verifySchema),
    defaultValues: {
      code: "",
    },
  })

  useEffect(() => {
    if (!email) {
      toast({
        title: "Error",
        description: "Email address is missing",
        variant: "destructive",
      })
      router.push("/signup")
    }
  }, [email, router, toast])

  async function onSubmit(data: VerifyFormValues) {
    if (!email) return

    setIsLoading(true)
    try {
      await authService.verifyEmail(email, data.code)
      
      toast({
        title: "Success",
        description: "Email verified successfully",
      })
      
      // Auto-login or redirect to login/onboarding
      // Since backend verify_email doesn't return a token, we might need to ask user to login or rely on existing session if any (api token might be persistent)
      // The signup flow logs them in before sending them here, so the session should be active.
      // But verify_email doesn't exchange token.
      
      router.push("/onboarding")
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to verify email. Please check the code and try again.",
        variant: "destructive",
      })
    } finally {
      setIsLoading(false)
    }
  }

  async function handleResend() {
    if (!email) return

    setIsResending(true)
    try {
      await authService.resendVerification(email)
      toast({
        title: "Code sent",
        description: "A new verification code has been sent to your email",
      })
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to resend code",
        variant: "destructive",
      })
    } finally {
      setIsResending(false)
    }
  }

  return (
    <PageLayout>
      <PageHeader
        title="Verify Your Email"
        description="Please enter the verification code sent to your email"
      />
      <div className="mx-auto max-w-md py-16">
        <Card>
          <CardHeader>
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-primary/20 to-primary/5">
              <Mail className="h-6 w-6 text-primary" />
            </div>
            <CardTitle className="text-2xl">Check your inbox</CardTitle>
            <CardDescription>
              We sent a 6-digit verification code to <span className="font-medium text-foreground">{email}</span>
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Form {...form}>
              <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
                <FormField
                  control={form.control}
                  name="code"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Verification Code</FormLabel>
                      <FormControl>
                        <Input 
                          placeholder="123456" 
                          className="text-center text-lg tracking-widest" 
                          maxLength={6}
                          {...field} 
                          onChange={(e) => {
                             const value = e.target.value.replace(/[^0-9]/g, '').slice(0, 6)
                             field.onChange(value)
                          }}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <div className="flex flex-col gap-3 pt-4">
                  <Button
                    type="submit"
                    size="lg"
                    className="w-full"
                    disabled={isLoading}
                  >
                    {isLoading ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Verifying...
                      </>
                    ) : (
                      <>
                        Verify Email
                        <ArrowRight className="ml-2 h-4 w-4" />
                      </>
                    )}
                  </Button>
                </div>
              </form>
            </Form>

            <div className="mt-6 text-center text-sm text-muted-foreground">
              Didn't receive the code?{" "}
              <Button 
                variant="link" 
                className="p-0 h-auto font-normal text-primary"
                onClick={handleResend}
                disabled={isResending}
              >
                {isResending ? "Sending..." : "Resend Code"}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </PageLayout>
  )
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<PageLayout><div className="flex justify-center py-20"><Loader2 className="h-8 w-8 animate-spin" /></div></PageLayout>}>
      <VerifyEmailContent />
    </Suspense>
  )
}
