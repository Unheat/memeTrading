# Dialogue JSON schema

Write a raw JSON array. Do not add Markdown fences or explanatory text inside `dialogue.json`.

Each object has exactly these fields:

```json
{
  "text": "(excited) Dialogue line.",
  "index": 0,
  "voiceId": "602d75cd373f4756a880e9e903b14a1d"
}
```

## Current fixed voices

| Character | Voice ID |
|---|---|
| Peter | `e34b4e061b874623a08f41e5c4fecfb9` |
| Stewie | `fdffd3722cd040fcb3f95eec5a7f29f3` |
| Rick | `d2e75a3e3fd6419893057c02a375a113` |
| Morty | `3d445d095ba04681bcba7177faedf55a` |

Select exactly one pair per run:

- Peter & Stewie
- Rick & Morty

## Validation rules

- `index` begins at `0` and increments by one with no gaps.
- `text` includes the emotion tag.
- Use only the two voice IDs belonging to the selected pair.
- The selected pair's voice IDs alternate strictly.
- The final line uses the selected second character's voice ID: Stewie or Morty.
- The JSON contains no Creatorberry promotional line unless the user explicitly made it part of their source script.
