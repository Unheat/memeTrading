#!/usr/bin/env node
import {spawn} from 'node:child_process';
import {access, mkdir, readFile, rename, rm, stat, writeFile} from 'node:fs/promises';
import {join, resolve} from 'node:path';
import {ensureFfmpeg} from './ffmpeg.mjs';

const VOICE_IDS = new Set([
  'e34b4e061b874623a08f41e5c4fecfb9',
  'fdffd3722cd040fcb3f95eec5a7f29f3',
  'd2e75a3e3fd6419893057c02a375a113',
  '3d445d095ba04681bcba7177faedf55a',
]);
const STOP_WORDS = new Set(['a', 'an', 'and', 'are', 'as', 'at', 'be', 'but', 'by', 'for', 'from', 'he', 'her', 'his', 'i', 'if', 'in', 'is', 'it', 'its', 'of', 'on', 'or', 'our', 'so', 'that', 'the', 'their', 'then', 'there', 'they', 'this', 'to', 'was', 'we', 'what', 'when', 'with', 'you', 'your']);
const usage = 'Usage: add-captions.mjs --video <character-video.mp4> --script <dialogue.json> --audio-dir <audio-topic-directory> --topic <topic-slug> --output <faceless-output-directory>';

function parseArguments(argumentList) {
  const options = {};
  for (let index = 0; index < argumentList.length; index += 2) {
    const key = argumentList[index];
    const value = argumentList[index + 1];
    if (!key?.startsWith('--') || !value || value.startsWith('--')) throw new Error(usage);
    options[key.slice(2)] = value;
  }
  return options;
}

function run(executable, argumentList, {captureStderr = false} = {}) {
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(executable, argumentList, {stdio: captureStderr ? ['ignore', 'ignore', 'pipe'] : 'inherit'});
    let stderr = '';
    if (captureStderr) child.stderr.on('data', (chunk) => { stderr += chunk; });
    child.on('error', () => rejectPromise(new Error('FFmpeg is required to create the caption preview.')));
    child.on('exit', (code) => resolvePromise({code, stderr}));
  });
}

async function getDuration(executable, filePath) {
  const {stderr} = await run(executable, ['-hide_banner', '-i', filePath], {captureStderr: true});
  const match = stderr.match(/Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)/);
  if (!match) throw new Error(`Could not read the duration of ${filePath}.`);
  return Number(match[1]) * 3600 + Number(match[2]) * 60 + Number(match[3]);
}

async function completed(filePath) {
  try {
    return (await stat(filePath)).size > 0;
  } catch {
    return false;
  }
}

function toTimestamp(seconds) {
  const centiseconds = Math.max(0, Math.round(seconds * 100));
  const hours = Math.floor(centiseconds / 360000);
  const minutes = Math.floor((centiseconds % 360000) / 6000);
  const remainder = centiseconds % 6000;
  return `${hours}:${String(minutes).padStart(2, '0')}:${String(Math.floor(remainder / 100)).padStart(2, '0')}.${String(remainder % 100).padStart(2, '0')}`;
}

function normaliseText(text) {
  return text.replace(/^\s*\([^)]*\)\s*/, '').trim();
}

function wordsFrom(text) {
  return normaliseText(text).match(/[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*/g) || [];
}

function groupWords(words) {
  const groups = [];
  for (let index = 0; index < words.length;) {
    const remaining = words.length - index;
    const size = remaining === 4 ? 2 : Math.min(3, remaining);
    groups.push(words.slice(index, index + size));
    index += size;
  }
  return groups;
}

function stressWord(group) {
  const candidates = group.filter((word) => !STOP_WORDS.has(word.toLowerCase()));
  return (candidates.length ? candidates : group).reduce((longest, word) => word.length > longest.length ? word : longest);
}

function escapeAss(value) {
  return value.replace(/\\/g, '\\\\').replace(/{/g, '\\{').replace(/}/g, '\\}');
}

function captionText(group) {
  const stress = stressWord(group);
  return group.map((word) => {
    const escaped = escapeAss(word.toUpperCase());
    return word === stress ? `{\\c&H00FFD700&}${escaped}{\\c&HFFFFFF&}` : escaped;
  }).join(' ');
}

function assPath(filePath) {
  return filePath.replace(/\\/g, '/').replace(':', '\\:').replace(/'/g, "\\'");
}

const options = parseArguments(process.argv.slice(2));
if (!options.video || !options.script || !options['audio-dir'] || !options.topic || !options.output) throw new Error(usage);
if (!/^[a-z0-9]+(?:-[a-z0-9]+){0,2}$/.test(options.topic)) {
  throw new Error('Topic must be a lowercase two- or three-word slug, for example claude-video.');
}

const sourceVideo = resolve(options.video);
const scriptPath = resolve(options.script);
const audioDirectory = resolve(options['audio-dir']);
const outputDirectory = resolve(options.output);
const videoDirectory = join(outputDirectory, 'video', options.topic);
const assFile = join(videoDirectory, 'caption-timing.ass');
const chunkFile = join(videoDirectory, 'caption-chunks.json');
const finalVideo = join(videoDirectory, 'final-faceless-reel.mp4');
const temporaryVideo = `${finalVideo}.part.mp4`;

await access(sourceVideo);
const script = JSON.parse(await readFile(scriptPath, 'utf8'));
const manifest = JSON.parse(await readFile(join(audioDirectory, 'audio-manifest.json'), 'utf8'));
if (!Array.isArray(script) || !Array.isArray(manifest.lines) || script.length !== manifest.lines.length) {
  throw new Error('The dialogue JSON and audio manifest must contain the same number of lines.');
}

const executable = await ensureFfmpeg();
let currentTime = 0;
const chunks = [];
for (const [position, line] of [...script].sort((first, second) => first.index - second.index).entries()) {
  if (!VOICE_IDS.has(line.voiceId) || line.voiceId !== manifest.lines[position].voiceId) {
    throw new Error(`Dialogue line ${line.index} does not match the generated audio manifest.`);
  }
  const audioFile = join(audioDirectory, manifest.lines[position].file);
  await access(audioFile);
  const duration = await getDuration(executable, audioFile);
  const groups = groupWords(wordsFrom(line.text));
  const totalWeight = groups.reduce((total, group) => total + group.join('').length, 0);
  let groupStart = currentTime;
  for (const group of groups) {
    const weight = group.join('').length / totalWeight;
    const groupEnd = groupStart + duration * weight;
    chunks.push({
      lineIndex: line.index,
      start: Number(groupStart.toFixed(3)),
      end: Number(groupEnd.toFixed(3)),
      words: group.map((word) => word.toUpperCase()),
      stress: stressWord(group).toUpperCase(),
    });
    groupStart = groupEnd;
  }
  currentTime += duration;
}

await mkdir(videoDirectory, {recursive: true});
const assLines = [
  '[Script Info]',
  'ScriptType: v4.00+',
  'PlayResX: 1080',
  'PlayResY: 1920',
  'ScaledBorderAndShadow: yes',
  '',
  '[V4+ Styles]',
  'Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding',
  'Style: Caption,Poppins,82,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,10,4,5,80,80,0,1',
  '',
  '[Events]',
  'Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text',
  ...chunks.map((chunk) => `Dialogue: 0,${toTimestamp(chunk.start)},${toTimestamp(chunk.end)},Caption,,0,0,0,,{\\an5\\pos(540,960)\\fad(70,80)\\fscx88\\fscy88\\t(0,110,\\fscx100\\fscy100)}${captionText(chunk.words)}`),
];
await writeFile(assFile, `${assLines.join('\n')}\n`, 'utf8');
await writeFile(chunkFile, `${JSON.stringify(chunks, null, 2)}\n`, 'utf8');
await rm(temporaryVideo, {force: true});

console.log(`Adding ${chunks.length} caption chunks to ${finalVideo}`);
try {
  const {code} = await run(executable, [
    '-y',
    '-i', sourceVideo,
    '-vf', `ass=filename='${assPath(assFile)}'`,
    '-map', '0:v:0',
    '-map', '0:a:0',
    '-c:v', 'libx264',
    '-crf', '18',
    '-preset', 'medium',
    '-c:a', 'copy',
    '-movflags', '+faststart',
    temporaryVideo,
  ]);
  if (code !== 0 || !(await completed(temporaryVideo))) throw new Error('FFmpeg did not produce the caption video.');
  await rename(temporaryVideo, finalVideo);
} finally {
  await rm(temporaryVideo, {force: true});
}

console.log(`Captions added: ${finalVideo}`);
