import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdir } from 'node:fs/promises';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost' });
for (const name of ['window', 'document', 'HTMLElement', 'Element', 'Node', 'MutationObserver']) globalThis[name] = dom.window[name];
Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
await mkdir('.test-tmp-fire-panel', { recursive: true });
await build({ entryPoints: ['src/components/EventPanel.tsx'], outfile: '.test-tmp-fire-panel/panel.mjs', bundle: true, format: 'esm', platform: 'node', packages: 'external', jsx: 'automatic', plugins: [{ name: 'boundaries', setup(b) {
  b.onResolve({ filter: /^react-plotly.js$/ }, () => ({ path: 'plot', namespace: 'stub' }));
  b.onResolve({ filter: /api\/client$/ }, () => ({ path: 'api', namespace: 'stub' }));
  b.onLoad({ filter: /.*/, namespace: 'stub' }, ({ path }) => ({ contents: path === 'plot' ? 'export default function Plot(){return null;}' : 'export const normalizeApiError=e=>e.message; export const startEvidence=async()=>{if(globalThis.fireEvidenceFixture)return globalThis.fireEvidenceFixture;throw new Error("Evidence offline")}; export const startOutlook=async()=>null; export const runJob=async p=>await p;' }));
} }] });
const React = await import('react');
const { render, screen, fireEvent, cleanup } = await import('@testing-library/react');
const { default: Panel } = await import('../.test-tmp-fire-panel/panel.mjs');
const point = { sensor: 'modis', satellite: 'Aqua', lat: 14.41810, lon: -12.58401, acq_datetime: '2026-11-09T15:58:00Z', frp: 123.2, confidence_pct: 85, daynight: 'D' };
const props = { event: null, detection: point, onClose() {}, onForecast() {}, onExposure() {}, onCaseUpdate() {} };

test('one card retains actual observation metadata, changes tabs and resets for another selection', () => {
  let closed = false;
  const view = render(React.createElement(Panel, { ...props, onClose() { closed = true; } }));
  try {
    assert.equal(screen.getAllByRole('complementary').length, 1);
    assert.equal(screen.getByRole('tab', { name: 'Summary' }).getAttribute('aria-selected'), 'true');
    fireEvent.click(screen.getByRole('tab', { name: 'Sighting' }));
    assert.ok(screen.getByText('2026-11-09 15:58:00 UTC'));
    assert.ok(screen.getByText('14.41810°, -12.58401°'));
    assert.ok(screen.getByText('123.2 MW'));
    assert.ok(screen.getByText('85%'));
    assert.ok(screen.getByText('Day'));
    assert.equal(document.querySelectorAll('.observation-popup').length, 0);
    view.rerender(React.createElement(Panel, { ...props, detection: { ...point, satellite: 'Terra', frp: 42 } }));
    assert.equal(screen.getByRole('tab', { name: 'Summary' }).getAttribute('aria-selected'), 'true');
    fireEvent.click(screen.getByRole('tab', { name: 'Sighting' }));
    assert.ok(screen.getByText('42 MW'));
    view.rerender(React.createElement(Panel, { ...props, onClose() { closed = true; } }));
    fireEvent.click(screen.getByRole('button', { name: 'Close event details' }));
    assert.equal(closed, true);
  } finally { cleanup(); }
});

test('event analysis and every contributing observation share the same card', async () => {
  const event = { event_id: 'fixture', detections: [point, { ...point, satellite: 'Terra', frp: 50 }], behaviour: { state: 'Unknown' }, observation_count: 2, sensors: ['modis'], max_frp: 123.2 };
  const view = render(React.createElement(Panel, props));
  try {
    fireEvent.click(screen.getByRole('tab', { name: 'Sighting' }));
    view.rerender(React.createElement(Panel, { ...props, event }));
    assert.equal(screen.getByRole('tab', { name: 'Sighting' }).getAttribute('aria-selected'), 'true');
    fireEvent.click(screen.getByRole('tab', { name: 'Summary' }));
    await screen.findAllByText(/Evidence offline/);
    fireEvent.click(screen.getByRole('tab', { name: 'Sighting' }));
    assert.ok(screen.getByText('All event observations (2)'));
    assert.ok(screen.getByText('50 MW'));
    assert.equal(screen.getAllByRole('complementary').length, 1);
    assert.equal(screen.getAllByRole('button', { name: 'Close event details' }).length, 1);
    for (const name of ['Summary', 'Sighting', 'Fire story', 'Reliability', 'Sources', 'Past fires', 'Forecast', 'Nearby']) assert.ok(screen.getByRole('tab', { name }));
  } finally { cleanup(); }
});

test('source-backed summary never turns missing data into percentages or extinction', async () => {
  const fireCase = {
    data_policy: 'source-backed-v2', checked_at: point.acq_datetime,
    opened_at: point.acq_datetime, closes_at: '2026-11-10T15:58:00Z', status: 'closed', provisional: true,
    pending_witnesses: [], answer: {
      is_real: { label: 'No external confirmation yet', basis: 'Satellite heat is recorded; external checks are incomplete.' },
      kind: { category: 'unknown', label: 'Unknown (not verified)', decided: false, basis: 'No linked official report establishes a fire type.' },
      now: { label: 'Unknown', basis: 'Extinction is not established.' },
    },
    category_scores: [], decision_rules: { top: 'unknown', passed: false },
    passes: [], next_passes: [], streams: { A: { status: 'done', passes_observed: 1, passes_expected: 0 }, B: { status: 'unavailable' }, C: { status: 'partial', reports: 0 } },
    geostationary: { status: 'unavailable', detail: 'Source unavailable', review_links: [] },
    evidence_block: [], satellite_fire_probability: { probability: null, prior: null, method: 'Unvalidated probability withheld.' },
    burning_season: { status: 'not_used' }, overpass_method: 'unavailable', overpass_errors: [], situations: {},
    score_note: 'Unvalidated category weights withheld.', marker: { state: 'Unknown', kind: 'unknown', provisional: true },
  };
  globalThis.fireEvidenceFixture = { fire_case: fireCase, inference: { final_status: 'No external confirmation yet' }, generated_at: point.acq_datetime };
  const event = { event_id: 'source-fixture', detections: [point], behaviour: { state: 'Unknown' }, observation_count: 1 };
  render(React.createElement(Panel, { ...props, event }));
  try {
    await screen.findAllByText('Satellite heat is recorded; external checks are incomplete.');
    assert.ok(screen.getByText('verification incomplete'));
    assert.ok(screen.getByText('Extinction is not established.'));
    assert.equal(screen.queryByText(/Final answer by/), null);
    assert.equal(screen.queryByText(/It appears to have stopped/), null);
    assert.equal(screen.queryByText(/39%/), null);
    assert.equal(screen.queryByText('no report found'), null);
  } finally { cleanup(); delete globalThis.fireEvidenceFixture; }
});
