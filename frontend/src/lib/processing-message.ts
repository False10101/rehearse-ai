/** Internal failure codes stay in server logs, not in the user-facing message. */
export function processingMessage(code: string | null | undefined, fallback: string): string {
  if (code === "JOB_INTERRUPTED") return "Processing was interrupted. Please try again.";
  if (code === "Previous analysis data is incomplete. Run Slide Analyzer again.") {
    return "Your previous feedback is incomplete. Analyze this deck again to get fresh results.";
  }
  return fallback;
}
