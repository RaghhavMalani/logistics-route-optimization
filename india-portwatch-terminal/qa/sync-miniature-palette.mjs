import { readFileSync, writeFileSync } from "node:fs";
import ts from "typescript";

const source = new URL(
  "../src/components/miniature/palette.ts",
  import.meta.url,
);
const output = new URL(
  "../src/components/miniature/palette.css",
  import.meta.url,
);
const compiled = ts.transpileModule(readFileSync(source, "utf8"), {
  compilerOptions: { module: ts.ModuleKind.ESNext },
}).outputText;
const { COLORS, CSS_TOKENS } = await import(
  "data:text/javascript;base64," + Buffer.from(compiled).toString("base64")
);
const tokens = Object.entries(CSS_TOKENS).map(([name, key]) => {
  const value = COLORS[key];
  if (!/^#[0-9a-f]{6}(?:[0-9a-f]{2})?$/i.test(value)) {
    throw new Error(`Invalid palette entry for --${name}`);
  }
  return `  --${name}: ${value};`;
});
const css = [
  "/* Generated from palette.ts; run node qa/sync-miniature-palette.mjs. */",
  ":root {",
  ...tokens,
  "}",
  "",
].join("\n");

if (process.argv.includes("--check")) {
  if (readFileSync(output, "utf8").replaceAll("\r\n", "\n") !== css) {
    throw new Error(
      "Regenerate palette.css with node qa/sync-miniature-palette.mjs",
    );
  }
} else {
  writeFileSync(output, css);
}
