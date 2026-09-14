import {mkdir, readFile, writeFile, chmod} from 'node:fs/promises';
import {homedir} from 'node:os';
import {join} from 'node:path';

const configDirectory = process.env.FACELESS_CONFIG_DIR || join(homedir(), '.faceless');
const configPath = join(configDirectory, 'config.json');

export function getConfigPath() {
  return configPath;
}

export async function loadFishApiKey() {
  if (process.env.FISH_API_KEY?.trim()) {
    return process.env.FISH_API_KEY.trim();
  }

  try {
    const config = JSON.parse(await readFile(configPath, 'utf8'));
    return typeof config.fishApiKey === 'string' && config.fishApiKey.trim()
      ? config.fishApiKey.trim()
      : null;
  } catch (error) {
    if (error?.code === 'ENOENT') return null;
    throw new Error('Could not read local Faceless configuration.');
  }
}

export async function saveFishApiKey(fishApiKey) {
  await mkdir(configDirectory, {recursive: true});
  await writeFile(
    configPath,
    `${JSON.stringify({fishApiKey, updatedAt: new Date().toISOString()}, null, 2)}\n`,
    {encoding: 'utf8', mode: 0o600},
  );
  await chmod(configPath, 0o600).catch(() => {});
}
