/** @type {import('@bacons/apple-targets').Config} */
module.exports = (config) => ({
  type: "widget",
  name: "GapWidget",
  bundleIdentifier: `${config.ios.bundleIdentifier}.widget`,
  deploymentTarget: "16.0",
  entitlements: {
    "com.apple.security.application-groups": ["group.com.causalme.thegap"],
  },
});
