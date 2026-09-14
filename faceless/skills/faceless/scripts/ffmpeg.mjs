import {spawn} from 'node:child_process';
import {access, mkdir, writeFile} from 'node:fs/promises';
import {dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const skillDirectory = dirname(scriptDirectory);
const runtimeDirectory = join(skillDirectory, '.runtime');
const localExecutable = join(runtimeDirectory, 'node_modules', 'ffmpeg-static', process.platform === 'win32' ? 'ffmpeg.exe' : 'ffmpeg');

function run(executable, argumentsList, stdio = 'ignore') {
  return new Promise((resolve) => {
    const child = spawn(executable, argumentsList, {stdio});
    child.on('error', () => resolve(false));
    child.on('exit', (code) => resolve(code === 0));
  });
}

async function isReady(executable) {
  if (!executable) return false;
  try {
    await access(executable);
  } catch {
    if (executable !== 'ffmpeg') return false;
  }
  return run(executable, ['-version']);
}

export async function findFfmpeg() {
  for (const executable of [process.env.FFMPEG_PATH, localExecutable, 'ffmpeg']) {
    if (await isReady(executable)) return executable;
  }
  return null;
}

export async function ensureFfmpeg() {
  const existing = await findFfmpeg();
  if (existing) return existing;

  await mkdir(runtimeDirectory, {recursive: true});
  await writeFile(
    join(runtimeDirectory, 'package.json'),
    `${JSON.stringify({private: true}, null, 2)}\n`,
    'utf8',
  );

  const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm';
  console.log('Setting up local FFmpeg for Faceless…');
  const installed = await run(npm, ['install', '--no-save', '--no-package-lock', '--prefix', runtimeDirectory, 'ffmpeg-static@5.3.0'], 'inherit');
  if (!installed || !(await isReady(localExecutable))) {
    throw new Error('Faceless could not set up local FFmpeg. Check your network connection and run the audio step again.');
  }
  return localExecutable;
}
