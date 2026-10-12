import ExpoModulesCore
import Security

// Keeps the quick-log key in the Keychain so the "Log to The Gap" App Intent
// (native/quicklog/QuickLogClient.swift) can read it when the app isn't open.
// The service and account names below must match QuickLogClient.swift.
public class QuickLogCredentialsModule: Module {
  private let service = "com.causalme.thegap.quicklog"
  private let account = "token"

  private func baseQuery() -> [String: Any] {
    return [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: service,
      kSecAttrAccount as String: account,
    ]
  }

  private func store(_ token: String) -> Bool {
    guard let data = token.data(using: .utf8) else { return false }
    SecItemDelete(baseQuery() as CFDictionary)
    var query = baseQuery()
    query[kSecValueData as String] = data
    // Readable once the phone has been unlocked after a restart, so Siri works with the screen locked.
    query[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
    return SecItemAdd(query as CFDictionary, nil) == errSecSuccess
  }

  private func read() -> String? {
    var query = baseQuery()
    query[kSecReturnData as String] = true
    query[kSecMatchLimit as String] = kSecMatchLimitOne
    var item: CFTypeRef?
    guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
          let data = item as? Data,
          let token = String(data: data, encoding: .utf8),
          !token.isEmpty else { return nil }
    return token
  }

  private func remove() -> Bool {
    let status = SecItemDelete(baseQuery() as CFDictionary)
    return status == errSecSuccess || status == errSecItemNotFound
  }

  public func definition() -> ModuleDefinition {
    Name("QuickLogCredentials")

    Function("setToken") { (token: String) -> Bool in
      return self.store(token)
    }

    Function("getToken") { () -> String? in
      return self.read()
    }

    Function("clearToken") { () -> Bool in
      return self.remove()
    }
  }
}
