# D-Day guest access

The landing page offers **Try without signing in** alongside Google sign-in.
Each guest entry creates an isolated workspace with an opaque bearer credential.
Only its SHA-256 hash is saved in the database. The browser retains the credential
across refreshes; **Leave guest workspace** clears it and revokes access.
Guest uploads remain stored until explicitly cleaned up; leaving does not delete files.
There are no guest-specific usage quotas. Existing file validation still applies.

Guests can use Live Practice, upload PPTX files for Slide Analyzer and Transcript
Enhancer, and use the normal script generation, editing and review workflows.
The existing resource ownership checks also apply to guests.

Guest Upload Practice shows only a selected completed sample report and its
captured media. Guests cannot upload recordings, delete reports or request
reprocessing. Until a sample is selected, it shows a preparation message.

## Configuration

Apply the migration before starting the backend:

```sh
cd backend
.venv/bin/alembic upgrade head
```

Backend environment variables:

```dotenv
GUEST_ACCESS_ENABLED=true
GUEST_PRACTICE_SAMPLE_ID=
```

After analyzing the custom recording with a signed-in account, set
`GUEST_PRACTICE_SAMPLE_ID` to that completed report's UUID and restart the backend.
Only that report becomes readable to guests; other users' reports stay private.
Do not delete the selected report while it is being used as the sample.

After D-Day, set `GUEST_ACCESS_ENABLED=false` and restart the backend. This blocks
new guest entries and existing guest API credentials; Google sign-in stays enabled.
An already-open live connection ends when the backend restarts.

Guest mode does not transfer guest files into a Google account on sign-in.
