import { LegalLayout } from "@/components/legal/legal-layout"

export default function TermsPage() {
  return (
    <LegalLayout title="Terms of Service" lastUpdated="December 21, 2025">
      <section className="space-y-6">
        <div>
          <h2 className="text-xl font-semibold mb-3 text-foreground">1. Acceptance of Terms</h2>
          <p className="text-muted-foreground leading-relaxed">
            By accessing and using Jamify ("the Service"), you accept and agree to be bound by the terms and provisions
            of this agreement. If you do not agree to abide by these terms, please do not use this service.
          </p>
        </div>

        <div>
          <h2 className="text-xl font-semibold mb-3 text-foreground">2. Description of Service</h2>
          <p className="text-muted-foreground leading-relaxed">
            Jamify is an AI-powered music streaming service that provides personalized music recommendations based on
            your mood preferences and listening habits. The service uses machine learning algorithms to curate and
            generate playlists tailored to your tastes.
          </p>
        </div>

        <div>
          <h2 className="text-xl font-semibold mb-3 text-foreground">3. User Accounts</h2>
          <p className="text-muted-foreground leading-relaxed">
            To use certain features of the Service, you must register for an account. You agree to provide accurate,
            current, and complete information during registration and to update such information to keep it accurate,
            current, and complete. You are responsible for safeguarding your password and for all activities that occur
            under your account.
          </p>
        </div>

        <div>
          <h2 className="text-xl font-semibold mb-3 text-foreground">4. User Conduct</h2>
          <p className="text-muted-foreground leading-relaxed mb-3">You agree not to:</p>
          <ul className="list-disc list-inside text-muted-foreground space-y-2 ml-4">
            <li>Use the Service for any unlawful purpose</li>
            <li>Attempt to gain unauthorized access to any portion of the Service</li>
            <li>Interfere with or disrupt the Service or servers</li>
            <li>Share your account credentials with others</li>
            <li>Use automated means to access the Service without permission</li>
          </ul>
        </div>

        <div>
          <h2 className="text-xl font-semibold mb-3 text-foreground">5. Intellectual Property</h2>
          <p className="text-muted-foreground leading-relaxed">
            All content, features, and functionality of the Service are owned by Jamify and are protected by
            international copyright, trademark, and other intellectual property laws. You may not reproduce, distribute,
            or create derivative works without express written permission.
          </p>
        </div>

        <div>
          <h2 className="text-xl font-semibold mb-3 text-foreground">6. Music Content</h2>
          <p className="text-muted-foreground leading-relaxed">
            Music content provided through the Service is licensed from various rights holders. Your use of music
            content is subject to the terms of those licenses. You may not download, copy, or redistribute music content
            except as expressly permitted.
          </p>
        </div>

        <div>
          <h2 className="text-xl font-semibold mb-3 text-foreground">7. Limitation of Liability</h2>
          <p className="text-muted-foreground leading-relaxed">
            Jamify shall not be liable for any indirect, incidental, special, consequential, or punitive damages
            resulting from your use of or inability to use the Service. Our total liability shall not exceed the amount
            you paid us in the twelve months preceding the claim.
          </p>
        </div>

        <div>
          <h2 className="text-xl font-semibold mb-3 text-foreground">8. Changes to Terms</h2>
          <p className="text-muted-foreground leading-relaxed">
            We reserve the right to modify these terms at any time. We will notify users of any material changes via
            email or through the Service. Your continued use of the Service after such modifications constitutes your
            acceptance of the updated terms.
          </p>
        </div>

        <div>
          <h2 className="text-xl font-semibold mb-3 text-foreground">9. Contact</h2>
          <p className="text-muted-foreground leading-relaxed">
            If you have any questions about these Terms, please contact us at{" "}
            <a href="mailto:legal@jamify.app" className="text-primary hover:underline">
              legal@jamify.app
            </a>
            .
          </p>
        </div>
      </section>
    </LegalLayout>
  )
}
