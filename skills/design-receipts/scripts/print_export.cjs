#!/usr/bin/env node

const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { parseArgs } = require('node:util');

const HELP = `Print a standalone HTML export with an already-installed Chromium browser.

node print_export.cjs --input /absolute/export.html --output /absolute/staging.pdf
  --module ABSOLUTE_PATH         Use a trusted, installed Playwright package.
  --browser-executable PATH      Use an installed compatible Chromium executable.
`;

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

function inputPath(filename) {
  if (!filename || !path.isAbsolute(filename) || !/\.html?$/i.test(filename)) {
    throw new Error('Provide --input as an absolute path to a standalone HTML file.');
  }
  if (!fs.statSync(filename).isFile()) {
    throw new Error('--input must be a regular HTML file.');
  }
  return fs.realpathSync(filename);
}

async function printExport(args) {
  const input = inputPath(args.input);
  if (!args.output || !path.isAbsolute(args.output) || !/\.pdf$/i.test(args.output)) {
    throw new Error('Provide a new absolute --output path ending in .pdf.');
  }
  const output = path.resolve(args.output);
  if (fs.lstatSync(output, { throwIfNoEntry: false })) {
    throw new Error(`The output already exists at ${output}. Choose a new staging path.`);
  }
  const chromium = loadChromium(args.module);
  let browser;
  let pdf;
  try {
    try {
      browser = await chromium.launch({ executablePath: args['browser-executable'], timeout: 12_000 });
    } catch (error) {
      throw new Error(`Could not start Chromium. Use a browser already installed for Playwright or pass --browser-executable. ${error.message.split('\n')[0]}`);
    }
    const context = await browser.newContext({
      acceptDownloads: false,
      javaScriptEnabled: false,
      offline: true,
      serviceWorkers: 'block',
    });
    let unavailableResource = false;
    await context.route('**/*', async (route) => {
      const protocol = new URL(route.request().url()).protocol;
      if (protocol === 'file:' || protocol === 'data:') {
        await route.continue();
      } else {
        unavailableResource = true;
        await route.abort();
      }
    });
    const page = await context.newPage();
    page.on('requestfailed', () => { unavailableResource = true; });
    await page.emulateMedia({ media: 'print' });
    await page.goto(pathToFileURL(input).href, { waitUntil: 'load', timeout: 15_000 });
    await page.evaluate(() => {
      for (const image of document.images) image.loading = 'eager';
    });
    await page.waitForFunction(() =>
      Array.from(document.images).every((image) => image.complete) && document.fonts.status === 'loaded',
      undefined, { timeout: 10_000 },
    );
    const broken = await page.evaluate(() => ({
      image: Array.from(document.images).some((image) => !image.complete || !image.naturalWidth),
      font: Array.from(document.fonts).some((font) => font.status === 'error'),
    }));
    if (unavailableResource || broken.image || broken.font) {
      throw new Error('An image, font, or stylesheet could not load. Embed all export resources before printing.');
    }
    pdf = await page.pdf({
      format: 'A4',
      displayHeaderFooter: false,
      preferCSSPageSize: true,
      printBackground: true,
      tagged: true,
      timeout: 15_000,
    });
  } finally {
    await browser?.close();
  }
  fs.writeFileSync(output, pdf, { flag: 'wx', mode: 0o600 });
  console.log(JSON.stringify({ path: output }));
}

async function main() {
  const { values: args } = parseArgs({
    options: {
      help: { type: 'boolean' },
      input: { type: 'string' },
      output: { type: 'string' },
      module: { type: 'string' },
      'browser-executable': { type: 'string' },
    },
  });
  if (args.help) {
    console.log(HELP.trim());
    return;
  }
  await printExport(args);
}

main().catch((error) => {
  console.error(`print-export: ${error.message.split('\n')[0]}`);
  process.exitCode = 1;
});
