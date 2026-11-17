#!/usr/bin/env node

const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { once } = require('node:events');
const { parseArgs } = require('node:util');

const HELP = `Capture a local web app in an isolated Chromium session.

node capture_browser.cjs --url http://127.0.0.1:3000/ --output /tmp/state.png
  --width PX --height PX          Set the viewport (default 1440×900).
  --actions PATH                 Replay click, fill, press, or waitFor steps from JSON.
  --module ABSOLUTE_PATH         Use a trusted, already-installed Playwright package.
  --browser-executable PATH      Use an already-installed compatible Chromium executable.
`;

const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]']);
const ACTION_FIELDS = { click: [], fill: ['value'], press: ['key'], waitFor: [] };

function localUrl(value) {
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || !LOCAL_HOSTS.has(url.hostname) || url.username || url.password) {
    throw new Error('Use an HTTP or HTTPS URL on localhost, 127.0.0.1, or [::1], with no credentials.');
  }
  return url;
}

function parseViewport(value, fallback, flag) {
  if (value === undefined) return fallback;
  if (!/^\d+$/.test(value) || Number(value) < 1 || Number(value) > 4096) {
    throw new Error(`--${flag} must be a whole number between 1 and 4096.`);
  }
  return Number(value);
}

function readActions(filename) {
  if (!filename) return [];
  const actions = JSON.parse(fs.readFileSync(filename, 'utf8'));
  if (!Array.isArray(actions) || actions.length > 12) {
    throw new Error('--actions must contain a JSON array of up to 12 steps.');
  }
  for (const [index, step] of actions.entries()) {
    const allowed = step && Object.hasOwn(ACTION_FIELDS, step.action) && ACTION_FIELDS[step.action];
    if (!allowed || typeof step.selector !== 'string' || !step.selector.trim() ||
        allowed.some((key) => typeof step[key] !== 'string') ||
        Object.keys(step).some((key) => !['action', 'selector', ...allowed].includes(key))) {
      throw new Error(`Invalid action ${index + 1}. Use click, fill, press, or waitFor with a selector.`);
    }
  }
  return actions;
}

function loadChromium(modulePath) {
  if (modulePath && !path.isAbsolute(modulePath)) {
    throw new Error('--module must be an absolute path to an installed Playwright package.');
  }
  const lookup = { paths: [process.cwd(), __dirname] };
  for (const candidate of modulePath ? [modulePath] : ['playwright', 'playwright-core']) {
    let resolved;
    try {
      resolved = require.resolve(candidate, lookup);
    } catch (error) {
      if (error.code !== 'MODULE_NOT_FOUND') throw error;
      continue;
    }
    const { chromium } = require(resolved);
    if (chromium && typeof chromium.launch === 'function') return chromium;
  }
  throw new Error('Playwright was not found. Run from a project with Playwright or pass --module for an existing installation.');
}

async function applyAction(page, step) {
  const element = page.locator(step.selector);
  switch (step.action) {
    case 'click': return element.click();
    case 'fill': return element.fill(step.value);
    case 'press': return element.press(step.key);
    case 'waitFor': return element.waitFor({ state: 'visible' });
  }
}

async function startRejectingProxy() {
  const proxy = http.createServer((_request, response) => {
    response.writeHead(403, { 'Content-Type': 'text/plain' });
    response.end('External requests are disabled for local app screenshots.');
  });
  proxy.on('connect', (_request, socket) => socket.destroy());
  proxy.listen(0, '127.0.0.1');
  await once(proxy, 'listening');
  return proxy;
}

async function main() {
  const { values: args } = parseArgs({
    options: {
      help: { type: 'boolean' },
      url: { type: 'string' },
      output: { type: 'string' },
      width: { type: 'string' },
      height: { type: 'string' },
      actions: { type: 'string' },
      module: { type: 'string' },
      'browser-executable': { type: 'string' },
    },
  });
  if (args.help) {
    console.log(HELP.trim());
    return;
  }
  if (!args.url || !args.output || !/\.png$/i.test(args.output)) {
    throw new Error('Provide --url and a new --output path ending in .png. Run --help for usage.');
  }
  const url = localUrl(args.url);
  const output = path.resolve(args.output);
  if (fs.lstatSync(output, { throwIfNoEntry: false })) {
    throw new Error(`The output already exists at ${output}. Choose a new staging path.`);
  }
  const viewport = {
    width: parseViewport(args.width, 1440, 'width'),
    height: parseViewport(args.height, 900, 'height'),
  };
  const steps = readActions(args.actions);
  const chromium = loadChromium(args.module);
  const proxy = await startRejectingProxy();
  let browser;
  let image;
  let route;
  try {
    try {
      browser = await chromium.launch({
        executablePath: args['browser-executable'],
        timeout: 12_000,
        // Replace Chromium's implicit exclusions so redirects allow only known loopback hosts.
        proxy: { server: `http://127.0.0.1:${proxy.address().port}`, bypass: '<-loopback>,localhost,127.0.0.1,[::1]' },
      });
    } catch (error) {
      throw new Error(`Could not start Chromium. Use a browser already installed for Playwright or pass --browser-executable. ${error.message.split('\n')[0]}`);
    }
    const context = await browser.newContext({
      viewport, acceptDownloads: false, serviceWorkers: 'block', reducedMotion: 'reduce',
    });
    const page = await context.newPage();
    page.setDefaultTimeout(5_000);
    const response = await page.goto(url.href, { waitUntil: 'domcontentloaded', timeout: 10_000 });
    if (!response || !response.ok()) {
      throw new Error(`The app did not return a successful page${response ? ` (HTTP ${response.status()})` : ''}.`);
    }
    for (const [index, step] of steps.entries()) {
      try {
        await applyAction(page, step);
        localUrl(page.url());
      } catch (error) {
        throw new Error(`Action ${index + 1} (${step.action}) failed. ${error.message.split('\n')[0]}`);
      }
    }
    localUrl(page.url());
    image = await page.screenshot({ animations: 'disabled', type: 'png', timeout: 8_000 });
    route = localUrl(page.url()).pathname;
  } finally {
    try {
      await browser?.close();
    } finally {
      proxy.close();
    }
  }
  fs.writeFileSync(output, image, { flag: 'wx', mode: 0o600 });
  console.log(JSON.stringify({ path: output, route, ...viewport }));
}

main().catch((error) => {
  console.error(`capture-browser: ${error.message.split('\n')[0]}`);
  process.exitCode = 1;
});
