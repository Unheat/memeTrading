# Local Fish Audio generation

## Privacy boundary

Fish Audio is called directly from the user's computer. Creatorberry does not receive the Fish API key, source script, dialogue JSON, generated audio, or final video.

The first-run setup helper stores the Fish key only in the user's local Faceless configuration. It never writes the key to the current project, `.env` file, source-control files, skill output, or logs. The user must never paste the key into the agent chat.

## First-time setup

Tell the user to create a key at:

```text
https://fish.audio/app/api-keys/
```

Then run `setup-fish.mjs`. On Windows it opens a visible local input box with a character count; on other systems it uses visible terminal input. The `FISH_API_KEY` environment variable can also be used for an individual run; it takes precedence over saved local configuration.

## Generation flow

1. Faceless makes sure its local FFmpeg dependency is ready before it calls Fish Audio.
2. The local helper reads the complete approved `dialogue.json`.
3. It validates indexes and the four approved voice IDs.
4. It calls Fish Audio directly for each missing dialogue line.
5. It writes each completed line to `audio/<topic-slug>/<zero-padded-index>.mp3`.
6. It combines the individual files locally into `full-dialogue.mp3`.
7. It writes `audio-manifest.json` in the same folder.

No local video generation begins until every line and the combined file are present.

## Local manifest

`audio-manifest.json` records only local render data needed by the future video workflow:

```json
{
  "topic": "claude-video",
  "combinedAudio": "full-dialogue.mp3",
  "lines": [
    {"index": 0, "voiceId": "a84d19016bc34098b3c89d78f9299e33", "file": "000.mp3"}
  ]
}
```

## Failure behavior

- Do not write partial or failed audio as a completed file.
- Preserve successfully downloaded individual lines.
- Retry only missing or invalid lines.
- Do not log the source-script body or generated-audio bytes.
- Do not claim a combined file exists until local combination succeeds.

## Fish request rules

- Use Fish's TTS endpoint directly.
- Send the fixed dialogue `voiceId` as Fish's `reference_id`.
- Use the Fish model configured in `generate-audio.mjs`.
- Never print or serialize the Fish API key.
