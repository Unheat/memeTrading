# Contributing to Faceless

Thanks for helping improve Faceless, an open-source Creatorberry project.

## Before you open a pull request

1. Make changes only in `skills/faceless/`. This is the canonical skill source.
2. Run `node scripts/sync-agent-skills.mjs` to update the Claude and Codex copies.
3. Run `node --check` on every changed `.mjs` file.
4. Keep the public README accurate and concise.

## Do not commit

- Fish Audio API keys, `.env` files, tokens, or credentials;
- generated `faceless-output/` workspaces;
- downloaded Minecraft templates or other large video files;
- generated audio or final reel videos.

## Workflow boundaries

Faceless begins with a user-provided source script. Keep creator research, hook analysis, thumbnail generation, Telegram, and n8n out of this skill.

The Fish Audio key must remain local. Do not add a server-side key store or send user scripts, audio, or videos to Creatorberry.

## Pull requests

Explain what changed, why it helps creators, and how you tested it. Creatorberry maintains the core workflow and reviews changes that alter the character flow, voice mapping, local privacy model, or output structure.
