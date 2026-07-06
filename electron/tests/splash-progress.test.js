// electron/tests/splash-progress.test.js
const { test } = require('node:test');
const assert = require('node:assert');
const { creepPercent, formatElapsedSeconds, isLongWait } = require('../lib/splash-progress');

test('creepPercent: at t=0 equals start', () => {
  assert.equal(creepPercent(0, 90, 99, 12000), 90);
});
test('creepPercent: monotonic non-decreasing and bounded below ceiling', () => {
  let prev = -1;
  for (let t = 0; t <= 120000; t += 1000) {
    const p = creepPercent(t, 90, 99, 12000);
    assert.ok(p >= prev, `not monotonic at ${t}: ${p} < ${prev}`);
    assert.ok(p < 99, `must stay below ceiling at ${t}: ${p}`);
    prev = p;
  }
});
test('creepPercent: approaches but never reaches ceiling for large t', () => {
  const p = creepPercent(10 * 60 * 1000, 90, 99, 12000); // 10 min
  assert.ok(p > 98 && p < 99, `expected (98,99), got ${p}`);
});
test('formatElapsedSeconds: floors ms to integer seconds', () => {
  assert.equal(formatElapsedSeconds(0), 0);
  assert.equal(formatElapsedSeconds(1999), 1);
  assert.equal(formatElapsedSeconds(8000), 8);
});
test('isLongWait: true only at/after threshold', () => {
  assert.equal(isLongWait(7999, 8000), false);
  assert.equal(isLongWait(8000, 8000), true);
});
