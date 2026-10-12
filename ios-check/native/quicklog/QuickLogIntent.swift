import AppIntents

// "Hey Siri, log to The Gap" -> "What happened?" -> "just had a cigarette" -> "Logged 1 cigarette, 1 today."
// Also shows up in the Shortcuts app, so it can be put on the Action Button or Back Tap.
// The server sorts the sentence (water, saved foods, check-in counts, weight, or a note),
// so new things can be understood without a new app build.
@available(iOS 16.0, *)
struct LogToTheGapIntent: AppIntent {
    static let title: LocalizedStringResource = "Log to The Gap"
    static let description = IntentDescription("Say what just happened, like \"just had a cigarette\" or \"drank 500 ml of water\". The Gap logs it with the time.")
    static let openAppWhenRun: Bool = false

    @Parameter(title: "What happened?", requestValueDialog: IntentDialog("What happened?"))
    var text: String

    static var parameterSummary: some ParameterSummary {
        Summary("Log \(\.$text) to The Gap")
    }

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let reply = await QuickLogClient.send(text: text, source: "siri")
        return .result(dialog: IntentDialog(stringLiteral: reply))
    }
}

@available(iOS 16.0, *)
struct TheGapShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: LogToTheGapIntent(),
            phrases: [
                "Log to \(.applicationName)",
                "Log in \(.applicationName)",
                "Tell \(.applicationName)",
                "\(.applicationName) log",
            ],
            shortTitle: "Log to The Gap",
            systemImageName: "mic.fill"
        )
    }
}
