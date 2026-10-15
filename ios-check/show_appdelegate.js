// Prints the AppDelegate that expo prebuild generated, as an annotation, so its exact shape can be read.
const fs = require("fs");
const path = require("path");
const iosDir = path.join(__dirname, "ios");
for (const dir of fs.readdirSync(iosDir)) {
  const full = path.join(iosDir, dir);
  if (!fs.statSync(full).isDirectory()) continue;
  for (const file of fs.readdirSync(full)) {
    if (!/^AppDelegate\./.test(file)) continue;
    const text = fs.readFileSync(path.join(full, file), "utf8").replace(/\r/g, "").slice(0, 5000);
    console.log(`::notice title=${file}::` + text.replace(/%/g, "%25").replace(/\n/g, "%0A"));
  }
}
