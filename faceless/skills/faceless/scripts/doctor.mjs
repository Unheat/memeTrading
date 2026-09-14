#!/usr/bin/env node
import {spawn} from 'node:child_process';
import {dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {findFfmpeg} from './ffmpeg.mjs';
import {loadFishApiKey} from './fish-config.mjs';

function runSilently(executable, argumentsList) {
  return new Promise((resolve) => {
    const child = spawn(executable, argumentsList, {stdio: 'ignore'});
    child.on('error', () => resolve(false));
    child.on('exit', (code) => resolve(code === 0));
  });
}

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const nodeMajorVersion = Number.parseInt(process.versions.node.split('.')[0], 10);
const ffmpegReady = Boolean(await findFfmpeg());
const fishReady = Boolean(await loadFishApiKey());
const templatesReady = await runSilently(process.execPath, [join(scriptDirectory, 'download-templates.mjs'), '--status']);

console.log('Faceless preflight check');
console.log(nodeMajorVersion >= 20
  ? `✓ Node.js ${process.versions.node}`
  : `✗ Node.js 20+ is required (found ${process.versions.node}). Install it from https://nodejs.org/.`);
console.log(ffmpegReady
  ? '✓ FFmpeg is ready for video generation.'
  : '○ FFmpeg is not set up yet. Faceless will set up a local copy before generating audio.');
console.log(fishReady
  ? '✓ Fish Audio is configured locally.'
  : '○ Fish Audio is not configured. Create a key at https://fish.audio/app/api-keys/ when prompted.');
console.log(templatesReady
  ? '✓ Minecraft templates are installed and verified.'
  : '○ Minecraft templates are not installed yet. The video step will ask before downloading them.');

if (nodeMajorVersion < 20) {
  process.exitCode = 1;
}
