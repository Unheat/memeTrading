# Execution Plan 14 — Media Package & Faceless Bridge (Article & Reel Generation)

## Purpose

Implement the dual-layer content generation stage:
1. **Cited Forensic Article (`article.md`)**: In-depth, publication-ready research article with numbered primary SEC citations `[1]`, `[2]`, official EDGAR accession numbers, gross margin % tables, and expectation-gap analysis.
2. **Viral Two-Person Dialogue Reel (`dialogue.json` + `reel_script.txt` + `caption.txt`)**: 60–75 second punchy, witty dialogue between a skeptical questioner (The President / Everyday Retail) and a forensic economist (Peter/Stewie style) breaking down the trade mechanics without dry jargon.
3. **Faceless Bridge (`app/media/faceless_bridge.py`)**: Subprocess bridge that invokes `faceless/skills/faceless/scripts/` directly as an external app (audio generation, video generation, character overlay, caption rendering) without rewriting or porting its Node.js codebase.

## Donor Code Provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
|---|---|---|---|
| `app.agent.media.generate_dialogue_json` | adapted | `faceless/skills/faceless/references/dialogue-json-schema.md:1-37` | Adheres strictly to the Faceless JSON schema: alternating voice IDs (`e34b4e06...` Peter, `fdffd372...` Stewie), sequential indices starting at 0, emotion tags `(shocked)`, `(smirking)`, final line spoken by character 2. |
| `app.media.faceless_bridge.FacelessBridge` | black-box execution | `faceless/skills/faceless/scripts/{generate-audio,generate-video,add-characters,add-captions}.mjs` | Subprocess wrapper invoking local Node.js scripts in `faceless/` with absolute path resolution and graceful degradation if Node/FFmpeg/Fish key is absent. |

## Required Behavior

1. **`app/agent/media.py`**:
   - `MediaPackage`: Frozen dataclass with `article_markdown: str`, `dialogue_json: list[dict]`, `reel_script_text: str`, `caption_text: str`.
   - `generate_media_package(state: InvestigationState, model: Any, character_pair: str = "peter_stewie") -> MediaPackage`
   - Formats `dialogue.json` strictly conforming to Faceless schema:
     - Alternates speakers with Peter & Stewie (or Rick & Morty) voice IDs.
     - Prepends valid emotion tags: `(shocked)`, `(smirking)`, `(excited)`, `(deadpan)`, `(laughing)`.
     - Final line ends with Stewie or Morty directing viewers to the cited article below.
   - Formats `article.md` with:
     - Headline & Bottom Line
     - Scuttlebutt Ground Signal
     - SEC Execution Audit with numbered `[1]`, `[2]` citations
     - Wall Street Consensus Expectation Gap Table
     - Adversarial Red Team 2 Numeric Kill Triggers
   - Formats `caption.txt` with hook, short summary, and hashtags.

2. **`app/media/faceless_bridge.py`**:
   - `FacelessBridge(faceless_root: Path | None = None)`
   - Methods:
     - `check_doctor() -> dict[str, bool]` (runs `doctor.mjs`)
     - `run_audio(dialogue_path: Path, topic_slug: str, output_dir: Path) -> Path | None`
     - `run_video(audio_path: Path, topic_slug: str, output_dir: Path) -> Path | None`
     - `build_reel(dialogue_path: Path, topic_slug: str, output_dir: Path) -> Path | None`
   - Graceful fallback: If Node or Fish key or FFmpeg is unconfigured, logs a clear setup message and returns None without raising an unhandled exception.

3. **`app/agent/runner.py`**:
   - In `run_investigation()`, when `generate_media=True` (default True), calls `generate_media_package()` and writes:
     - `cases/<case_id>/article.md`
     - `cases/<case_id>/faceless/dialogue.json`
     - `cases/<case_id>/faceless/source-script.txt`
     - `cases/<case_id>/faceless/caption.txt`

## Execution Steps

1. Create `doc/specs/agent/media.md`.
2. Write unit tests in `tests/agent/test_media.py` and `tests/media/test_faceless_bridge.py`.
3. Implement `app/agent/media.py`.
4. Implement `app/media/faceless_bridge.py`.
5. Update `app/agent/runner.py`.
6. Verify all tests pass (175+ tests).
7. Commit cleanly to Git.
