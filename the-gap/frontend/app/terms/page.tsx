import LegalPage, { LegalSection } from "../../components/LegalPage";

export const metadata = { title: "Terms of Service — The Gap" };

const INTRO = [
  "These terms are an agreement between you and the operator of The Gap (Samuel Roberts, Queensland, Australia; \"we\", \"us\"). By creating an account or using the app, you agree to them and to our Privacy Policy. If you don't agree, please don't use The Gap.",
];

const SECTIONS: LegalSection[] = [
  {
    heading: "Who can use The Gap",
    paragraphs: [
      "You must be at least 18 and able to enter into a binding agreement. You're responsible for keeping your Apple account secure and for what happens under your account.",
    ],
  },
  {
    heading: "What The Gap does",
    paragraphs: [
      "The Gap analyses information from your phone, connected wearables and services, and what you log, to show patterns in your own data. It also offers a daily plan, reminders, food and workout tracking, an AI assistant, and suggested foods, recipes and videos.",
      "The Gap is under active development. Features may change, be added, or be removed, and the service may be unavailable from time to time.",
    ],
  },
  {
    heading: "Not medical advice",
    paragraphs: [
      "Everything in The Gap is general information only. It is not medical, nutritional or psychological advice, not a diagnosis, and not a substitute for a qualified professional who knows your circumstances. The Gap is not a medical device.",
    ],
    bullets: [
      "Check with a doctor before starting or changing an exercise or eating plan, particularly if you have a medical condition, are pregnant, or take medication.",
      "Exercise carries a risk of injury. Use weights and intensities you can control, and stop if something hurts.",
      "Food, recipe and nutrition information, including calorie and protein figures, is an estimate and can be wrong. If you have an allergy or intolerance, always check ingredients and labels yourself. Do not rely on the app to keep you safe.",
      "Insights are statistical and can be wrong, especially with little data. They show patterns, not proof of cause in your body. Do not make medical decisions based only on them.",
      "In an emergency call 000. If gambling, alcohol, tobacco or other substances are a concern for you, support is available: Gambling Help Online 1800 858 858, Quitline 13 78 48, and Lifeline 13 11 14.",
    ],
  },
  {
    heading: "Your account and your information",
    paragraphs: [
      "You own the information you put into The Gap. You give us a limited licence to store and process it, including using the AI and other service providers listed in our Privacy Policy, only so we can provide and improve the service for you.",
      "You can delete your account in Settings at any time. That permanently deletes your information and sign-in, as described in the Privacy Policy.",
    ],
  },
  {
    heading: "Subscriptions and payments",
    paragraphs: [
      "The Gap requires a paid subscription. Prices, the length of each subscription and any free trial or introductory offer are shown on the purchase screen before you buy. Payment is taken from your Apple ID account when you confirm the purchase.",
      "Subscriptions renew automatically for the same period unless you cancel at least 24 hours before the end of the current period. You can manage or cancel in Settings on your iPhone, under your name, then Subscriptions. Cancelling stops future renewals; you keep access until the end of the period you've paid for.",
      "Purchases are processed by Apple, so refunds are handled by Apple under its policies. If we change the price we'll follow Apple's rules for notifying you. Subscriptions can be restored on a new device using Restore Purchases.",
    ],
  },
  {
    heading: "Acceptable use",
    paragraphs: ["You agree not to:"],
    bullets: [
      "access or try to access anyone else's data or account;",
      "copy, reverse-engineer, scrape, overload, or interfere with the service, or try to get around its limits or security;",
      "use it unlawfully, or to harm others; or",
      "enter information that isn't yours to share.",
    ],
    after: ["We may suspend or end access if these terms are broken or to protect the service or other people."],
  },
  {
    heading: "AI-generated content",
    paragraphs: [
      "Some content, including insight explanations, daily plans, assistant answers, and recipe and food ideas, is written by an AI service. It can be inaccurate, incomplete or unsuitable for you. You're responsible for how you use it.",
    ],
  },
  {
    heading: "Third-party services and content",
    paragraphs: [
      "The Gap connects to services we don't control, including Apple Health, wearable and calendar providers, food databases, and YouTube. They have their own terms and privacy policies, and may change or stop working. Videos and links are shown for your convenience; we don't own or endorse them and aren't responsible for them. Food data may come from public and crowd-sourced databases and can contain errors.",
    ],
  },
  {
    heading: "Our property",
    paragraphs: [
      "The app, its analysis methods, text, design and branding belong to us or our licensors. We give you a personal, non-transferable licence to use the app for its intended purpose. The app includes open-source software, which remains under its own licences. If you send us feedback, we may use it without owing you anything.",
    ],
  },
  {
    heading: "Our responsibility",
    paragraphs: [
      "We take care in providing The Gap, but it is provided \"as is\" and we don't promise it will be uninterrupted, error-free, or that any insight or suggestion is accurate or suits you.",
      "Nothing in these terms limits or excludes any right you have under the Australian Consumer Law or other laws that can't be limited or excluded. Subject to that, and to the extent the law allows, we are not liable for indirect or consequential loss or for loss of data, profit or opportunity, and our total liability for any claim relating to the service is limited to the amount you paid us for the service in the 12 months before the claim (or, where the law permits, supplying the service again).",
    ],
  },
  {
    heading: "Ending your use",
    paragraphs: [
      "You can stop using The Gap and delete your account at any time. We can end or change the service with reasonable notice where we can. Sections that by their nature should continue (such as ownership, disclaimers and limits on liability) continue after your account ends.",
    ],
  },
  {
    heading: "Governing law",
    paragraphs: ["These terms are governed by the laws of Queensland, Australia, and you and we submit to the non-exclusive jurisdiction of its courts."],
  },
  {
    heading: "Terms that apply because you use an iPhone",
    paragraphs: ["These apply in addition to the rest of these terms, and in any conflict about Apple, they prevail:"],
    bullets: [
      "These terms are between you and us only, not Apple. We, not Apple, are responsible for The Gap and its content, maintenance and support, and for any claims about it.",
      "Our licence to you is limited to use on Apple devices you own or control, under the App Store's usage rules.",
      "Apple has no obligation to provide maintenance or support. If the app fails to meet a warranty, you may tell Apple and Apple will refund the purchase price of the app (if any); to the extent allowed by law Apple has no other warranty obligation for it.",
      "If a third party claims the app infringes their intellectual property, we, not Apple, are responsible for dealing with that claim.",
      "You confirm you aren't in a country subject to a U.S. embargo or listed as a restricted party, and that you'll comply with applicable third-party terms, such as your mobile data agreement.",
      "Apple and its subsidiaries are third-party beneficiaries of these terms and may enforce them against you.",
    ],
  },
  {
    heading: "Changes and contact",
    paragraphs: [
      "We may update these terms; the date above shows the latest version, and we'll tell you in the app about significant changes. Continuing to use The Gap after a change means you accept it.",
      "Questions or claims about The Gap: hello@causalme.com.",
    ],
  },
];

export default function TermsPage() {
  return <LegalPage title="Terms of Service" updated="6 October 2026" intro={INTRO} sections={SECTIONS} />;
}
