// Adds the "Log to The Gap" Siri / Shortcuts action to the iPhone app.
//
// The app's ios/ folder is rebuilt from scratch by every EAS build, so the Swift
// files live in native/quicklog/ and this plugin copies them into the main app
// target each time. (The Keychain helper is a normal local Expo module in modules/.)
const fs = require("fs");
const path = require("path");
const { withXcodeProject, IOSConfig } = require("expo/config-plugins");

const SOURCE_DIR = path.join("native", "quicklog");

module.exports = function withQuickLog(config) {
  return withXcodeProject(config, (cfg) => {
    const project = cfg.modResults;
    const { projectRoot, platformProjectRoot, projectName } = cfg.modRequest;
    const sourceDir = path.join(projectRoot, SOURCE_DIR);
    const destDir = path.join(platformProjectRoot, projectName);

    const files = fs.readdirSync(sourceDir).filter((name) => name.endsWith(".swift"));
    if (files.length === 0) {
      throw new Error(`withQuickLog: no Swift files found in ${SOURCE_DIR}`);
    }

    for (const name of files) {
      fs.copyFileSync(path.join(sourceDir, name), path.join(destDir, name));
      IOSConfig.XcodeUtils.addBuildSourceFileToGroup({
        filepath: `${projectName}/${name}`,
        groupName: projectName,
        project,
        verbose: true,
      });
    }
    return cfg;
  });
};
