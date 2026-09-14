#!/usr/bin/env node
import {createHash} from 'node:crypto';
import {createReadStream, createWriteStream} from 'node:fs';
import {access, mkdir, readFile, rename, rm, stat} from 'node:fs/promises';
import {pipeline} from 'node:stream/promises';
import {Readable, Transform} from 'node:stream';
import {basename, dirname, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const usage = 'Usage: download-templates.mjs [--status] [--replace] [--templates <video-templates-directory>]';

function parseArguments(argumentsList) {
  const options = {status: false, replace: false};
  for (let index = 0; index < argumentsList.length; index += 1) {
    const argument = argumentsList[index];
    if (argument === '--status') options.status = true;
    else if (argument === '--replace') options.replace = true;
    else if (argument === '--templates') {
      const value = argumentsList[index + 1];
      if (!value || value.startsWith('--')) throw new Error(usage);
      options.templates = value;
      index += 1;
    } else if (argument === '--help' || argument === '-h') {
      console.log(usage);
      process.exit(0);
    } else {
      throw new Error(usage);
    }
  }
  return options;
}

async function hashFile(filePath) {
  const hash = createHash('sha256');
  await pipeline(createReadStream(filePath), new Transform({
    transform(chunk, _encoding, callback) {
      hash.update(chunk);
      callback(null, chunk);
    },
  }), new Transform({
    transform(_chunk, _encoding, callback) {
      callback();
    },
  }));
  return hash.digest('hex');
}

async function verifyTemplate(template, directory) {
  const filePath = join(directory, template.name);
  try {
    if ((await stat(filePath)).size !== template.bytes) return false;
    return (await hashFile(filePath)) === template.sha256;
  } catch {
    return false;
  }
}

async function downloadTemplate({asset, directory, template}) {
  const response = await fetch(asset.browser_download_url, {
    headers: {'User-Agent': 'creatorberry-faceless-template-downloader'},
  });
  if (!response.ok || !response.body) {
    throw new Error(`Could not download ${template.name} (HTTP ${response.status}).`);
  }

  const temporaryPath = join(directory, `${template.name}.part`);
  const destinationPath = join(directory, template.name);
  const hash = createHash('sha256');
  let bytesReceived = 0;
  let lastReportedMegabytes = -1;
  const tracker = new Transform({
    transform(chunk, _encoding, callback) {
      bytesReceived += chunk.length;
      hash.update(chunk);
      const megabytes = Math.floor(bytesReceived / (1024 * 1024));
      if (megabytes >= lastReportedMegabytes + 25 || bytesReceived === template.bytes) {
        lastReportedMegabytes = megabytes;
        console.log(`${template.name}: ${megabytes} MB downloaded`);
      }
      callback(null, chunk);
    },
  });

  await rm(temporaryPath, {force: true});
  try {
    await pipeline(Readable.fromWeb(response.body), tracker, createWriteStream(temporaryPath));
    if (bytesReceived !== template.bytes || hash.digest('hex') !== template.sha256) {
      throw new Error(`Downloaded ${template.name} did not match its expected file checksum.`);
    }
    await rm(destinationPath, {force: true});
    await rename(temporaryPath, destinationPath);
  } finally {
    await rm(temporaryPath, {force: true});
  }
}

const options = parseArguments(process.argv.slice(2));
const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const skillDirectory = dirname(scriptDirectory);
const manifestPath = join(skillDirectory, 'video-templates-manifest.json');
const templateDirectory = resolve(options.templates || join(skillDirectory, 'video-templates'));
const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
if (!Array.isArray(manifest.templates) || !manifest.githubRepository || !manifest.releaseTag) {
  throw new Error(`Invalid template manifest: ${manifestPath}`);
}
for (const template of manifest.templates) {
  if (template.name !== basename(template.name) || !Number.isSafeInteger(template.bytes) || !/^[a-f0-9]{64}$/.test(template.sha256)) {
    throw new Error(`Invalid template entry in ${manifestPath}.`);
  }
}

const validTemplates = [];
for (const template of manifest.templates) {
  if (await verifyTemplate(template, templateDirectory)) validTemplates.push(template.name);
}
if (options.status) {
  if (validTemplates.length === manifest.templates.length) {
    console.log('Minecraft templates are installed and verified locally.');
    process.exit(0);
  }
  const totalGigabytes = (manifest.templates.reduce((total, template) => total + template.bytes, 0) / 1_000_000_000).toFixed(1);
  console.log(`Minecraft templates are not ready (${validTemplates.length}/${manifest.templates.length} verified). Template pack: ${totalGigabytes} GB.`);
  process.exit(1);
}

const missingTemplates = manifest.templates.filter((template) => !validTemplates.includes(template.name));
if (missingTemplates.length === 0) {
  console.log('Minecraft templates are already installed and verified locally.');
  process.exit(0);
}
if (!options.replace) {
  for (const template of missingTemplates) {
    try {
      await access(join(templateDirectory, template.name));
      throw new Error(`A missing or changed ${template.name} already exists. Re-run with --replace to replace it.`);
    } catch (error) {
      if (error?.code !== 'ENOENT') throw error;
    }
  }
}

const releaseResponse = await fetch(`https://api.github.com/repos/${manifest.githubRepository}/releases/tags/${manifest.releaseTag}`, {
  headers: {
    Accept: 'application/vnd.github+json',
    'User-Agent': 'creatorberry-faceless-template-downloader',
  },
});
if (!releaseResponse.ok) {
  throw new Error(`The Minecraft template release is not available yet (HTTP ${releaseResponse.status}).`);
}
const release = await releaseResponse.json();
const assets = new Map(release.assets.map((asset) => [asset.name, asset]));
await mkdir(templateDirectory, {recursive: true});
for (const template of missingTemplates) {
  const asset = assets.get(template.name);
  if (!asset) throw new Error(`The release is missing ${template.name}.`);
  console.log(`Downloading ${template.name}...`);
  await downloadTemplate({asset, directory: templateDirectory, template});
}
console.log(`Minecraft templates are ready: ${templateDirectory}`);
