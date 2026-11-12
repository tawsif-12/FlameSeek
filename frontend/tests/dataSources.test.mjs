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
await build({
  entryPoints: ['src/pages/DataSourcesPage.tsx'],
  outfile: '.test-tmp-sources/page.mjs',
  bundle: true,
  format: 'esm',
  platform: 'node',
  packages: 'external',
  jsx: 'automatic',
});

const React = await import('react');
const { render, screen, cleanup } = await import('@testing-library/react');
const { default: Page } = await import('../.test-tmp-sources/page.mjs');

test('renders every verified project source with required metadata', () => {
  render(React.createElement(Page));
  try {
    assert.equal(screen.getByRole('heading', { name: 'Data Sources', level: 1 }).textContent, 'Data Sources');
    assert.equal(screen.getAllByText('Data type').length, 21);
    assert.equal(screen.getAllByText('Source').length, 21);
    assert.equal(screen.getAllByRole('link', { name: /Visit the official source for/ }).length, 21);
    assert.equal(screen.queryByText(/team members/i), null);
    assert.equal(screen.queryByRole('heading', { name: /About FlameSeek/i }), null);
  } finally {
    cleanup();
  }
});

test('official dataset links open their source websites directly', () => {
  render(React.createElement(Page));
  try {
    const links = screen.getAllByRole('link', { name: /Visit the official source for/ });
    for (const link of links) {
      assert.match(link.href, /^https:\/\//);
      assert.equal(link.target, '_blank');
      assert.match(link.rel, /noreferrer/);
    }
  } finally {
    cleanup();
  }
});
