import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdir } from 'node:fs/promises';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';
const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost/data-sources' });
for (const name of ['window', 'document', 'HTMLElement', 'Element', 'Node', 'MutationObserver']) globalThis[name] = dom.window[name];
Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
await mkdir('.test-tmp-sources', { recursive: true });
await build({ entryPoints: ['src/pages/DataSourcesPage.tsx'], outfile: '.test-tmp-sources/page.mjs', bundle: true, format: 'esm', platform: 'node', packages: 'external', jsx: 'automatic', plugins: [{ name: 'fixtures', setup(b) {
  b.onResolve({ filter: /api\/client$|components\/VerificationPanel$/ }, ({ path }) => ({ path, namespace: 'fixture' }));
  b.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path }) => ({ contents: path.includes('VerificationPanel') ? 'export default function Panel(){return null;}' : 'export const normalizeApiError=e=>e.message; export const getDataSources=()=>globalThis.loadSources();' }));
} }] });
const React = await import('react');
const { render, screen, fireEvent, cleanup } = await import('@testing-library/react');
const { default: Page } = await import('../.test-tmp-sources/page.mjs');
test('source loading failure is visible and Retry restores provider links', async () => {
  let calls = 0;
  globalThis.loadSources = async () => {
    if (++calls === 1) throw new Error('Backend unavailable');
    return [{ group: 'Satellites', name: 'NASA FIRMS', description: 'Satellite observations', access: 'Automated', url: 'https://firms.modaps.eosdis.nasa.gov/' }];
  };
  render(React.createElement(Page));
  try {
    assert.match((await screen.findByRole('alert')).textContent, /Backend unavailable/);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await screen.findByRole('heading', { name: 'NASA FIRMS' });
    assert.equal(screen.getByRole('link', { name: /Visit/ }).href, 'https://firms.modaps.eosdis.nasa.gov/');
    assert.equal(screen.queryByRole('alert'), null);
    assert.equal(calls, 2);
  } finally { cleanup(); }
});
test('an empty source directory has an explicit empty state', async () => {
  globalThis.loadSources = async () => [];
  render(React.createElement(Page));
  try { await screen.findByText('No data sources were returned.'); }
  finally { cleanup(); }
});
