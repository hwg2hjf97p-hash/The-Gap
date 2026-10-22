"""
The how-to-use-the-app guide that Help mode answers from (routers/help.py).

Keep this in step with the app. It is the ONLY thing Help may answer from, so a screen that has changed and isn't
updated here becomes a wrong answer given with confidence. Add a line here whenever a release moves, renames or adds
something a person would look for. Anything not covered should make Help say it isn't sure and point to the email.
"""

SUPPORT_EMAIL = "hello@causalme.com"

APP_GUIDE = """
THE GAP: HOW THE APP WORKS

WHAT IT IS
The Gap finds which of a person's habits seem to move their body's numbers (sleep, HRV, resting heart rate and so on). It uses the person's own data from a wearable or Apple Health plus what they log. It is general information about their own data. It is not medical advice and does not diagnose anything.

THE FIVE TABS (along the bottom): Home, Your Health, Insights, Ask Gappy, Settings.

HOME
- Quick Entry button: opens the Journal screen, where the daily check-in and the "What just happened?" box live.
- Today's one thing: a single suggestion that unlocks after the day's check-in is saved.
- Heads-up cards: short coach-style messages about today compared with the person's usual (a big step day, a short night, water or protein running behind). Tap the X to hide one. Water and protein cards go away by themselves once the person has logged enough.
- Live strip ("So far today, live from your phone"): steps and similar numbers for today.
- Key readings (for example from Whoop or Apple Health), tappable for history. Three hexagon gauges (for example sleep, recovery and HRV) can be tapped to switch between them. Under the gauges is "Your reading": one or two sentences about that exact number, written by AI, usually comparing it with the person's own usual. It is refreshed at most once an hour (sooner only if the number itself changes). If it can't be written (AI turned off in Settings, no connection, or the trial has ended) a general line about why the reading matters is shown instead. "Understand this better" opens the full view: first what the reading is in plain words (for example sleep is the total time spent asleep, not counting time lying awake in bed), then the full personal reading, then the typical range.
- Order of Home, top to bottom: the greeting and live numbers, heads-up cards, new discoveries, Quick Entry, today's one thing, the three reading gauges, then (only when there are any) the weekly review and research cards picked for the person, then "Your progress", then the research feed.
- "Your progress" is one card below the readings that is closed by default; tap it to open or close it (the app remembers). Closed, it shows a one-line summary such as "5-day streak · 3 confirmed findings · workout planned today". Open, it holds the streak and Weekly recap link, how many days of data have been collected, Closest to a new finding, In progress (things being tried), Goals teaser, Weekly recap, Workouts teaser, and (for anyone who has trained in the last six weeks) a one-line "2 of 4 workouts this week" with a small ring, which opens Workouts. The weekly target is the one on the Workouts screen ring.
- Cards from the "Check this out" feed: short summaries of published research, with a link to the study. The X hides a card.
- An icon at the top of Home opens History, which shows any past day (day summary and Quick Entries).

JOURNAL SCREEN (opened from Quick Entry on Home)
- Daily check-in: tap the header ("Daily check-in") to open it. It asks about alcohol, caffeine, stress (1 to 10), energy drinks, cigarettes, gambling, work, arguments, travel, screen time and coffees. It opens on Yesterday before midday and on Today after. A past day can be picked and edited. Saving the same day again replaces it. "Choose what to track" at the bottom of the check-in switches categories on or off. A category that is switched off is left out of the analysis (it does not count as zero). Supplements (magnesium, melatonin, ashwagandha, omega-3) are off until switched on there; if on, they only let the app compare the person's own days with and without. It never tells anyone to take anything.
- "What just happened?" box: type a note about something that just happened (a drink of water, a cigarette, an argument, a coffee) and tap Log. Simple things are sorted automatically into water, caffeine, alcohol, cigarettes, weight or saved foods, and every note is also kept as a note. Quick prompts appear above the box when it is empty.
- A mic button next to the box (in the newest version of the app) lets the person talk instead of typing: tap it, speak, tap it again to stop, check the words, then tap Log. The first time, the phone asks to allow the microphone and speech recognition. If there is no mic button, the app needs updating from TestFlight or the App Store.
- A small list button on the left of the box opens "Anything happen today you might have forgotten?": twenty short things that often affect sleep, recovery and HRV, such as feeling more stressed or emotional than usual, an argument, being around people the person doesn't get along with, feeling bullied or walked over, feeling sick, travelling, a very late night, a boss saying good job, a really nice meal out, good news or a great time with friends. Tick any that apply, tap Done, and the sentences are added to the box to edit before tapping Log. Nothing is logged until Log is tapped. These are written so the app can pick them up as stress, conflict, illness, travel or routine change, a big win, or mood, which the engine then compares with sleep and HRV over time. It needs many days of notes before it can say anything.
- At the bottom of the Journal screen, "How Gappy read your notes" can be opened to see, day by day, how the app understood the notes (for example a good day or a tough day, and whether it noticed stress, travel, feeling unwell, conflict or a big win).
- The same thing can be done by voice with Siri when the app is closed (see Voice logging).

YOUR HEALTH TAB
- Nutrition: log food (search, scan a barcode, takeaway and restaurant items, "My regulars" saved foods and saved meals, or add your own), and water. Daily goals for calories, protein and water can be set. Tapping an entry lets you edit its servings, meal or time.
- Daily goals (the pencil or "Daily goals" on Your Health): calories, protein and water. Under protein and water the app shows a suggested range with a "Why this?" and a "Use" button. The ranges come from published guidance and the person's weight and goal; they are general guidance, not medical or dietitian advice. Suggestions can be switched off in Food preferences ("Don't suggest targets for me"), which is meant for pregnancy, breastfeeding, a medical reason to limit protein or fluids, or preferring to set your own. The app never suggests calorie targets.
- Weight card: log weight; body fat and weight can also arrive from Apple Health.
- Workouts / Training: plan a workout and check it off, start a workout, see the week's schedule, and ideas for meals and training.
- Reminders: a reminders button lets the person set water, meal, workout and check-in reminders and quiet hours. These are notifications from the phone itself.
- "Food notes to log": foods the person mentioned in a note that are not saved yet.

WORKOUTS
- Start a workout: Browse by type (7 types), For you (suggestions from the person's own habits), My templates, or start from scratch and pick exercises. There are about 43 ready-made workouts that can be edited.
- During a workout: log sets, reps and weights. For-time and AMRAP workouts use one clock for the whole workout, with an Ideal split (a time per round) or a Custom split (as many sections as wanted).
- In Training preferences the person can optionally choose which plans to show first: Women's, Men's, or No preference. It only changes the order (women's picks lead with glutes, legs and strength plans; men's with upper-body strength). Every plan stays available. The Start a workout screen also asks once if they haven't chosen.
- Progression: when a workout is started from a template or a program, each movement's weights are filled in from the person's own past lifts, with a blue line under the movement's name saying why (for example "You hit every rep last time (60 kg x 8, 8, 8). Try 62.5 kg (+2.5)."). The rule: once every rep is hit at a weight, add a little weight next time; miss reps once and repeat the weight; miss them twice and drop about 10% to rebuild. If recovery looks low that day, the weight isn't pushed. All of it can be changed.
- Rest timer: in Actual mode, finishing a set starts a rest countdown at the bottom of the workout screen, with -15s, +15s and Skip. The phone buzzes when the rest is over, and a quiet notification says so if the app is in the background (if notifications are allowed). "Rest timer: Auto" under the Planned/Actual switch changes it: Auto (about 2.5 minutes after sets of 5 reps or fewer, 90 seconds up to 12 reps, 1 minute above that), 1 minute, 90 seconds, 2 minutes, 3 minutes, or Off. There's no rest after the last set, for timed movements, or in for-time and AMRAP workouts. The choice follows the person to a new phone.
- Suggested weights also appear when repeating a past workout or starting one of the person's own saved templates.
- Finishing a workout that sets a new personal record (a heavier weight, or a better estimated one-rep max) shows a "New personal record" message. The Workouts screen also shows Personal bests (strongest lifts, ranked by estimated one-rep max), Muscle balance (sets per muscle group over the last 7 days, and groups that have gone quiet), and a "This week" ring: workouts done against a weekly target, with the days ticked and the number of weeks in a row the target was met. The target starts from the suggested range for the person's goal (or 3), and the + and - under the ring change it. The target and the active program are kept on the person's account, so they follow them to a new phone.
- Programs: Start a workout has a Programs list (for example Two days a week, Full body three days, Glutes and strength, Four-day strength split). Starting one puts a Your program card on the Workouts screen showing the week, the sessions done, and a Start button for the next session. Sessions count as done when a workout with the same name is completed that week. Longer programs have a lighter final week at about 90% of the usual weights. Stop program is on the card.
- Any workout can be saved as "my own template". Workouts can be planned for another day, and history shows past ones.

INSIGHTS TAB
- Two views: Findings and Improve.
- Findings: confirmed findings (a pattern that passed the app's checks against chance) and "still checking" cards, also called early signals (faint hints that may be chance; the card says STILL CHECKING). New confirmed findings arrive sealed ("Sealed discovery"): tap to open it. Tap a finding for its details, a chart, and "Related research" (published studies on the same subject, general information about groups of people, not about the person). A study may carry a line saying whether it points the same way as the person's own data or the other way; the person's own data always comes first. Share is available for confirmed findings only.
- Inside a finding's details: "How big is this?" (the finding next to the person's own usual range for that reading, with a plain word such as small, modest, clear or large), "Your days, side by side" (the reading on days with and without the habit, or on lower, middle and higher days, showing the average, the typical range, and the best and worst day, plus a scatter of their days for amounts), "Your last 45 days" (a timeline with the habit days highlighted), and "How we got this number" (numbered steps with the real day counts, what was accounted for, the likely range, and the check for chance). Findings saved before this was added show it after the next update of their data.
- Most tests need about three weeks of days with both the habit and the reading recorded. Until then the tab shows "Day X of Y" progress.
- "Try this": starts tracking a suggestion, and the app follows up about a week later with whether it seemed to help.
- Improve: today's focus, what the person is trying, findings ready to try, goals, food and workout cards, and short videos.
- "Big changes in your life" card (above the patterns): the person can add a lost or new job, a move, a relationship change, a new baby, an injury or illness, or a loss of someone close, with a date and an optional short note. Once there are enough days on each side, the app shows what their HRV, sleep, resting heart rate and steps did around it. This is a description, not a cause. Events can be deleted. When a note the person logs mentions one (for example losing a job), the app offers to add it, and nothing is added unless they tap Add. Gappy can refer to them (type and date only, never the note).
- Patterns card: best and worst days, and "What tends to come together in your days" (for example, on the days a person logged an argument, how many also had no lunch logged). These are same-day counts, not causes, and they only appear after several days of the event.
- Findings about a supplement the person logged are only a description of their own days. There is no Try this or improvement plan for them.

ASK GAPPY TAB
- Two modes at the top: "My data" (Gappy answers questions about the person's own findings and numbers) and "How to use the app" (this help). Help is free and does not use the AI allowance.
- Gappy never recommends a supplement or medicine, never gives doses, and does not give medical advice.
- Each subscription has a monthly AI allowance. The free month has a smaller one and up to 10 Gappy questions a day. When it is used up the Gappy screen says when it resets and, during the free month, offers "Go Pro now".

GOALS
- When setting a goal for steps, sleep or workout days, the app shows a common range and a realistic first step based on the person's recent average, with a "Use" button.
- Open Goals from Home (the goals teaser). Set a goal on a reading (for example sleep per night, steps, HRV), with a target. "Find research for my goals" adds research cards to Home. Achieved goals are listed.

SETTINGS TAB (four sections that open when tapped)
- Connections: Data sources (choose which device is the main one for each kind of reading), Apple Health, Device Calendar, "Add a Google or other calendar" (opens iPhone Settings to add the account), and the connections for Whoop, Oura, Strava, Withings and Polar. Voice logging (Siri, Action Button, Back Tap) is here. A background-sync switch for Apple Health and the heads-ups switch are here too.
- Questions & answers: a list of common questions.
- Policies & Procedures: How your data is used, AI features (a switch to turn AI features off), Manage subscription, See The Gap Pro plans, Weekly recap, Privacy Policy, Terms of Service, Credits, export your data, and delete your data or account.
- About You: name, height, weight and similar details.
- Sign out is in Settings.

CONNECTING DEVICES
- Settings, then Connections. Apple Health, Whoop, Oura, Strava, Withings and Polar can be connected. Hume body scales can send weight and body fat through Apple Health (turn on Apple Health syncing in the Hume app). Garmin and Fitbit cannot be connected directly yet.
- Whoop, Oura and the other connected services sync about every hour. Apple Health updates when the app is opened and about hourly in the background while the phone is in use. Background updates stop if the app is swiped away, Low Power Mode is on, or Background App Refresh is off.
- With more than one device, Data sources lets the person choose which one is the main one for each reading.

VOICE LOGGING
- Say "Hey Siri, log to The Gap" (also "Log The Gap", "Add to The Gap", "Add a log to The Gap"), then what happened, for example "just had a cigarette" or "500 ml of water".
- It is switched on in Settings, then Connections, then Voice logging. That section also has a guide for putting it on the Action Button or Back Tap: it uses a two-step shortcut (Dictate Text, then Log to The Gap) so the button listens instead of asking the person to type. In the shortcut, tap the "What happened?" box and pick the Dictated Text bubble above the keyboard; do not type the words.
- If it logs the words "Dictated text", the shortcut has those words typed in instead of the Dictated Text bubble.

NOTIFICATIONS
- The Gap sends: new-discovery notifications, heads-ups (at most three a day, none during quiet hours, water and protein ones only in the afternoon and evening), follow-ups on things being tried, the weekly recap, and any reminders the person set. Turn heads-ups off in Settings. Turn reminders off in the Reminders sheet. iPhone Settings, then Notifications, then The Gap controls everything.
- Setup when the app is first opened has four steps: a welcome, what the person wears, Apple Health, and wearables to connect. It does not ask for notifications or the calendar. Those are asked later, when they have a clear use:
  - Notifications: under the first heads-up on Home (or Your Health) a card asks "Want these on your lock screen?" with Turn on notifications and Not now. Not now hides it for a week. Tapping Turn on notifications shows the iPhone's own pop-up, which the iPhone only ever shows once. The "Check" row in Settings also asks if it has never been asked. If someone said no on the pop-up, they can turn notifications on in iPhone Settings, then Notifications, then The Gap.
  - Calendar: on the Insights tab, under "more on the way", a card appears when patterns that need the calendar (meetings and busy days against sleep and recovery) are waiting. It uses only how many events there were and for how long, never titles or who is in them. Not now hides it for two weeks. It can also be turned on any time in Settings, under Device Calendar.
  - A reminder before the free month ends is only delivered if notifications are on.
- If notifications are not arriving: check iPhone Settings, then Notifications, then The Gap is allowed; check Focus modes and quiet hours.

SUBSCRIPTION
- The Gap Pro starts with a free month, then renews at the price shown when the person started. Cancel any time in iPhone Settings, then the person's name, then Subscriptions, at least 24 hours before it renews. Billing is run by Apple. A refund request goes to Apple.
- During the free month, "Go Pro now" on the Gappy screen ends the free month early and starts paying straight away with the full AI allowance.

DATA AND PRIVACY
- Data is used to find patterns for the person and is never sold. There are no ads. Some features send the details they need to an AI service to write summaries, never a name or email. AI features can be turned off in Settings, under Policies & Procedures.
- Export or delete data: Settings, then Policies & Procedures. To fully remove Apple Health access, also turn it off in iPhone Settings, then Privacy & Security, then Health.

COMMON PROBLEMS
- "I have no insights yet": patterns need days of data. About three weeks of days with both the habit and the reading. The daily check-in matters most. Wear the device overnight. Missed days are fine.
- "My numbers are not updating": check the connection in Settings, then Connections; open the app to refresh Apple Health; check Background App Refresh and Low Power Mode.
- "Nothing happens when I tap Log": check the internet connection and try again.
- A check-in edit is saved by tapping Update.
"""
