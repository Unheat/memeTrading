# Video generation

## Video templates

Reusable Minecraft templates are stored in the installed Faceless skill's `video-templates/` folder. They are not committed to Git. The `download-templates.mjs` helper downloads and verifies them from the public `video-templates-v1` GitHub Release. The six-template pack is about 2.4 GB. The video script picks one at random for each video.

Per-script audio, working files, and final rendered videos remain in the current run's local `faceless-output/` workspace. Do not mix run-specific output into `video-templates/`.

## Generation rule

Use the combined `audio/<topic-slug>/full-dialogue.mp3`, not the individual speaker clips.

The selected video must loop if needed and stop exactly when the combined audio ends. Keep the original video framing. Do not add effects, cropping, transitions, music, or the template's original audio.

Write the completed file to:

```text
video/<topic-slug>/final-faceless-reel.mp4
```

This requires local FFmpeg. Faceless sets up a local copy automatically if one is not already available. The script also accepts `FFMPEG_PATH` when the user has an existing copy.

Before generating a video, check the local templates:

```text
node <faceless-skill>/scripts/download-templates.mjs --status
```

If they are missing or changed, ask the user before downloading them. After approval, download or repair them with:

```text
node <faceless-skill>/scripts/download-templates.mjs --replace
```

The downloaded files are checked against the sizes and SHA-256 checksums in `video-templates-manifest.json`.

## Character stage

After the Minecraft base video is approved, Faceless can add one visible speaker for each dialogue turn. It reads `audio-manifest.json` and uses its real clip durations to keep character changes matched to the generated audio.

- Stewie and Morty enter quickly from the left and remain on the left.
- Peter and Rick enter quickly from the right and remain on the right.
- Only the active speaker is visible.
- The input is the existing `final-faceless-reel.mp4`. Render to a temporary file, verify it, then replace that same final file. Do not create a second final video for this stage.

Use:

```text
node <faceless-skill>/scripts/add-characters.mjs --video <output-directory>/video/<topic-slug>/final-faceless-reel.mp4 --audio-dir <output-directory>/audio/<topic-slug> --topic <topic-slug> --output <output-directory>
```

## Caption stage

After characters are approved, Faceless can add readable short-form captions to the same final video. Captions are uppercase two- or three-word phrases in the middle of the video: white text with one cyan key word, black outline, and a small pop-in. Timings use the actual generated clip durations and the dialogue text; they are phrase-level rather than word-perfect transcription timings.

Use:

```text
node <faceless-skill>/scripts/add-captions.mjs --video <output-directory>/video/<topic-slug>/final-faceless-reel.mp4 --script <output-directory>/scripts/<topic-slug>/dialogue.json --audio-dir <output-directory>/audio/<topic-slug> --topic <topic-slug> --output <output-directory>
```

The caption stage also renders to a temporary file, verifies it, then safely replaces `final-faceless-reel.mp4`.
