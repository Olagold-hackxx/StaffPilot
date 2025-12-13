import { PageLayout } from "@/components/shared/page-layout"
import { PageHeader } from "@/components/shared/page-header"

export default function PrivacyPage() {
  return (
    <PageLayout>
      <PageHeader title="Privacy Policy" description="Last updated: January 2025" />

      <div className="py-16">
        <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8">
          <div className="prose prose-lg dark:prose-invert max-w-none">
            <section className="mb-12">
              <h2 className="mb-4 text-2xl font-bold">Introduction</h2>
              <p className="mb-4 leading-relaxed text-muted-foreground">
                At StaffPilot, we take your privacy seriously. This Privacy Policy explains how we collect, use, disclose,
                and safeguard your information when you use our AI consultant and management services.
              </p>
            </section>

            <section className="mb-12">
              <h2 className="mb-4 text-2xl font-bold">Information We Collect</h2>
              <h3 className="mb-3 text-xl font-semibold">Personal Information</h3>
              <p className="mb-4 leading-relaxed text-muted-foreground">
                We collect information that you provide directly to us, including:
              </p>
              <ul className="mb-4 list-disc space-y-2 pl-6 text-muted-foreground">
                <li>Name, email address, and contact information</li>
                <li>Company name and business information</li>
                <li>Payment and billing information</li>
                <li>Communications with our support team</li>
              </ul>

              <h3 className="mb-3 text-xl font-semibold">Usage Information</h3>
              <p className="mb-4 leading-relaxed text-muted-foreground">
                We automatically collect certain information about your device and how you interact with our services:
              </p>
              <ul className="mb-4 list-disc space-y-2 pl-6 text-muted-foreground">
                <li>Log data and usage patterns</li>
                <li>Device information and IP address</li>
                <li>Cookies and similar tracking technologies</li>
                <li>AI assistant interaction data</li>
              </ul>
            </section>

            <section className="mb-12">
              <h2 className="mb-4 text-2xl font-bold">How We Use Your Information</h2>
              <p className="mb-4 leading-relaxed text-muted-foreground">We use the information we collect to:</p>
              <ul className="mb-4 list-disc space-y-2 pl-6 text-muted-foreground">
                <li>Provide, maintain, and improve our AI services</li>
                <li>Process transactions and send related information</li>
                <li>Send technical notices and support messages</li>
                <li>Respond to your comments and questions</li>
                <li>Train and optimize AI models for better performance</li>
                <li>Monitor and analyze trends and usage</li>
                <li>Detect and prevent fraud and abuse</li>
              </ul>
            </section>

            <section className="mb-12">
              <h2 className="mb-4 text-2xl font-bold">Data Security</h2>
              <p className="mb-4 leading-relaxed text-muted-foreground">
                We implement appropriate technical and organizational measures to protect your personal information,
                including:
              </p>
              <ul className="mb-4 list-disc space-y-2 pl-6 text-muted-foreground">
                <li>Encryption of data in transit and at rest</li>
                <li>Regular security assessments and audits</li>
                <li>Access controls and authentication measures</li>
                <li>Employee training on data protection</li>
                <li>Compliance with industry standards (SOC 2, GDPR, CCPA)</li>
              </ul>
            </section>

            <section className="mb-12">
              <h2 className="mb-4 text-2xl font-bold">Data Retention</h2>
              <p className="mb-4 leading-relaxed text-muted-foreground">
                We retain your personal information for as long as necessary to provide our services and fulfill the
                purposes outlined in this policy. You may request deletion of your data at any time by contacting us at
                privacy@staffpilot.ai.
              </p>
            </section>

            <section className="mb-12">
              <h2 className="mb-4 text-2xl font-bold">Your Rights</h2>
              <p className="mb-4 leading-relaxed text-muted-foreground">
                Depending on your location, you may have certain rights regarding your personal information:
              </p>
              <ul className="mb-4 list-disc space-y-2 pl-6 text-muted-foreground">
                <li>Access and receive a copy of your data</li>
                <li>Correct inaccurate or incomplete data</li>
                <li>Request deletion of your data</li>
                <li>Object to or restrict processing</li>
                <li>Data portability</li>
                <li>Withdraw consent at any time</li>
              </ul>
            </section>

            <section className="mb-12">
              <h2 className="mb-4 text-2xl font-bold">Contact Us</h2>
              <p className="mb-4 leading-relaxed text-muted-foreground">
                If you have questions about this Privacy Policy or our data practices, please contact us at:
              </p>
              <p className="leading-relaxed text-muted-foreground">
                Email: privacy@staffpilot.ai
                <br />
                Address: 123 AI Street, San Francisco, CA 94105
              </p>
            </section>
          </div>
        </div>
      </div>
    </PageLayout>
  )
}
