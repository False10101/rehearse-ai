# Slide Analyzer Beta Checkpoint

Last reviewed: 2026-09-12

## Test snapshot

- Presentation ID: `af544b7a-d02a-4f41-92da-7412ef30a9a0`
- File: `JOBES Sprint04 (3).pptx`
- Analyzer model: `openai/gpt-5.4-mini`
- Vision model: `qwen/qwen3-vl-8b-instruct`
- Prompt version: `slide-analyzer-structured-extraction-v8`
- Processing result: completed, 10 slides, all slide images and vision context generated
- Saved overall score: 6.4/10

## Current beta decision

The slide analyzer is usable for beta testing. The upload, extraction, vision pass,
structured analysis, persistence, and slide UI pipeline work end to end. The output
must still be treated as coaching assistance rather than an authoritative review.

The grouped-text extraction fix is working: content from separate text regions is
now available to the analyzer, and the dense third slide was correctly identified
as overloaded.

## Quality findings from this run

### Working acceptably

- The deck sequence and overall cohesion were understood.
- Slide 3 was correctly identified as overloaded.
- Slide 4's fragmented feature headings were detected.
- The stray Thai editing marker `แก้` on slide 6 was detected.
- Slide 9's wording and spelling problems were detected.
- Missing agenda detection worked.
- Suggestions no longer contain unnecessary `Slide N` prefixes.

### Confirmed defects and missed issues

1. Slide 4 contains five feature cards, but the analysis calls it a
   "six-feature layout."
2. Slide 8's pricing is mathematically consistent: `6.99 x 12 = 83.88`, and an
   18% discount gives approximately `69`. The real issue is ambiguous labeling,
   not conflicting amounts.
3. Slide 8 is readable. Repeated benefits are a content-efficiency problem, not
   necessarily visual overload.
4. Slide 6 is titled "Traction" but mainly contains target audience, future plans,
   potential partnerships, and unexplained percentages. It does not demonstrate
   achieved traction, and the analyzer missed this important claim-evidence gap.
5. Slide 5's market-size figures and slide 6's claims need clearer evidence or
   sourcing. These should rank above minor wording fixes.
6. Slide 2 visibly contains a source line inside a chart image, but reference
   detection returned no references because the citation was not recovered from
   extracted text or vision context.
7. `TAM` and `SAM` should probably not be returned as unexplained complex terms,
   because their full forms are provided earlier in the deck.
8. Slide 3 is correctly marked overloaded, but recommending additional takeaway
   lines could add more content. Suggestions should replace or condense content.
9. Slide 9 already contains the comparison table recommended by its table tip.
   The tip should be empty or propose a genuinely different structure.
10. Slide 10 contains two substantially duplicate next-step/contact suggestions.
11. Examiner red flags are too lenient. The result should question unsupported
    market figures and whether the slide labeled "Traction" contains actual
    traction evidence.

## Remaining work after transcript integration

These are quality improvements, not blockers for starting transcript work:

1. Add cross-slide grounding so definitions, citations, and explanations on other
   slides are considered before returning missing-term or missing-reference flags.
2. Improve citation detection for text embedded in images, preferably with OCR or
   a dedicated vision instruction and deterministic validation.
3. Tighten claim-evidence checks for market sizing, traction, partnerships,
   percentages, and other examiner-sensitive claims.
4. Separate factual inconsistency, ambiguous labeling, redundancy, and visual
   overload instead of treating them as interchangeable problems.
5. Validate table tips against the existing slide structure so the analyzer does
   not recommend a table that is already present.
6. Reject factual-count mistakes and semantically duplicate suggestions.
7. Improve priority ranking so substantive evidence problems outrank cosmetic
   wording fixes.

## Deferred scope

- Manual reanalysis remains unavailable unless processing fails.
- App-generated agenda slides are not analyzed as original user slides.
- Export can remain deferred until after the beta feature work.

## Demo validation still required

- Run Slide Analyzer on the same PPTX 10 times, then compare all 10 complete
  responses to measure whether the feedback varies too much for a reliable beta
  presentation.
- Time those same 10 runs and record both total processing time and approximate
  per-slide processing time so the demo duration can be estimated realistically.
