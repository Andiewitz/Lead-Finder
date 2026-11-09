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

const { ENV_FILE, loadExistingEnv, saveEnv } = require('./config');

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
  console.log(`  ${cyan('lead-finder send-email --email <address>')} Send a cold email`);
  console.log(`  ${cyan('lead-finder check-replies')} Poll IMAP for replies`);
  console.log(`  ${cyan('lead-finder status')}    View campaign statistics`);
  console.log(`  ${cyan('lead-finder --config')}  Run interactive setup\n`);
}

/**
 * Config wizard using enquirer prompts
 */
async function configWizard() {
  banner('Interactive Setup', 'Configure your lead outreach system');
  console.log(`${dim(`Settings are saved to ${ENV_FILE}`)}\n`);

  if (!process.stdin.isTTY) throw new Error('Setup requires an interactive terminal. Set environment variables or run lead-finder --config in a terminal.');
  const existing = loadExistingEnv();
  if (fs.existsSync(ENV_FILE)) {
    const { choice } = await prompt({ type: 'select', name: 'choice',
      message: 'Existing settings found. What would you like to do?',
      choices: [
        { name: 'keep', message: 'Keep current settings and exit' },
        { name: 'edit', message: 'Edit settings' },
        { name: 'cancel', message: 'Cancel' },
      ],
    });
    if (choice !== 'edit') { console.log('Settings were left unchanged.'); return; }
  }
  console.log('All fields can be skipped. Leave a field blank to keep its saved value.');
  console.log('Environment variables take precedence over saved values.');

  const answers = await prompt([
    {
      type: 'password',
      name: 'OPENROUTER_API_KEY',
      message: 'OpenRouter API Key (optional)',
      initial: existing.OPENROUTER_API_KEY || '',
      hint: 'Get it from https://openrouter.ai/keys',
      mask: true,
      format: (val) => val.trim(),
      result: (val) => val.trim(),
    },
    {
      type: 'password',
      name: 'SEARCH_API_KEY',
      message: 'Tavily Search API Key',
      initial: existing.SEARCH_API_KEY || '',
      hint: 'Needed only for discovery; get it from https://tavily.com',
      mask: true,
      format: (val) => val.trim(),
      result: (val) => val.trim(),
    },
    {
      type: 'input',
      name: 'SMTP_USER',
      message: 'Gmail Address',
      initial: existing.SMTP_USER || '',
      hint: 'Your Gmail email for sending + IMAP',
      format: (val) => val.trim(),
      result: (val) => val.trim(),
    },
    {
      type: 'password',
      name: 'SMTP_PASS',
      message: 'Gmail App Password',
      initial: existing.SMTP_PASS || '',
      hint: '16-char App Password from myaccount.google.com/apppasswords',
      mask: '*',
      format: (val) => val.trim(),
      result: (val) => val.trim(),
    },
    {
      type: 'input',
      name: 'FROM_NAME',
      message: 'Your Name',
      initial: existing.FROM_NAME || '',
      hint: 'Appears as email sender',
      format: (val) => val.trim(),
      result: (val) => val.trim(),
    },
    {
      type: 'input',
      name: 'FROM_EMAIL',
      message: 'Sender Email',
      initial: existing.FROM_EMAIL || '',
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
      hint: 'Positive whole number; default 20',
      validate: (value) => !value.trim() || (/^[1-9]\d*$/.test(value.trim()) && Number.isSafeInteger(Number(value))) || 'Enter a positive whole number',
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
  const allVars = { ...existing };
  for (const [key, value] of Object.entries(answers)) {
    if (value !== '') allVars[key] = value;
  }

  // Save to .env
  saveEnv(allVars);

  console.log(`\n${green(`✓ Configuration saved to ${ENV_FILE}`)}`);
  console.log(`${dim('Run: lead-finder start to begin')}\n`);
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
  console.log(`${bold('Sends requiring review:')} ${yellow(stats.needs_send_review || 0)}`);
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
