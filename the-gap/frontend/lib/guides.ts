/**
 * The topic guides: plain-English explainers that answer the questions people ask about their sleep and recovery data. They give
 * general information and cite published research; they never tell anyone what to do about their own health. Each reference is checked
 * against its publisher's page. Dates are the dates the guide was written or last reviewed.
 */

export type GuideSection = { heading: string; paragraphs?: string[]; bullets?: string[] };
export type Reference = { text: string; url: string };

export type Guide = {
  slug: string;
  title: string;
  headline: string;
  description: string;
  published: string;
  intro: string;
  sections: GuideSection[];
  references: Reference[];
};

export const GUIDES: Guide[] = [
  {
    slug: "what-affects-hrv",
    title: "What affects heart rate variability (HRV)?",
    headline: "What affects your HRV, and how to find out what affects yours",
    description:
      "A plain-English guide to heart rate variability: what it is, the things commonly linked to changes in it, why comparing with other people's numbers misleads, and how to learn what moves your own.",
    published: "2026-10-27",
    intro:
      "Heart rate variability (HRV) is the small variation in the time between heartbeats. Wearables report it as a single number, and many people watch it as a rough signal of how recovered they are. This guide explains what it is, what is commonly linked to changes in it, and why your own baseline matters far more than anyone else's number.",
    sections: [
      {
        heading: "What HRV is",
        paragraphs: [
          "Your heartbeat isn’t perfectly regular. The gaps between beats vary slightly, and HRV summarises how much. There are several ways to calculate it, so a number from one device or app can’t be compared directly with a number from another.",
        ],
      },
      {
        heading: "Why your numbers can’t be compared with other people’s",
        paragraphs: [
          "Published reviews of HRV research stress that typical values depend on age, sex and, importantly, how and for how long it was measured. A 5-minute reading, an overnight average and a 24-hour value are not interchangeable. This is why “is my HRV good?” has no useful answer without knowing what is normal for you, measured the same way.",
        ],
      },
      {
        heading: "Things commonly linked to changes",
        paragraphs: ["Researchers and wearable makers commonly point to a handful of factors. None of these is a rule, and their effects differ between people:"],
        bullets: [
          "Sleep: how long and how well you slept.",
          "Alcohol, especially in the evening.",
          "Training load: hard sessions, and how recovered you were going in.",
          "Illness or a developing infection.",
          "Stress and a busy or disrupted day.",
          "The time of day and conditions of the measurement itself.",
        ],
      },
      {
        heading: "How to learn what moves yours",
        paragraphs: [
          "The reliable way to find out is to look at your own data over several weeks, with a note of what you did on each day. Because many of these factors travel together (a stressful day can mean a late meal, a drink and a poor night), simply noticing that two things go together can mislead. Tools that adjust for other factors and for chance, as The Gap does, are better placed to tell what seems to matter for you.",
          "A low reading on its own is not a diagnosis. If your HRV or any other reading worries you, or changes sharply for no reason you can find, talk to a doctor.",
        ],
      },
    ],
    references: [
      {
        text: "Shaffer F, Ginsberg JP. An Overview of Heart Rate Variability Metrics and Norms. Frontiers in Public Health. 2017;5:258.",
        url: "https://www.frontiersin.org/journals/public-health/articles/10.3389/fpubh.2017.00258",
      },
      {
        text: "Pietilä J, et al. Acute Effect of Alcohol Intake on Cardiovascular Autonomic Regulation During the First Hours of Sleep in a Large Real-World Sample of Finnish Employees: Observational Study. JMIR Mental Health. 2018;5(1):e23.",
        url: "https://mental.jmir.org/2018/1/e23",
      },
    ],
  },
  {
    slug: "alcohol-and-sleep",
    title: "Does alcohol affect your sleep?",
    headline: "Does alcohol affect your sleep? What research says, and what your own data can show",
    description:
      "What published research says about alcohol and sleep, why a nightcap can feel like it helps, and how to look at your own sleep and recovery data to see what a drink does for you.",
    published: "2026-10-27",
    intro:
      "Many people feel that a drink helps them fall asleep. The research on what alcohol does to sleep is more complicated, and the effect on you may differ from the average. This guide summarises what published studies report and how to look at your own data.",
    sections: [
      {
        heading: "What research reports",
        paragraphs: [
          "A review of the laboratory studies on healthy people (Ebrahim and colleagues, 2013) found that alcohol tends to shorten the time it takes to fall asleep, and that deep sleep can increase in the first half of the night. It also found that alcohol reduces REM sleep, especially at higher doses, and that sleep tends to be more broken in the second half of the night. The authors concluded that alcohol isn’t a good sleep aid.",
          "Studies outside the laboratory point the same general way. One observational study of about 4,000 Finnish employees looked at overnight heart-rate recordings on nights with and without alcohol, to see how drinking related to the body’s overnight recovery.",
        ],
      },
      {
        heading: "Why averages aren’t enough",
        paragraphs: [
          "Those results describe groups of people. How much a drink changes your own sleep or overnight recovery depends on you, the amount, the timing, and what else is going on that day. Two people can drink the same amount and see different results.",
        ],
      },
      {
        heading: "How to see what it does for you",
        bullets: [
          "Record your drinks (and when) alongside your sleep and recovery readings for several weeks.",
          "Compare nights with and without alcohol, keeping in mind that other things differ too: a night out often means a later bedtime, a big meal and a different day.",
          "Look for a pattern that repeats across many nights, not a single bad night.",
        ],
        paragraphs: [
          "The Gap does this comparison for you: you log alcohol in the daily check-in, and it tests whether nights after drinking differ from other nights in your own sleep and HRV, adjusting for other factors and for chance. It reports a finding only when the pattern holds up, and labels it early or confirmed.",
          "This is general information, not advice about whether or how much to drink. If you’re concerned about your drinking, free confidential support is available (in Australia, the National Alcohol and Other Drug Hotline is 1800 250 015), and your doctor can help.",
        ],
      },
    ],
    references: [
      {
        text: "Ebrahim IO, Shapiro CM, Williams AJ, Fenwick PB. Alcohol and sleep I: effects on normal sleep. Alcoholism: Clinical and Experimental Research. 2013;37(4):539-549.",
        url: "https://pubmed.ncbi.nlm.nih.gov/23347102/",
      },
      {
        text: "Pietilä J, et al. Acute Effect of Alcohol Intake on Cardiovascular Autonomic Regulation During the First Hours of Sleep in a Large Real-World Sample of Finnish Employees: Observational Study. JMIR Mental Health. 2018;5(1):e23.",
        url: "https://mental.jmir.org/2018/1/e23",
      },
    ],
  },
  {
    slug: "correlation-vs-cause-in-health-data",
    title: "Correlation vs cause in your health data",
    headline: "Correlation vs cause: why “these two move together” isn’t the same as “this causes that”",
    description:
      "A plain-English explanation of why two things moving together in your health data doesn't mean one causes the other, what confounding is, and how to get closer to what really affects you.",
    published: "2026-10-27",
    intro:
      "Your wearable app might tell you that on days you drink coffee late, your sleep is worse. That’s a correlation: two things that move together. It doesn’t say the coffee caused the bad sleep. This guide explains the difference and why it matters for anyone using their own data to make decisions.",
    sections: [
      {
        heading: "Correlation is a starting point",
        paragraphs: [
          "When two things move together, there are at least three possible explanations: the first causes the second, the second causes the first, or something else causes both. A stressful day could lead to both late coffee and poor sleep, with the coffee itself doing little. That “something else” is called a confounder.",
        ],
      },
      {
        heading: "Why it’s hard with everyday data",
        paragraphs: [
          "Real lives are messy. Habits cluster: a night out brings a later dinner, a drink and a short night all at once. You can’t easily run a clean experiment on yourself, and a handful of days can show a pattern purely by luck, especially if you look at many possible patterns.",
        ],
      },
      {
        heading: "What gets you closer to cause",
        bullets: [
          "Enough days, with and without the habit, for the pattern to be seen repeatedly.",
          "Accounting for the other things going on, such as the day of the week, how you slept the night before, and how hard you trained.",
          "Correcting for the fact that testing many patterns will turn up some that look real by chance.",
          "Being honest about confidence: “early” is not the same as “confirmed”.",
        ],
        paragraphs: [
          "Even then, analysing everyday data can’t prove cause the way a controlled experiment can. It can show what seems to affect you, and you can then test it deliberately, for example by changing one thing for a week.",
        ],
      },
      {
        heading: "How The Gap approaches it",
        paragraphs: [
          "The Gap runs statistical tests on your own days that adjust for the other factors above and for chance, and labels each finding early or confirmed. It only calls something confirmed after it has held up, and it tells you how far along each pattern is.",
          "A finding is something to think about, not an instruction. This is general information, not medical advice.",
        ],
      },
    ],
    references: [
      {
        text: "Hernán MA, Robins JM. Causal Inference: What If. Chapman & Hall/CRC; 2020.",
        url: "https://miguelhernan.org/whatifbook",
      },
    ],
  },
];
