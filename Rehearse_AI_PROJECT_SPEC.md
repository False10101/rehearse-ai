# Rehearse AI — Complete Product and Implementation Specification

**Project type:** B.Sc. Computer Science capstone project  
**Institution:** School of Information Technology, King Mongkut's University of Technology Thonburi (KMUTT)  
**Project year:** 2026  
**Alpha checkpoint:** September 14, 2026  
**Final checkpoint:** November 2026; exact date not yet confirmed  
**Document purpose:** This is the implementation source of truth for a coding agent. It describes what the application must do, the architecture it should use, the data it should store, the behavior of each module, the required user flows, and the order in which the system should be built.

---

## 1. Instructions for the Coding Agent

You are implementing **Rehearse AI**, an AI-powered presentation coaching web application for university students.

Follow these rules while working:

1. Read this complete specification before changing or generating code.
2. Inspect the existing repository and prototype scripts before assuming that a component does not exist.
3. Implement the application incrementally. Do not attempt the entire product in one giant change.
4. Start with the repository structure, frontend/backend scaffolding, database connection, authentication foundation, and a single end-to-end presentation-upload flow.
5. Keep AI providers, storage providers, thresholds, prompts, and model identifiers configurable through environment variables or typed settings.
6. Never hardcode private API keys, database credentials, bucket names, OAuth secrets, or production URLs.
7. Use strict request, response, and AI-output schemas. Never trust raw LLM JSON without validation.
8. Keep long-running extraction, AI, video, and speech work outside synchronous request handlers.
9. Preserve the privacy rules in this document, especially immediate cleanup of uploaded video media and zero storage of live camera frames.
10. Treat all AI/CV feedback as coaching guidance, not objective grading or psychological diagnosis.
11. Do not add features outside the documented scope unless explicitly asked.
12. Before each implementation phase, state the files and components that will be created or changed. Afterward, run relevant tests and report the result.

### First implementation objective

The first coding milestone is not the complete product. It is this thin vertical slice:

1. A user can register and sign in.
2. The user can upload a valid PPTX file.
3. The backend stores the PPTX, creates the presentation record, extracts slide information, renders slide images, and persists the results.
4. The frontend displays the presentation and ordered slide thumbnails.
5. Processing and failure statuses are visible to the user.

Once that vertical slice works, integrate the Slide Analyzer, then the Transcript Enhancer. The Live Practice and File Upload Practice tracks may be developed in parallel but should not destabilize the first working flow.

---

## 2. Product Summary

Rehearse AI is a desktop-oriented web application that helps individual university students prepare academic presentations. It combines three main capabilities:

1. **Slide Analyzer** — analyzes a PowerPoint deck and gives deck-level and slide-level feedback.
2. **Transcript Enhancer** — generates a presentation script or improves a script written by the user.
3. **Presentation Coach** — analyzes presentation delivery through either a live camera session or an uploaded rehearsal video.

The system is intended to help students identify presentation problems without needing a lecturer, friend, or coach to be available during every rehearsal.

The product provides recommendations and observable measurements. It must not claim that it can determine a user's personality, confidence, competence, anxiety, honesty, or psychological state.

---

## 3. Current Project State

The application itself has not yet been implemented or integrated. Existing work consists of:

- A standalone Slide Analyzer prototype script.
- A standalone Transcript Enhancer prototype script.
- A model benchmarking script.
- Computer-vision logic and research notes.
- UI mockups, architecture diagrams, requirements, user flows, and database designs.

The prototypes are proof-of-concept modules, not production application code. They currently include stale model identifiers and project-specific prompt text that must be removed during integration.

### Existing prototype behavior to preserve where useful

- `python-pptx` extraction of text, tables, layout metadata, and formatting hints.
- LibreOffice conversion from PPTX to PDF.
- PDF-to-image rendering at approximately 200 DPI.
- Optional vision captioning of rendered slide images.
- Strict structured JSON output for Slide Analyzer results.
- AI Generate and Human Enhance transcript modes.
- Selected-slide and selected-paragraph regeneration.
- Tone classification, complex-term detection, phonetic pronunciation text, and vocabulary suggestions.
- Model benchmarking with automated and human evaluation.

### Prototype behavior that must not be copied blindly

- Hardcoded MiniMax model identifiers.
- Hardcoded May 23 exam references.
- Hardcoded claims that the project is still in a design-stage examination.
- Direct provider calls scattered through scripts.
- Local output folders used as permanent persistence.
- LLM responses parsed without a production-grade validation and retry layer.
- Capstone-specific prompts that make the feature unusable for general student presentations.

---

## 4. Team and Primary Ownership

### Min Paing Hein (Issac)

Primary responsibility: backend and infrastructure.

- FastAPI backend structure.
- API contracts and integrations.
- TiDB database schema and migrations.
- Authentication, JWT, and Google OAuth.
- Cloudflare R2 integration.
- PPTX extraction/rendering services.
- LLM integration and prompt engineering.
- Background processing.
- FFmpeg processing.
- Deployment and environment configuration.

### Louise Madison Maganda

Primary responsibility: frontend and UI/UX.

- Next.js and React application.
- Tailwind design system.
- Authentication screens.
- Dashboard and presentation pages.
- Slide Analyzer interfaces.
- Transcript editor and enhancement controls.
- Live Practice interface.
- Uploaded-video workflow and results reports.
- Desktop-browser usability and accessibility.

### Thitapa Ritnamsuk

Primary responsibility: AI/CV and speech processing.

- YOLOv11 pose inference.
- Live face/head analysis logic.
- Uploaded-video body-language analysis.
- Threshold and event algorithms.
- Groq Whisper V3 Turbo integration.
- WPM, filler-word, and sensitive-term processing.
- Azure pronunciation-audio integration for the final release.
- CV evaluation, calibration, and performance testing.

Ownership identifies the primary implementer, not the only person allowed to modify a component.

---

## 5. Target Users and Product Constraints

### Target user

An individual university student preparing an English-language academic, capstone, classroom, or project presentation.

### Supported platform

- Desktop web browsers only.
- Current Chrome, Firefox, Safari, and Edge.
- Responsive behavior should support normal laptop and desktop widths.
- A mobile application and mobile-specific experience are out of scope.

### Supported content

- Presentation format: `.pptx` only.
- Presentation and generated transcript language: English only for the initial product.
- Uploaded rehearsal video: maximum 10 minutes and maximum 1080p.
- Internet connection is required.
- Authentication is required for application features.

### Explicitly out of scope

- PDF, Keynote, Google Slides, or legacy `.ppt` analysis.
- Offline mode.
- Instructor dashboards.
- Institutional analytics.
- Classroom administration.
- Automatic grades.
- Mobile application.
- Long-term progress analytics across many rehearsal sessions.
- Linking a Presentation Coach session to a specific uploaded presentation.
- Live microphone/speech analysis during the alpha release.
- Live full-body posture analysis during the alpha release.

---

## 6. Release Scope

## 6.1 Alpha scope — September 14, 2026

The alpha should provide thin but working vertical slices of the major product areas.

### Alpha P0 capabilities

- Application shell and desktop navigation.
- Email/password registration and login.
- JWT-protected routes.
- TiDB data persistence.
- Cloudflare R2 storage for PPTX files and rendered slide assets.
- PPTX upload, validation, extraction, rendering, and status reporting.
- Slide Analyzer using GPT-5.4 Mini as the primary analysis model.
- Transcript Enhancer with AI Generate and Human Enhance modes.
- Basic Live Practice using backend WebSocket processing and face/head measurements.
- Basic File Upload Practice using YOLOv11 pose and Groq Whisper.
- Privacy notices and guaranteed temporary-video cleanup.
- Deployed alpha environment.
- Error handling for primary user journeys.

### Alpha P1 capabilities

- Google OAuth.
- User-selected transcript tone and target duration.
- Complex-term pronunciation written as phonetic text.
- Detailed live-session summary.
- Cross-browser verification beyond the primary development browser.

### Alpha simplifications

- Detected references are listed but not externally verified.
- Pronunciation is text-only; no Azure-generated audio.
- No agenda-slide generation/export.
- No saved cross-session history page.
- No long-term progress comparison.
- Background jobs may use the simplest reliable abstraction suitable for the alpha environment, provided domain logic is not coupled to that implementation.

## 6.2 Final-release scope — October/November 2026

- Four or five fixed agenda-slide templates.
- User-selectable agenda layout.
- Limited agenda color and font customization.
- Insert generated agenda into a downloadable PPTX.
- Clearly defined and safely worded reference checking.
- Azure pronunciation audio.
- Final decision and implementation for session-history behavior, if retained.
- CV threshold calibration using recorded validation samples.
- OpenVINO/ONNX performance optimization where useful.
- Automated integration and regression coverage.
- Usability testing.
- Performance, privacy, authorization, and security verification.
- Updated report, diagrams, benchmark evidence, and final defense materials.

---

## 7. Core User Journeys

## 7.1 Authentication journey

1. A visitor can view the landing page.
2. The visitor chooses Register or Login.
3. The user registers with name, email, and password or uses Google OAuth.
4. The backend creates or resolves the user.
5. The user receives an authenticated session.
6. Protected pages redirect unauthenticated users to Login.
7. The user can log out and invalidate the active session or refresh token.

## 7.2 Presentation upload journey

1. The user opens the dashboard.
2. The user selects a PPTX file.
3. The frontend performs basic extension and size checks.
4. The backend verifies that the upload is a valid PPTX archive and applies server-side limits.
5. A `PRESENTATION` record and processing job are created.
6. The original PPTX is stored in Cloudflare R2.
7. The extraction service reads text, tables, layout, and formatting hints.
8. LibreOffice converts the presentation to PDF.
9. Each PDF page becomes an ordered PNG slide image.
10. Slide records and rendered assets are persisted.
11. The frontend displays queued, processing, completed, or failed status.
12. When completed, the user can open the presentation workspace.

## 7.3 Slide Analyzer journey

1. The user opens an extracted presentation.
2. The user starts analysis.
3. The system combines structured slide data with rendered visual context.
4. The configured AI pipeline analyzes the full deck.
5. The backend validates the response against the approved schema.
6. Deck-level and per-slide results are stored.
7. The UI shows the overall deck summary and ordered priorities.
8. The user can select individual slides and inspect their feedback.
9. The user can view complex terms and detected references.
10. The user may rerun analysis explicitly; the UI must not accidentally trigger expensive duplicate calls.

## 7.4 Transcript Enhancer — AI Generate journey

1. The user opens the Transcript tab for a processed presentation.
2. The user selects all slides or a slide range.
3. The user optionally selects tone and target duration if those controls are enabled.
4. The backend generates a spoken script for each selected slide.
5. The script is stored by slide in presentation order.
6. The UI displays an editable transcript with slide navigation.
7. Tone, complex terms, pronunciation text, and vocabulary suggestions are shown.
8. The user may regenerate selected slides, selected paragraphs, or the full script.

## 7.5 Transcript Enhancer — Human Enhance journey

1. The user enters or pastes their own script by slide.
2. The user selects one paragraph, multiple paragraphs, selected slides, or the full script.
3. The backend removes fillers, corrects grammar, improves rhythm, and upgrades weak vocabulary while preserving meaning and voice.
4. Only selected content is replaced.
5. Unselected paragraphs remain byte-for-byte or semantically unchanged, depending on storage format.
6. The user reviews and edits the enhanced result.

## 7.6 Live Practice journey

1. The authenticated user opens Live Practice.
2. The interface explains camera use and confirms that live frames are not stored.
3. The browser requests camera permission.
4. The UI helps the user center their face and upper body.
5. The user starts the session.
6. The frontend samples compressed frames and sends them to the backend through an authenticated WebSocket.
7. The backend runs YOLOv11-based pose/head analysis.
8. The backend returns near-real-time feedback events.
9. The UI shows camera-facing ratio, thinking-pause warnings, and head-stability feedback.
10. The user stops or closes the session.
11. All frame data and in-memory frame buffers are discarded.
12. The system may store numerical/text summary results, but never live images or video.

## 7.7 File Upload Practice journey

1. The user opens Upload Practice.
2. The UI explains video limits and deletion behavior.
3. The user uploads a supported rehearsal video.
4. The backend verifies format, codec, duration, and resolution using FFprobe/FFmpeg.
5. The file is stored only in temporary processing storage.
6. FFmpeg extracts frames and audio.
7. YOLOv11 analyzes full-body pose events.
8. Groq Whisper V3 Turbo transcribes speech.
9. The system calculates WPM, filler events, sensitive-term flags, and timestamped posture events.
10. The backend stores only approved result data.
11. Original video, extracted audio, and frames are deleted after the job reaches a terminal state.
12. The UI displays the results report.

---

## 8. Frontend Pages and Routes

Use the existing project UI direction and mockups as visual references. Do not replace them with a generic AI-dashboard aesthetic.

Suggested Next.js routes:

| Route | Purpose | Authentication |
|---|---|---:|
| `/` | Landing page and product explanation | No |
| `/login` | Email/password and Google login | No |
| `/register` | Account registration | No |
| `/dashboard` | User presentations and primary actions | Yes |
| `/presentations/new` | PPTX upload | Yes |
| `/presentations/[presentationId]` | Presentation overview and slide thumbnails | Yes |
| `/presentations/[presentationId]/analysis` | Slide Analyzer results | Yes |
| `/presentations/[presentationId]/transcript` | Transcript generation and editing | Yes |
| `/practice/live` | Live Practice camera session | Yes |
| `/practice/upload` | Rehearsal-video upload | Yes |
| `/practice/sessions/[sessionId]/results` | Uploaded-session or saved-summary report | Yes |
| `/settings` | Account and deletion controls | Yes |

### Shared frontend requirements

- Desktop-first layout.
- Reusable navigation, buttons, forms, cards, dialogs, tabs, badges, and loading states.
- Accessible form labels and keyboard focus.
- Visible processing statuses.
- Clear retry actions for recoverable errors.
- Confirmation before destructive deletion or expensive complete regeneration.
- No silent AI calls on page load.
- Do not display raw provider errors, stack traces, storage keys, or internal IDs to users.
- Use optimistic UI only where rollback behavior is safe.

### Presentation workspace

The presentation workspace should provide stable navigation among:

- Overview.
- Slides.
- Analysis.
- Transcript.

The selected presentation remains in context while switching tabs.

### Slide Analyzer UI

Deck-level area:

- Overall score from 0 to 10.
- Score rationale.
- Exactly three top priorities when provided by the model.
- Examiner/audience red flags.
- Agenda status.
- Cohesion feedback.

Per-slide area:

- Slide image.
- Slide number and extracted title.
- Slide score.
- Overload status and explanation.
- Visual-hierarchy issues.
- Ordered suggestions with priority badges.
- Table suggestions only when present.
- Detected references.

Terms area:

- Term.
- Plain-language definition.
- Do not claim that the term list is exhaustive.

### Transcript UI

- Slide navigation or slide list.
- Editable paragraphs.
- AI Generate and Human Enhance mode switch.
- Slide-range and paragraph selection.
- Tone control when enabled.
- Target-duration control when enabled.
- Regenerate selection action.
- Regenerate full script action with confirmation.
- Tone result with confidence and rationale.
- Complex terms with definition and pronunciation text.
- Vocabulary upgrades showing original phrase, suggestion, and reason.
- Unsaved-change warning.

### Live Practice UI

- Camera permission state.
- Ideal framing guide.
- Start, pause if supported, and stop controls.
- Connection status.
- Camera-facing/gaze-proxy status.
- Thinking-pause timer or warning.
- Head-stability feedback.
- Neutral language such as “Face the camera more consistently” instead of “You appear insecure.”
- Explicit “Live frames are not stored” message.

### Uploaded-video results UI

- Processing summary.
- Speech duration.
- Words per minute and target range.
- Filler count and timestamped occurrences.
- Sensitive-term flags with context.
- Pose-event counts and timestamps.
- Timeline or sortable event list.
- Clear notice that the source video has been deleted.

---

## 9. Detailed Functional Requirements

## 9.1 Authentication and authorization

### Alpha requirements

- Register using display name, email, and password.
- Normalize email before lookup.
- Enforce a documented minimum password policy.
- Hash passwords using a modern password-hashing algorithm such as Argon2id or bcrypt.
- Never store plaintext passwords.
- Login using email and password.
- Issue short-lived access tokens and a safe refresh mechanism.
- Return the current user through `/auth/me`.
- Logout and invalidate the refresh session.
- Protect every user-owned resource by both authentication and ownership checks.

### Google OAuth

- Use OAuth 2.0/OpenID Connect.
- Match an existing account only through verified email rules.
- Store provider identifiers separately from local password credentials.
- Do not require a password for an OAuth-only account.

### Authorization rule

Knowing a presentation, slide, job, or session ID must never allow one user to access another user's data.

## 9.2 Presentation lifecycle

Presentation statuses:

- `uploaded`
- `queued`
- `extracting`
- `ready`
- `analysis_queued`
- `analyzing`
- `completed`
- `failed`
- `deleting`

The exact implementation may separate extraction status and analysis status. Do not force unrelated processes into one ambiguous field if separate fields are clearer.

Users can:

- Upload a presentation.
- List their presentations.
- View one presentation.
- View ordered slides.
- Start/restart analysis.
- Generate or edit a transcript.
- Delete the presentation.

Deleting a presentation must remove:

- Presentation database record.
- Slide records.
- Analysis records.
- Transcript records.
- Original PPTX object.
- Rendered slide images.

Deletion must not remove independent coaching-session records unless the user explicitly deletes those through a separate function.

## 9.3 PPTX extraction and rendering

### Structured extraction

Extract at minimum:

- Slide number.
- Slide layout name where available.
- Title or best title candidate.
- Text runs.
- Font-size hints.
- Bold state.
- Text-color hints when directly available.
- Tables.
- Background-color hint.
- Count or presence of visual/non-text elements.

Do not treat `python-pptx` as a complete visual renderer.

### Rendering

Use the working prototype approach:

1. Save the PPTX to an isolated temporary workspace.
2. Run LibreOffice headlessly to produce a PDF.
3. Verify that a PDF was created.
4. Convert PDF pages to PNG images at approximately 200 DPI.
5. Preserve page/slide order.
6. Upload slide images to R2.
7. Clean local temporary files in a `finally` block.

Rendering must have a timeout and must not allow user-controlled paths to escape the temporary workspace.

## 9.4 Slide Analyzer

### Model behavior

- Primary analysis model: GPT-5.4 Mini.
- Provider/model ID must be configurable.
- Current prototypes call models through OpenRouter; retain a provider abstraction so direct provider APIs can be added later.
- A separate configurable vision model may describe the rendered slide images before main analysis.
- The vision step and main analysis step must be separable and mockable in tests.

### Alpha reference behavior

The alpha only detects references or citations visible in extracted slide content. It does not open URLs, verify credibility, or fact-check claims. The UI must label this as “Detected references,” not “Validated references.”

### Required output schema

```json
{
  "overall_score": 0.0,
  "score_rationale": "string",
  "deck_top_priorities": ["string", "string", "string"],
  "examiner_red_flags": ["string"],
  "agenda_status": "found",
  "cohesion_feedback": "string",
  "per_slide": [
    {
      "num": 1,
      "slide_score": 0.0,
      "overload": false,
      "overload_reason": null,
      "visual_hierarchy_issues": null,
      "improvement_suggestions": [
        {
          "priority": "HIGH",
          "text": "string"
        }
      ],
      "table_tips": ["string"],
      "refs_found": ["string"]
    }
  ],
  "complex_terms": [
    {
      "term": "string",
      "definition": "string"
    }
  ]
}
```

Use a typed/Pydantic equivalent. Scores must be bounded. Slide numbers must exist in the presentation. Invalid model output must not be persisted as a successful result.

### Analysis principles

- Evaluate narrative flow, clarity, readability, visual hierarchy, technical explanation, and audience suitability.
- Do not assume every slide needs more visuals.
- Do not mark structured card grids as overloaded merely because they contain multiple text blocks.
- Do not penalize title/reference slides for having limited content.
- Suggestions must name real content from the slide.
- Do not invent citations or claim external validation.
- A score is coaching guidance, not an academic grade.

## 9.5 Transcript Enhancer

### Mode A: AI Generate

- Generate a spoken script from slide content.
- Generate by selected slide range or full deck.
- Use adjacent slide titles/summaries to produce genuine transitions.
- Do not open every slide with robotic phrases such as “In this slide.”
- Use natural spoken English.
- Do not read bullet points verbatim.
- Respect target duration when enabled.
- Respect tone selection when enabled.

### Mode B: Human Enhance

- Preserve user meaning, structure, and voice.
- Remove fillers and false starts.
- Correct grammar and tense consistency.
- Improve spoken rhythm.
- Replace weak vocabulary only when the replacement remains natural.
- Do not add unsupported technical claims.
- Return the same number of selected paragraphs.
- Never overwrite unselected content.

### Required per-slide result

```json
{
  "slide_num": 1,
  "mode": "ai_generate",
  "script": {
    "original": null,
    "enhanced": ["paragraph one", "paragraph two"],
    "processed_selection": "all"
  },
  "complex_terms": [
    {
      "term": "YOLOv11",
      "definition": "Plain-language definition.",
      "pronunciation": "YOH-loh vee eleven"
    }
  ],
  "tone_check": {
    "classification": "Informative",
    "confidence": 0.91,
    "rationale": "One specific sentence."
  },
  "vocabulary_upgrades": [
    {
      "original": "string",
      "suggested": "string",
      "reason": "string"
    }
  ]
}
```

Allowed tone classifications:

- `Persuasive`
- `Informative`
- `Aggressive`
- `Neutral`
- `Conversational`

Pronunciation is phonetic text during alpha. Azure audio is a final-release enhancement.

## 9.6 Live Practice

### Important interpretation

The live alpha uses YOLOv11 pose/head keypoints. Unless a dedicated face/iris model is later added, “gaze” must be implemented and described as a **camera-facing or head-orientation proxy**, not true iris-level eye tracking.

### Live inputs

- Authenticated WebSocket connection.
- Compressed camera frames.
- Client timestamps and sequence numbers.
- Optional client-reported frame dimensions.

### Starting transport defaults

These are configurable engineering defaults, not permanent product rules:

- Prefer binary JPEG or WebP frame payloads over base64 JSON.
- Resize frames to approximately 640 pixels on the long or relevant dimension.
- Sample around 2–5 frames per second initially.
- Drop stale queued frames instead of allowing latency to grow continuously.
- Return feedback separately as JSON messages.

### Live outputs

- Face/person detected status.
- Camera-facing boolean or confidence.
- Rolling camera-facing percentage.
- Thinking-away duration.
- Head-motion stability status.
- Neutral feedback message.
- Server processing latency where useful for debugging.

### Initial coaching logic

- Rolling camera-facing window: 10 seconds.
- Intended acceptable range: approximately 60–80%.
- Low warning region: below approximately 50%.
- High/staring warning region: above approximately 90%.
- Thinking-away grace period: 2 seconds before warning.
- Head stability: use configurable velocity and yaw/roll thresholds.
- Exact head thresholds remain calibration settings, not unexplained constants inside business logic.

### Live privacy

- Never write frames to R2.
- Never write frames to the database.
- Avoid writing frames to disk.
- Do not include raw images in logs or error monitoring.
- Clear in-memory buffers on disconnect or stop.
- Expire orphaned live sessions.
- The live module has no audio processing in alpha.

## 9.7 File Upload Practice

### Alpha media support

Start with MP4/H.264 where possible to reduce alpha complexity. Additional formats such as WebM or MOV may be enabled only after server-side FFmpeg validation is tested.

### Limits

- Maximum duration: 10 minutes.
- Maximum resolution: 1920×1080.
- Reject unsupported codecs or corrupt files.
- Do not trust client-provided MIME type or metadata.

### Pose events

Initial full-body rules:

1. **Hands clasped low / fig-leaf pose**  
   Both wrists below hip level and close together. Replace real-world “10 cm” with a body-relative normalized-distance threshold before production use.

2. **Arms crossed**  
   Wrist/arm keypoints cross the body toward the opposite shoulder. Use multi-frame confirmation to reduce false positives.

3. **Gesture-box excursion**  
   Hands spend an excessive portion of time outside a box roughly spanning neck to hips and approximately 1.5 shoulder widths. The current 20% value is a configurable heuristic until calibrated.

Events must include:

- Type.
- Start timestamp.
- End timestamp or duration.
- Confidence.
- Human-readable neutral feedback.

Do not display psychological labels such as “insecure,” “defensive,” “aggressive,” or “low competence.” Describe the observable movement and coaching suggestion.

### Speech outputs

- Transcript.
- Speech duration.
- Word count.
- Words per minute.
- Recommended WPM range: approximately 110–160.
- Filler words with timestamps when available.
- Sensitive-term flags with surrounding context.

Sensitive-term detection must be configurable and presented as a caution, not as proof that the speaker intended harm.

### Temporary-media cleanup

Media lifecycle:

1. Accept the upload into an isolated temporary location or temporary R2 prefix.
2. Process it through FFmpeg, YOLOv11, and Whisper.
3. Persist only result data needed for the report.
4. Delete original video, extracted audio, frames, thumbnails not required by the report, and temporary working files.
5. Perform cleanup after success, failure, timeout, cancellation, and worker restart recovery.
6. A cleanup failure must be visible to internal monitoring and retried.

“Delete immediately” means delete immediately after analysis reaches a terminal state and result persistence has succeeded or failed safely.

## 9.8 Agenda Generator — final release

- Generate an agenda from extracted presentation structure.
- Offer four or five fixed slide-layout templates.
- Allow the user to choose a template.
- Allow limited font and color customization.
- Do not provide a free-form slide designer.
- Show a preview.
- Insert the agenda into a copy of the PPTX.
- Allow download of the modified PPTX.
- Never overwrite the user's original stored deck without an explicit versioning decision.

## 9.9 Reference checking — final release

Before implementation, choose and document which of these levels the feature supports:

1. Citation/reference detection.
2. URL reachability.
3. Basic source metadata and domain identification.
4. Credibility heuristics.
5. Claim-level fact checking.

Do not label level 1 or level 2 as full “reference validation.” Communicate uncertainty and external-provider limitations.

---

## 10. System Architecture

## 10.1 Main components

### Frontend

- Next.js.
- React.
- TypeScript.
- Tailwind CSS.
- Browser camera APIs.
- Authenticated HTTP client.
- Authenticated WebSocket client for live practice.

### Backend API

- FastAPI.
- Python.
- Pydantic request/response schemas.
- Authentication and authorization.
- Presentation and session APIs.
- Job creation and status APIs.
- WebSocket endpoint.

### Processing services

- PPTX extraction service.
- LibreOffice rendering service.
- Slide-vision service.
- Slide Analyzer LLM service.
- Transcript LLM service.
- YOLOv11 inference service.
- FFmpeg media service.
- Groq Whisper speech service.
- Azure pronunciation service for the final release.

### Persistence

- TiDB for structured data.
- Cloudflare R2 for original PPTX and rendered slide assets.
- Temporary processing storage for rehearsal videos.

### External AI services

- GPT-5.4 Mini for Slide Analyzer and Transcript Enhancer.
- Configurable vision-caption model where needed.
- Groq Whisper V3 Turbo for uploaded-video speech transcription.
- Azure AI pronunciation audio after alpha.

## 10.2 Architectural boundaries

Use interfaces/adapters instead of importing provider-specific clients throughout domain code.

Recommended boundaries:

- `ObjectStorage`
- `PresentationExtractor`
- `SlideRenderer`
- `VisionCaptioner`
- `SlideAnalysisModel`
- `TranscriptModel`
- `PoseInferenceEngine`
- `SpeechTranscriber`
- `PronunciationProvider`
- `JobRunner`

This allows tests to use fakes and allows provider/model changes without rewriting application logic.

## 10.3 Suggested repository structure

```text
rehearse-ai/
├── frontend/
│   ├── src/app/
│   ├── src/components/
│   ├── src/features/auth/
│   ├── src/features/presentations/
│   ├── src/features/analyzer/
│   ├── src/features/transcript/
│   ├── src/features/live-practice/
│   ├── src/features/upload-practice/
│   ├── src/lib/
│   └── tests/
├── backend/
│   ├── app/main.py
│   ├── app/api/v1/
│   ├── app/core/
│   ├── app/auth/
│   ├── app/models/
│   ├── app/schemas/
│   ├── app/repositories/
│   ├── app/services/presentations/
│   ├── app/services/ai/
│   ├── app/services/cv/
│   ├── app/services/media/
│   ├── app/services/storage/
│   ├── app/jobs/
│   ├── app/websockets/
│   ├── migrations/
│   └── tests/
├── docs/
│   ├── PROJECT_SPEC.md
│   ├── API.md
│   └── DECISIONS.md
├── fixtures/
│   ├── presentations/
│   └── videos/
├── .env.example
├── docker-compose.yml
└── README.md
```

The exact structure may be adjusted to an existing repository. Preserve clear separation between API routes, domain/service logic, provider adapters, repositories, and schemas.

---

## 11. Background Processing

PPTX extraction, rendering, LLM analysis, transcript generation, uploaded-video processing, pose inference, and Whisper transcription can exceed normal HTTP request timeouts.

### Job states

- `queued`
- `running`
- `succeeded`
- `failed`
- `cancelled`
- `cleanup_pending`
- `cleanup_failed`

### Job requirements

- Each job has an owner user ID.
- Each job has a type and target resource ID.
- Job creation is idempotent where possible.
- Workers update progress and timestamps.
- Failures store a safe internal error code and sanitized message.
- Frontend polls or subscribes to status.
- Retrying must not duplicate persisted slides, analysis rows, or session results.
- Temporary-media jobs always execute cleanup.

### Alpha implementation approach

Create a `JobRunner` abstraction. A single-process development/alpha implementation may use FastAPI background execution if deployment guarantees it can complete. Do not place business logic directly inside `BackgroundTasks`. Keep the processing function callable by a later dedicated worker.

If the alpha hosting environment can terminate requests/processes unpredictably, use a separate worker and a jobs table or queue before relying on the feature in demonstrations.

---

## 12. Database Model

Use migrations. Use UUIDs or another non-sequential externally safe identifier strategy. Add created/updated timestamps consistently.

## 12.1 `users`

- `id`
- `email` — unique and normalized
- `display_name`
- `password_hash` — nullable for OAuth-only accounts
- `google_subject` — nullable, unique when present
- `is_active`
- `created_at`
- `updated_at`

## 12.2 `presentations`

- `id`
- `user_id`
- `title`
- `original_filename`
- `r2_pptx_key`
- `status`
- `slide_count`
- `processing_error_code` — nullable
- `created_at`
- `updated_at`

## 12.3 `slides`

- `id`
- `presentation_id`
- `slide_number`
- `title`
- `layout_name`
- `extracted_content_json`
- `r2_image_key`
- `background_color`
- `created_at`

Unique constraint: `(presentation_id, slide_number)`.

## 12.4 `presentation_analyses`

- `id`
- `presentation_id`
- `model_id`
- `prompt_version`
- `overall_score`
- `score_rationale`
- `deck_top_priorities_json`
- `examiner_red_flags_json`
- `agenda_status`
- `cohesion_feedback`
- `status`
- `created_at`

## 12.5 `slide_analyses`

- `id`
- `presentation_analysis_id`
- `slide_id`
- `slide_score`
- `overload`
- `overload_reason`
- `visual_hierarchy_issues`
- `improvement_suggestions_json`
- `table_tips_json`
- `refs_found_json`

## 12.6 `analysis_complex_terms`

- `id`
- `presentation_analysis_id`
- `term`
- `definition`

## 12.7 `presentation_transcripts`

- `id`
- `presentation_id`
- `mode`
- `target_tone` — nullable
- `target_duration_seconds` — nullable
- `model_id`
- `prompt_version`
- `created_at`
- `updated_at`

## 12.8 `slide_transcripts`

- `id`
- `presentation_transcript_id`
- `slide_id`
- `original_paragraphs_json` — nullable
- `enhanced_paragraphs_json`
- `tone_classification`
- `tone_confidence`
- `tone_rationale`
- `updated_at`

## 12.9 `slide_complex_terms`

- `id`
- `slide_transcript_id`
- `term`
- `definition`
- `pronunciation_text`
- `pronunciation_audio_key` — nullable and post-alpha

## 12.10 `slide_vocabulary_upgrades`

- `id`
- `slide_transcript_id`
- `original_phrase`
- `suggested_phrase`
- `reason`

## 12.11 `sessions`

- `id`
- `user_id`
- `session_type` — `live` or `upload`
- `title` — optional user label
- `status`
- `duration_seconds`
- `started_at`
- `completed_at`
- `created_at`

Important: there is no required `presentation_id`. Coaching sessions are independent from uploaded presentations.

## 12.12 `session_results`

- `id`
- `session_id`
- `summary_json`
- `transcript_text` — nullable
- `wpm` — nullable
- `filler_count` — nullable
- `camera_facing_ratio` — nullable
- `created_at`

## 12.13 `session_violations`

- `id`
- `session_id`
- `violation_type`
- `started_at_seconds`
- `ended_at_seconds` — nullable
- `confidence` — nullable
- `details_json`
- `feedback_text`

## 12.14 `jobs`

- `id`
- `user_id`
- `job_type`
- `resource_type`
- `resource_id`
- `status`
- `progress_percent`
- `attempt_count`
- `error_code` — nullable
- `safe_error_message` — nullable
- `started_at` — nullable
- `completed_at` — nullable
- `created_at`
- `updated_at`

## 12.15 Refresh sessions or tokens

If refresh tokens are persisted, store only a hashed/token-safe representation with user, expiry, revocation, and device/session metadata. Do not store reusable raw refresh tokens in logs.

---

## 13. API Design

Use a version prefix such as `/api/v1`.

### Response convention

Successful response:

```json
{
  "data": {},
  "meta": {}
}
```

Error response:

```json
{
  "error": {
    "code": "PRESENTATION_INVALID_FILE",
    "message": "The uploaded file is not a valid PPTX presentation.",
    "details": null
  }
}
```

Do not return stack traces or raw provider responses.

## 13.1 Authentication endpoints

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `GET /api/v1/auth/google/start`
- `GET /api/v1/auth/google/callback`

## 13.2 Presentation endpoints

- `POST /api/v1/presentations` — multipart PPTX upload
- `GET /api/v1/presentations`
- `GET /api/v1/presentations/{presentation_id}`
- `DELETE /api/v1/presentations/{presentation_id}`
- `GET /api/v1/presentations/{presentation_id}/slides`
- `GET /api/v1/presentations/{presentation_id}/jobs`

## 13.3 Slide Analyzer endpoints

- `POST /api/v1/presentations/{presentation_id}/analyses`
- `GET /api/v1/presentations/{presentation_id}/analyses/latest`
- `GET /api/v1/presentations/{presentation_id}/analyses/{analysis_id}`

The create endpoint should return a job or accepted response rather than waiting for complete analysis.

## 13.4 Transcript endpoints

- `POST /api/v1/presentations/{presentation_id}/transcripts/generate`
- `POST /api/v1/presentations/{presentation_id}/transcripts/enhance`
- `GET /api/v1/presentations/{presentation_id}/transcripts/latest`
- `GET /api/v1/presentations/{presentation_id}/transcripts/{transcript_id}`
- `PATCH /api/v1/presentations/{presentation_id}/transcripts/{transcript_id}/slides/{slide_id}`
- `POST /api/v1/presentations/{presentation_id}/transcripts/{transcript_id}/regenerate`

Regeneration request must explicitly identify:

- Full deck, selected slides, or selected paragraphs.
- Mode.
- Tone/duration overrides where enabled.

## 13.5 Live Practice endpoints

- `POST /api/v1/practice/live/sessions`
- `WS /api/v1/practice/live/sessions/{session_id}/stream`
- `POST /api/v1/practice/live/sessions/{session_id}/stop`
- `GET /api/v1/practice/sessions/{session_id}/results`

## 13.6 Upload Practice endpoints

- `POST /api/v1/practice/upload/sessions` — create session/upload video
- `GET /api/v1/practice/upload/sessions/{session_id}` — status
- `GET /api/v1/practice/sessions/{session_id}/results`
- `DELETE /api/v1/practice/sessions/{session_id}` — delete stored result record when supported

## 13.7 Job endpoint

- `GET /api/v1/jobs/{job_id}`
- `POST /api/v1/jobs/{job_id}/retry` — only for approved retryable jobs
- `POST /api/v1/jobs/{job_id}/cancel` — where cancellation is safely supported

---

## 14. WebSocket Protocol

Use an authenticated session and confirm ownership before accepting frames.

### Client control message

```json
{
  "type": "session_start",
  "protocol_version": 1,
  "frame_format": "jpeg",
  "client_width": 640,
  "client_height": 480
}
```

### Frame transport

Prefer binary frame messages. Associate frames with an incrementing sequence number through a small preceding metadata message or a defined binary header.

### Server feedback message

```json
{
  "type": "feedback",
  "sequence": 101,
  "timestamp_ms": 1720000000000,
  "person_detected": true,
  "camera_facing": true,
  "camera_facing_ratio": 0.68,
  "thinking_away_seconds": 0.4,
  "head_stability": "stable",
  "events": [],
  "processing_latency_ms": 84
}
```

### Server warning message

```json
{
  "type": "warning",
  "code": "NO_FACE_DETECTED",
  "message": "Move closer and keep your face within the guide."
}
```

### Connection requirements

- Heartbeat or idle timeout.
- Maximum frame size.
- Backpressure policy.
- Drop stale frames.
- Clean shutdown.
- Sanitized error messages.
- No frame logging.

---

## 15. Storage and Retention

## 15.1 Persistent data

Persist until user deletion or later retention-policy change:

- User account.
- Original PPTX.
- Rendered slide images.
- Extracted slide data.
- Slide Analyzer results.
- Transcript data.
- Approved session result records.

## 15.2 Temporary data

Delete after the processing job reaches a terminal state:

- Uploaded rehearsal video.
- Extracted audio.
- Extracted video frames.
- Temporary converted media.
- Temporary local PPTX/PDF rendering files after the persistent slide assets are safely stored.

## 15.3 Never persist

- Live camera frames.
- Live video recording.
- Raw live-frame buffers after disconnect.
- API keys in database content or logs.
- Passwords.

## 15.4 Suggested R2 keys

```text
users/{user_id}/presentations/{presentation_id}/original.pptx
users/{user_id}/presentations/{presentation_id}/slides/{slide_number}.png
users/{user_id}/presentations/{presentation_id}/exports/{export_id}.pptx
temporary/upload-sessions/{session_id}/source.mp4
```

The `temporary/` prefix must have application cleanup and preferably bucket lifecycle protection. Application deletion remains mandatory; lifecycle expiration is a fallback.

---

## 16. Security and Privacy Requirements

- Validate ownership on every object access.
- Validate PPTX as an archive and defend against zip bombs and path traversal.
- Use upload-size limits.
- Use FFprobe rather than trusting media metadata from the client.
- Sanitize filenames; use generated storage keys.
- Apply timeouts to LibreOffice, FFmpeg, AI, CV, and speech calls.
- Prevent arbitrary command construction; pass subprocess arguments as arrays.
- Limit concurrency for expensive jobs.
- Add rate limits for login, uploads, AI generation, and analysis reruns.
- Do not log presentation content, transcripts, frames, or videos by default.
- Redact tokens and provider credentials from logs.
- Use HTTPS in deployed environments.
- Configure CORS narrowly.
- Use secure cookie settings if refresh/session cookies are used.
- Provide clear consent/notice before camera or video processing.
- Tell users that presentation/script content may be sent to configured external AI providers.
- Tell users accurately what is retained and deleted.

---

## 17. Error Handling

Define stable application error codes. Suggested examples:

- `AUTH_INVALID_CREDENTIALS`
- `AUTH_TOKEN_EXPIRED`
- `RESOURCE_FORBIDDEN`
- `PRESENTATION_INVALID_FILE`
- `PRESENTATION_TOO_LARGE`
- `PRESENTATION_EXTRACTION_FAILED`
- `PRESENTATION_RENDER_FAILED`
- `AI_PROVIDER_UNAVAILABLE`
- `AI_OUTPUT_INVALID`
- `VIDEO_UNSUPPORTED_FORMAT`
- `VIDEO_TOO_LONG`
- `VIDEO_RESOLUTION_TOO_HIGH`
- `VIDEO_PROCESSING_FAILED`
- `SPEECH_TRANSCRIPTION_FAILED`
- `POSE_ANALYSIS_FAILED`
- `LIVE_CONNECTION_FAILED`
- `LIVE_NO_PERSON_DETECTED`
- `TEMPORARY_MEDIA_CLEANUP_FAILED`

Frontend errors should explain what the user can do next. Internal logs may contain correlation IDs and technical detail but must not contain sensitive media.

---

## 18. Configuration

At minimum, provide environment variables or typed configuration for:

```text
APP_ENV
FRONTEND_URL
API_BASE_URL
DATABASE_URL
JWT_SECRET
JWT_ACCESS_TTL_MINUTES
JWT_REFRESH_TTL_DAYS
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
GOOGLE_REDIRECT_URI
R2_ACCOUNT_ID
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_BUCKET_NAME
R2_ENDPOINT
OPENROUTER_API_KEY
SLIDE_ANALYSIS_MODEL=openai/gpt-5.4-mini
TRANSCRIPT_MODEL=openai/gpt-5.4-mini
SLIDE_VISION_MODEL
GROQ_API_KEY
WHISPER_MODEL=whisper-large-v3-turbo
AZURE_SPEECH_KEY
AZURE_SPEECH_REGION
YOLO_MODEL_PATH
LIVE_FRAME_MAX_BYTES
LIVE_TARGET_FPS
LIVE_CAMERA_FACING_LOW
LIVE_CAMERA_FACING_HIGH
LIVE_THINKING_GRACE_SECONDS
LIVE_HEAD_VELOCITY_THRESHOLD
LIVE_YAW_VARIANCE_THRESHOLD
VIDEO_MAX_DURATION_SECONDS=600
VIDEO_MAX_WIDTH=1920
VIDEO_MAX_HEIGHT=1080
```

The application must start with a clear error if mandatory configuration is missing. Optional final-release providers should not prevent alpha modules from starting.

---

## 19. Non-Functional Requirements

### Reliability

- User-facing processing status survives page refresh.
- Failed jobs are distinguishable from still-running jobs.
- Repeated requests do not create uncontrolled duplicates.
- Cleanup runs even after processing failure.

### Performance

- Normal API requests should not wait for LLM or video completion.
- Live processing should prioritize low latency over processing every frame.
- Slide rendering and video processing have bounded concurrency.
- Record real team benchmarks before claiming percentage improvements.

### Maintainability

- Typed frontend models and Pydantic backend schemas.
- Migrations under version control.
- Provider adapters.
- Central configuration.
- Central error codes.
- Prompt versions stored with results.
- No business logic inside UI components or API route handlers.

### Observability

- Structured logs.
- Correlation/request IDs.
- Job IDs.
- Provider latency and failure metrics without content logging.
- Cleanup-failure monitoring.
- Live latency metrics without saving frames.

### Accessibility

- Keyboard-operable forms and dialogs.
- Visible focus states.
- Sufficient contrast.
- Labels for inputs.
- Status messages that are not color-only.
- Clear camera and upload instructions.

---

## 20. Testing Strategy

## 20.1 Backend unit tests

- Authentication and password rules.
- Ownership checks.
- PPTX validation.
- Extraction mapping.
- AI schema validation.
- Partial transcript regeneration merge behavior.
- WPM calculation.
- Filler detection.
- Pose-rule calculations using synthetic keypoints.
- Live rolling-window logic.
- Temporary-media cleanup.

## 20.2 Backend integration tests

- TiDB repository behavior.
- R2 adapter using a test bucket or compatible local fake.
- PPTX to slide records and rendered images.
- Analysis job using mocked AI provider.
- Transcript flows using mocked AI provider.
- Video processing with short fixture videos.
- WebSocket authentication and feedback messages.

## 20.3 Frontend tests

- Authentication forms.
- Protected navigation.
- Upload validation.
- Processing-state rendering.
- Analyzer result rendering.
- Transcript selection and regeneration behavior.
- Camera permission states.
- Upload-practice results.

## 20.4 End-to-end critical flows

1. Register → upload PPTX → wait for extraction → view slides.
2. Login → open presentation → run analysis → view results.
3. Generate transcript → edit → regenerate selected paragraph → reload.
4. Start live session → receive feedback → stop → confirm no frame retention.
5. Upload valid video → process → view results → verify source media deletion.
6. Attempt to access another user's presentation/session → receive forbidden/not-found response.

## 20.5 Required fixtures

- Small text-only PPTX.
- PPTX with images and tables.
- PPTX with charts/diagrams.
- Corrupt or renamed non-PPTX file.
- Short valid MP4 with a visible person and speech.
- MP4 with no visible person.
- Silent MP4.
- Corrupt video.
- Video at duration/resolution boundaries.

---

## 21. Implementation Order

## Phase 0 — Decisions and scaffolding

1. Create repository structure.
2. Add frontend and backend scaffolds.
3. Add environment templates.
4. Add lint/test commands.
5. Add architecture decision log.
6. Define common API/error conventions.

## Phase 1 — Identity and presentation vertical slice

1. Create database migration framework and core entities.
2. Implement user registration/login and protected endpoints.
3. Implement R2 adapter.
4. Implement presentation upload endpoint.
5. Implement dashboard/upload frontend.
6. Implement extraction/rendering service.
7. Persist slides and display thumbnails.
8. Add processing job/status behavior.
9. Add ownership and deletion tests.

## Phase 2 — Slide Analyzer

1. Refactor the prototype into provider-independent services.
2. Configure GPT-5.4 Mini.
3. Remove stale prompt context.
4. Define versioned Pydantic output schema.
5. Implement analysis job.
6. Persist results.
7. Implement deck-level and per-slide frontend.
8. Add failure and invalid-output tests.

## Phase 3 — Transcript Enhancer

1. Refactor the prototype.
2. Implement AI Generate.
3. Implement Human Enhance.
4. Implement slide/paragraph selection.
5. Implement persistence and safe regeneration merging.
6. Add tone/duration controls if alpha capacity allows.
7. Implement transcript editor UI.
8. Test both workflows.

## Parallel CV Phase A — Live technical proof

1. Load YOLOv11 model.
2. Test target-device/server FPS.
3. Decide and document camera-facing proxy.
4. Implement configurable rolling metrics.
5. Define WebSocket protocol.
6. Test with prerecorded/synthetic frame sequences before UI integration.

## Parallel CV Phase B — Uploaded-video technical proof

1. Define supported alpha video format.
2. Implement FFmpeg probing/extraction.
3. Implement pose-event aggregation.
4. Implement Whisper transcription.
5. Calculate WPM/fillers/sensitive terms.
6. Guarantee cleanup.

## Phase 4 — Coach integration

1. Integrate Live Practice frontend and WebSocket backend.
2. Integrate Upload Practice frontend, job pipeline, and report.
3. Add privacy and consent wording.
4. Run latency, limit, and cleanup tests.

## Phase 5 — Alpha stabilization

1. Deploy one alpha environment.
2. Run the full critical-flow checklist.
3. Run browser tests.
4. Triage and fix P0 bugs.
5. Prepare deterministic demo data and fallback assets.
6. Freeze and tag the alpha release.

## Phase 6 — Final enhancements and validation

1. Agenda generator/export.
2. Reference checking.
3. Azure pronunciation audio.
4. CV calibration and neutral wording.
5. OpenVINO/ONNX optimization if measured improvements justify it.
6. Usability test.
7. Security/privacy/performance validation.
8. Final report, deck, deployment, and defense preparation.

---

## 22. Definitions of Done

### A feature is not done merely because its happy-path UI exists.

A feature is complete when:

- Backend and frontend are connected.
- Requests and responses use validated schemas.
- Authentication and ownership are enforced.
- Loading, empty, success, failure, and retry states exist.
- Relevant data persists or is intentionally deleted.
- Privacy behavior matches UI wording.
- Unit/integration tests for critical logic pass.
- Environment configuration is documented.
- No secrets are committed.
- The feature works from a clean setup using the README.

### Alpha release is done when:

- The complete demo can run from a fresh user account.
- A valid PPTX can be uploaded and rendered.
- Slide Analyzer returns and displays real results.
- Transcript Enhancer supports both modes.
- Live Practice returns face/head feedback without retaining frames.
- Uploaded-video practice returns pose and speech results and deletes media.
- No open P0 bugs remain.
- A stable deployed alpha URL exists.
- Fallback demo assets exist for external-provider failure.

---

## 23. Product Language Rules

Use neutral, evidence-based coaching language.

Preferred:

- “Your hands remained clasped below waist level for 18% of the analyzed time.”
- “Try keeping your hands visible around waist-to-chest level.”
- “Your face was directed toward the camera for 48% of the rolling window.”
- “The model could not reliably detect your full body in this segment.”

Avoid:

- “You are insecure.”
- “You appear defensive.”
- “You look aggressive.”
- “This proves low competence.”
- “The system objectively grades your confidence.”

The system detects patterns and produces suggestions; it does not determine mental states.

---

## 24. Known Assumptions and Decisions

These values should be stored in `docs/DECISIONS.md` and changed deliberately:

- Primary Slide Analyzer model: GPT-5.4 Mini.
- Primary Transcript Enhancer model: GPT-5.4 Mini.
- Slide vision model: separately configurable; prototype uses Qwen3-VL.
- Backend: FastAPI.
- Frontend: Next.js/React/Tailwind.
- Database: TiDB.
- Persistent object storage: Cloudflare R2.
- Upload-practice speech model: Groq Whisper V3 Turbo.
- Pose model: YOLOv11.
- Live transport: WebSocket from browser to backend.
- Live input: camera frames only; no audio.
- Live scope: face/head feedback only.
- Uploaded-video scope: full-body posture plus speech.
- PPTX retention: persistent until user deletion.
- Uploaded-video retention: delete after terminal processing state.
- Live-frame retention: none.
- Coach sessions: independent from presentations.
- Research method: 55-response survey; planned interviews were dropped.
- Alpha date: September 14, 2026.
- Final date: November 2026, exact date pending.
- Cross-session progress tracking: out of scope.
- Alpha reference behavior: detection only.
- Alpha pronunciation behavior: phonetic text only.

---

## 25. Questions the Coding Agent May Ask

The coding agent should ask only questions that block implementation. Suitable blocking questions include:

- Which existing repository should be modified?
- Which TiDB connection and migration/ORM choice is already approved?
- Which alpha hosting environments will run the frontend, API, and workers?
- Is the current visual design available as code, Figma, or screenshots?
- What maximum PPTX file size should be enforced?
- Which exact MP4 codecs are accepted for alpha?
- Does the chosen deployment reliably support in-process background jobs?

The agent should not repeatedly ask about decisions already present in this specification.

---

## 26. Starter Prompt to Use with This Specification

After placing this file in the repository as `docs/PROJECT_SPEC.md`, give the coding agent this instruction:

> Read `docs/PROJECT_SPEC.md` completely and inspect the repository. Do not implement the whole application at once. First report what already exists, identify conflicts with the specification, propose the smallest Phase 0 and Phase 1 implementation plan, and then begin with repository scaffolding plus the authentication-to-PPTX-upload vertical slice. Keep provider integrations behind interfaces, use strict schemas, add tests as each backend unit is created, and do not implement post-alpha features unless I explicitly request them.

---

## 27. Final Product Statement

Rehearse AI is an authenticated desktop web application that lets university students upload a PowerPoint presentation, receive structured AI feedback on the deck and individual slides, generate or improve a spoken presentation script, practice delivery through live face/head coaching, and analyze an uploaded rehearsal video for posture and speech patterns. The application uses Next.js on the frontend, FastAPI on the backend, TiDB for structured data, Cloudflare R2 for persistent presentation assets, GPT-5.4 Mini for slide and transcript intelligence, YOLOv11 for pose analysis, Groq Whisper for speech transcription, and WebSockets for near-real-time live feedback. It retains presentation assets until the user deletes them, deletes uploaded rehearsal media after processing, never stores live camera frames, and presents all feedback as neutral coaching guidance rather than grades or psychological judgments.
