export default function TermsPage() {
  return (
    <div className="min-h-screen px-5 py-16" style={{ background: "#0a1710" }}>
      <div className="max-w-2xl mx-auto">
        <h1 className="text-3xl font-bold mb-2" style={{ color: "#eef3f0" }}>
          Terms of Service
        </h1>
        <p className="text-sm mb-10" style={{ color: "#a2bcaf" }}>
          Last updated: July 2026
        </p>

        <div className="space-y-8" style={{ color: "#d0ddd6" }}>
          <section>
            <h2 className="text-lg font-semibold mb-2" style={{ color: "#c9a84c" }}>
              Using The Gap
            </h2>
            <p className="text-sm leading-relaxed">
              The Gap ("we", "us") provides personal causal-analytics software
              that connects to third-party health and calendar services on
              your behalf, with your explicit permission, to surface patterns
              in your own data. By using the app, you agree to these terms.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-2" style={{ color: "#c9a84c" }}>
              Not medical advice
            </h2>
            <p className="text-sm leading-relaxed">
              Insights, scores, and any statistics shown in the app are
              informational only. They are not medical advice, not a
              diagnosis, and not a substitute for consultation with a
              qualified healthcare professional. Do not make medical decisions
              based solely on anything shown in this app.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-2" style={{ color: "#c9a84c" }}>
              Your data connections
            </h2>
            <p className="text-sm leading-relaxed">
              You are responsible for the accounts you connect to The Gap
              (Whoop, Oura, Strava, Google, Withings, Polar, or others). You
              can disconnect any of them, or delete your account entirely, at
              any time from Settings.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-2" style={{ color: "#c9a84c" }}>
              Acceptable use
            </h2>
            <p className="text-sm leading-relaxed">
              You agree not to use The Gap to attempt to access another
              person&apos;s data without authorization, to reverse-engineer or
              abuse the service, or to use it in any way that violates
              applicable law.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-2" style={{ color: "#c9a84c" }}>
              No warranty
            </h2>
            <p className="text-sm leading-relaxed">
              The Gap is provided "as is," without warranty of any kind. We do
              not guarantee that any insight generated is complete, accurate,
              or free of error — statistical findings can be wrong, especially
              with limited data, and should be treated as a starting point for
              your own judgment, not a final answer.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-2" style={{ color: "#c9a84c" }}>
              Limitation of liability
            </h2>
            <p className="text-sm leading-relaxed">
              To the maximum extent permitted by law, The Gap and its
              creators are not liable for any indirect, incidental, or
              consequential damages arising from your use of the app.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-2" style={{ color: "#c9a84c" }}>
              Changes
            </h2>
            <p className="text-sm leading-relaxed">
              We may update these terms as the app evolves. Continued use
              after a change means you accept the updated terms.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-2" style={{ color: "#c9a84c" }}>
              Contact
            </h2>
            <p className="text-sm leading-relaxed">
              Questions about these terms can be sent to{" "}
              <a href="mailto:hello@causalme.com" style={{ color: "#34d399" }}>
                hello@causalme.com
              </a>
              .
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}
