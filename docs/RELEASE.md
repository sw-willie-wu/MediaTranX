# Release Flow

正式發版分兩段：**本機 `scripts/release.py` 做 git 編排**（merge/bump/tag/push），tag push 後 **GitHub Actions 完成 build → 簽名 → 發 release**（`.github/workflows/release.yml`）。
（2026-04 取代舊 8 個 `.bat`；2026-06 monorepo 化簡為 6 步；2026-07 build/簽名/release 上 CI。）

## 快速指令

於專案根目錄（`MediaTranX/`）執行：

```bash
# 正式發版（直接給版本）
python scripts/release.py v1.6.0

# 自動從最新 tag 遞增
python scripts/release.py --bump patch          # v1.6.0 -> v1.6.1
python scripts/release.py --bump minor          # v1.6.0 -> v1.7.0
```

- `release.py` 只用標準庫，**一般 `python` 跑即可**。
- 版本格式必須 `vX.Y.Z`。
- self-copy trick 保留：`git checkout main` 會動 `scripts/`，所以先複製自己到 temp 再執行。

## 前置條件

- repo 在 `dev` branch、working tree 乾淨（連 untracked 都擋）。
- 目標版本 tag 尚未存在。
- **`CHANGELOG.md` 已有 `## [X.Y.Z]` 段落**（非空、日期不能是 placeholder）——release notes 由 CI 從這裡抽取，preflight 會擋。

## 本機流程（release.py，5 步）

```
Step 0: Pre-flight ── branch / clean tree / tag 不存在 / CHANGELOG 段落
Step 1: merge dev → main（--no-ff）
Step 2: bump 版號（pyproject + uv.lock + 兩個 package.json）+ 一次 commit
Step 3: tag vX.Y.Z
Step 4: push main + tag ──→ 觸發 CI
Step 5: sync main 回 dev
```

> Step 5 **不會** push dev——發版只推 main + tag，dev 是否推自行決定。

## CI 流程（tag push 觸發）

runner（windows-latest）上：checkout → `uv sync --frozen`（嚴格照 committed `uv.lock`，不重 resolve）→ `build.py --mode prod --version X.Y.Z --no-lock`（vite + Nuitka + electron-builder）→ SignPath 簽名（secrets 未設定時跳過、出未簽名版）→ 抽 `CHANGELOG.md` 該版段落當 notes → 建 release 掛 installer。

- **冷 build 實測約 15 分**（2026-07 實測 13–14 分；cache 對正式 release 無效：GitHub cache 按 ref 隔離 + 7 天清除，每次正式版都當冷 build 估）。若未來變慢可改 `runs-on` 為 8-core larger runner。
- **build 失敗不會出 release，但 tag 已存在**（與舊流程「build 失敗不建 tag」相反）。修好後直接 re-run workflow 即可（release step 是 create-or-upload，可安全 re-run）；需要改 code 就 bump patch 出新版。
- 簽名 secrets：`SIGNPATH_API_TOKEN`（secret）+ `SIGNPATH_ORGANIZATION_ID` / `SIGNPATH_PROJECT_SLUG` / `SIGNPATH_POLICY_SLUG`（vars）。

## CHANGELOG 規則

- repo root `CHANGELOG.md`，UTF-8 **無 BOM**，繁體中文，Keep a Changelog 風格。
- 段落 anchor＝行首 `## [X.Y.Z]`（後面可帶 ` - 日期`）；段落到下一個 `## [` 或檔尾。
- preflight 與 CI 用同一支 `scripts/extract_changelog.py`，規則保證一致。

## 測試 Build（不發版）

```
uv run --project backend python scripts/build.py --mode dev
```

- `--mode dev` → 版號 `X.Y.Z-dev.N`（N 自動遞增），build 完自動還原版號；不 commit、不 tag、不 push。
- dev 預發版（GitHub prerelease）流程不變：本機 build + push tag + `gh release --prerelease`（見 `/release-dev`）。

## 注意事項

- **build.py 必須 `uv run --project backend`**——nuitka 步驟用「行程所在環境的已安裝套件」算排除清單。
- **CI 用 `--no-lock`**——跳過 `uv lock`、Nuitka 的 `uv run` 帶 `--frozen`；出貨的 `uv.lock` 必須等於驗證過的 committed lock（簽名蓋在驗證過的依賴組合上）。
- 本機 build 前先關閉 dev 環境（electron / node / python / llama-server）避免檔案鎖。
