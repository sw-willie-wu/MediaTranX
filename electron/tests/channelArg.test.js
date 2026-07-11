// 管路契約：--update-channel 的 arg 名必須同時存在於 main.js（注入端）與
// preload.cjs（解析端）。此 argv 路徑只有 featureGate 消費、與更新分流的
// IPC 遞送互相獨立——斷掉不會壞更新、CI 冒煙看不到，靠本測試鎖住兩端。
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

test('channel arg contract: --update-channel= appears in both main.js and preload.cjs', () => {
  const mainSrc = fs.readFileSync(path.join(__dirname, '..', 'main.js'), 'utf8');
  const preloadSrc = fs.readFileSync(path.join(__dirname, '..', 'preload.cjs'), 'utf8');
  assert.ok(mainSrc.includes('--update-channel='), 'main.js must inject --update-channel=');
  assert.ok(preloadSrc.includes('--update-channel='), 'preload.cjs must parse --update-channel=');
});
