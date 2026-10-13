/** Internal failure codes stay in server logs, not in the user-facing message. */
export function processingMessage(code: string | null | undefined, fallback: string): string {
  if (code === "AI_PROVIDER_BUSY") return "The AI service is temporarily busy. Please try again in a few minutes.";
  if (code === "AI_PROVIDER_CREDITS") return "The AI service has reached its credit or spending limit. Please contact the app owner.";
  if (code === "AI_PROVIDER_UNAVAILABLE") return "The AI service is temporarily unavailable. Please try again later.";
  if (code === "AI_PROVIDER_REQUEST_FAILED") return "The AI service could not accept this request. Please contact the app owner.";
  if (code === "invalid_analysis_response") return "The AI response was incomplete. Please analyze this deck again.";
  if (code === "JOB_INTERRUPTED") return "Processing was interrupted. Please try again.";
  if (code === "Previous analysis data is incomplete. Run Slide Analyzer again.") {
    return "Your previous feedback is incomplete. Analyze this deck again to get fresh results.";
  }
  return fallback;
}
