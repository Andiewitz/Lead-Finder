#!/usr/bin/env node
/**
 * Lead Finder TUI (Terminal User Interface)
 *
 * Uses `enquirer` for interactive prompts with masked secret input,
 * `chalk` for colors, and `cli-spinners` for loading states.
 *
 * Screens:
 *   - welcome()     - Welcome banner
 *   - configWizard() - Step-by-step config input
 *   - dashboard()   - Campaign statistics dashboard
 *   - mainMenu()    - Main action menu
 *   - confirm()     - Yes/no confirmation
 *   - success()     - Success message
 *   - error()       - Error message
 */

const { prompt } = require('enquirer');
const chalk = require('chalk');
const spinners = require('cli-spinners');
const fs = require('fs');
const path = require('path');

const { green, red, yellow, cyan, magenta, bold, dim, gray } = chalk;

const PROJECT_ROOT = path.resolve(__dirname, '..');
const ENV_FILE = path.join(PROJECT_ROOT, '.env');

/**
 * Print a styled banner/header
 */
function banner(text, subtext = '') {
  const width = Math.max(text.length, subtext.length) + 4;
  const line = '═'.repeat(width);
  console.log(`\n${cyan('╔')}${line}${cyan('╗')}`);
  console.log(`${cyan('║')}  ${bold(text)}${' '.repeat(width - text.length - 4)}${cyan('║')}`);
  if (subtext) {
    console.log(`${cyan('║')}  ${dim(subtext)}${' '.repeat(width - subtext.length - 4)}${cyan('║')}`);
  }
  console.log(`${cyan('╚')}${line}${cyan('╝')}\n`);
}

/**
 * Welcome screen
 */
async function welcome() {
  banner('Lead Finder', 'Autonomous lead outreach automation for web developers');
  console.log(`${dim('Find Portland-area businesses • Research • Write • Send • Track replies')}\n`);
  console.log(`${yellow('Quick commands:')}`);
  console.log(`  ${cyan('lead-finder start')}    Start MCP server (for OpenCode/KiloCode)`);
  console.log(`  ${cyan('lead-finder find-leads')} Discover new leads via Tavily`);
  console.log(`  ${cyan('lead-finder send-email <email>')} Send a cold email`);
  console.log(`  ${cyan('lead-finder check-replies')} Poll IMAP for replies`);
  console.log(`  ${cyan('lead-finder status')}    View campaign statistics`);
  console.log(`  ${cyan('lead-finder --config')}  Run interactive setup\n`);
}

/**
 * Config wizard using enquirer prompts
 */
async function configWizard() {
  banner('Interactive Setup', 'Configure your lead outreach system');
  console.log(`${dim('All values are saved to .env (gitignored — never committed)')}\n`);

  const existing = require('fs').existsSync(ENV_FILE)
    ? loadExistingEnv()
    : {};

  const answers = await prompt([
    {
      type: 'input',
      name: 'OPENROUTER_API_KEY',
      message: 'OpenRouter API Key',
      initial: existing.OPENROUTER_API_KEY || '',
      required: true,
      hint: 'Get it from https://openrouter.ai/keys',
      mask: true,
      format: (val) => val.trim(),
      result: (val) => val.trim(),
    },
    {
      type: 'input',
      name: 'SEARCH_API_KEY',
      message: 'Tavily Search API Key',
      initial: existing.SEARCH_API_KEY || '',
      required: true,
      hint: 'Get it from https://tavily.com (free: 1,000 searches/month)',
      mask: true,
      format: (val) => val.trim(),
      result: (val) => val.trim(),
    },
    {
      type: 'input',
      name: 'SMTP_USER',
      message: 'Gmail Address',
      initial: existing.SMTP_USER || '',
      required: true,
      hint: 'Your Gmail email for sending + IMAP',
      format: (val) => val.trim(),
      result: (val) => val.trim(),
    },
    {
      type: 'password',
      name: 'SMTP_PASS',
      message: 'Gmail App Password',
      initial: existing.SMTP_PASS || '',
      required: true,
      hint: '16-char App Password from myaccount.google.com/apppasswords',
      mask: '*',
      format: (val) => val.trim(),
      result: (val) => val.trim(),
    },
    {
      type: 'input',
      name: 'FROM_NAME',
      message: 'Your Name',
      initial: existing.FROM_NAME || 'Andrei',
      required: true,
      hint: 'Appears as email sender',
      format: (val) => val.trim(),
      result: (val) => val.trim(),
    },
    {
      type: 'input',
      name: 'FROM_EMAIL',
      message: 'Sender Email',
      initial: existing.FROM_EMAIL || '',
      required: true,
      hint: 'Email shown in From header (usually same as Gmail)',
      format: (val) => val.trim(),
      result: (val) => val.trim(),
    },
    {
      type: 'input',
      name: 'FROM_COMPANY',
      message: 'Your Company',
      initial: existing.FROM_COMPANY || '',
      hint: 'Company name shown in emails',
      format: (val) => val.trim(),
      result: (val) => val.trim(),
    },
    {
      type: 'input',
      name: 'VALUE_PROP',
      message: 'Your Value Proposition',
      initial: existing.VALUE_PROP || '',
      hint: 'One sentence describing what you do',
      format: (val) => val.trim(),
      result: (val) => val.trim(),
    },
    {
      type: 'input',
      name: 'DAILY_LIMIT',
      message: 'Daily Email Limit',
      initial: existing.DAILY_LIMIT || '20',
      hint: 'Maximum emails per day (recommended: 20)',
      format: (val) => val.trim() || '20',
      result: (val) => val.trim() || '20',
    },
    {
      type: 'input',
      name: 'IMAP_USER',
      message: 'IMAP Username (for reply tracking)',
      initial: existing.IMAP_USER || '',
      hint: 'Usually same as SMTP_USER',
      format: (val) => val.trim(),
      result: (val) => val.trim(),
    },
    {
      type: 'password',
      name: 'IMAP_PASS',
      message: 'IMAP Password',
      initial: existing.IMAP_PASS || '',
      hint: 'Same App Password as SMTP_PASS',
      mask: '*',
      format: (val) => val.trim(),
      result: (val) => val.trim(),
    },
  ]);

  // Merge with existing values for fields not changed
  const allVars = { ...existing, ...answers };

  // Save to .env
  saveEnv(allVars);

  console.log(`\n${green('✓ Configuration saved to .env')}`);
  console.log(`${dim('Run: lead-finder start to begin')}\n`);
}

/**
 * Load existing .env values
 */
function loadExistingEnv() {
  const fs = require('fs');
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

/**
 * Save all variables to .env
 */
function saveEnv(vars) {
  const fs = require('fs');
  const lines = [];
  lines.push('# ── Lead Finder Configuration ──');
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
  lines.push(`VALUE_PROP=${vars.VALUE_PROP || 'I build custom websites for small businesses'}`);
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
}

/**
 * Main menu
 */
async function mainMenu() {
  const { action } = await prompt({
    type: 'select',
    name: 'action',
    message: 'What would you like to do?',
    choices: [
      { name: 'start', message: `${cyan('start')}  — Start MCP server (for OpenCode/KiloCode)` },
      { name: 'find-leads', message: `${cyan('find-leads')}  — Discover new leads via Tavily` },
      { name: 'send-email', message: `${cyan('send-email')}  — Send a personalized cold email` },
      { name: 'check-replies', message: `${cyan('check-replies')}  — Poll IMAP and classify replies` },
      { name: 'status', message: `${cyan('status')}  — View campaign statistics` },
      { name: 'config', message: `${cyan('config')}  — Edit settings` },
      { name: 'exit', message: `${gray('exit')}  — Quit` },
    ],
  });
  return action;
}

/**
 * Dashboard with stats
 */
async function dashboard(stats) {
  banner('Campaign Dashboard');
  console.log(`${bold('Emails sent today:')} ${green(stats.sent_today || 0)}`);
  console.log(`${bold('Total sent:')} ${green(stats.total_sent || stats.sent || 0)}`);
  console.log(`${bold('Drafts:')} ${yellow(stats.draft || 0)}`);
  console.log(`${bold('Whitelist:')} ${cyan(stats.whitelist || 0)}`);
  console.log(`${bold('Blacklist:')} ${red(stats.blacklist || 0)}\n`);
}

/**
 * Success message
 */
function success(msg) {
  console.log(`${green('✓')} ${msg}\n`);
}

/**
 * Error message
 */
function error(msg) {
  console.log(`${red('✗')} ${msg}\n`);
}

/**
 * Info message
 */
function info(msg) {
  console.log(`${dim('ℹ')} ${msg}`);
}

/**
 * Spinner helper
 */
function spinner(text) {
  const spin = spinners.dots;
  let i = 0;
  const interval = setInterval(() => {
    process.stdout.write(`\r${cyan(spin.frames[i++ % spin.frames.length])} ${text}`);
  }, spin.interval);
  return {
    stop: (finalText) => {
      clearInterval(interval);
      process.stdout.write(`\r${green('✓')} ${finalText}\n`);
    },
  };
}

module.exports = {
  banner,
  welcome,
  configWizard,
  mainMenu,
  dashboard,
  success,
  error,
  info,
  spinner,
  loadExistingEnv,
  saveEnv,
};
