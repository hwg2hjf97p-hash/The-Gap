import Foundation
import Security

// Sends one spoken sentence to The Gap's server and returns what Siri should say back.
// The key it uses is the separate quick-log key the app keeps in the Keychain
// (modules/quick-log-credentials), not the person's normal login, and it can only add quick logs.
enum QuickLogClient {
    static let baseURL = "https://the-gap-backend.onrender.com"
    // These two must match modules/quick-log-credentials/ios/QuickLogCredentialsModule.swift.
    static let keychainService = "com.causalme.thegap.quicklog"
    static let keychainAccount = "token"

    static func readToken() -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: keychainAccount,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data,
              let token = String(data: data, encoding: .utf8),
              !token.isEmpty else { return nil }
        return token
    }

    private static func message(from data: Data, key: String) -> String? {
        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let text = object[key] as? String,
              !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        return text
    }

    /// Returns the sentence for Siri to say. Never throws: a problem is spoken, not hidden.
    static func send(text: String, source: String) async -> String {
        let cleaned = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if cleaned.isEmpty {
            return "I didn't catch anything to log."
        }
        guard let token = readToken() else {
            return "Open The Gap and sign in first, then try again."
        }
        guard let url = URL(string: baseURL + "/quicklog/entry") else {
            return "Something is wrong with The Gap's address. Please update the app."
        }

        // The exact moment and the phone's own time zone, so the entry keeps its true local time.
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let body: [String: Any] = [
            "text": cleaned,
            "occurred_at": formatter.string(from: Date()),
            "tz": TimeZone.current.identifier,
            "source": source,
        ]
        guard let payload = try? JSONSerialization.data(withJSONObject: body) else {
            return "I couldn't log that. Please try again."
        }

        // Render's free servers can take a while to wake up, so allow for that.
        var request = URLRequest(url: url, timeoutInterval: 28)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(token, forHTTPHeaderField: "X-QuickLog-Token")
        request.httpBody = payload

        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            if status == 200 {
                return message(from: data, key: "spoken") ?? "Logged."
            }
            if status == 401 {
                return "Open The Gap and sign in again, then try once more."
            }
            return message(from: data, key: "detail") ?? "I couldn't log that. Please try again."
        } catch {
            return "I couldn't reach The Gap. Check your connection and try again."
        }
    }
}
