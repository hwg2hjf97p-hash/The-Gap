export default function PrivacyPolicyPage() {
  return (
    <div className="min-h-screen px-5 py-16" style={{ background: "#0a1710" }}>
      <div className="max-w-2xl mx-auto prose-invert">
        <h1 className="text-3xl font-bold mb-2" style={{ color: "#eef3f0" }}>
          Privacy Policy
        </h1>
        <p className="text-sm mb-10" style={{ color: "#a2bcaf" }}>
          Last updated: July 2026
        </p>

        <div className="space-y-8" style={{ color: "#d0ddd6" }}>
          <section>
            <h2 className="text-lg font-semibold mb-2" style={{ color: "#c9a84c" }}>
              What we collect
            </h2>
            <p className="text-sm leading-relaxed">
              When you connect a device or service — Whoop, Oura, Strava, Google
              Calendar, Withings, or Polar — we access the health, activity, or
              calendar data those services make available to us, using the
              permissions you explicitly grant during that connection. This can
              include heart rate variability, resting heart rate, sleep duration
              and stages, recovery or readiness scores, weight, step counts, and
              calendar event timing. We also store any &quot;Quick Entry&quot; notes you
              write directly in the app.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-2" style={{ color: "#c9a84c" }}>
              How we use it
            </h2>
            <p className="text-sm leading-relaxed">
              Your data is used solely to compute causal insights about your own
              patterns — for example, whether poor sleep on your own data
              actually precedes lower next-day HRV for you specifically. Quick
              Entry notes are sent to Anthropic&apos;s Claude API to extract
              structured signals (such as whether an entry mentions stress,
              travel, or illness) and, if you use the in-app Assistant, to
              answer your questions grounded in your own stored results.
              We do not use your data to train any AI model, ours or
              anyone else&apos;s.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-2" style={{ color: "#c9a84c" }}>
              Who we share it with
            </h2>
            <p className="text-sm leading-relaxed">
              We share data only with the infrastructure providers necessary to
              run the app: Supabase (our database), Anthropic (AI processing of
              journal entries and assistant queries), and the wearable/calendar
              providers you&apos;ve connected (solely to retrieve your own data
              back from them). We do not sell your data, and we do not share it
              with advertisers — this app carries no ads.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-2" style={{ color: "#c9a84c" }}>
              Your rights
            </h2>
            <p className="text-sm leading-relaxed">
              You can export everything we have stored about you, or permanently
              delete your account and all associated data, at any time from
              Settings. Deleting your account removes our stored copy of your
              data; it does not automatically revoke the connection on the
              provider&apos;s own side (e.g. Whoop) — you can do that separately
              from that provider&apos;s own account settings if you&apos;d like to fully
              revoke access at the source.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-2" style={{ color: "#c9a84c" }}>
              Data retention
            </h2>
            <p className="text-sm leading-relaxed">
              We retain your data for as long as your account is active, so we
              can keep computing fresh insights as new data arrives. If you
              disconnect a data source, previously synced data from it remains
              until you delete your account, unless you request its removal
              directly.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-2" style={{ color: "#c9a84c" }}>
              Not a medical device
            </h2>
            <p className="text-sm leading-relaxed">
              The Gap provides statistical, informational insights about your
              own data. It is not a medical device, does not diagnose any
              condition, and should not replace advice from a qualified
              healthcare provider.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-2" style={{ color: "#c9a84c" }}>
              Contact
            </h2>
            <p className="text-sm leading-relaxed">
              Questions about this policy or your data can be sent to{" "}
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
