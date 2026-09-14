#!/usr/bin/env node
import {spawn} from 'node:child_process';
import {access, mkdir, readdir, rename, rm, stat} from 'node:fs/promises';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {ensureFfmpeg} from './ffmpeg.mjs';

function parseArguments(argumentsList) {
  const options = {};
  for (let index = 0; index < argumentsList.length; index += 2) {
    const key = argumentsList[index];
    const value = argumentsList[index + 1];
    if (!key?.startsWith('--') || !value || value.startsWith('--')) {
      throw new Error('Usage: generate-video.mjs --audio <full-dialogue.mp3> --topic <topic-slug> --output <faceless-output-directory> [--templates <video-templates-directory>]');
    }
    options[key.slice(2)] = value;
  }
  return options;
}

async function runFfmpeg(argumentsList) {
  const executable = await ensureFfmpeg();
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(executable, argumentsList, {stdio: 'inherit'});
    child.on('error', () => rejectPromise(new Error('FFmpeg is required to generate the video.')));
    child.on('exit', (code) => {
      if (code === 0) resolvePromise();
      else rejectPromise(new Error(`FFmpeg failed while generating the video (exit ${code}).`));
    });
  });
}

async function isCompletedFile(filePath) {
  try {
    return (await stat(filePath)).size > 0;
  } catch {
    return false;
  }
}

const options = parseArguments(process.argv.slice(2));
if (!options.audio || !options.topic || !options.output) {
  throw new Error('Usage: generate-video.mjs --audio <full-dialogue.mp3> --topic <topic-slug> --output <faceless-output-directory> [--templates <video-templates-directory>]');
}
if (!/^[a-z0-9]+(?:-[a-z0-9]+){0,2}$/.test(options.topic)) {
  throw new Error('Topic must be a lowercase two- or three-word slug, for example claude-video.');
}

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const skillDirectory = dirname(scriptDirectory);
const audioPath = resolve(options.audio);
const outputDirectory = resolve(options.output);
const templateDirectory = resolve(options.templates || join(skillDirectory, 'video-templates'));
const videoDirectory = join(outputDirectory, 'video', options.topic);
const finalVideo = join(videoDirectory, 'final-faceless-reel.mp4');
const temporaryVideo = `${finalVideo}.part.mp4`;

await access(audioPath);
const templates = (await readdir(templateDirectory, {withFileTypes: true}))
  .filter((entry) => entry.isFile() && /\.(mp4|mov|mkv|webm)$/i.test(entry.name))
  .map((entry) => join(templateDirectory, entry.name));
if (templates.length === 0) {
  throw new Error(`No video templates found in ${templateDirectory}.`);
}

const template = templates[Math.floor(Math.random() * templates.length)];
await mkdir(videoDirectory, {recursive: true});
await rm(temporaryVideo, {force: true});
console.log(`Using template: ${template}`);

try {
  await runFfmpeg([
    '-y',
    '-stream_loop', '-1',
    '-i', template,
    '-i', audioPath,
    '-map', '0:v:0',
    '-map', '1:a:0',
    '-c:v', 'libx264',
    '-crf', '18',
    '-preset', 'medium',
    '-c:a', 'aac',
    '-b:a', '192k',
    '-shortest',
    '-movflags', '+faststart',
    temporaryVideo,
  ]);
  if (!(await isCompletedFile(temporaryVideo))) {
    throw new Error('FFmpeg did not produce a video file.');
  }
  await rename(temporaryVideo, finalVideo);
} finally {
  await rm(temporaryVideo, {force: true});
}

console.log(`Video complete: ${finalVideo}`);
