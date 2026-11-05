import {
  mkdtempSync,
  readFileSync,
  rmdirSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const require = createRequire(import.meta.url);
const cli = require.resolve("@playwright/test/cli");
const projects = ["desktop-1920", "laptop-1366"];
const args = [
  cli,
  "test",
  ...projects.map((project) => `--project=${project}`),
];
const requested = process.argv.slice(2);
const researchOnly = requested.includes("--research-only");
const withoutResearch = requested.includes("--without-research");
if (researchOnly && withoutResearch)
  throw new Error("Choose one Research test partition");
const forwarded = requested.filter(
  (argument) => !["--research-only", "--without-research"].includes(argument),
);
const { baseline, cases } = JSON.parse(
  readFileSync(new URL("./browser-quarantine.json", import.meta.url)),
);
const selectors = cases.map(({ project, file, title, owner, reason }) => {
  if (
    !projects.includes(project) ||
    !/^qa\/tests\/[\w-]+\.spec\.ts$/.test(file) ||
    !title?.trim() ||
    !owner?.trim() ||
    !reason?.trim()
  )
    throw new Error(
      `Invalid browser quarantine entry: ${JSON.stringify({ project, file, title })}`,
    );
  return `[${project}] › ${file.slice("qa/tests/".length)} › ${title}`;
});
if (new Set(selectors).size !== selectors.length)
  throw new Error("Duplicate browser quarantine entry");

const list = spawnSync(
  process.execPath,
  [...args, "--list", "--reporter=list"],
  { encoding: "utf8" },
);
if (list.status !== 0)
  throw new Error(list.stderr || list.stdout || "Could not list browser tests");
const known = new Set(
  list.stdout.split(/\r?\n/).map((line) =>
    line
      .trim()
      .replaceAll("\\", "/")
      .replace(/(\.spec\.ts):\d+:\d+/, "$1"),
  ),
);
for (const selector of selectors) {
  if (!known.has(selector))
    throw new Error(`Stale browser quarantine entry: ${selector}`);
}
console.log(
  `Browser quarantine: ${selectors.length} baseline failures from ${baseline}`,
);
// Research retains its complete assertions and both viewports. A separate CI
// worker prevents two software-rendered charts from consuming its test budget.
const research = [...known].filter((selector) =>
  selector.includes(" › shared-feedback.spec.ts › "),
);
const activeResearch = research.filter(
  (selector) => !selectors.includes(selector),
);
if ((researchOnly || withoutResearch) && activeResearch.length === 0)
  throw new Error("Research partition must contain active tests");
const routedAway = researchOnly
  ? [...known].filter(
      (selector) =>
        /^\[(?:desktop-1920|laptop-1366)\] › /.test(selector) &&
        !research.includes(selector),
    )
  : withoutResearch
    ? research
    : [];
if (researchOnly || withoutResearch)
  console.log(
    `${activeResearch.length} active Research cases ${researchOnly ? "in the isolated renderer job" : "assigned to the isolated renderer job"}`,
  );

const scratch = mkdtempSync(join(tmpdir(), "portwatch-browser-ci-"));
const exclusions = join(scratch, "exclude.txt");
try {
  writeFileSync(
    exclusions,
    [...new Set([...selectors, ...routedAway])].join("\n") + "\n",
  );
  const result = spawnSync(
    process.execPath,
    [
      ...args,
      "--test-list-invert",
      exclusions,
      ...forwarded,
      ...(researchOnly ? ["--workers=1"] : []),
    ],
    {
      stdio: "inherit",
    },
  );
  if (result.error) throw result.error;
  process.exitCode = result.status ?? 1;
} finally {
  unlinkSync(exclusions);
  rmdirSync(scratch);
}
