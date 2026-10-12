import WidgetKit
import SwiftUI

// Reads whatever lib/widgetData.ts last wrote to the shared App Group —
// see that file for the exact keys. No network calls from the widget
// itself; it only ever shows what the app already fetched and cached.
private let appGroupId = "group.com.causalme.thegap"

struct GapWidgetEntry: TimelineEntry {
    let date: Date
    let streak: Int
    let metricLabel: String
    let metricValue: String
}

struct GapWidgetProvider: TimelineProvider {
    func placeholder(in context: Context) -> GapWidgetEntry {
        GapWidgetEntry(date: Date(), streak: 0, metricLabel: "HRV", metricValue: "—")
    }

    func getSnapshot(in context: Context, completion: @escaping (GapWidgetEntry) -> Void) {
        completion(readEntry())
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<GapWidgetEntry>) -> Void) {
        let entry = readEntry()
        // Refresh hourly — the app itself pushes fresh data into the App
        // Group on every sync/check-in, so this just re-reads periodically
        // to reflect whatever the app last wrote.
        let nextUpdate = Calendar.current.date(byAdding: .hour, value: 1, to: Date()) ?? Date()
        completion(Timeline(entries: [entry], policy: .after(nextUpdate)))
    }

    private func readEntry() -> GapWidgetEntry {
        let defaults = UserDefaults(suiteName: appGroupId)
        let streak = defaults?.integer(forKey: "gap_widget_streak") ?? 0
        let metricLabel = defaults?.string(forKey: "gap_widget_metric_label") ?? "HRV"
        let metricValue = defaults?.string(forKey: "gap_widget_metric_value") ?? "—"
        return GapWidgetEntry(date: Date(), streak: streak, metricLabel: metricLabel, metricValue: metricValue)
    }
}

struct GapWidgetView: View {
    var entry: GapWidgetEntry

    var body: some View {
        ZStack {
            Color(red: 0.039, green: 0.090, blue: 0.063) // #0a1710
            VStack(alignment: .leading, spacing: 8) {
                Text("THE GAP")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(Color(red: 0.788, green: 0.659, blue: 0.298)) // #c9a84c
                Spacer()
                Text("\(entry.streak)")
                    .font(.system(size: 34, weight: .bold))
                    .foregroundColor(Color(red: 0.933, green: 0.953, blue: 0.941)) // #eef3f0
                Text("day streak")
                    .font(.system(size: 11))
                    .foregroundColor(Color(red: 0.635, green: 0.737, blue: 0.686)) // #a2bcaf
                Spacer()
                Text("\(entry.metricLabel): \(entry.metricValue)")
                    .font(.system(size: 11))
                    .foregroundColor(Color(red: 0.635, green: 0.737, blue: 0.686))
            }
            .padding()
        }
    }
}

struct GapWidget: Widget {
    let kind: String = "GapWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: GapWidgetProvider()) { entry in
            GapWidgetView(entry: entry)
        }
        .configurationDisplayName("The Gap")
        .description("Your current streak and a key metric at a glance.")
        .supportedFamilies([.systemSmall])
    }
}
