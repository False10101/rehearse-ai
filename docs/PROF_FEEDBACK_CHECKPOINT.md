# Professor feedback implementation checkpoint

Reviewed 5 November 2026 against the supplied meeting transcript.

## Transcript comparison and control

- Added a non-mutating selected-text enhancement preview.
- The review dialog shows original and suggested wording side by side, with the requested tone, style, and audience level.
- Cancel leaves the stored script untouched; Accept applies the exact reviewed replacement without another generation call.
- Accept checks ownership, paragraph structure, current revision and whether a newer generated script exists.
- Accepted enhancement history is stored using the existing revision table, including original text, replacement, settings, and time. No database migration is required.
- History is accessible below the script and survives reload and later manual paragraph deletion.
- Older revision records did not store their full original selection. Their replacement remains available, and the UI explicitly says the original is unavailable.
- The shared tone/style instructions are now included in selected-text enhancement. Formal wording explicitly excludes casual greetings and slang; audience knowledge does not change formality.
- The script badge reflects saved script provenance rather than whichever editing tab is selected.

## Upload and live coaching

- Existing gesture timeline already displays movement-specific icons, simultaneous detections on separate rows, and positions spanning the complete recording.
- Existing measured gesture observations identify the actual body part, duration, and movement from recorded measurements; AI cannot change detections or observations.
- Existing pace chart permanently shades all fast/slow intervals, with clickable audio/transcript evidence. These were checked in code and utility tests, not reprocessed against new real recordings in this task.
- Live feedback now explicitly says “Live coaching”. Empty events use camera-facing, looking-away, and head-turn wording. The current cue no longer exposes numerical-signal transport details.
- A live webcam session was not run during this task. Field testing still belongs in the demo checklist.
- Uploaded head movement is not proof of eye contact or reading notes; hands-in-pockets detection was discussed but was not an agreed implemented capability. No unsupported detector claims were added.

## Professor/demo deliverables

Under `output/prof-feedback/`:

- `Transcript_Before_After_Comparison.pdf`: four configurations, same strongly informal source, actual model responses. General/formal, beginner/formal, specialist/formal, conversational/natural.
- `transcript-comparisons.json`: exact input, context, model/prompt version, response text, and observed per-call time. These times are not whole-feature latency benchmarks.
- `Good_Delivery_Visual_Reference.pdf`: attributed TED thumbnail with visible strengths annotated. The file distinguishes still-image observations from motion or gaze claims.
- `DEMO_CHECKLIST.md`: coaching-first demo order, clear test cases, slower presentation pacing, pronunciation rehearsal, and network/offline fallback preparation.
- `transcript-review.png`, `transcript-history.png`: screenshots from an isolated local browser fixture.

## Verification

- Backend tests exercise preview without persistence, acceptance without regeneration, stale suggestions, paragraph preservation, ownership, no-op previews, history after deletion, and coaching-provider failure after acceptance.
- Browser walkthrough used actual application routes and frontend components with an isolated in-memory database and deterministic provider responses. Verified preview, Cancel, Accept, and history after reload.
- Four separate real provider calls validated the current enhancement prompt and supplied the PDF outputs.
- Production frontend build, TypeScript, ESLint, backend targeted Ruff checks, and frontend utility tests passed.
- No deployment, git commit, message to the professor, or real user-record mutation was performed.

## Still requires people/on-site execution

- Send the PDFs to the professor when ready.
- Rehearse and perform the revised demo order; use the intended network and devices.
- Verify the deployed live camera flow and keep a working fallback.
- Continue judging detection accuracy against actual video evidence; passing code/UI checks does not establish complete real-world detection coverage.


## Transcript speech-quality revision (v11, 5 November 2026)

- Replaced conflicting generation instructions with a shared spoken-writing contract used by generation, the final edit, and selected-text enhancement.
- The existing second model call now returns an edited final script and coaching for that same script. Internal writing/source issues are separate from spoken paragraphs. No extra normal-stage model call was added.
- Single-slide and bulk paths now supply the nearest saved scripts on either side for continuity. Existing script text is context, not factual evidence. Bulk still skips nonempty slides and passes newly written earlier scripts forward.
- Source defects are handled silently; actual limitations explicitly discussed by the source remain valid content. Ambiguous numerical entries are not flattened into definite claims.
- Enhancement receives the exact untouched surrounding text. Fragment whitespace and newly introduced duplicate boundary punctuation are corrected before preview; acceptance still saves the exact reviewed replacement.
- Analysis of manually saved scripts does not apply the optional generated-script rewrite.
- Verification artifacts are in `output/transcript-quality/v11/`: `Latest_Three_Before_After.md`, `Verified_Outputs.md`, and exact response JSON. Real provider calls were made through the actual API router with isolated SQLite writes, plus unrelated research/teaching cases. Source DB reads were read only. Finite quality checks do not establish perfection on unseen inputs.


## Transcript audience/configuration audit (v13)

User clarified that Specialist means polished professional/public-talk delivery, General means a normal presentation, and Beginner means student-friendly teaching. Updated shared audience rules and frontend help text accordingly; retained API enum values.

A complete 72-case first pass exposed learner/professional differentiation issues and persuasive strategy drift. Revised shared rules to v13 and began a complete rerun using the same frozen source and real API/provider with isolated SQLite writes. The v13 rerun reached 53/72 before provider credit was exhausted (credits endpoint reported approximately -0.10). All 53 responses succeeded and met the timing word range. All 53 were read: 50 clear fits; 3 marked Needs review with quotations. Nineteen v13 combinations are pending. Do not call the v13 exhaustive run complete.

Artifacts and exact resumption instructions: `output/transcript-quality/config-matrix-v13/README.md`. The runner is `tmp/transcript-revision/matrix_v13.py`; it skips completed cases and verifies source/code hashes. Test processes were stopped; saved user scripts were not overwritten.


### Configuration audit completed — 6 November 2026

After the user added credit, the remaining 19 cases were resumed using the same frozen source and unchanged v13 production code. All 72 v13 combinations now generated successfully, met the timing word range, and were read. All 24 matched length groups increased from Short to Standard to Detailed. Reading-based outcome: 61 clear fits, 11 Needs review (4 weak persuasion, 6 Detailed/Specialist feature catalogues, 1 beginner tautology). Do not call all 72 semantically perfect. The full matrix and exact quotations are in `output/transcript-quality/config-matrix-v13/`. The earlier 53/72 state above is historical; no v13 combinations remain pending.

## Continued transcript refinement — 6 November 2026 (v18)

The v13 audit above was a baseline, not the end of the work. The writer and final speech editor were refined and tested again using actual provider calls.

- Replaced conflicting instructions with a shared spoken-writing contract. Private composition planning and source assessment stay out of the words the presenter says.
- Persuasive delivery now develops a supported position through the body, rather than appending a positive sentence to a neutral inventory. It must preserve the original presentation purpose.
- Specialist means polished professional/public-talk delivery with a few developed supporting ideas. It does not mean an exhaustive technical catalogue or presumed domain expertise.
- Beginner explanations must add usable meaning rather than repeat the term being defined. General remains a normal broad-audience presentation.
- Missing or contradictory source information is handled privately; genuine subject limitations, such as research uncertainty explicitly in the source, remain valid speech.
- Final-page guidance preserves the page's actual role. A conclusion starts with its substance, honors the requested delivery tone, and acknowledges the audience at most once at the end. References and appendices are not automatically turned into closings.
- Enhancement receives exact paragraph-boundary metadata, preserves fragments that connect to untouched words, and restores an existing dropped sentence mark at a known paragraph end before preview. Accept still applies the exact reviewed text without another rewrite. No semantic keyword rejection was added.
- The normal generation path still has two model stages: draft, then final speech edit plus coaching about that final speech. Manual saved scripts are analyzed without being rewritten.

Verification artifacts are under `output/transcript-quality/config-matrix-v16/`. All 72 generation combinations were produced and read: 3 durations × 4 tones × 2 styles × 3 audience approaches. All met the word-count timing range; all 24 matched groups increased from Short to Standard to Detailed. These use one identical frozen content slide and its deck context, not 72 different decks. The subsequent v18 changes affect final-page guidance and enhancement only: `final-prompt-equivalence.json` confirms identical writer/editor prompts and request builder for all 72 content-page configurations. Separate actual API calls check openings, conclusions, tables, technical teaching, plus unrelated research and photosynthesis content. Finite sample review is not proof of perfection on unseen material.

Backend suite: 476 tests pass; targeted Ruff checks pass. User scripts were not overwritten, test writes use isolated in-memory SQLite, and harnesses/artifacts remain gitignored. No commit, push, or deployment was performed in this refinement.

Final enhancement verification: all 24 tone/style/audience combinations completed actual Preview and Accept calls and were read. Tests checked paragraph count, sentence starts, existing terminal punctuation, exact accepted replacements, and unchanged surrounding content. Four final v18 conclusions matched requested tones and word-count timing ranges. An empty optional vocabulary replacement encountered during a provider test no longer invalidates the entire coaching response: it is omitted and logged, while valid tone/term feedback is retained. The exact logged response was replayed successfully against the fix (`empty-upgrade-replay.json`). This is structural handling of an unusable optional replacement, not a semantic keyword gate.

## Current-slide speech boundary correction — 6 November 2026 (v31)

The earlier 72-case content-slide audit was insufficient evidence for opening quality on a different deck. The user's AI Park-Check opening exposed repetition, a spoken roll call, borrowed later-slide explanations, and narration of the presentation outline. Do not use the older audit to claim universal transcript quality.

Current runtime behavior:

- One dedicated speech-writing request receives the current slide's text, tables, structured chart data, and separately labeled visual-reference notes. Speech-writing rules are system instructions; the output is paragraphs only.
- Other slides contribute titles/positions for orientation, not their body text. Only earlier saved-script endings are supplied for continuity; future script content is excluded. The arbitrary first-four-text-entry outline was removed.
- Tone/vocabulary feedback runs separately on the actual written paragraphs. It cannot rewrite them or trigger regeneration. If optional feedback fails, the generated speech remains usable and feedback availability is reported honestly.
- Removed the semantic retry loop, minimum-word-count rerolls, best-of-three ranking/fallback, and the second bulk-generation retry loop. Transient HTTP handling in the shared provider helper remains unchanged.
- Short/Standard/Detailed guide paragraph depth. There is no backend word-count acceptance gate. Sparse pages may be shorter than their nominal time instead of borrowing other pages or padding.
- Bulk still skips nonempty slides, preserves completed work, and allows an explicit retry of remaining empty slides after an actual failure. The loading message no longer promises three automatic attempts.
- Invalid writing/feedback structures remain technical errors with logging. No keyword-based speech-quality validator was introduced.

Actual output review: `output/transcript-quality/v31-current-slide/Read_Actual_Scripts.html` contains the prior saved opening beside the new output and all 12 real API cases. Cases cover the opening at three lengths, a beginner opening, agenda, team, problem, proposed solution, workflow, beginner technical explanation, inputs/outputs, and closing. Each trace has exactly one writer and one non-mutating coaching call; the returned script matches the writer's paragraphs. Additional actual provider checks cover an unrelated beginner lesson opening, observational research with causal uncertainty, dense professional content, and a selected interior passage on a cover. These are finite reading-based checks, not proof that every future output will be perfect. No saved user script was overwritten.

Regression checks cover no semantic regeneration, unchanged written speech after feedback, usable speech when feedback fails, no multiplied bulk attempts, preservation of existing scripts, paragraph boundaries, and exclusion of future slide/script bodies from the writing prompt. Backend suite: 477 passing. TypeScript, targeted ESLint/Ruff, and diff whitespace checks pass. No commit, push, or deployment was performed.


## Current transcript revision and incomplete audit — 7 November 2026 (v56)

This section supersedes the v31 runtime description above. Do not use earlier matrix results to claim that the present version is exhaustively verified.

- AI Generate has two provider stages: a speech draft, then a final speech edit plus feedback about that exact final text. There is no semantic keyword gate, word-count acceptance gate, best-of-N ranking, or content reroll loop. Transient HTTP handling remains in the shared provider adapter.
- The writer receives the current page's complete extracted paragraphs (falling back to formatting runs for older decks), tables, charts, and separately labeled visual notes. Text/tables take precedence for claims. Other-page bodies and future scripts stay excluded; titles/positions and earlier script endings provide continuity only.
- Generalized rules distinguish openings, content, agendas, teams, references, and closings. They exclude credits/navigation, borrowed future explanations, source critique, and repeated introductions. There are no deck-specific answers in the production prompt.
- Tone, style, audience, and duration reach both writing stages. Specialist means professional delivery rather than elementary teaching; Beginner means understandable explanations for new learners. The editor receives the target word guide and actual draft length without using either as a backend rejection rule.
- Editing/source uncertainty goes to private edit_notes. Saved/generated speech and coaching metadata remain separate. The final response budget was raised to allow speech, reasoning, and coaching fields; malformed-JSON logging now includes finish reason and token usage.
- Human save still calls analysis only, never the generated-script editor. Existing saved user words were not overwritten by tests. Bulk skips nonempty slides and preserves completed work on failure.

Current-version verification: 21 actual API responses (6 targeted, 12/72 configuration combinations, 3/13 additional page-role cases), with two completed provider operations each. All 21 were read and their exact speech plus individual notes saved in `output/transcript-quality/TRANSCRIPT_REVIEW.html` and `.md`. The current samples are spoken scripts, but repetition, elementary Specialist wording, and approximate length remain in some cases. Do not call the feature perfect or the configuration audit complete.

Provider credit was exhausted (approximately -$0.04). Temporary paid test processes were stopped, then the user selected **Keep the saved results for now**. Remaining current-version work: 60 configurations, 10 additional role cases, 2 unrelated-domain checks. Do not restart paid tests without a new request. `README_CURRENT.md` and `CURRENT_AUDIT_STATUS.json` in the output directory record the state. Earlier experiments are retained separately and are not counted as current passes.

Local verification: 484 backend tests pass; targeted Ruff and diff-whitespace checks pass. Report selector/response counts and exact-text hashes were checked; no claim of browser visual QA. No commit, push, or deployment was performed for this revision.


## Transcript one-shot overhaul — 7 November 2026

User explicitly requested replacing the overengineered transcript pipeline with a simple spoken-script generator and enhancer. Current prompt version is `transcript-one-shot-v1`; it supersedes v56 above.

- Generation makes one `_request_json` call, returning actual spoken `paragraphs` and separate tone/term/vocabulary feedback in the same response. The final editing call and `finalize_generated_script` were removed entirely.
- Replaced long audience/tone/style rules with short instructions explicitly about a spoken presentation transcript. Removed compulsory imagined scenes, role classification/recipes, introduction assembly, draft-length comparisons, private editing notes, and duplicated composition contracts.
- Removed unused grounding critique, deck-specific term blacklist, claim-word/"slight" filters, forced acronym placeholders and letter map, ASCII pronunciation gate, and arbitrary feedback-item caps. Backend feedback handling checks structure and whether quoted terms/phrases appear in the actual script; it does not grade writing or invent missing feedback.
- Current-slide text/tables/charts/visual references remain available. Complete extracted paragraphs preserve formatting-split words; old run/string inputs remain supported. Other-page body text and future scripts stay excluded from continuity.
- Selected-text enhancement is one replacement request with the chosen settings and exact editor context. Existing paragraph boundaries, whitespace/punctuation handling, preview/accept behavior, and untouched text remain preserved.
- Human saves/accepted edits still refresh per-slide feedback without rewriting saved words. Generation keeps valid speech if optional feedback is malformed, with logging and no extra request.
- The shared JSON request helper remains generic for upload speech/gesture coaching; transcript instructions are explicitly supplied only by the transcript entry points. Model, Fast routing, and provider-error handling are preserved.

Verification: 472 backend tests pass; targeted Ruff and diff-whitespace checks pass. Tests include all 72 generation-setting combinations, all 24 enhancement-setting combinations, actual route/database persistence from one mocked provider response, human-save and enhancement acceptance invariants, empty saves, and bulk preservation. Removed tests that demanded the obsolete two-call editor or deleted semantic filters were replaced with regressions for the new behavior. These are local mocked-provider checks, not evidence of live language quality.

No paid provider calls were made during this overhaul, per the user's instruction to keep saved results for now. The 21 saved v56 responses remain historical evidence for the previous pipeline, not outputs of this one-shot version. Current one-shot generation has not been tested against the live model. No commit, push, or deployment was performed.


## Parallel bulk transcript generation — 7 November 2026

- Bulk generation now runs provider requests concurrently, defaulting to four (`TRANSCRIPT_GENERATION_WORKERS`), using frozen current-deck data and already-saved neighboring scripts. It no longer waits for each newly generated predecessor as continuity.
- Provider threads receive plain data only. The coordinating thread saves each completed result and updates job progress; SQLAlchemy sessions are not shared with workers. Single-slide generation reuses the same persistence helper.
- Existing nonempty transcripts are skipped. Empty saved transcripts remain eligible; selected slide ranges remain enforced. Content is rechecked before saving a late result. Successful parallel results survive another slide failing; the batch then reports failure for retry of remaining empty slides without multiplying provider retries.
- Verification: real thread barriers prove overlapping requests, controlled completion ordering proves incremental saves, and tests cover the concurrency limit, progress, saved context, partial failures, existing/late human content, empty scripts, and range boundaries. All 477 backend tests pass, targeted Ruff and whitespace checks pass. No paid AI calls, commit, push, or deployment performed.
