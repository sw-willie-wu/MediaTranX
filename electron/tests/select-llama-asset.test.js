const test = require('node:test');
const assert = require('node:assert');
const { selectLlamaAsset } = require('../setup.js');

const ASSETS = [
  'llama-b8763-bin-win-cuda-13.1-x64.zip',
  'llama-b8763-bin-win-cuda-12.4-x64.zip',
  'llama-b8763-bin-win-vulkan-x64.zip',
  'llama-b8763-bin-win-cpu-x64.zip',
];

test('old NVIDIA (cc 5.0) with new driver avoids cuda-13', () => {
  const got = selectLlamaAsset(
    { type: 'nvidia', driverVersion: 570, computeCap: 5.0 }, ASSETS);
  assert.ok(got.includes('cuda-12.4'), `got ${got}`);
  assert.ok(!got.includes('cuda-13'), `got ${got}`);
});

test('modern NVIDIA (cc 8.6) keeps driver-based choice', () => {
  const got = selectLlamaAsset(
    { type: 'nvidia', driverVersion: 570, computeCap: 8.6 }, ASSETS);
  assert.ok(got.includes('cuda-13'), `got ${got}`);
});

test('unknown computeCap keeps driver-based choice', () => {
  const got = selectLlamaAsset(
    { type: 'nvidia', driverVersion: 570, computeCap: null }, ASSETS);
  assert.ok(got.includes('cuda-13'), `got ${got}`);
});

test('Turing (cc 7.5) stays on cuda-13', () => {
  const got = selectLlamaAsset(
    { type: 'nvidia', driverVersion: 570, computeCap: 7.5 }, ASSETS);
  assert.ok(got.includes('cuda-13'), `got ${got}`);
});
