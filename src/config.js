#!/usr/bin/env node
/**
 * Interactive config setup for lead-finder
 *
 * Prompts the user for all required configuration values one by one,
 * then writes them to .env in the project root.
 *
 * Usage:
 *   lead-finder --config   or   lead-finder -config
 *   lead-finder start   (runs setup automatically if .env is missing/incomplete)
 */

const readline = require('readline');
const fs = require('fs');
const path = require('path');

const PROJECT_ROOT = path.resolve(__dirname, '..');
const ENV_FILE = path.join(PROJECT_ROOT, '.env');
const ENV_EXAMPLE = path.join(PROJECT_ROOT, '.env.example');

// ── Required config fields ─────────────────────────────────────────────
const CONFIG_FIELDS = [
  {
    key: 'OPENROUTER_API_KEY',
    label: 'OpenRouter API Key',
    description: 'Get it from https://openrouter.ai/keys (powers AI email writing)',
    secret: true,
    required: true,
    example: 'sk-or-v1-...',
  },
  {
    key: 'SEARCH_API_KEY',
    label: 'Tavily Search API Key',
    description: 'Get it from https://tavily.com (free tier: 1,000 searches/month)',
    secret: true,
    required: true,
    example: 'tvly-dev-...',
  },
  {
    key: 'SMTP_USER',
    label: 'Gmail Address',
    description: 'Your Gmail email address (used for sending and IMAP)',
    secret: false,
    required: true,
    example: 'you@gmail.com',
  },
  {
    key: 'SMTP_PASS',
    label: 'Gmail App Password',
    description: '16-char App Password from myaccount.google.com/apppasswords (NOT your Gmail password)',
    secret: true,
    required: true,
    example: 'abcd efgh ijkl mnop',
  },
  {
    key: 'FROM_NAME',
    label: 'Your Name',
    description: 'Name that appears as email sender (e.g., Andrei)',
    secret: false,
    required: true,
    example: 'Andrei',
  },
  {
    key: 'FROM_EMAIL',
    label: 'Sender Email',
    description: 'Email address shown in the From header (usually same as Gmail)',
    secret: false,
    required: true,
    example: 'you@gmail.com',
  },
  {
    key: 'FROM_COMPANY',
    label: 'Your Company',
    description: 'Company name shown in emails',
    secret: false,
    required: false,
    example: 'Andrei Freelance Web Development',
  },
  {
    key: 'VALUE_PROP',
    label: 'Your Value Proposition',
    description: 'One sentence describing what you do (e.g., "I build custom websites for small businesses")',
    secret: false,
    required: false,
    example: 'I build custom websites for small businesses',
  },
  {
    key: 'DAILY_LIMIT',
    label: 'Daily Email Limit',
    description: 'Maximum emails to send per day (recommended: 20)',
    secret: false,
    required: false,
    example: '20',
  },
  {
    key: 'IMAP_USER',
    label: 'IMAP Username',
    description: 'Gmail address for reading replies (usually same as SMTP_USER)',
    secret: false,
    required: false,
    example: 'you@gmail.com',
  },
  {
    key: 'IMAP_PASS',
    label: 'IMAP Password',
    description: 'Same 16-char App Password as SMTP_PASS',
    secret: true,
    required: false,
    example: 'abcd efgh ijkl mnop',
  },
];

function mask(value) {
  if (!value) return '';
  return value.replace(/./g, '*');
}

function rlQuestion(prompt) {
  return new Promise((resolve) => {
    rl.question(prompt, (answer) => resolve(answer.trim()));
  });
}

async function promptForField(field, currentValue) {
  const current = currentValue ? ` (current: ${field.secret ? mask(currentValue) : currentValue})` : '';
  const req = field.required ? ' [REQUIRED]' : '';
  const ex = field.example ? ` (e.g., ${field.example})` : '';

  let promptText = `\n${field.label}${req}${ex}${current}\n  ${field.description}\n  Enter value: `;

  if (field.secret) {
    // For secrets, hide input
    const answer = await new Promise((resolve) => {
      readline.emitKeypressEvents(process.stdin);
      if (process.stdin.isTTY) process.stdin.setRawMode(true);
      let input = '';
      process.stdout.write(promptText);
      process.stdin.on('data', (chunk) => {
        const char = chunk.toString();
        if (char === '\r' || char === '\n') {
          process.stdout.write('\n');
          process.stdin.removeAllListeners('data');
          resolve(input);
        } else if (char === '\u0003') {
          // Ctrl+C
          process.exit(1);
        } else if (char === '\u007f' || char === '\b') {
          if (input.length > 0) {
            input = input.slice(0, -1);
            process.stdout.write('\b \b');
          }
        } else {
          input += char;
          process.stdout.write('*');
        }
      });
    });
    return answer.trim();
  } else {
    return rlQuestion(promptText);
  }
}

function loadExistingEnv() {
  const vars = {};
  if (!fs.existsSync(ENV_FILE)) return vars;
  const content = fs.readFileSync(ENV_FILE, 'utf-8');
  for (const line of content.split('\n')) {
    const match = line.match(/^([^#\s][^=]*)=(.*)$/);
    if (match) {
      vars[match[1].trim()] = match[2].trim().replace(/^"|"$|^'|'$/g, '');
    }
  }
  return vars;
}

function saveEnv(vars) {
  const lines = [];
  lines.push('# ── Required ──');
  lines.push('# Configured by lead-finder --config');
  lines.push(`OPENROUTER_API_KEY=${vars.OPENROUTER_API_KEY || ''}`);
  lines.push(`ENRICH_API_KEY=${vars.ENRICH_API_KEY || ''}`);
  lines.push('');
  lines.push('# ── SMTP Email (Gmail - free, no domain needed) ──');
  lines.push(`SMTP_HOST=${vars.SMTP_HOST || 'smtp.gmail.com'}`);
  lines.push(`SMTP_PORT=${vars.SMTP_PORT || '587'}`);
  lines.push(`SMTP_USER=${vars.SMTP_USER || ''}`);
  lines.push(`SMTP_PASS=${vars.SMTP_PASS || ''}`);
  lines.push('');
  lines.push(`FROM_NAME=${vars.FROM_NAME || ''}`);
  lines.push(`FROM_EMAIL=${vars.FROM_EMAIL || ''}`);
  lines.push(`FROM_COMPANY=${vars.FROM_COMPANY || 'Your Company'}`);
  lines.push(`VALUE_PROP=${vars.VALUE_PROP || 'I help small businesses with custom websites'}`);
  lines.push('');
  lines.push('# ── Limits ──');
  lines.push(`DAILY_LIMIT=${vars.DAILY_LIMIT || '20'}`);
  lines.push('');
  lines.push('# ── Reply tracking (IMAP) ──');
  lines.push(`IMAP_HOST=${vars.IMAP_HOST || 'imap.gmail.com'}`);
  lines.push(`IMAP_USER=${vars.IMAP_USER || ''}`);
  lines.push(`IMAP_PASS=${vars.IMAP_PASS || ''}`);
  lines.push('');
  lines.push('# ── Search API (Tavily) ──');
  lines.push(`SEARCH_API_KEY=${vars.SEARCH_API_KEY || ''}`);
  lines.push(`SEARCH_API_URL=https://api.tavily.com/search`);
  lines.push('');
  lines.push('# ── Database ──');
  lines.push(`DB_PATH=leads.db`);

  fs.writeFileSync(ENV_FILE, lines.join('\n') + '\n');
  console.log(`\n✓ Configuration saved to ${ENV_FILE}`);
}

async function runConfigWizard() {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  console.log('\n╔══════════════════════════════════════════════════════════════╗');
  console.log('║  Lead Finder — Interactive Setup                            ║');
  console.log('║  Configure your lead outreach system                        ║');
  console.log('╚══════════════════════════════════════════════════════════════╝');

  const existing = loadExistingEnv();
  const newVars = {};

  for (const field of CONFIG_FIELDS) {
    const current = existing[field.key] || '';
    const value = await promptForField(field, current);
    if (value) {
      newVars[field.key] = value;
    } else if (current) {
      newVars[field.key] = current;
    } else if (field.required) {
      console.log(`  ⚠ ${field.label} is required. Skipping...`);
    }
  }

  // Merge with existing for fields not prompted
  const allVars = { ...existing, ...newVars };

  rl.close();

  saveEnv(allVars);

  console.log('\n╔══════════════════════════════════════════════════════════════╗');
  console.log('║  Setup complete!                                            ║');
  console.log('║  Run: lead-finder start                                     ║');
  console.log('║  Or: lead-finder --config to edit settings later            ║');
  console.log('╚══════════════════════════════════════════════════════════════╝\n');
}

function checkEnvComplete() {
  if (!fs.existsSync(ENV_FILE)) return false;
  const content = fs.readFileSync(ENV_FILE, 'utf-8');
  const required = ['OPENROUTER_API_KEY', 'SEARCH_API_KEY', 'SMTP_USER', 'SMTP_PASS', 'FROM_EMAIL'];
  for (const key of required) {
    const match = content.match(new RegExp(`^${key}=(.*)$`, 'm'));
    if (!match || !match[1].trim()) return false;
  }
  return true;
}

module.exports = {
  runConfigWizard,
  checkEnvComplete,
  ENV_FILE,
};
