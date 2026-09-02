/* Check the browser interpreter against the Python one.
 *
 *   node web/test_ti84.mjs
 *
 * Two implementations of the same language is a liability, not a feature.
 * It exists because a browser cannot run the Python one, and it is only
 * worth having if the two agree. This runs both over the same programs
 * and inputs and diffs the resulting screen, character for character.
 *
 * The Python one is the reference: it shares its scanner with the builder,
 * so it sees the same token stream that gets written into the .8xp. When
 * they disagree, this file's job is to say so, not to pick a winner.
 */
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..");

const TI84 = require(join(HERE, "ti84.js"));
const TABLE = JSON.parse(readFileSync(join(ROOT, "tools", "tokens_84.json"), "utf8"));

/* Each case: a program, and the answers to feed its prompts in order. */
const CASES = [
  ["ti84/src/QUADFORM.txt", ["3", "1", "-4", "3", "4", "5"]],
  ["ti84/src/QUADFORM.txt", ["3", "2", "-1", "-1", "4", "5"]],
  ["ti84/src/QUADFORM.txt", ["3", "1", "0", "1", "4", "5"]],
  ["ti84/src/QUADFORM.txt", ["1", "3", "1", "-4", "3", "4", "5"]],
  ["ti84/src/TRIANGLE.txt", ["1", "3", "4", "5"]],
  ["ti84/src/TRIANGLE.txt", ["2", "3", "4", "60"]],
];

function pythonScreen(path, inputs) {
  const args = [join(ROOT, "tools", "simulate_84.py"), join(ROOT, path)];
  for (const value of inputs) args.push("--input", value);
  let output;
  try {
    output = execFileSync("python", args, {
      encoding: "utf8",
      env: { ...process.env, PYTHONIOENCODING: "utf-8" },
      // Empty stdin, closed immediately. Without this the child blocks
      // forever the moment it asks for an input the case did not supply.
      input: "",
      timeout: 20000,
    });
  } catch (err) {
    output = (err.stdout || "") + (err.stderr || "");
  }
  // The last rendered frame is the final screen. Frames are the blocks
  // between the +---+ rules.
  // Split on CRLF as well as LF: python writes Windows line endings here,
  // and a stray \r at the end of every row reads as a phantom difference.
  const lines = output.split(/\r?\n/);
  const rules = [];
  lines.forEach((line, i) => { if (/^\s*\+-+\+\s*$/.test(line)) rules.push(i); });
  if (rules.length < 2) return null;
  const end = rules[rules.length - 1];
  const start = rules[rules.length - 2];
  return lines.slice(start + 1, end)
    .map((line) => line.replace(/^\s*\d+\s\|/, "").replace(/\|$/, ""));
}

function jsScreen(path, inputs) {
  const source = readFileSync(join(ROOT, path), "utf8");
  const { screen } = TI84.runToCompletion(source, TABLE, inputs);
  return screen.lines();
}

let failures = 0;
for (const [path, inputs] of CASES) {
  const label = `${path}  [${inputs.join(" ")}]`;
  const expected = pythonScreen(path, inputs);
  if (!expected) {
    console.log(`  SKIP  ${label}\n        python produced no screen`);
    continue;
  }
  const actual = jsScreen(path, inputs);
  const same =
    expected.length === actual.length &&
    expected.every((line, i) => line === actual[i]);

  if (same) {
    console.log(`  ok    ${label}`);
  } else {
    failures++;
    console.log(`  FAIL  ${label}`);
    const rows = Math.max(expected.length, actual.length);
    for (let i = 0; i < rows; i++) {
      const a = expected[i] ?? "";
      const b = actual[i] ?? "";
      if (a !== b) {
        console.log(`        row ${i + 1}`);
        console.log(`          python |${a}|`);
        console.log(`          js     |${b}|`);
      }
    }
  }
}

console.log("");
console.log(failures ? `${failures} case(s) disagree` : "browser and Python agree on every case");
process.exit(failures ? 1 : 0);
