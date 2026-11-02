/** The Monitor's Today card: per-day request, token, speed and concurrency counters kept in the store file, and read back when the host starts. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const TODAY = new Date().toLocaleDateString('en-CA');
const home = mkdtempSync(join(tmpdir(), 'strata-daily-'));
mkdirSync(join(home, 'data'), { recursive: true });
writeFileSync(join(home, 'data', 'state.json'), JSON.stringify({
  version: 1,
  usage: { date: TODAY, tokensIn: 100, tokensOut: 40, requests: 1, usageRequests: 1, avgTps: 40, cachedTokens: 25, peakRunning: 3, peakWaiting: 1 },
}));
process.env.STRATA_HOME = home;
const monitor = await import('../server/monitor.mjs');
const { get: getStore } = await import('../server/store.mjs');

test('the host starts with the day it already counted: the saved counters come back', () => {
  monitor.init({ send: () => {} }, { memory: { totalGb: 16, usedGb: 8 }, accelerator: { usableVramGb: 8, unified: false }, gpus: [] });
  const daily = monitor.snapshot().daily;
  assert.equal(daily.date, TODAY);
  assert.equal(daily.requests, 1);
  assert.equal(daily.tokensIn, 100);
  assert.equal(daily.avgTps, 40);
  assert.equal(daily.peakRunning, 3);
});

test("a recorded request lands in today's totals", () => {
  monitor.record({ tokensIn: 100, tokensOut: 40, durationMs: 1000, tps: 40, cachedTokens: 25 });
  monitor.record({ tokensIn: 50, tokensOut: 10, durationMs: 500, tps: 20 });
  const daily = monitor.snapshot().daily;
  assert.equal(daily.requests, 3);
  assert.equal(daily.tokensIn, 250);
  assert.equal(daily.tokensOut, 90);
  assert.equal(daily.cachedTokens, 50);
  assert.equal(daily.usageRequests, 3);
  assert.equal(daily.avgTps, Number(((40 + 40 + 20) / 3).toFixed(1)));
  assert.equal(daily.date, TODAY);
});

test("today's counters are saved, so a host restart keeps them", () => {
  assert.equal(getStore().usage.date, TODAY);
  assert.equal(getStore().usage.requests, 3);
  assert.equal(getStore().usage.tokensOut, 90);
});

test('the peak concurrency of the day is kept, and a quieter minute does not lower it', () => {
  monitor.noteConcurrency(5, 2);
  assert.equal(monitor.snapshot().daily.peakRunning, 5);
  assert.equal(monitor.snapshot().daily.peakWaiting, 2);
  monitor.noteConcurrency(1, 0);
  assert.equal(monitor.snapshot().daily.peakRunning, 5);
  assert.equal(monitor.snapshot().daily.peakWaiting, 2);
});

test('a request with no usage is counted, and adds no tokens', () => {
  monitor.record({ tokensIn: null, tokensOut: null, durationMs: 300 });
  const daily = monitor.snapshot().daily;
  assert.equal(daily.requests, 4);
  assert.equal(daily.tokensIn, 250);
  assert.equal(daily.usageRequests, 3);
});
