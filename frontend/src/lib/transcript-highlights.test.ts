import assert from "node:assert/strict";
import test from "node:test";
import { compareWords, phraseMatches } from "./transcript-highlights.ts";

test("comparison preserves both full texts including whitespace", () => {
  for (const [before, after] of [
    ["We use  AI.\n\nNext point.", "We use AI to help.\n\nNext point."],
    ["", "New script."], ["Delete this.", ""], ["Same text.", "Same text."],
    ["A cat and a cat.", "A dog and a cat."], ["สวัสดี SME", "สวัสดี SMEs"],
  ]) {
    const result = compareWords(before, after);
    assert.equal(result.before.map((part) => part.text).join(""), before);
    assert.equal(result.after.map((part) => part.text).join(""), after);
  }
});
test("comparison marks changed words without marking the unchanged sentence", () => {
  const result = compareWords("It is kinda messy. Keep this sentence.", "It is unclear. Keep this sentence.");
  assert.equal(result.before.filter((part) => part.changed).map((part) => part.text).join(""), "kindamessy.");
  assert.equal(result.after.filter((part) => part.changed).map((part) => part.text).join(""), "unclear.");
  assert.ok(result.after.some((part) => !part.changed && part.text.includes("Keep this sentence.")));
});
test("identical scripts have no changes", () => {
  const result = compareWords("Hello there.\n\nAnother point.", "Hello there.\n\nAnother point.");
  assert.ok([...result.before, ...result.after].every((part) => !part.changed));
});
test("large selections preserve text without an unbounded comparison", () => {
  const before = "same ".repeat(2000) + "old ending";
  const after = "same ".repeat(2000) + "new ending";
  const result = compareWords(before, after);
  assert.equal(result.before.map((part) => part.text).join(""), before);
  assert.equal(result.after.map((part) => part.text).join(""), after);
  assert.ok(result.after[0].text.startsWith("same ") && !result.after[0].changed);
});
test("annotations match whole phrases and retain exact character offsets", () => {
  const text = "Paid tools use AI, then ai. A.I. uses C++ and job  fit analytics.";
  assert.deepEqual(phraseMatches(text, "AI").map((part) => text.slice(part.start, part.end)), ["AI", "ai"]);
  assert.equal(phraseMatches(text, "C++").length, 1);
  assert.equal(phraseMatches(text, "A.I.").length, 1);
  const [match] = phraseMatches(text, "job fit analytics");
  assert.equal(text.slice(match.start, match.end), "job  fit analytics");
  assert.deepEqual(phraseMatches(text, ""), []);
  assert.deepEqual(phraseMatches(text, "not present"), []);
});
