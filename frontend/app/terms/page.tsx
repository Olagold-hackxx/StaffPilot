import { PageLayout } from "@/components/shared/page-layout"
import { PageHeader } from "@/components/shared/page-header"

export default function TermsPage() {
  return (
    <PageLayout>
      <PageHeader title="Terms of Service" description="Last updated: January 2025" />

      <div className="py-16">
        <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8">
          <div className="prose prose-lg dark:prose-invert max-w-none">
            <section className="mb-12">
              <h2 className="mb-4 text-2xl font-bold">Agreement to Terms</h2>
              <p className="mb-4 leading-relaxed text-muted-foreground">
                By accessing or using StaffPilot's services, you agree to be bound by these Terms of Service. If you
                disagree with any part of these terms, you may not access our services.
              </p>
            </section>

            <section className="mb-12">
              <h2 className="mb-4 text-2xl font-bold">Services Description</h2>
              <p className="mb-4 leading-relaxed text-muted-foreground">
                StaffPilot provides AI consultant and management services, including:
              </p>
              <ul className="mb-4 list-disc space-y-2 pl-6 text-muted-foreground">
                <li>Custom AI assistant setup and configuration</li>
                <li>Integration with third-party platforms</li>
                <li>Ongoing management and optimization</li>
                <li>Technical support and training</li>
                <li>Performance monitoring and reporting</li>
              </ul>
            </section>

            <section className="mb-12">
              <h2 className="mb-4 text-2xl font-bold">User Responsibilities</h2>
              <p className="mb-4 leading-relaxed text-muted-foreground">As a user of our services, you agree to:</p>
              <ul className="mb-4 list-disc space-y-2 pl-6 text-muted-foreground">
                <li>Provide accurate and complete information</li>
                <li>Maintain the security of your account credentials</li>
                <li>Use the services in compliance with applicable laws</li>
                <li>Not misuse or attempt to disrupt our services</li>
                <li>Not use the services for illegal or unauthorized purposes</li>
                <li>Respect intellectual property rights</li>
              </ul>
            </section>

            <section className="mb-12">
              <h2 className="mb-4 text-2xl font-bold">Payment Terms</h2>
              <p className="mb-4 leading-relaxed text-muted-foreground">
                Subscription fees are billed in advance on a monthly or annual basis. You agree to:
              </p>
              <ul className="mb-4 list-disc space-y-2 pl-6 text-muted-foreground">
                <li>Pay all fees associated with your selected plan</li>
                <li>Provide valid payment information</li>
                <li>Authorize automatic recurring charges</li>
                <li>Pay any applicable taxes</li>
              </ul>
              <p className="mb-4 leading-relaxed text-muted-foreground">
                Refunds are available within 30 days of initial purchase. Cancellations take effect at the end of the
                current billing period.
              </p>
            </section>

            <section className="mb-12">
              <h2 className="mb-4 text-2xl font-bold">Intellectual Property</h2>
              <p className="mb-4 leading-relaxed text-muted-foreground">
                The services, including all content, features, and functionality, are owned by StaffPilot and protected by
                international copyright, trademark, and other intellectual property laws.
              </p>
              <p className="mb-4 leading-relaxed text-muted-foreground">
                You retain ownership of any data you provide to our services. By using our services, you grant us a
                license to use your data solely for the purpose of providing and improving our services.
              </p>
            </section>

            <section className="mb-12">
              <h2 className="mb-4 text-2xl font-bold">Limitation of Liability</h2>
              <p className="mb-4 leading-relaxed text-muted-foreground">
                To the maximum extent permitted by law, StaffPilot shall not be liable for any indirect, incidental,
                special, consequential, or punitive damages resulting from your use of or inability to use the services.
              </p>
            </section>

            <section className="mb-12">
              <h2 className="mb-4 text-2xl font-bold">Service Level Agreement</h2>
              <p className="mb-4 leading-relaxed text-muted-foreground">
                We strive to maintain 99.9% uptime for our services. In the event of service disruptions, we will work
                promptly to restore functionality and may provide service credits as outlined in your service agreement.
              </p>
            </section>

            <section className="mb-12">
              <h2 className="mb-4 text-2xl font-bold">Termination</h2>
              <p className="mb-4 leading-relaxed text-muted-foreground">
                We may terminate or suspend your access to our services immediately, without prior notice, for any
                breach of these Terms. Upon termination, your right to use the services will cease immediately.
              </p>
            </section>

            <section className="mb-12">
              <h2 className="mb-4 text-2xl font-bold">Changes to Terms</h2>
              <p className="mb-4 leading-relaxed text-muted-foreground">
                We reserve the right to modify these terms at any time. We will notify you of any changes by posting the
                new Terms of Service on this page and updating the "Last updated" date.
              </p>
            </section>

            <section className="mb-12">
              <h2 className="mb-4 text-2xl font-bold">Contact Information</h2>
              <p className="mb-4 leading-relaxed text-muted-foreground">
                For questions about these Terms of Service, please contact us at:
              </p>
              <p className="leading-relaxed text-muted-foreground">
                Email: legal@staffpilot.ai
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
 