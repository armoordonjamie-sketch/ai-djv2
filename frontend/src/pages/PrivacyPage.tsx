import { LegalLayout } from "@/components/legal/legal-layout"

export default function PrivacyPage() {
  return (
    <LegalLayout title="Privacy Policy" lastUpdated="December 21, 2025">
      <section className="space-y-6">
        <div>
          <h2 className="text-xl font-semibold mb-3 text-foreground">1. Information We Collect</h2>
          <p className="text-muted-foreground leading-relaxed mb-3">
            We collect information you provide directly to us, including:
          </p>
          <ul className="list-disc list-inside text-muted-foreground space-y-2 ml-4">
            <li>Account information (email, display name, password)</li>
            <li>Music preferences and mood selections</li>
            <li>Listening history and feedback (likes/dislikes)</li>
            <li>Device information and usage data</li>
          </ul>
        </div>

        <div>
          <h2 className="text-xl font-semibold mb-3 text-foreground">2. How We Use Your Information</h2>
          <p className="text-muted-foreground leading-relaxed mb-3">We use the information we collect to:</p>
          <ul className="list-disc list-inside text-muted-foreground space-y-2 ml-4">
            <li>Provide, maintain, and improve the Service</li>
            <li>Personalize your music recommendations</li>
            <li>Train our AI to better understand your preferences</li>
            <li>Send you updates, security alerts, and support messages</li>
            <li>Analyze usage patterns to improve our algorithms</li>
          </ul>
        </div>

        <div>
          <h2 className="text-xl font-semibold mb-3 text-foreground">3. AI and Machine Learning</h2>
          <p className="text-muted-foreground leading-relaxed">
            Jamify uses artificial intelligence and machine learning to personalize your experience. Your listening
            habits, mood selections, and feedback are used to train models that predict what music you'll enjoy. This
            data is processed securely and is used solely to improve your personal recommendations.
          </p>
        </div>

        <div>
          <h2 className="text-xl font-semibold mb-3 text-foreground">4. Data Sharing</h2>
          <p className="text-muted-foreground leading-relaxed mb-3">
            We do not sell your personal information. We may share your information with:
          </p>
          <ul className="list-disc list-inside text-muted-foreground space-y-2 ml-4">
            <li>Service providers who assist in operating our platform</li>
            <li>Music rights holders for royalty and licensing purposes (anonymized)</li>
            <li>Law enforcement when required by law</li>
          </ul>
        </div>

        <div>
          <h2 className="text-xl font-semibold mb-3 text-foreground">5. Data Security</h2>
          <p className="text-muted-foreground leading-relaxed">
            We implement industry-standard security measures to protect your personal information, including encryption
            in transit and at rest, secure authentication, and regular security audits. However, no method of
            transmission over the Internet is 100% secure.
          </p>
        </div>

        <div>
          <h2 className="text-xl font-semibold mb-3 text-foreground">6. Your Rights</h2>
          <p className="text-muted-foreground leading-relaxed mb-3">You have the right to:</p>
          <ul className="list-disc list-inside text-muted-foreground space-y-2 ml-4">
            <li>Access and download your personal data</li>
            <li>Correct inaccurate information</li>
            <li>Delete your account and associated data</li>
            <li>Opt out of certain data processing activities</li>
            <li>Export your data in a portable format</li>
          </ul>
        </div>

        <div>
          <h2 className="text-xl font-semibold mb-3 text-foreground">7. Cookies and Tracking</h2>
          <p className="text-muted-foreground leading-relaxed">
            We use cookies and similar technologies to remember your preferences, authenticate your sessions, and
            analyze usage patterns. You can control cookie settings through your browser, though this may affect some
            functionality.
          </p>
        </div>

        <div>
          <h2 className="text-xl font-semibold mb-3 text-foreground">8. Children's Privacy</h2>
          <p className="text-muted-foreground leading-relaxed">
            Jamify is not intended for children under 13. We do not knowingly collect personal information from children
            under 13. If you believe we have collected such information, please contact us immediately.
          </p>
        </div>

        <div>
          <h2 className="text-xl font-semibold mb-3 text-foreground">9. Changes to This Policy</h2>
          <p className="text-muted-foreground leading-relaxed">
            We may update this Privacy Policy from time to time. We will notify you of any changes by posting the new
            Privacy Policy on this page and updating the "Last updated" date.
          </p>
        </div>

        <div>
          <h2 className="text-xl font-semibold mb-3 text-foreground">10. Contact Us</h2>
          <p className="text-muted-foreground leading-relaxed">
            If you have any questions about this Privacy Policy, please contact us at{" "}
            <a href="mailto:privacy@jamify.app" className="text-primary hover:underline">
              privacy@jamify.app
            </a>
            .
          </p>
        </div>
      </section>
    </LegalLayout>
  )
}
