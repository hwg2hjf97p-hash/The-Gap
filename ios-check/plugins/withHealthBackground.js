// Lets Apple Health wake The Gap in the background when new data arrives ("background delivery"),
// so steps, sleep and heart data can reach the server while the app is closed.
//
// Two things are needed that the react-native-health plugin does not do:
//   1. the background-delivery entitlement
//   2. starting the library's background observers when the app launches (its README says to edit
//      AppDelegate by hand; ios/ is rebuilt by every EAS build, so this plugin patches it each time)
const { withAppDelegate, withEntitlementsPlist } = require("expo/config-plugins");

const IMPORT = [
  "#if __has_include(<RNAppleHealthKit/RCTAppleHealthKit.h>)",
  "#import <RNAppleHealthKit/RCTAppleHealthKit.h>",
  "#else",
  '#import "RCTAppleHealthKit.h"',
  "#endif",
].join("\n");

const LAUNCH_CALL = "return [super application:application didFinishLaunchingWithOptions:launchOptions];";

module.exports = function withHealthBackground(config) {
  config = withEntitlementsPlist(config, (cfg) => {
    cfg.modResults["com.apple.developer.healthkit.background-delivery"] = true;
    return cfg;
  });

  config = withAppDelegate(config, (cfg) => {
    const language = cfg.modResults.language;
    if (language !== "objcpp" && language !== "objc") {
      throw new Error(`withHealthBackground: expected an Objective-C AppDelegate, found ${language}`);
    }
    let src = cfg.modResults.contents;
    if (!src.includes("initializeBackgroundObservers")) {
      if (!src.includes('#import "AppDelegate.h"')) {
        throw new Error("withHealthBackground: couldn't find the AppDelegate import line");
      }
      if (!src.includes(LAUNCH_CALL)) {
        throw new Error("withHealthBackground: couldn't find the launch call in AppDelegate");
      }
      src = src.replace('#import "AppDelegate.h"', () => `#import "AppDelegate.h"\n\n${IMPORT}`);
      src = src.replace(
        LAUNCH_CALL,
        () =>
          [
            "BOOL launched = [super application:application didFinishLaunchingWithOptions:launchOptions];",
            "  // Apple Health background delivery: start listening for new health data while the app is closed.",
            "  [[RCTAppleHealthKit new] initializeBackgroundObservers:self.bridge];",
            "  return launched;",
          ].join("\n")
      );
    }
    cfg.modResults.contents = src;
    return cfg;
  });

  return config;
};
