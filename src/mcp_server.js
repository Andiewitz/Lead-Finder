#!/usr/bin/env node
/**
 * lead-finder MCP Server
 *
 * Implements the Model Context Protocol (MCP) over stdio so that OpenCode
 * and KiloCode can call lead-finding, email-sending, and reply-tracking
 * as first-class tools.
 *
 * Protocol: JSON-RPC 2.0 over stdio
 *   Client sends:  { jsonrpc: "2.0", id: 1, method: "initialize", params: {...} }
 *   Server replies: { jsonrpc: "2.0", id: 1, result: {...} }
 *
 * Tools exposed:
 *   find_leads         - Discover Portland-area businesses via Tavily
 *   send_email         - Send personalized cold email via Gmail SMTP
 *   check_replies      - Poll IMAP inbox and classify replies
 *   get_stats          - View campaign statistics from SQLite
 *   add_to_blacklist   - Block an email/domain permanently
 *   search_leads       - Query existing lead database by name/email/category
 */

const { spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const readline = require('readline');

const PROJECT_ROOT = path.resolve(__dirname, '..');
const PYTHON_BIN = process.env.LEAD_FINDER_PYTHON || 'python3';
const MAIN_SCRIPT = path.join(PROJECT_ROOT, 'src', 'main.py');
const ENV_FILE = path.join(PROJECT_ROOT, '.env');

// ── MCP Protocol Helters ──────────────────────────────────────────────

let nextId = 1;

function sendJson(obj) {
  process.stdout.write(JSON.stringify(obj) + '\n');
}

function sendResult(id, result) {
  sendJson({ jsonrpc: '2.0', id, result });
}

function sendError(id, code, message, data) {
  sendJson({ jsonrpc: '2.0', id, error: { code, message, data } });
}

// ── Tool Definitions ──────────────────────────────────────────────────

const TOOLS = [
  {
    name: 'find_leads',
    description: 'Discover Portland-area small businesses via Tavily web search. Returns candidate leads with names, URLs, and snippets.',
    inputSchema: {
      type: 'object',
      properties: {
        industry: {
          type: 'string',
          description: 'Industry to search for (e.g., "cleaning services", "landscaping", "handyman")',
        },
        location: {
          type: 'string',
          description: 'City/area to search in (e.g., "Portland, OR", "Beaverton, OR")',
          default: 'Portland, OR',
        },
        count: {
          type: 'number',
          description: 'Maximum number of leads to return (default: 10)',
          default: 10,
        },
      },
      required: [],
    },
  },
  {
    name: 'send_email',
    description: 'Send a personalized cold email to a business via Gmail SMTP.',
    inputSchema: {
      type: 'object',
      properties: {
        email: {
          type: 'string',
          description: 'Recipient email address',
        },
        company: {
          type: 'string',
          description: 'Company name for personalization',
        },
        personalization_fact: {
          type: 'string',
          description: 'Verified detail about the business to reference in the email',
        },
        category: {
          type: 'string',
          description: 'Business category (cleaning, landscaping, handyman, etc.)',
          default: 'services',
        },
      },
      required: ['email'],
    },
  },
  {
    name: 'check_replies',
    description: 'Poll Gmail IMAP inbox for replies and classify them (Interested / Not interested / Out of office).',
    inputSchema: {
      type: 'object',
      properties: {},
      required: [],
    },
  },
  {
    name: 'get_stats',
    description: 'View campaign statistics: emails sent today, total sent, drafts, whitelist count, blacklist count.',
    inputSchema: {
      type: 'object',
      properties: {},
      required: [],
    },
  },
  {
    name: 'add_to_blacklist',
    description: 'Add an email address or domain to the permanent do-not-contact list.',
    inputSchema: {
      type: 'object',
      properties: {
        email: {
          type: 'string',
          description: 'Email address or domain to blacklist',
        },
        reason: {
          type: 'string',
          description: 'Reason for blacklisting',
          default: 'User requested',
        },
      },
      required: ['email'],
    },
  },
  {
    name: 'search_leads',
    description: 'Search existing lead database by business name, email, or category.',
    inputSchema: {
      type: 'object',
      properties: {
        query: {
          type: 'string',
          description: 'Search term (business name, email, or category)',
        },
      },
      required: ['query'],
    },
  },
];

// ── Python Bridge ─────────────────────────────────────────────────────

function runPython(args = []) {
  const result = spawnSync(PYTHON_BIN, [MAIN_SCRIPT, ...args], {
    cwd: PROJECT_ROOT,
    stdio: ['pipe', 'pipe', 'pipe'],
    env: { ...process.env },
    encoding: 'utf-8',
    timeout: 300000, // 5 minutes
  });

  return {
    status: result.status,
    stdout: result.stdout ? result.stdout.toString() : '',
    stderr: result.stderr ? result.stderr.toString() : '',
    error: result.error,
  };
}

// ── Tool Handlers ─────────────────────────────────────────────────────

async function handleFindLeads(args) {
  const industry = args.industry || 'cleaning services';
  const location = args.location || 'Portland, OR';
  const count = args.count || 10;

  const result = runPython([
    'find-leads',
    '--industry', industry,
    '--location', location,
    '--count', String(count),
  ]);

  if (result.status !== 0) {
    return {
      success: false,
      error: result.stderr || 'Unknown error',
      stdout: result.stdout,
    };
  }

  try {
    const data = JSON.parse(result.stdout);
    return { success: true, leads: data };
  } catch (e) {
    return { success: true, raw: result.stdout };
  }
}

async function handleSendEmail(args) {
  const email = args.email;
  if (!email) {
    throw new Error('email is required');
  }

  const result = runPython([
    'send-email',
    '--email', email,
    '--company', args.company || '',
    '--personalization', args.personalization_fact || '',
    '--category', args.category || 'services',
  ]);

  if (result.status !== 0) {
    return { success: false, error: result.stderr || 'Failed to send email' };
  }

  return { success: true, sent: true, email };
}

async function handleCheckReplies(args) {
  const result = runPython(['check-replies']);

  if (result.status !== 0) {
    return { success: false, error: result.stderr || 'Unknown error' };
  }

  try {
    return { success: true, ...JSON.parse(result.stdout) };
  } catch (e) {
    return { success: true, raw: result.stdout };
  }
}

async function handleGetStats(args) {
  const result = runPython(['status']);

  if (result.status !== 0) {
    return { success: false, error: result.stderr || 'Unknown error' };
  }

  try {
    return { success: true, ...JSON.parse(result.stdout) };
  } catch (e) {
    return { success: true, raw: result.stdout };
  }
}

async function handleAddToBlacklist(args) {
  const email = args.email;
  if (!email) {
    throw new Error('email is required');
  }

  const result = runPython([
    'blacklist',
    '--email', email,
    '--reason', args.reason || 'User requested via MCP',
  ]);

  if (result.status !== 0) {
    return { success: false, error: result.stderr || 'Failed to blacklist' };
  }

  return { success: true, blacklisted: email };
}

async function handleSearchLeads(args) {
  const query = args.query;
  if (!query) {
    throw new Error('query is required');
  }

  const result = runPython([
    'search',
    '--query', query,
  ]);

  if (result.status !== 0) {
    return { success: false, error: result.stderr || 'Unknown error' };
  }

  try {
    return { success: true, results: JSON.parse(result.stdout) };
  } catch (e) {
    return { success: true, raw: result.stdout };
  }
}

const HANDLERS = {
  find_leads: handleFindLeads,
  send_email: handleSendEmail,
  check_replies: handleCheckReplies,
  get_stats: handleGetStats,
  add_to_blacklist: handleAddToBlacklist,
  search_leads: handleSearchLeads,
};

// ── MCP Protocol Loop ─────────────────────────────────────────────────

function handleMessage(line) {
  let msg;
  try {
    msg = JSON.parse(line);
  } catch (e) {
    // Ignore malformed lines
    return;
  }

  const { id, method, params } = msg;

  if (method === 'initialize') {
    sendResult(id, {
      protocolVersion: '2024-11-05',
      capabilities: {
        tools: { listChanged: false },
      },
      serverInfo: {
        name: 'lead-finder',
        version: '1.0.0',
      },
    });
    return;
  }

  if (method === 'initialized') {
    // Notification, no response needed
    return;
  }

  if (method === 'tools/list') {
    sendResult(id, { tools: TOOLS });
    return;
  }

  if (method === 'tools/call') {
    const { name, arguments: toolArgs } = params || {};
    const handler = HANDLERS[name];

    if (!handler) {
      sendError(id, -32601, `Unknown tool: ${name}`);
      return;
    }

    Promise.resolve(handler(toolArgs || {}))
      .then((result) => sendResult(id, result))
      .catch((err) => sendError(id, -32603, err.message || 'Internal error'));
    return;
  }

  // Unknown method
  sendError(id, -32601, `Method not found: ${method}`);
}

// ── Start stdio loop ──────────────────────────────────────────────────

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
  terminal: false,
});

rl.on('line', (line) => {
  handleMessage(line);
});

process.on('SIGINT', () => process.exit(0));
process.on('SIGTERM', () => process.exit(0));

// Announce readiness
sendJson({
  jsonrpc: '2.0',
  method: 'server/ready',
  params: { name: 'lead-finder', version: '1.0.0' },
});
