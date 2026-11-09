#!/usr/bin/env node
/**
 * Configuration storage for lead-finder
 *
 * Prompts the user for all required configuration values one by one,
 * then writes them to .env in the project root.
 *
 * Usage:
 *   lead-finder --config   or   lead-finder -config
 *   lead-finder start   (runs setup automatically if .env is missing/incomplete)
 */

const fs = require('fs');
const path = require('path');
const os = require('os');

const PROJECT_ROOT = path.resolve(__dirname, '..');
const LEGACY_ENV = path.join(PROJECT_ROOT, '.env');
const DATA_DIR = process.env.LEAD_FINDER_HOME || (fs.existsSync(LEGACY_ENV) ? PROJECT_ROOT : path.join(os.homedir(), '.lead-finder'));
const ENV_FILE = path.join(DATA_DIR, '.env');

function loadExistingEnv() {
  if (!fs.existsSync(ENV_FILE)) return {};
  const text = fs.readFileSync(ENV_FILE, 'utf8');
  const values = require('dotenv').parse(text);
  // Files saved by this application use JSON strings; decode their escapes.
  if (text.startsWith('# Lead Finder settings. Environment variables take precedence.')) {
    for (const line of text.split(/\r?\n/)) {
      const match = line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
      if (match) { try { values[match[1]] = JSON.parse(match[2]); } catch (_) {} }
    }
  }
  return values;
}

function saveEnv(vars) {
  const lines = ['# Lead Finder settings. Environment variables take precedence.'];
  for (const [key, value] of Object.entries(vars)) {
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) continue;
    lines.push(`${key}=${JSON.stringify(String(value ?? ''))}`);
  }
  fs.mkdirSync(DATA_DIR, { recursive: true });
  const temporary = `${ENV_FILE}.${process.pid}.tmp`;
  try {
    fs.writeFileSync(temporary, lines.join('\n') + '\n', { mode: 0o600 });
    fs.renameSync(temporary, ENV_FILE);
  } finally {
    if (fs.existsSync(temporary)) fs.unlinkSync(temporary);
  }
}

function checkEnvComplete() {
  const values = { ...loadExistingEnv(), ...process.env };
  return ['SEARCH_API_KEY', 'SMTP_USER', 'SMTP_PASS', 'FROM_EMAIL']
    .every((key) => Boolean(values[key] && values[key].trim()));
}

module.exports = {
  checkEnvComplete,
  loadExistingEnv,
  saveEnv,
  ENV_FILE,
  DATA_DIR,
};
