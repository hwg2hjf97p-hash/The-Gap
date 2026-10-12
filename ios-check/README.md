# iOS check

A stand-in for the iPhone app's native setup, used only by CI (`.github/workflows/ios-check.yml`).
The real files live in the private mobile repo (`plugins/withQuickLog.js`, `native/quicklog/`,
`modules/quick-log-credentials/`, `targets/widget/`); these are copies so the Siri/Shortcuts setup
can be built and compiled on every change before spending an App Store build on it.
