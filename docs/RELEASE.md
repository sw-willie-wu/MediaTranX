# Release Flow

發版由 `scripts/release.py` 全自動化(2026-04 取代舊的 8 個 `.bat`;2026-06 合併為 monorepo 後從雙 repo 8 步簡化為單 repo 6 步)。

## 快速指令

於專案根目錄(`MediaTranX/`)執行:

```bash
# 正式發版(直接給版本)
python scripts/release.py v1.4.0

# 自動從最新 tag 遞增
python scripts/release.py --bump patch          # v1.3.3 -> v1.3.4
python scripts/release.py --bump minor          # v1.3.3 -> v1.4.0

# 跳過 build(dist/ 已有對應 installer)
python scripts/release.py v1.4.0 --skip-build

# full installer(含 .venv + bin tools)
python scripts/release.py v1.4.0 --full
```

- `release.py` 只用標準庫,**用一般 `python` 跑即可**(不需 `uv run`)。
- 版本格式必須 `vX.Y.Z`。
- `release.py` 啟動時會把自己複製到 temp 再執行(self-copy trick)—— 因為流程中的 `git checkout main` 會改動 `scripts/`,避免原檔被行程鎖住。

## 前置條件

- repo 在 `dev` branch。
- working tree **乾淨**(`git status --porcelain` 為空 —— 連未追蹤檔都會擋住,須先 commit / gitignore / 刪除)。
- GitHub CLI (`gh`) 已安裝並登入。
- 目標版本 tag 尚未存在。

## 完整流程(release.py,6 步)

```
Step 0: Pre-flight ── 檢查 branch / clean tree / tag / gh
  ↓
Step 1: merge dev → main(--no-ff)
Step 2: bump backend/pyproject.toml (+uv.lock) + electron/package.json 版號 + 一次 commit
  ↓
Step 3: Build installer
  ↓
Step 4: Tag(build 成功才打 tag)
Step 5: Push main + tag → 建 GitHub Release
  ↓
Step 6: Sync main 回 dev
```

### Step 0 — Pre-flight

- repo 須在 `dev`、working tree 乾淨。
- `gh auth status` 通過。
- 目標 tag 不存在。
- `git fetch origin`。
- 任一檢查失敗即中止,不做任何變更。

### Step 1 — merge dev → main

```
git checkout main
git reset --hard origin/main
git merge dev --no-ff -m "Merge branch 'dev' into main"
```

### Step 2 — bump version

改 `backend/pyproject.toml` 的 `version` + 跑 `uv lock`(於 `backend/`)、`npm version X.Y.Z --no-git-tag-version`(於 `electron/`),一次 commit `backend/pyproject.toml` + `backend/uv.lock` + `electron/package.json` + `electron/package-lock.json`。

### Step 3 — Build installer

```
uv run --project backend python scripts/build.py --mode prod --version X.Y.Z
```

- **必須帶 `--project backend`** —— `build.py` 的 nuitka 步驟用「行程所在環境的已安裝套件」算 Nuitka `--nofollow-import-to` 排除清單;不在 backend venv 跑 → 排除清單錯 → build 壞。
- `--full` 才把 `.venv` + bin tools 打進 installer;預設不含(AI 環境由 app 首次啟動時自行安裝)。正式 release 多為非-full。
- `--skip-build` 可跳過此步(dist/ 須已有對應 installer)。
- Build 在 tag 之前 —— **build 失敗則不會建立 tag**。

### Step 4 — Tag

```
git tag -a vX.Y.Z -m "Release vX.Y.Z"
```

### Step 5 — Push + GitHub Release

push `main` 與 tag;release notes 由「前一個 tag..本次 tag」的 commit log(`--no-merges`)產生;`gh release create` 上傳 `dist/MediaTranX-Setup-X.Y.Z-win.exe`(`--full` 時為 `...-full-win.exe`)到 `sw-willie-wu/MediaTranX`。

### Step 6 — Sync main 回 dev

```
git checkout dev
git merge main --no-edit
```

> 注意:`release.py` Step 6 **不會** `git push origin dev` —— 發版只把 `main` + tag 推上去,`dev` 是否推由你自行決定。

## 測試 Build(不發版)

```
uv run --project backend python scripts/build.py --mode dev
```

- `--mode dev` → 版號 `X.Y.Z-dev.N`(N 自動遞增),build 完**自動還原版號**。
- 不 commit、不 tag、不 push。
- 產出 `dist/MediaTranX-Setup-X.Y.Z-dev.N-win.exe`。

## 注意事項

- **Tag 在 build 之後** —— build 失敗不汙染 tag。
- **`--no-ff` merge** —— 保留 git graph 的合併關係。
- **build.py 必須 `uv run --project backend`** —— 見 Step 3。
- **build 前先關閉 dev 環境**(electron / node / python / llama-server)避免檔案鎖。
- **`release.py` 用標準庫**,一般 `python` 即可;`build.py` 才需 `uv run --project backend`。
