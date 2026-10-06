import LegalPage, { LegalSection } from "../../components/LegalPage";

export const metadata = { title: "Privacy Policy — The Gap" };

const INTRO = [
  "The Gap is a personal health-insights app. It finds patterns in your own data, such as how your sleep, training, food and daily habits relate to your recovery. Much of the information involved is health information, so we want to be clear and specific about what we collect, why, and who else handles it.",
  "In this policy, \"The Gap\", \"we\" and \"us\" mean the operator of The Gap (Samuel Roberts, Queensland, Australia). It covers the app and the website at app.causalme.com. We aim to handle personal information in line with the Australian Privacy Principles in the Privacy Act 1988 (Cth).",
];

const SECTIONS: LegalSection[] = [
  {
    heading: "What we collect",
    paragraphs: ["We collect only what you give us, connect, or log, plus a small amount of technical information needed to run the app."],
    bullets: [
      "Your account: your Sign in with Apple identifier, and your name and email address if you choose to share them (Apple may give us a private relay address instead). We create an internal user id for you. We don't see your Apple ID password or payment card details.",
      "Apple Health data you allow (read-only): heart rate variability, resting heart rate, heart rate, steps, sleep (total and stages), active energy, VO2 max, and nutrition totals. The app reads this on your phone and sends us daily summaries.",
      "Connected services you choose to link (Whoop, Oura, Strava, Withings, Polar, Google Calendar): the data each one makes available under the permissions you grant, such as recovery, sleep, HRV, workouts, weight, and calendar timing.",
      "Your calendar: from your phone's calendar or Google Calendar, we use the number of events, meeting hours and timing. We don't store event titles or attendees.",
      "What you log: Quick Entry notes; daily check-ins (stress, alcohol, caffeine, energy drinks, cigarettes, gambling time, work hours, arguments, travel, and, only if you switch it on, other substances); food and water; workouts (exercises, sets, reps, weights, set start and stop times, and each set's average and peak heart rate); and any notes you add.",
      "About you: height, weight and age if you enter them; your calorie, protein and water goals; your workout schedule; your diet goal, eating style, allergies or foods to avoid; your training goal and equipment; your goals and experiments; and the questions you ask the in-app assistant (Gappy).",
      "Places: a home and work address if you enter them, the coordinates we look up from them, the weather for that place, and estimated commute times. The app does not use your phone's GPS.",
      "Results we create: insights, scores, summaries, daily plans, recipe and video suggestions, and weekly recaps produced from the information above.",
      "Technical information: your notification token, and standard server logs (such as IP address, time, and error details) used to keep the service running and secure.",
    ],
    after: [
      "A lot of this is health information, which the Privacy Act treats as sensitive. We collect it only with your consent, which you give when you first open the app and by connecting a source, turning on a feature, or logging something. You can withdraw consent at any time by disconnecting a source, switching a check-in category off, or deleting your account (see section 8).",
    ],
  },
  {
    heading: "How we use it",
    bullets: [
      "To find patterns and show you insights about your own data, and to produce your daily plan, recaps, reminders and suggestions.",
      "To send notifications you've allowed, such as discoveries, check-in reminders and workout reminders. You can turn these off in iOS Settings or in the app.",
      "To run, secure and fix the service, to look after your subscription, and to comply with the law.",
    ],
    after: [
      "We do not sell your information. We do not show advertising, and the app contains no advertising or third-party analytics tools. We do not track you across other companies' apps or websites.",
    ],
  },
  {
    heading: "AI processing",
    paragraphs: [
      "Some features use an AI service, Claude, provided by Anthropic. AI features are optional: the app asks you on first use and you can change your choice at any time in Settings. If you switch them off, nothing is sent to the AI service, and those features stop (the rest of the app keeps working).",
      "When AI features are on, the app's server sends Anthropic only the information needed for the feature you use. We don't send your name, email address or account id.",
    ],
    bullets: [
      "Quick Entry notes: the text, so it can pick out things like stress, travel or illness.",
      "The assistant (Gappy): your question, plus a summary of your recent insights and metrics.",
      "Insight stories, plans and explanations: the details of an insight (what was compared, the size of the effect, how confident we are) and metric trends.",
      "Daily plan: your recovery readings compared with your own average, whether you've logged a workout, and how your food and water are going.",
      "Metric explanations: the reading, how it compares with your recent average, and, if you've entered them, your age, height and weight.",
      "Food and recipe ideas: your diet goal, eating style, allergies or foods to avoid, and your calorie and protein goals.",
    ],
    after: [
      "We do not use your data to train AI models. Under Anthropic's terms for its API, content sent through it is not used to train its models by default, and Anthropic may keep it for a limited time for safety and abuse prevention.",
      "AI output can be wrong. It is general information, not medical or dietary advice. Please read our Terms of Service.",
    ],
  },
  {
    heading: "Who else handles your information",
    paragraphs: ["We use these service providers to run The Gap. Each handles your information only to provide its service to us."],
    rows: [
      { label: "Supabase", text: "Our database and sign-in system. Holds your account and the information described above." },
      { label: "Render", text: "Hosts our server, which processes your data and talks to the other services." },
      { label: "Anthropic", text: "The AI service described in section 3." },
      { label: "Apple", text: "Sign in with Apple, push notifications, and App Store purchases. Apple Health data stays on your phone except for the summaries the app sends us." },
      { label: "RevenueCat", text: "Manages subscriptions. It receives your internal user id and purchase status." },
      { label: "Expo", text: "Delivers push notifications and app updates to your phone." },
      { label: "Wearable and calendar providers", text: "Whoop, Oura, Strava, Withings, Polar and Google, only if you connect them, so we can retrieve your own data. Their own privacy policies apply to what they hold." },
      { label: "Open-Meteo and Google Maps", text: "Look up the place you enter, fetch weather for it, and estimate commute times. They receive the place names or coordinates, not your name or account." },
      { label: "USDA FoodData Central and Open Food Facts", text: "Receive the food names you search for and barcodes you scan, through our server. They don't receive your account details." },
      { label: "YouTube (Google) and jsDelivr", text: "The app loads video thumbnails and exercise pictures from them, so they can see your IP address, like any website you visit. Videos open in YouTube, which has its own policy." },
    ],
    after: [
      "We may also share information if the law requires it, to protect people's safety or our legal rights, or as part of a sale or restructure of the business (in which case this policy would continue to apply to your information).",
    ],
  },
  {
    heading: "Where your information is processed",
    paragraphs: [
      "Some of our providers process information outside Australia, including in the United States. Before sending information overseas we take reasonable steps to make sure the provider handles it in a way consistent with the Australian Privacy Principles, for example through their contractual terms.",
    ],
  },
  {
    heading: "Security",
    paragraphs: [
      "Information is encrypted in transit. Our database does not accept direct access from the public; only our server, using a protected key, can read and write it, and each request is checked against the signed-in account. We keep access to production data to the minimum needed. No system is perfectly secure. If a breach is likely to cause you serious harm, we will tell you and the Australian Information Commissioner as the law requires.",
    ],
  },
  {
    heading: "How long we keep it, and deleting it",
    paragraphs: [
      "We keep your information while your account is active so your insights can keep improving as new data arrives.",
      "You can delete your account in the app under Settings. This permanently deletes the information we hold about you and your sign-in. Copies in our providers' routine backups are removed on their normal schedule. Records held by others are not affected, for example Apple's purchase records, RevenueCat's subscription history, and data inside your wearable accounts. To fully revoke a connection at its source, also disconnect The Gap in that provider's own settings.",
      "If you only disconnect a source, we stop collecting from it, but what we already synced stays until you delete your account or ask us to remove it.",
    ],
  },
  {
    heading: "Your choices and rights",
    bullets: [
      "Access: you can ask for a copy of your information by emailing us, and Settings also has an export option. We'll respond within 30 days.",
      "Correct: you can edit most things you've logged in the app, including a past day's check-in. Email us for anything you can't change yourself.",
      "Delete or withdraw consent: see section 7. You can also change Apple Health, Calendar, camera and notification permissions in iOS Settings at any time.",
      "If you are in the European Economic Area or the United Kingdom, you may also have rights to portability, to object to or restrict processing, and to complain to your local data protection authority. Contact us and we'll help.",
    ],
  },
  {
    heading: "Age",
    paragraphs: ["The Gap is for people aged 18 and over. We don't knowingly collect information from anyone under 18. If you think we have, contact us and we'll delete it."],
  },
  {
    heading: "Not medical advice",
    paragraphs: [
      "The Gap provides general, informational insights about your own data. It is not a medical device and does not diagnose, treat or prevent any condition. It is not a substitute for advice from a qualified health professional. Our Terms of Service explain this further.",
    ],
  },
  {
    heading: "Changes to this policy",
    paragraphs: ["We may update this policy as the app changes. We'll update the date above, and tell you in the app if a change is significant."],
  },
  {
    heading: "Contact and complaints",
    paragraphs: [
      "Questions, access requests or complaints: hello@causalme.com. We'll acknowledge your message promptly and aim to resolve it within 30 days. If you're not satisfied, you can complain to the Office of the Australian Information Commissioner (oaic.gov.au).",
    ],
  },
];

export default function PrivacyPolicyPage() {
  return <LegalPage title="Privacy Policy" updated="6 October 2026" intro={INTRO} sections={SECTIONS} />;
}
