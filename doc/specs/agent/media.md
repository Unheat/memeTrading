# Module Spec — `app/agent/media.py` and `app/media/faceless_bridge.py`

## Responsibility

Generate the dual-layer content package:
1. Public-facing forensic research article with numbered primary citations (`article.md`).
2. Two-person dialogue reel script (`dialogue.json`, `reel_script.txt`, `caption.txt`) formatted strictly for `faceless/` (Fish Audio + local FFmpeg character/caption rendering).
3. Subprocess bridge executing `faceless/` scripts without porting or rewriting Node.js code.

## Public Contracts

### `app/agent/media.py`

#### `MediaPackage`
```python
@dataclass(frozen=True)
class MediaPackage:
    ticker: str
    article_markdown: str
    dialogue_json: list[dict[str, Any]]
    reel_script_text: str
    caption_text: str
```

#### Voice Constants (Faceless Schema):
- Peter: `e34b4e061b874623a08f41e5c4fecfb9`
- Stewie: `fdffd3722cd040fcb3f95eec5a7f29f3`
- Rick: `d2e75a3e3fd6419893057c02a375a113`
- Morty: `3d445d095ba04681bcba7177faedf55a`

#### `generate_media_package(state: InvestigationState, model: Any, character_pair: str = "peter_stewie") -> MediaPackage`
- Takes `InvestigationState` with facts, consensus, adversarial kill triggers, and IC verdict.
- Prompts model with `MEDIA_ARTICLE_PROMPT` to write `article.md` with numbered `[1]`, `[2]` citations.
- Prompts model with `MEDIA_REEL_PROMPT` to write a 5-beat dialogue script.
- Validates `dialogue.json`:
  - Exactly alternates speakers.
  - Sequential `index` starting at 0.
  - Spoken text includes emotion tag `(shocked)`, `(smirking)`, etc.
  - Final line uses the second character (Stewie or Morty) and points to the article below.

### `app/media/faceless_bridge.py`

#### `FacelessBridge`
```python
class FacelessBridge:
    def __init__(self, faceless_root: Path | None = None) -> None:
        self.faceless_root = faceless_root or Path("faceless")

    def is_available(self) -> bool:
        """Check if Node.js and faceless scripts exist."""

    def check_doctor(self) -> dict[str, Any]:
        """Run doctor.mjs to verify node, ffmpeg, fish audio, and templates."""

    def generate_audio(self, dialogue_path: Path, topic_slug: str, output_dir: Path) -> Path | None:
        """Invoke generate-audio.mjs."""

    def generate_video(self, audio_path: Path, topic_slug: str, output_dir: Path) -> Path | None:
        """Invoke generate-video.mjs."""
```

## Donor Code Provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
|---|---|---|---|
| `app.agent.media.VOICE_IDS` | adapted | `faceless/skills/faceless/scripts/generate-audio.mjs:10-18` | Standard voice IDs for Peter, Stewie, Rick, Morty. |
| `app.agent.media.validate_dialogue_json` | adapted | `faceless/skills/faceless/scripts/generate-audio.mjs:33-55` | Strict schema validation: non-empty array, zero-based index, alternating speakers, valid voice IDs. |
| `app.media.faceless_bridge.FacelessBridge` | black-box execution | `faceless/skills/faceless/scripts/{doctor,generate-audio,generate-video}.mjs` | Subprocess wrapper calling existing scripts without modifying their source code. |

## Acceptance Criteria
1. `dialogue.json` passes all Faceless validation rules (alternating voice IDs, emotion tags, sequential indices).
2. `article.md` includes numbered SEC citations `[1]`, `[2]` with exact accession numbers and URLs.
3. `FacelessBridge` handles missing Node or missing Fish API key gracefully without raising unhandled exceptions.
