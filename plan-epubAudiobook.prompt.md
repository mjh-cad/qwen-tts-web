Goal: Extend the app to support EPUB input and produce consistent audiobook-style audio for long text.

Current limitations:

- The app only accepts plain text uploads, not EPUB files.
- Long text is split into multiple independent TTS calls, causing voice drift.
- The frontend does not show generation progress or support long audiobook workflows.
- The backend is synchronous, so generation blocks the server and the UI can appear unresponsive.
- The app currently uses a model specified by `QWEN_TTS_MODEL` and should default to `Qwen/Qwen3-TTS-12Hz-1.7B-Base` for audiobook generation.

Key requirements:

- Accept EPUB uploads from the web UI.
- Extract readable text from EPUB chapters reliably.
- Route EPUB uploads and text file uploads through the same chunking and generation pipeline so a small text file can be used for testing.
- Use a single consistent voice prompt across all generated chunks.
- Generate larger chunks where possible (up to the app’s 4000-character chunk limit).
- Combine generated chunk audio into a single audiobook file or clearly grouped output.
- Allow model selection via `QWEN_TTS_MODEL` and document the Base vs VoiceDesign tradeoffs.
- Support GPU-friendly settings for a single 12GB GPU, including `float16` and optional flash attention.

Implementation plan:

1. Add EPUB parsing support.
   - Add a backend utility to load EPUB files and extract chapter text.
   - Use a library like `ebooklib`, or parse EPUB as ZIP and extract HTML with `BeautifulSoup`.
   - Normalize extracted text and remove navigation, metadata, and non-content elements.
   - Preserve chapter order, headings, and simple structure when possible.

2. Add EPUB upload support in the frontend.
   - Update `app/static/app.js` to accept `.epub` files and show upload status.
   - Add a UI state or option for EPUB upload versus plain text input.
   - Send EPUB as `multipart/form-data` to a new API endpoint, such as `/api/generate-epub`.

3. Keep voice consistent across chunks.
   - Use one `voice_description` prompt for the whole EPUB job.
   - Preserve that same prompt for every chunk generation call.
   - Add a default narrator prompt like "A calm, warm audiobook narrator with a clear, steady voice."
   - If the TTS library supports fixed voice IDs, expose that option.

4. Improve chunk generation for long books.
   - Continue using `split_text_into_chunks` with a `max_chars_per_chunk` capped at 4000.
   - Prefer fewer, larger chunks with chapter-aware splitting.
   - Combine chunk WAV files into one audiobook file or organized chapter outputs.

5. Add a dedicated EPUB generation flow.
   - Add a backend route for EPUB uploads, such as `/api/generate-epub`.
   - Ensure EPUB uploads and plain text uploads share the same backend chunking and voice-generation pipeline so small text files can be used as end-to-end tests.
   - Reuse the existing chunk generator and TTS generation pipeline.
   - Return a single combined WAV file URL or a list of chapter audio files.
   - Optionally include EPUB metadata in the filename or response.

6. Add progress visibility and responsiveness.
   - Add a frontend progress indicator for chunk generation.
   - Show status updates such as "Extracting EPUB", "Generating chunk 3 of 8", and "Combining audio files."
   - Consider background task execution or worker-based generation so the UI remains responsive.

7. Modernize the UI and job handling.
   - Treat long audiobook generation as a background job.
   - Persist job state so the user can close the page and return later.
   - Provide a job dashboard with status, progress, estimated time remaining, and final download links.
   - Disable new generation requests while a background job is already running for the same user/session.
   - Keep the UI responsive by moving generation off the main request thread and using polling or websocket updates.
   - Prefer a lightweight local job system for one-user local use rather than full Redis queue infrastructure.
     - Use local persistence (file or SQLite) and a worker thread/process instead of Redis if you only need personal use.

8. Add GPU and model performance guidance.
   - Document recommended environment variables for 12GB GPU usage:
     - `QWEN_TTS_DEVICE=cuda:0`
     - `QWEN_TTS_DTYPE=float16`
     - `QWEN_TTS_FLASH_ATTENTION=true` when flash-attn is installed.
   - Document that `Qwen/Qwen3-TTS-12Hz-1.7B-Base` should be the default for audiobook generation, while `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign` remains available for guided voice styles.
   - Note that `flash-attn` and `sox` are optional performance/utility dependencies.

Next refinement areas:

- Choose the exact EPUB extraction library and install dependencies like `ebooklib` or `beautifulsoup4`.
- Define how the final audiobook file is presented in the UI.
- Decide whether to support full-book generation in one request or chapter-by-chapter batching.
- Decide whether to keep EPUB content as a text preview before generation.
- Consider consistent narrator presets and a fixed speaker option if the TTS library supports it.
