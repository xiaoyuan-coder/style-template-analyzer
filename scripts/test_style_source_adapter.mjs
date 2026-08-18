import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import {
  SOURCE_POLICIES,
  SourceBlockedError,
  classifyPageBlock,
  crawlCommons,
  parseCommonsCategoryPage,
  parseCommonsFilePage,
  parseCommonsNextCategoryPage,
  parseCommonsSearchPage,
  requireEnabledSource,
} from './style_source_adapter.mjs';

const fixtures = new URL('./fixtures/', import.meta.url);

test('Commons category fixture yields stable file-page URLs', async () => {
  const html = await readFile(new URL('commons-search.html', fixtures), 'utf8');
  assert.deepEqual(parseCommonsCategoryPage(html), [
    'https://commons.wikimedia.org/wiki/File:Red_apple_on_table.jpg',
    'https://commons.wikimedia.org/wiki/File:Blue_cup_in_room.jpg',
  ]);
});

test('Commons file fixture yields attribution and image evidence', async () => {
  const html = await readFile(new URL('commons-file.html', fixtures), 'utf8');
  const record = parseCommonsFilePage(html, 'https://commons.wikimedia.org/wiki/File:Red_apple_on_table.jpg');
  assert.equal(record.author, 'Example Photographer');
  assert.equal(record.license, 'CC0');
  assert.equal(record.width, 1200);
  assert.equal(record.imageUrl, 'https://upload.wikimedia.org/example/Red_apple.jpg');
});

test('Pinterest is policy blocked before browser work starts', () => {
  assert.equal(SOURCE_POLICIES.pinterest.status, 'policy-blocked');
  assert.throws(() => requireEnabledSource('pinterest'), error => (
    error instanceof SourceBlockedError && error.code === 'source_policy_blocked'
  ));
});

test('login walls and rate limits are machine readable', () => {
  assert.equal(classifyPageBlock(429, '<html></html>'), 'source_rate_limited');
  assert.equal(classifyPageBlock(200, '<input type="password">欢迎来到 Pinterest'), 'source_login_wall');
  assert.equal(classifyPageBlock(200, '<html>ordinary page</html>'), null);
});

test('checkpoint resume skips fully visited pages and advances to later offsets', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'style-source-resume-'));
  const checkpointFile = join(directory, 'checkpoint.json');
  const firstPage = await readFile(new URL('commons-search.html', fixtures), 'utf8');
  const detailPage = await readFile(new URL('commons-file.html', fixtures), 'utf8');
  const visited = parseCommonsSearchPage(firstPage);
  await writeFile(checkpointFile, JSON.stringify({
    artifactType: 'style_source_metadata_checkpoint',
    schemaVersion: '2.0.0',
    producer: 'style-template-analyzer',
    source: 'commons',
    category: 'Product_photography',
    visited,
    records: [{ sourcePageUrl: visited[0] }],
    nextPageUrl: 'https://commons.wikimedia.org/wiki/Category:Product_photography?pagefrom=Later',
    status: 'completed',
  }), 'utf8');

  let currentUrl = '';
  const page = {
    async goto(url) {
      currentUrl = url;
      return { status: () => 200 };
    },
    async content() {
      if (currentUrl.includes('pagefrom=Later')) return '<a href="/wiki/File:Later_photo.jpg">later</a>';
      if (currentUrl.includes('/wiki/File:')) return detailPage;
      return firstPage;
    },
  };
  const chromium = {
    async launch() {
      return { newPage: async () => page, close: async () => {} };
    },
  };

  try {
    const result = await crawlCommons({
      category: 'Product_photography', limit: 2, maxPages: 2, delayMs: 0, checkpointFile, chromium,
    });
    assert.equal(result.records.length, 2);
    assert.ok(result.visited.some(url => url.endsWith('File:Later_photo.jpg')));
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test('Commons crawler rejects free-form or non-allowlisted categories before browser work', async () => {
  await assert.rejects(
    crawlCommons({ category: 'Special:MediaSearch', chromium: {} }),
    error => error instanceof SourceBlockedError && error.code === 'source_category_blocked',
  );
});

test('next category page is rewritten onto the allowed wiki category path', () => {
  const html = '<a href="/w/index.php?title=Category:Product_photography&pagefrom=Later">next page</a>';
  assert.equal(
    parseCommonsNextCategoryPage(html, 'Product_photography'),
    'https://commons.wikimedia.org/wiki/Category:Product_photography?pagefrom=Later',
  );
});
