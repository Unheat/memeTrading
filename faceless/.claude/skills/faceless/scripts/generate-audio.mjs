#!/usr/bin/env node
import {spawn} from 'node:child_process';
import {access, mkdir, readFile, rename, rm, stat, writeFile} from 'node:fs/promises';
import {join, resolve} from 'node:path';
import {ensureFfmpeg} from './ffmpeg.mjs';
import {loadFishApiKey} from './fish-config.mjs';

const FISH_TTS_URL = 'https://api.fish.audio/v1/tts';
const FISH_MODEL = process.env.FISH_MODEL?.trim() || 's2';
const PETER_VOICE_ID = 'a84d19016bc34098b3c89d78f9299e33';
const STEWIE_VOICE_ID = 'e91c4f5974f149478a35affe820d02ac';
const RICK_VOICE_ID = 'd2e75a3e3fd6419893057c02a375a113';
const MORTY_VOICE_ID = '3d445d095ba04681bcba7177faedf55a';
const ALLOWED_VOICE_IDS = new Set([PETER_VOICE_ID, STEWIE_VOICE_ID, RICK_VOICE_ID, MORTY_VOICE_ID]);
const CASTS = [
  {name: 'Peter & Stewie', first: PETER_VOICE_ID, second: STEWIE_VOICE_ID},
  {name: 'Rick & Morty', first: RICK_VOICE_ID, second: MORTY_VOICE_ID},
];

function parseArguments(argumentsList) {
  const options = {};
  for (let index = 0; index < argumentsList.length; index += 2) {
    const key = argumentsList[index];
    const value = argumentsList[index + 1];
    if (!key?.startsWith('--') || !value || value.startsWith('--')) {
      throw new Error('Usage: generate-audio.mjs --script <dialogue.json> --topic <topic-slug> --output <faceless-output-directory>');
    }
    options[key.slice(2)] = value;
  }
  return options;
}

function validateLines(value) {
  if (!Array.isArray(value) || value.length === 0) {
    throw new Error('Dialogue JSON must be a non-empty array.');
  }

  const lines = [...value].sort((a, b) => a.index - b.index);
  for (let expectedIndex = 0; expectedIndex < lines.length; expectedIndex += 1) {
    const line = lines[expectedIndex];
    if (!line || line.index !== expectedIndex || typeof line.text !== 'string' || !line.text.trim()) {
      throw new Error(`Dialogue line ${expectedIndex} is invalid.`);
    }
    if (!ALLOWED_VOICE_IDS.has(line.voiceId)) {
      throw new Error(`Dialogue line ${expectedIndex} has an unsupported voice ID.`);
    }
    if (expectedIndex > 0 && line.voiceId === lines[expectedIndex - 1].voiceId) {
      throw new Error(`Dialogue line ${expectedIndex} does not alternate speakers.`);
    }
  }

  const cast = CASTS.find(({first, second}) => lines.every((line) => line.voiceId === first || line.voiceId === second));
  if (!cast) {
    throw new Error('Dialogue JSON must use exactly one approved character pair.');
  }
  if (!lines.some((line) => line.voiceId === cast.first) || !lines.some((line) => line.voiceId === cast.second)) {
    throw new Error(`Dialogue JSON must include both ${cast.name} voices.`);
  }
  if (lines.at(-1).voiceId !== cast.second) {
    throw new Error(`The final dialogue line must use the second ${cast.name} voice.`);
  }
  return lines;
}

async function isCompletedAudioFile(filePath) {
  try {
    return (await stat(filePath)).size > 0;
  } catch {
    return false;
  }
}

async function generateLine({fishApiKey, line, filePath}) {
  const response = await fetch(FISH_TTS_URL, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${fishApiKey}`,
      'Content-Type': 'application/json',
      model: FISH_MODEL,
    },
    body: JSON.stringify({
      text: line.text,
      reference_id: line.voiceId,
      format: 'mp3',
    }),
  });

  if (!response.ok) {
    throw new Error(`Fish Audio could not generate line ${line.index} (HTTP ${response.status}).`);
  }

  const bytes = Buffer.from(await response.arrayBuffer());
  if (bytes.length === 0) {
    throw new Error(`Fish Audio returned empty audio for line ${line.index}.`);
  }

  const temporaryPath = `${filePath}.part`;
  await writeFile(temporaryPath, bytes);
  await rename(temporaryPath, filePath);
}

async function runFfmpeg(argumentsList) {
  const executable = await ensureFfmpeg();
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(executable, argumentsList, {stdio: 'inherit'});
    child.on('error', () => rejectPromise(new Error('FFmpeg is required to create full-dialogue.mp3.')));
    child.on('exit', (code) => {
      if (code === 0) resolvePromise();
      else rejectPromise(new Error(`FFmpeg failed while creating full-dialogue.mp3 (exit ${code}).`));
    });
  });
}

function toConcatEntry(filePath) {
  return `file '${filePath.replace(/\\/g, '/').replace(/'/g, "'\\\\''")}'`;
}

const options = parseArguments(process.argv.slice(2));
if (!options.script || !options.topic || !options.output) {
  throw new Error('Usage: generate-audio.mjs --script <dialogue.json> --topic <topic-slug> --output <faceless-output-directory>');
}
if (!/^[a-z0-9]+(?:-[a-z0-9]+){0,2}$/.test(options.topic)) {
  throw new Error('Topic must be a lowercase two- or three-word slug, for example claude-video.');
}

const fishApiKey = await loadFishApiKey();
if (!fishApiKey) {
  throw new Error('Fish Audio is not configured. Create a key at https://fish.audio/app/api-keys/ and run setup-fish.mjs first.');
}

const scriptPath = resolve(options.script);
const outputDirectory = resolve(options.output);
const audioDirectory = join(outputDirectory, 'audio', options.topic);
const lines = validateLines(JSON.parse(await readFile(scriptPath, 'utf8')));
await ensureFfmpeg();
await mkdir(audioDirectory, {recursive: true});

for (const line of lines) {
  const file = `${String(line.index).padStart(3, '0')}.mp3`;
  const filePath = join(audioDirectory, file);
  if (await isCompletedAudioFile(filePath)) {
    console.log(`Keeping existing ${file}.`);
    continue;
  }
  console.log(`Generating line ${line.index + 1} of ${lines.length}.`);
  await generateLine({fishApiKey, line, filePath});
  console.log(`Saved ${file}.`);
}

const audioFiles = lines.map((line) => `${String(line.index).padStart(3, '0')}.mp3`);
for (const file of audioFiles) {
  await access(join(audioDirectory, file));
}

const concatFile = join(audioDirectory, 'ffmpeg-concat.txt');
const combinedAudio = join(audioDirectory, 'full-dialogue.mp3');
await writeFile(concatFile, `${audioFiles.map((file) => toConcatEntry(join(audioDirectory, file))).join('\n')}\n`);
try {
  await runFfmpeg(['-y', '-f', 'concat', '-safe', '0', '-i', concatFile, '-c', 'copy', combinedAudio]);
} finally {
  await rm(concatFile, {force: true});
}

await writeFile(
  join(audioDirectory, 'audio-manifest.json'),
  `${JSON.stringify({
    topic: options.topic,
    combinedAudio: 'full-dialogue.mp3',
    lines: lines.map((line) => ({
      index: line.index,
      voiceId: line.voiceId,
      file: `${String(line.index).padStart(3, '0')}.mp3`,
    })),
  }, null, 2)}\n`,
);

console.log(`Audio complete: ${audioDirectory}`);
