// electron/tests/crash-recovery.test.js — pure logic, no electron imports
const { test } = require('node:test');
const assert = require('node:assert');
const { isCrashReason, ReloadLoopGuard } = require('../lib/crash-recovery');

test('isCrashReason: clean-exit is not a crash', () => {
  assert.equal(isCrashReason('clean-exit'), false);
});
test('isCrashReason: any other reason is a crash', () => {
  for (const r of ['crashed', 'oom', 'killed', 'abnormal-exit', 'launch-failed', 'integrity-failure', 'memory-eviction', 'something-new']) {
    assert.equal(isCrashReason(r), true, `${r} should be a crash`);
  }
});
test('isCrashReason: missing reason is treated as a crash', () => {
  assert.equal(isCrashReason(undefined), true);
  assert.equal(isCrashReason(null), true);
  assert.equal(isCrashReason(''), true);
});

test('ReloadLoopGuard: allows up to max reloads in window, then error-ui', () => {
  const g = new ReloadLoopGuard(3, 30000);
  assert.equal(g.onCrash(1000), 'reload');   // 1
  assert.equal(g.onCrash(2000), 'reload');   // 2
  assert.equal(g.onCrash(3000), 'reload');   // 3
  assert.equal(g.onCrash(4000), 'error-ui'); // 4th within 30s window
});
test('ReloadLoopGuard: prunes timestamps older than window', () => {
  const g = new ReloadLoopGuard(3, 30000);
  g.onCrash(1000); g.onCrash(2000); g.onCrash(3000);
  assert.equal(g.onCrash(43000), 'reload');  // 40s later → first three pruned
});
test('ReloadLoopGuard: reset() clears history', () => {
  const g = new ReloadLoopGuard(3, 30000);
  g.onCrash(1000); g.onCrash(2000); g.onCrash(3000);
  g.reset();
  assert.equal(g.onCrash(3500), 'reload');
});
test('ReloadLoopGuard: stamp exactly windowMs old is pruned (half-open window)', () => {
  const g = new ReloadLoopGuard(1, 30000);
  assert.equal(g.onCrash(0), 'reload');       // stamps=[0]
  // now - t === windowMs → 30000 - 0 === 30000 → NOT < 30000 → pruned → allowed
  assert.equal(g.onCrash(30000), 'reload');
});
test('ReloadLoopGuard: never throws on NaN/undefined now (self-corrects)', () => {
  const g = new ReloadLoopGuard(3, 30000);
  assert.doesNotThrow(() => g.onCrash(NaN));
  assert.doesNotThrow(() => g.onCrash(undefined));
  // a valid call afterward still behaves
  assert.equal(g.onCrash(1000), 'reload');
});
