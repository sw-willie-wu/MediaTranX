// 資料夾遞迴列舉 — 上限語意鏡射 frontend/src/utils/dropEntries.ts 的 expandDropItems:
// dir guard depth >= 8(最深可收檔 = depth 7 目錄的直屬檔 = 等效深度 8)、
// cap 500 → truncated、深度濾除不設 truncated、symlink(目錄/檔案)不跟不收、
// 讀取失敗的目錄靜默略過(對齊 drop 路徑 readEntries error → 空批)。
// 獨立成 module 讓 node smoke 可 require 真實實作驗證。
const fs = require('fs');
const { join } = require('path');

const MAX_DEPTH = 8;
const MAX_FILES = 500;

function walkFolderFiles(root) {
  const paths = [];
  let truncated = false;
  const walk = (dir, depth) => {
    if (depth >= MAX_DEPTH) return;
    let entries;
    try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
    for (const ent of entries) {
      if (paths.length >= MAX_FILES) { truncated = true; return; }
      const full = join(dir, ent.name);
      if (ent.isFile()) paths.push(full);
      else if (ent.isDirectory()) walk(full, depth + 1);
    }
  };
  walk(root, 0);
  return { paths, truncated };
}

module.exports = { walkFolderFiles };
