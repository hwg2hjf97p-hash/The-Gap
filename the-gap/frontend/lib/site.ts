/**
 * Facts about The Gap that appear on more than one page, kept in one place so they can't drift apart (assistants and search engines
 * cross-check them). When something changes (the price, the App Store link), change it here.
 */

// Flip to true on launch day, once the app is live on the App Store. Until then the pages say it is launching, and no link points at a page that doesn't exist yet.
export const APP_LIVE = false;

export const SITE = {
  name: "The Gap",
  fullName: "The Gap app by CausalMe",
  tagline: "Don't just know what. Know why.",
  url: "https://causalme.com",
  email: "hello@causalme.com",
  appStoreId: "6793031477",
  appStoreUrl: "https://apps.apple.com/app/id6793031477",
  priceMonthly: "A$9.99",
  priceYearly: "A$79.99",
  currency: "AUD",
  platform: "iPhone (iOS)",
  region: "Australia",
};

export const DISCLAIMER =
  "The Gap shows patterns in your own data. It is general information, not medical advice, and not a substitute for a doctor or other health professional.";

/** The wearables and services it can use, as people would name them. The Whoop and Oura names are their owners' trademarks. */
export const WORKS_WITH = ["Apple Health", "Apple Watch", "Whoop", "Oura", "Strava", "Withings", "Polar"];

export const TRADEMARK_NOTE =
  "Apple, Apple Watch and Apple Health are trademarks of Apple Inc. Whoop, Oura, Strava, Withings, Polar and Garmin are trademarks of their respective owners. The Gap is not affiliated with or endorsed by them.";
