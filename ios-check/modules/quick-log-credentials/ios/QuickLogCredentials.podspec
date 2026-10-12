Pod::Spec.new do |s|
  s.name           = 'QuickLogCredentials'
  s.version        = '1.0.0'
  s.summary        = 'Keeps the Siri/Shortcuts quick-log key in the iOS Keychain'
  s.description    = 'Stores the revocable quick-log key where the Log to The Gap App Intent can read it when the app is not open.'
  s.author         = 'CausalMe'
  s.homepage       = 'https://app.causalme.com'
  s.platforms      = { :ios => '15.1' }
  s.source         = { git: '' }
  s.static_framework = true

  s.dependency 'ExpoModulesCore'

  # Swift/Objective-C compatibility
  s.pod_target_xcconfig = {
    'DEFINES_MODULE' => 'YES',
    'SWIFT_COMPILATION_MODE' => 'wholemodule'
  }

  s.source_files = "**/*.{h,m,mm,swift,hpp,cpp}"
end
