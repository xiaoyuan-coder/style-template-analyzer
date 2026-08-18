#!/usr/bin/env node
/** Public-HTML source adapters for maintaining the real-photo test pool. */

import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import { dirname } from 'node:path';
import { pathToFileURL } from 'node:url';

export const SOURCE_POLICIES = Object.freeze({
  commons: {
    status: 'enabled',
    baseUrl: 'https://commons.wikimedia.org',
    evidence: 'public-file-page-license',
    categories: Object.freeze([
      'Portrait_photographs',
      'Animal_photography',
      'Product_photography',
      'Food_photography',
      'Living_rooms',
      'Landscape_photography',
      'Architectural_photography',
      'Street_photography',
    ]),
  },
  pinterest: {
    status: 'policy-blocked',
    reason: 'Automated collection is disabled until express permission and compliance review exist.',
  },
});

export class SourceBlockedError extends Error {
  constructor(code, message) {
    super(message);
    this.name = 'SourceBlockedError';
    this.code = code;
  }
}

export function requireEnabledSource(name) {
  const source = SOURCE_POLICIES[name];
  if (!source) throw new SourceBlockedError('source_unknown', `Unknown source: ${name}`);
  if (source.status !== 'enabled') throw new SourceBlockedError('source_policy_blocked', source.reason);
  return source;
}

function decodeHtml(value) {
  return value
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>');
}

function textOnly(value) {
  return decodeHtml(value.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim());
}

function absoluteCommonsUrl(value) {
  return new URL(decodeHtml(value), SOURCE_POLICIES.commons.baseUrl).href;
}

export function parseCommonsCategoryPage(html) {
  const found = [];
  const seen = new Set();
  const pattern = /<a\b[^>]*href=["']([^"']*\/wiki\/File:[^"'#?]+)["'][^>]*>/gi;
  for (const match of html.matchAll(pattern)) {
    const url = absoluteCommonsUrl(match[1]);
    if (!seen.has(url)) {
      seen.add(url);
      found.push(url);
    }
  }
  return found;
}

// Kept as a parser alias for saved v3 fixtures; the v4 crawler never visits
// Special:MediaSearch or a free-text search endpoint.
export const parseCommonsSearchPage = parseCommonsCategoryPage;

export function parseCommonsNextCategoryPage(html, category) {
  const pattern = /<a\b[^>]*href=["']([^"']+)["'][^>]*>\s*(?:next page|下一页)\s*<\/a>/i;
  const match = pattern.exec(html);
  if (!match) return null;
  const parsed = new URL(decodeHtml(match[1]), SOURCE_POLICIES.commons.baseUrl);
  const pageFrom = parsed.searchParams.get('pagefrom');
  if (!pageFrom) return null;
  const target = new URL(`/wiki/Category:${category}`, SOURCE_POLICIES.commons.baseUrl);
  target.searchParams.set('pagefrom', pageFrom);
  return target.href;
}

function capture(html, pattern, label) {
  const match = pattern.exec(html);
  if (!match) throw new SourceBlockedError('source_parse_failed', `Missing ${label}`);
  return match;
}

function normalizeLicense(label, url) {
  const upper = `${label} ${url}`.toUpperCase();
  if (upper.includes('PUBLICDOMAIN/ZERO') || upper.includes('CC0')) return 'CC0';
  if (upper.includes('PUBLIC DOMAIN')) return 'Public Domain';
  if (upper.includes('BY-SA')) return 'CC BY-SA';
  if (upper.includes('CC BY') || upper.includes('/BY/')) return 'CC BY';
  return textOnly(label) || 'Unknown';
}

export function parseCommonsFilePage(html, sourcePageUrl) {
  const mediaBlock = capture(
    html,
    /<div\b[^>]*class=["'][^"']*fullMedia[^"']*["'][^>]*>([\s\S]*?)<\/div>/i,
    'original image block',
  )[1];
  const media = capture(
    mediaBlock,
    /<a\b[^>]*href=["']([^"']+)["']/i,
    'original image URL',
  );
  const author = capture(
    html,
    /id=["']fileinfotpl_aut["'][^>]*>[\s\S]*?<\/td>\s*<td[^>]*>([\s\S]*?)<\/td>/i,
    'author',
  );
  const licenseTemplateUrls = [...html.matchAll(/<span\b[^>]*class=["'][^"']*licensetpl_link[^"']*["'][^>]*>([\s\S]*?)<\/span>/gi)]
    .map(match => textOnly(match[1]))
    .filter(value => /^https?:\/\//i.test(value));
  const licenseTemplateLabels = [...html.matchAll(/<span\b[^>]*class=["'][^"']*licensetpl_short[^"']*["'][^>]*>([\s\S]*?)<\/span>/gi)]
    .map(match => textOnly(match[1]))
    .filter(value => value && !/^(?:true|false)$/i.test(value));
  const licenseAnchor = /<a\b[^>]*rel=["'][^"']*license[^"']*["'][^>]*href=["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/i.exec(html);
  if ((!licenseTemplateUrls.length || !licenseTemplateLabels.length) && !licenseAnchor) {
    throw new SourceBlockedError('source_parse_failed', 'Missing license');
  }
  const image = capture(
    html,
    /<img\b[^>]*class=["'][^"']*mw-file-element[^"']*["'][^>]*>/i,
    'image metadata',
  )[0];
  const fullDimensions = /([\d,]+)\s*[×x]\s*([\d,]+)\s*pixels/i.exec(textOnly(mediaBlock));
  const width = fullDimensions ? Number(fullDimensions[1].replace(/,/g, '')) : Number(capture(image, /\bwidth=["']?(\d+)/i, 'width')[1]);
  const height = fullDimensions ? Number(fullDimensions[2].replace(/,/g, '')) : Number(capture(image, /\bheight=["']?(\d+)/i, 'height')[1]);
  const licenseUrl = absoluteCommonsUrl(licenseTemplateUrls[0] || licenseAnchor[1]);
  const licenseLabel = licenseTemplateLabels[0] || textOnly(licenseAnchor[2]);
  return {
    sourceAdapter: 'wikimedia-commons-html',
    sourcePageUrl,
    imageUrl: absoluteCommonsUrl(media[1]),
    author: textOnly(author[1]),
    license: normalizeLicense(licenseLabel, licenseUrl),
    licenseUrl,
    width,
    height,
    photographicEvidence: 'Commons file page with raster image dimensions',
    photographic: false,
    riskLabels: [],
  };
}

export function classifyPageBlock(status, html) {
  if (status === 429) return 'source_rate_limited';
  if (status === 403) return 'source_forbidden';
  if (/class=["'][^"']*(?:g-recaptcha|h-captcha)[^"']*["']|id=["'][^"']*captcha[^"']*["']|<input\b[^>]*(?:name|id)=["'][^"']*captcha/i.test(html)) return 'source_captcha';
  if (/type=["']password["']|欢迎来到\s*Pinterest|log\s*in\s*to\s*continue/i.test(html)) return 'source_login_wall';
  return null;
}

async function atomicJson(file, value) {
  await mkdir(dirname(file), { recursive: true });
  const temporary = `${file}.tmp-${process.pid}`;
  await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
  await rename(temporary, file);
}

async function gotoWithBackoff(page, url, { maxRetries, delayMs }) {
  for (let attempt = 0; attempt <= maxRetries; attempt += 1) {
    const response = await page.goto(url, { waitUntil: 'domcontentloaded' });
    const html = await page.content();
    const blocked = classifyPageBlock(response?.status() ?? 0, html);
    if (!blocked) return html;
    if (blocked !== 'source_rate_limited' || attempt === maxRetries) {
      throw new SourceBlockedError(blocked, `Source navigation stopped: ${blocked}`);
    }
    await new Promise(resolve => setTimeout(resolve, delayMs * (2 ** attempt)));
  }
  throw new SourceBlockedError('source_failed', 'Navigation retry budget exhausted');
}

export async function crawlCommons({
  category,
  limit = 20,
  checkpointFile,
  delayMs = 1500,
  maxPages = 3,
  maxRetries = 3,
  chromium,
  executablePath,
}) {
  requireEnabledSource('commons');
  if (!SOURCE_POLICIES.commons.categories.includes(category)) {
    throw new SourceBlockedError('source_category_blocked', `Commons category is not allowlisted: ${category}`);
  }
  if (!chromium) {
    let runtime;
    try {
      runtime = await import(process.env.STYLE_PLAYWRIGHT_MODULE || 'playwright-core');
    } catch (error) {
      throw new SourceBlockedError('playwright_unavailable', `Install playwright-core or set STYLE_PLAYWRIGHT_MODULE: ${error.message}`);
    }
    chromium = runtime.chromium;
  }
  const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
  const page = await browser.newPage();
  let checkpoint = {
    artifactType: 'style_source_metadata_checkpoint',
    schemaVersion: '2.0.0',
    producer: 'style-template-analyzer',
    source: 'commons',
    category,
    visited: [],
    records: [],
    nextPageUrl: null,
    status: 'running',
  };
  if (checkpointFile) {
    try {
      const saved = JSON.parse(await readFile(checkpointFile, 'utf8'));
      if (saved.source === 'commons' && saved.category === category) checkpoint = { ...checkpoint, ...saved, status: 'running' };
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
  }
  const records = checkpoint.records;
  try {
    const visited = new Set(checkpoint.visited);
    let categoryUrl = checkpoint.nextPageUrl || `https://commons.wikimedia.org/wiki/Category:${category}`;
    for (let pageIndex = 0; pageIndex < maxPages && records.length < limit && categoryUrl; pageIndex += 1) {
      const html = await gotoWithBackoff(page, categoryUrl, { maxRetries, delayMs });
      const urls = parseCommonsCategoryPage(html).filter(url => !visited.has(url));
      const nextPageUrl = parseCommonsNextCategoryPage(html, category);
      for (const url of urls.slice(0, limit - records.length)) {
        const detailHtml = await gotoWithBackoff(page, url, { maxRetries, delayMs });
        records.push(parseCommonsFilePage(detailHtml, url));
        checkpoint.visited.push(url);
        visited.add(url);
        if (checkpointFile) await atomicJson(checkpointFile, checkpoint);
        if (delayMs > 0) await new Promise(resolve => setTimeout(resolve, delayMs));
      }
      categoryUrl = nextPageUrl;
      checkpoint.nextPageUrl = nextPageUrl;
      if (checkpointFile) await atomicJson(checkpointFile, checkpoint);
    }
    checkpoint.status = 'completed';
    delete checkpoint.error;
    return checkpoint;
  } catch (error) {
    checkpoint.status = error.code || 'source_failed';
    checkpoint.error = error.message;
    throw error;
  } finally {
    if (checkpointFile) await atomicJson(checkpointFile, checkpoint);
    await browser.close();
  }
}

async function main() {
  const args = process.argv.slice(2);
  const get = name => {
    const index = args.indexOf(name);
    return index >= 0 ? args[index + 1] : undefined;
  };
  const source = get('--source') || 'commons';
  requireEnabledSource(source);
  const result = await crawlCommons({
    category: get('--category') || 'Product_photography',
    limit: Number(get('--limit') || 20),
    maxPages: Number(get('--pages') || 3),
    checkpointFile: get('--checkpoint'),
    executablePath: get('--chrome'),
  });
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(error => {
    process.stderr.write(`${error.code || 'source_failed'}: ${error.message}\n`);
    process.exitCode = 1;
  });
}
