import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
const path = new URL("./lib/api-types.ts", import.meta.url);
const before = readFileSync(path, "utf8");
execFileSync(
  process.platform === "win32" ? "npm.cmd" : "npm",
  ["run", "generate-client"],
  { stdio: "inherit" },
);
if (before !== readFileSync(path, "utf8"))
  throw new Error("Generated client drift: commit the regenerated API types");
