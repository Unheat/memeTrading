#!/usr/bin/env node
import {getConfigPath, loadFishApiKey, saveFishApiKey} from './fish-config.mjs';
import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline/promises';
import {stdin, stdout} from 'node:process';

function runWindowsDialog() {
  const script = `
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$form = New-Object System.Windows.Forms.Form
$form.Text = 'Faceless — Fish Audio API key'
$form.Size = New-Object System.Drawing.Size(560, 210)
$form.StartPosition = 'CenterScreen'
$form.Topmost = $true
$label = New-Object System.Windows.Forms.Label
$label.Text = 'Paste your Fish Audio API key below. It is visible so you can confirm it before saving.'
$label.AutoSize = $true
$label.Location = New-Object System.Drawing.Point(18, 18)
$text = New-Object System.Windows.Forms.TextBox
$text.Location = New-Object System.Drawing.Point(18, 52)
$text.Size = New-Object System.Drawing.Size(505, 27)
$text.UseSystemPasswordChar = $false
$count = New-Object System.Windows.Forms.Label
$count.Location = New-Object System.Drawing.Point(18, 88)
$count.AutoSize = $true
$count.Text = '0 characters'
$text.Add_TextChanged({ $count.Text = \"$($text.Text.Length) characters\" })
$save = New-Object System.Windows.Forms.Button
$save.Text = 'Save key'
$save.Location = New-Object System.Drawing.Point(348, 118)
$save.Size = New-Object System.Drawing.Size(85, 30)
$cancel = New-Object System.Windows.Forms.Button
$cancel.Text = 'Cancel'
$cancel.Location = New-Object System.Drawing.Point(438, 118)
$cancel.Size = New-Object System.Drawing.Size(85, 30)
$cancel.Add_Click({ $form.DialogResult = [System.Windows.Forms.DialogResult]::Cancel; $form.Close() })
$save.Add_Click({ if ($text.Text.Trim()) { $form.DialogResult = [System.Windows.Forms.DialogResult]::OK; $form.Close() } else { [System.Windows.Forms.MessageBox]::Show('Paste an API key first.') } })
$form.Controls.AddRange(@($label, $text, $count, $save, $cancel))
$form.AcceptButton = $save
if ($form.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); [Console]::Write($text.Text.Trim()) }
`;
  const encodedScript = Buffer.from(script, 'utf16le').toString('base64');
  return new Promise((resolve, reject) => {
    const child = spawn('powershell.exe', ['-NoProfile', '-STA', '-EncodedCommand', encodedScript], {stdio: ['ignore', 'pipe', 'ignore']});
    let value = '';
    child.stdout.on('data', (chunk) => { value += chunk; });
    child.on('error', reject);
    child.on('exit', (code) => {
      if (code !== 0) reject(new Error('Fish key setup was cancelled.'));
      else resolve(value.trim());
    });
  });
}

async function readVisibleInput(prompt) {
  if (!stdin.isTTY || !stdout.isTTY) {
    throw new Error('Run this setup command in an interactive terminal.');
  }
  const terminal = createInterface({input: stdin, output: stdout});
  try {
    return (await terminal.question(prompt)).trim();
  } finally {
    terminal.close();
  }
}

if (process.argv.includes('--status')) {
  const fishApiKey = await loadFishApiKey();
  console.log(fishApiKey ? 'Fish Audio is configured locally.' : 'Fish Audio is not configured locally.');
  process.exit(fishApiKey ? 0 : 1);
}

console.log('Create your Fish Audio API key here: https://fish.audio/app/api-keys/');
const fishApiKey = process.platform === 'win32'
  ? await runWindowsDialog()
  : await readVisibleInput('Paste your Fish Audio API key (visible): ');

if (!fishApiKey) {
  throw new Error('No Fish API key was entered.');
}
if (/[\u0000-\u001F\u007F]/.test(fishApiKey)) {
  throw new Error('The key contains an unsupported hidden character. Copy it once again from Fish Audio.');
}

await saveFishApiKey(fishApiKey);
console.log(`Fish Audio is configured locally at ${getConfigPath()} (${fishApiKey.length} characters saved).`);
