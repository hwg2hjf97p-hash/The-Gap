// After `expo prebuild`: did the Siri files really land in the main app's compile list, and will the Keychain module be linked?
const fs = require("fs");
const path = require("path");
const xcode = require("xcode");

const problems = [];
const iosDir = path.join(__dirname, "ios");
const projectDir = fs.readdirSync(iosDir).find((n) => n.endsWith(".xcodeproj"));
if (!projectDir) {
  console.log("::error title=prebuild::no .xcodeproj was generated");
  process.exit(1);
}
const appName = projectDir.replace(".xcodeproj", "");
const project = xcode.project(path.join(iosDir, projectDir, "project.pbxproj"));
project.parseSync();

for (const f of ["QuickLogIntent.swift", "QuickLogClient.swift"]) {
  if (!fs.existsSync(path.join(iosDir, appName, f))) problems.push(`${f} was not copied into ios/${appName}`);
}

const targets = project.pbxNativeTargetSection();
const files = project.pbxBuildFileSection();
const refs = project.pbxFileReferenceSection();
const phases = project.hash.project.objects["PBXSourcesBuildPhase"];
const names = {};
for (const [key, tgt] of Object.entries(targets)) {
  if (key.endsWith("_comment")) continue;
  const compiled = [];
  for (const p of tgt.buildPhases || []) {
    const phase = phases[p.value];
    if (!phase) continue;
    for (const f of phase.files) {
      const bf = files[f.value];
      const ref = bf && refs[bf.fileRef];
      if (ref) compiled.push(String(ref.path).replace(/"/g, ""));
    }
  }
  names[String(tgt.name).replace(/"/g, "")] = { type: String(tgt.productType).replace(/"/g, ""), compiled };
}
console.log(JSON.stringify(names, null, 1));

const main = Object.entries(names).find(([, v]) => v.type === "com.apple.product-type.application");
if (!main) problems.push("no application target found");
else {
  for (const f of ["QuickLogIntent.swift", "QuickLogClient.swift"]) {
    const n = main[1].compiled.filter((c) => c.endsWith(f)).length;
    if (n !== 1) problems.push(`${f} is compiled ${n} times in the app target (want exactly 1)`);
  }
}
for (const [name, v] of Object.entries(names)) {
  if (v.type !== "com.apple.product-type.application" && v.compiled.some((c) => c.includes("QuickLog"))) problems.push(`QuickLog files leaked into target ${name}`);
}
const widget = Object.entries(names).find(([n]) => n.includes("Widget"));
if (!widget) problems.push("the widget target is missing (apple-targets did not run)");

// Apple Health background delivery: the entitlement and the AppDelegate patch (exactly once).
const delegatePath = ["AppDelegate.mm", "AppDelegate.m"].map((n) => path.join(iosDir, appName, n)).find((p) => fs.existsSync(p));
if (!delegatePath) problems.push("no AppDelegate was generated");
else {
  const d = fs.readFileSync(delegatePath, "utf8");
  const calls = (d.match(/initializeBackgroundObservers:self.bridge/g) || []).length;
  if (calls !== 1) problems.push(`AppDelegate has ${calls} background-observer calls (want exactly 1)`);
  if (!/RCTAppleHealthKit.h/.test(d)) problems.push("AppDelegate is missing the HealthKit import");
  if (!/BOOL launched = [super application:application didFinishLaunchingWithOptions:launchOptions];/.test(d)) problems.push("AppDelegate launch call was not rewritten");
  if (d.indexOf("initializeBackgroundObservers") < d.indexOf("BOOL launched")) problems.push("observers are started before the app finishes launching");
}
const entPath = path.join(iosDir, appName, appName + ".entitlements");
const ent = fs.existsSync(entPath) ? fs.readFileSync(entPath, "utf8") : "";
if (!ent.includes("com.apple.developer.healthkit.background-delivery")) problems.push("the background-delivery entitlement is missing");
if (!ent.includes("com.apple.developer.healthkit<")) problems.push("the HealthKit entitlement is missing");

const podfile = fs.existsSync(path.join(iosDir, "Podfile")) ? fs.readFileSync(path.join(iosDir, "Podfile"), "utf8") : "";
console.log("Podfile mentions autolinking:", /use_expo_modules!/.test(podfile));

if (problems.length) {
  const msg = problems.join("%0A");
  console.log(`::error title=ios-check::${msg}`);
  process.exit(1);
}
console.log("OK: Siri files are in the app target and the widget target is intact");
