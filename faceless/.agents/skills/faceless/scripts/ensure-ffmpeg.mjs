#!/usr/bin/env node
import {ensureFfmpeg, findFfmpeg} from './ffmpeg.mjs';

if (process.argv.includes('--status')) {
  const executable = await findFfmpeg();
  console.log(executable ? `FFmpeg is ready: ${executable}` : 'FFmpeg is not set up locally.');
  process.exit(executable ? 0 : 1);
}

const executable = await ensureFfmpeg();
console.log(`FFmpeg is ready: ${executable}`);
