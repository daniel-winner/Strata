/** The Monitor's Today card: per-day request, token, speed and concurrency counters kept in the store file. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

process.env.STRATA_HOME = mkdtempSync(join(tmpdir(), 'strata-daily-'));
const monitor = await import('../server/monitor.mjs');
const { get: getStore } = await import('../server/store.mjs');

test("a recorded request lands in today's totals", () => {
  monitor.record({ tokensIn: 100, tokensOut: 40, durationMs: 1000, tps: 40, cachedTokens: 25 });
  monitor.record({ tokensIn: 50, tokensOut: 10, durationMs: 500, tps: 20 });
  const daily = monitor.snapshot().daily;
  assert.equal(daily.requests, 2);
  assert.equal(daily.tokensIn, 150);
  assert.equal(daily.tokensOut, 50);
  assert.equal(daily.cachedTokens, 25);
  assert.equal(daily.usageRequests, 2);
  assert.equal(daily.avgTps, 30);
  assert.equal(daily.date, new Date().toLocaleDateString('en-CA'));
});

test("today's counters are saved, so a host restart keeps them", () => {
  assert.equal(getStore().usage.date, monitor.snapshot().daily.date);
  assert.equal(getStore().usage.requests, 2);
  assert.equal(getStore().usage.tokensOut, 50);
});

test('the peak concurrency of the day is kept, and a quieter minute does not lower it', () => {
  monitor.noteConcurrency(3, 1);
  assert.equal(monitor.snapshot().daily.peakRunning, 3);
  assert.equal(monitor.snapshot().daily.peakWaiting, 1);
  monitor.noteConcurrency(1, 0);
  assert.equal(monitor.snapshot().daily.peakRunning, 3);
  assert.equal(monitor.snapshot().daily.peakWaiting, 1);
});

test('a request with no usage is counted, and adds no tokens', () => {
  monitor.record({ tokensIn: null, tokensOut: null, durationMs: 300 });
  const daily = monitor.snapshot().daily;
  assert.equal(daily.requests, 3);
  assert.equal(daily.tokensIn, 150);
  assert.equal(daily.usageRequests, 2);
});
