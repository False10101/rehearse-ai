import assert from "node:assert/strict";
import test from "node:test";
import { processingMessage } from "./processing-message.ts";

test("internal error codes never become user-facing messages", () => {
  for (const code of [null, undefined, "ValidationError", "HTTPError", "Provider internal failure"]) {
    assert.equal(processingMessage(code, "Please try again."), "Please try again.");
  }
});

test("interrupted work and incomplete saved feedback have actionable messages", () => {
  assert.equal(processingMessage("JOB_INTERRUPTED", "Fallback"), "Processing was interrupted. Please try again.");
  assert.match(processingMessage("Previous analysis data is incomplete. Run Slide Analyzer again.", "Fallback"), /Analyze this deck again/);
});

test("provider failures are distinguished from incomplete analysis", () => {
  assert.match(processingMessage("AI_PROVIDER_BUSY", "Fallback"), /temporarily busy/);
  assert.match(processingMessage("AI_PROVIDER_CREDITS", "Fallback"), /credit or spending limit/);
  assert.match(processingMessage("AI_PROVIDER_UNAVAILABLE", "Fallback"), /temporarily unavailable/);
  assert.match(processingMessage("invalid_analysis_response", "Fallback"), /response was incomplete/);
});
