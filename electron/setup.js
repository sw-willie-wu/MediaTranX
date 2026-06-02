// electron/setup.js
// Handles GPU detection, pyproject.toml source writing, uv sync, and binary tool downloads.

'use strict';

const { execSync, spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');
const https = require('https');
const http = require('http');

// ---------------------------------------------------------------------------
// Pinned tool versions (update when bumping app version)
// ---------------------------------------------------------------------------
const TOOL_VERSIONS = {
  ffmpeg: '8.1',            // GyanD/codexffmpeg release tag
  soundfonts: '1',          // MusyngKite GM instrument samples version
  llama: 'b8763',          // ggml-org/llama.cpp release tag
  ytdlp: '2026.03.17',     // yt-dlp/yt-dlp release tag (date-format YYYY.MM.DD)
};

// ---------------------------------------------------------------------------
// 1. detectGPU()
// ---------------------------------------------------------------------------

/**
 * Detect GPU type and driver version.
 * Returns a gpuInfo object suitable for variant selection.
 *
 * @returns {{ type: string, variant: string|null, driverVersion?: number,
 *             gpuName?: string, memory?: string, label?: string }}
 */
function detectGPU() {
  const platform = process.platform;

  // macOS — no CUDA support
  if (platform === 'darwin') {
    const arch = process.arch; // arm64 or x64
    if (arch === 'arm64') {
      return { type: 'none', variant: null, label: 'Apple Silicon (CPU)' };
    }
    return { type: 'none', variant: null, label: 'Intel CPU' };
  }

  // Windows / Linux — try nvidia-smi first
  try {
    const raw = execSync(
      'nvidia-smi --query-gpu=driver_version,name,memory.total --format=csv,noheader',
      { timeout: 8000, stdio: ['ignore', 'pipe', 'ignore'] }
    ).toString().trim();

    if (raw) {
      // nvidia-smi may return multiple GPUs; use the first line
      const firstLine = raw.split('\n')[0].trim();
      const parts = firstLine.split(',').map(s => s.trim());
      const driverStr = parts[0] || '';
      const gpuName   = parts[1] || 'NVIDIA GPU';
      const memory    = parts[2] || '';

      // Driver version can be "570.00" or "570" — parse major version
      const driverVersion = parseFloat(driverStr);

      // NOTE: cu126/cu128/cu130 temporarily disabled due to PyTorch index
      // hash mismatch for torchvision 0.26.0. All drivers >= 550 use cu124.
      // Restore full mapping when PyTorch fixes their wheel hashes.
      let variant;
      if      (driverVersion >= 550) variant = 'cu124';
      else if (driverVersion >= 527) variant = 'cu121';
      else if (driverVersion >= 452) variant = 'cu118';
      else                           variant = 'cpu';

      // Compute capability via a SEPARATE nvidia-smi call — old drivers lack the
      // compute_cap field, and folding it into the CSV above would shift the
      // gpuName/memory column indices. Failure → leave null (driver-based choice).
      let computeCap = null;
      try {
        const ccRaw = execSync(
          'nvidia-smi --query-gpu=compute_cap --format=csv,noheader,nounits',
          { timeout: 8000, stdio: ['ignore', 'pipe', 'ignore'] }
        ).toString().trim().split('\n')[0].trim();
        const parsed = parseFloat(ccRaw);
        if (!Number.isNaN(parsed)) computeCap = parsed;
      } catch (_) { /* old nvidia-smi: leave computeCap null */ }

      return { type: 'nvidia', variant, driverVersion, gpuName, memory, computeCap };
    }
  } catch (_) {
    // nvidia-smi not available or failed
  }

  // AMD / Intel fallback
  try {
    let gpuList = '';

    if (platform === 'win32') {
      gpuList = execSync(
        'wmic path win32_videocontroller get name /format:list',
        { timeout: 8000, stdio: ['ignore', 'pipe', 'ignore'] }
      ).toString();
    } else {
      // Linux
      gpuList = execSync(
        'lspci | grep -i vga',
        { timeout: 8000, stdio: ['ignore', 'pipe', 'ignore'] }
      ).toString();
    }

    if (/radeon|amd/i.test(gpuList)) {
      const match = gpuList.match(/Name=(.*)/i);
      const label = match ? match[1].trim() : 'AMD GPU';
      return { type: 'amd', variant: 'cpu', label };
    }

    if (/intel.*(arc|iris|uhd)/i.test(gpuList)) {
      const match = gpuList.match(/Name=(.*)/i);
      const label = match ? match[1].trim() : 'Intel GPU';
      return { type: 'intel', variant: 'cpu', label };
    }
  } catch (_) {
    // wmic / lspci not available or failed
  }

  return { type: 'none', variant: 'cpu', label: 'CPU' };
}

// ---------------------------------------------------------------------------
// 2. updatePyprojectSources(pyprojectPath, variant)
// ---------------------------------------------------------------------------

const MARKER_START = '# --- AUTO-GENERATED TORCH SOURCES (do not edit manually) ---';
const MARKER_END   = '# --- END AUTO-GENERATED ---';

/**
 * Build the [tool.uv.sources] block content between the markers.
 * @param {string|null} variant  e.g. 'cu130', 'cpu', or null (macOS)
 * @returns {string}
 */
function buildSourcesBlock(variant) {
  const lines = [];
  lines.push(MARKER_START);
  lines.push('[tool.uv.sources]');
  lines.push('demucs = { git = "https://github.com/sw-willie-wu/demucs", rev = "e976d93ecc3865e5757426930257e200846a520a" }');

  if (variant !== null && variant !== undefined) {
    // CPU or CUDA variant — add torch sources
    const indexName = variant.startsWith('cu') ? `pytorch-${variant}` : 'pytorch-cpu';
    lines.push(`torch = { index = "${indexName}" }`);
    lines.push(`torchvision = { index = "${indexName}" }`);
    lines.push(`torchaudio = { index = "${indexName}" }`);
  }
  // If variant is null (macOS), only demucs line, no torch sources

  lines.push(MARKER_END);
  return lines.join('\n');
}

/**
 * Update [tool.uv.sources] block in pyproject.toml according to detected GPU variant.
 * @param {string} pyprojectPath  Absolute path to pyproject.toml
 * @param {string|null} variant   GPU variant string or null for macOS
 * @returns {boolean}  true if file was changed, false if no change needed
 */
function updatePyprojectSources(pyprojectPath, variant) {
  if (!fs.existsSync(pyprojectPath)) {
    throw new Error(`pyproject.toml not found at: ${pyprojectPath}`);
  }

  const original = fs.readFileSync(pyprojectPath, 'utf8');
  const newBlock = buildSourcesBlock(variant);

  const startIdx = original.indexOf(MARKER_START);
  const endIdx   = original.indexOf(MARKER_END);

  let updated;

  if (startIdx !== -1 && endIdx !== -1) {
    // Replace the existing block (including the end marker)
    const before  = original.slice(0, startIdx);
    const after   = original.slice(endIdx + MARKER_END.length);
    updated = before + newBlock + after;
  } else {
    // Append to end of file (ensure trailing newline before block)
    const sep = original.endsWith('\n') ? '\n' : '\n\n';
    updated = original + sep + newBlock + '\n';
  }

  if (updated === original) return false;

  fs.writeFileSync(pyprojectPath, updated, 'utf8');
  return true;
}

// ---------------------------------------------------------------------------
// 3. runUvSync({ uvExe, projectDir, venvPath, uvDataDir, onProgress })
// ---------------------------------------------------------------------------

/**
 * Run `uv sync --no-dev --inexact` under the given project.
 * @param {{ uvExe: string, projectDir: string, venvPath: string,
 *           uvDataDir: string, onProgress?: (pkg: string) => void }} opts
 * @returns {Promise<void>}
 */
function runUvSync({ uvExe, projectDir, venvPath, uvDataDir, onProgress }) {
  return new Promise((resolve, reject) => {
    const args = [
      '--project', projectDir,
      'sync',
      '--no-dev',
    ];

    const env = {
      ...process.env,
      UV_PROJECT_ENVIRONMENT: venvPath,
      UV_DATA_DIR: uvDataDir,
      // The `ai` deps include git+https packages (demucs, mobile-sam). On a
      // fresh Windows machine `git clone` invokes Git Credential Manager, which
      // pops a GitHub sign-in dialog even for these public repos. Force git
      // fully non-interactive and disable any credential helper for this child
      // so the clones proceed anonymously without prompting the user.
      GIT_TERMINAL_PROMPT: '0',
      GCM_INTERACTIVE: 'never',
      // credential.helper='' clears all helpers (git's reset sentinel), so GCM
      // never launches. Requires git >= 2.31; the bundled Git for Windows is
      // newer. Assumes the user hasn't already exported GIT_CONFIG_COUNT (a rare
      // power-user/CI var) — on a fresh end-user machine it's unset.
      GIT_CONFIG_COUNT: '1',
      GIT_CONFIG_KEY_0: 'credential.helper',
      GIT_CONFIG_VALUE_0: '',
    };

    const proc = spawn(uvExe, args, {
      cwd: projectDir,
      env,
      stdio: ['ignore', 'pipe', 'pipe'],
      shell: process.platform === 'win32',
    });

    let stderrBuf = '';

    proc.stdout.on('data', (chunk) => {
      // uv typically writes progress to stderr, but handle stdout too
      const text = chunk.toString();
      text.split('\n').forEach(line => {
        const trimmed = line.trim();
        if (trimmed.startsWith('+') && onProgress) {
          // Extract package name — line format: "+ packagename==version"
          const match = trimmed.match(/^\+\s+([\w\-_.]+)/);
          if (match) onProgress(match[1]);
        }
      });
    });

    proc.stderr.on('data', (chunk) => {
      const text = chunk.toString();
      stderrBuf += text;
      text.split('\n').forEach(line => {
        const trimmed = line.trim();
        if (!trimmed || !onProgress) return;
        // Installed package: "+ package==version"
        if (trimmed.startsWith('+')) {
          const match = trimmed.match(/^\+\s+([\w\-_.]+)/);
          if (match) onProgress({ type: 'install', name: match[1] });
        }
        // Downloading: "Downloading torch (1.8GiB)"
        else if (trimmed.startsWith('Downloading')) {
          const match = trimmed.match(/^Downloading\s+([\w\-_.]+)\s*(\(.*\))?/);
          if (match) onProgress({ type: 'download', name: match[1], size: match[2] || '' });
        }
        // Resolved: "Resolved 174 packages in 2.78s"
        else if (trimmed.startsWith('Resolved')) {
          onProgress({ type: 'resolve', message: trimmed });
        }
        // Building: "Building package @ ..."
        else if (trimmed.startsWith('Building') || trimmed.startsWith('Built')) {
          const match = trimmed.match(/(?:Building|Built)\s+([\w\-_.]+)/);
          if (match) onProgress({ type: 'build', name: match[1] });
        }
      });
    });

    proc.on('close', (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(new Error(
          `uv sync failed with exit code ${code}.\nStderr:\n${stderrBuf.slice(-2000)}`
        ));
      }
    });

    proc.on('error', (err) => {
      reject(new Error(`Failed to spawn uv: ${err.message}`));
    });
  });
}

// ---------------------------------------------------------------------------
// 4. Download framework utilities
// ---------------------------------------------------------------------------

/**
 * HTTPS GET with redirect following, returns parsed JSON.
 * @param {string} url
 * @returns {Promise<any>}
 */
function fetchJSON(url) {
  return new Promise((resolve, reject) => {
    _httpGet(url, (err, body) => {
      if (err) return reject(err);
      try {
        resolve(JSON.parse(body));
      } catch (e) {
        reject(new Error(`Failed to parse JSON from ${url}: ${e.message}`));
      }
    });
  });
}

/**
 * Internal helper: GET url, follow redirects, collect body as string.
 * Uses Electron's net module when available (avoids HTTP parser conflicts).
 * @param {string} url
 * @param {(err: Error|null, body: string) => void} cb
 * @param {number} [redirects=10]
 */
function _httpGet(url, cb, redirects = 10) {
  if (redirects <= 0) return cb(new Error('Too many redirects'));

  // Prefer Electron's net module (handles redirects + TLS better in Electron)
  let electronNet;
  try { electronNet = require('electron').net; } catch (_) {}

  if (electronNet) {
    const req = electronNet.request({ url, method: 'GET' });
    req.setHeader('User-Agent', 'Mozilla/5.0 MediaTranX-Setup/1.0');
    req.on('response', (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && String(res.headers.location)) {
        return _httpGet(String(res.headers.location), cb, redirects - 1);
      }
      if (res.statusCode !== 200) {
        return cb(new Error(`HTTP ${res.statusCode} for ${url}`));
      }
      const chunks = [];
      res.on('data', chunk => chunks.push(chunk));
      res.on('end', () => cb(null, Buffer.concat(chunks).toString('utf8')));
      res.on('error', cb);
    });
    req.on('error', cb);
    req.end();
    return;
  }

  // Fallback to Node.js https (for non-Electron environments)
  const lib = url.startsWith('https://') ? https : http;
  const options = new URL(url);
  const reqOptions = {
    hostname: options.hostname,
    path: options.pathname + options.search,
    method: 'GET',
    headers: {
      'User-Agent': 'Mozilla/5.0 MediaTranX-Setup/1.0',
    },
  };

  const req = lib.request(reqOptions, (res) => {
    if (res.statusCode >= 300 && res.statusCode < 400 && String(res.headers.location)) {
      res.resume();
      return _httpGet(String(res.headers.location), cb, redirects - 1);
    }
    if (res.statusCode !== 200) {
      res.resume();
      return cb(new Error(`HTTP ${res.statusCode} for ${url}`));
    }

    const chunks = [];
    res.on('data', chunk => chunks.push(chunk));
    res.on('end', () => cb(null, Buffer.concat(chunks).toString('utf8')));
    res.on('error', cb);
  });

  req.on('error', cb);
  req.end();
}

/**
 * Stream download a file with progress callback.
 * @param {string} url
 * @param {string} destPath
 * @param {(downloaded: number, total: number) => void} [onProgress]
 * @returns {Promise<void>}
 */
function downloadFile(url, destPath, onProgress) {
  return new Promise((resolve, reject) => {
    _downloadStream(url, destPath, onProgress, resolve, reject, 5);
  });
}

function _downloadStream(url, destPath, onProgress, resolve, reject, redirects) {
  if (redirects <= 0) return reject(new Error('Too many redirects'));

  // Prefer Electron's net module
  let electronNet;
  try { electronNet = require('electron').net; } catch (_) {}

  const handleResponse = (res) => {
    if (res.statusCode >= 300 && res.statusCode < 400 && String(res.headers.location)) {
      if (res.resume) res.resume();
      return _downloadStream(String(res.headers.location), destPath, onProgress, resolve, reject, redirects - 1);
    }
    if (res.statusCode !== 200) {
      if (res.resume) res.resume();
      return reject(new Error(`HTTP ${res.statusCode} downloading ${url}`));
    }

    const total = parseInt(String(res.headers['content-length'] || '0'), 10);
    let downloaded = 0;

    fs.mkdirSync(path.dirname(destPath), { recursive: true });
    const out = fs.createWriteStream(destPath);

    res.on('data', (chunk) => {
      downloaded += chunk.length;
      out.write(chunk);
      if (onProgress) onProgress(downloaded, total);
    });

    res.on('end', () => {
      out.end(() => {
        if (downloaded === 0) {
          reject(new Error(`Downloaded 0 bytes from ${url}`));
        } else {
          resolve();
        }
      });
    });

    out.on('error', reject);
    res.on('error', reject);
  };

  if (electronNet) {
    const req = electronNet.request({ url, method: 'GET' });
    req.setHeader('User-Agent', 'Mozilla/5.0 MediaTranX-Setup/1.0');
    req.on('response', handleResponse);
    req.on('error', reject);
    req.end();
    return;
  }

  // Fallback to Node.js https
  const lib = url.startsWith('https://') ? https : http;
  const options = new URL(url);
  const req = lib.request({
    hostname: options.hostname,
    path: options.pathname + options.search,
    method: 'GET',
    headers: { 'User-Agent': 'Mozilla/5.0 MediaTranX-Setup/1.0' },
  }, handleResponse);
  req.on('error', reject);
  req.end();
}

/**
 * Extract a zip archive.
 *   - Windows: PowerShell Expand-Archive to tmp dir, then copy matching files to destDir
 *   - Linux/macOS: unzip / tar
 *
 * @param {string} zipPath   Absolute path to the zip file
 * @param {string} destDir   Directory to extract into
 * @param {string[]|null} fileFilter
 *   Array of basenames to extract, or null to extract executables
 *   (*.exe, *.dll, *.so, and files without extension on Unix)
 * @returns {Promise<void>}
 */
/**
 * Extract zip by reading entries directly (like Python's zipfile).
 * Matches entries by basename — no temp directory needed.
 */
function extractZip(zipPath, destDir, fileFilter) {
  return new Promise((resolve, reject) => {
    fs.mkdirSync(destDir, { recursive: true });
    console.log(`[setup] Extracting: ${zipPath} → ${destDir}`);

    try {
      // Use PowerShell to list + extract specific entries, OR fallback to full extract
      if (process.platform === 'win32') {
        // Full extract to temp dir, then copy matching files
        const tmpDir = path.join(os.tmpdir(), `mediatranx_extract_${Date.now()}`);
        try {
          const psCmd = [
            'PowerShell', '-NonInteractive', '-Command',
            `Expand-Archive -Path '${zipPath}' -DestinationPath '${tmpDir}' -Force`
          ].join(' ');
          execSync(psCmd, { timeout: 600000, stdio: 'pipe', windowsHide: true });

          const copied = _copyExtractedFiles(tmpDir, destDir, fileFilter);
          console.log(`[setup] Extracted ${copied} files to ${destDir}`);

          if (copied === 0) {
            // Fallback: list what was extracted for debugging
            const allFiles = _walkDir(tmpDir);
            console.log(`[setup] WARNING: 0 files matched filter. Found ${allFiles.length} files in archive:`);
            allFiles.slice(0, 20).forEach(f => console.log(`[setup]   ${f}`));
          }
        } finally {
          try { fs.rmSync(tmpDir, { recursive: true, force: true }); } catch (_) {}
        }
      } else {
        const tmpDir = path.join(os.tmpdir(), `mediatranx_extract_${Date.now()}`);
        fs.mkdirSync(tmpDir, { recursive: true });
        try {
          execSync(`unzip -o "${zipPath}" -d "${tmpDir}"`, { timeout: 600000, stdio: 'pipe' });
          const copied = _copyExtractedFiles(tmpDir, destDir, fileFilter);
          console.log(`[setup] Extracted ${copied} files to ${destDir}`);
        } finally {
          try { fs.rmSync(tmpDir, { recursive: true, force: true }); } catch (_) {}
        }
      }
      resolve();
    } catch (err) {
      reject(new Error(`extractZip failed: ${err.message}`));
    }
  });
}

/**
 * Extract a .tar.gz archive (Linux/macOS).
 * @param {string} tgzPath
 * @param {string} destDir
 * @param {string[]|null} fileFilter
 * @returns {Promise<void>}
 */
function extractTarGz(tgzPath, destDir, fileFilter) {
  return new Promise((resolve, reject) => {
    fs.mkdirSync(destDir, { recursive: true });
    const tmpDir = path.join(os.tmpdir(), `mediatranx_extract_${Date.now()}`);
    fs.mkdirSync(tmpDir, { recursive: true });

    try {
      execSync(`tar -xzf "${tgzPath}" -C "${tmpDir}"`, { timeout: 120000, stdio: 'pipe' });
      _copyExtractedFiles(tmpDir, destDir, fileFilter);
      try { fs.rmSync(tmpDir, { recursive: true, force: true }); } catch (_) {}
      resolve();
    } catch (err) {
      try { fs.rmSync(tmpDir, { recursive: true, force: true }); } catch (_) {}
      reject(new Error(`extractTarGz failed: ${err.message}`));
    }
  });
}

/**
 * Walk srcDir recursively, copy files matching fileFilter to destDir (flat).
 */
function _copyExtractedFiles(srcDir, destDir, fileFilter) {
  const entries = _walkDir(srcDir);
  let count = 0;

  for (const filePath of entries) {
    const basename = path.basename(filePath);
    const ext = path.extname(basename).toLowerCase();

    let shouldCopy = false;

    if (fileFilter !== null && Array.isArray(fileFilter)) {
      shouldCopy = fileFilter.includes(basename);
    } else {
      // Default: executables — .exe, .dll, .so*, and no-extension files
      shouldCopy = (
        ext === '.exe' ||
        ext === '.dll' ||
        ext === '.so'  ||
        filePath.includes('.so.') ||   // libfoo.so.1.2
        (ext === '' && !basename.startsWith('.'))
      );
    }

    if (shouldCopy) {
      const dest = path.join(destDir, basename);
      fs.mkdirSync(path.dirname(dest), { recursive: true });
      fs.copyFileSync(filePath, dest);
      if (process.platform !== 'win32') {
        try { fs.chmodSync(dest, 0o755); } catch (_) {}
      }
      count++;
    }
  }
  return count;
}

/** Recursively return all file paths under dir. */
function _walkDir(dir) {
  const results = [];
  try {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        results.push(..._walkDir(fullPath));
      } else if (entry.isFile()) {
        results.push(fullPath);
      }
    }
  } catch (_) {}
  return results;
}

/**
 * Check if a tool needs updating by comparing installed .version with expected tag.
 * @returns {boolean} true if download is needed
 */
function needsDownload(toolDir, expectedTag, force) {
  if (force) return true;
  const versionFile = path.join(toolDir, '.version');
  if (!fs.existsSync(versionFile)) return true;
  try {
    const data = JSON.parse(fs.readFileSync(versionFile, 'utf-8'));
    return data.tag !== expectedTag;
  } catch (_) {
    return true;
  }
}

// ---------------------------------------------------------------------------
// 5. downloadFFmpeg(binDir, onProgress, force)
// ---------------------------------------------------------------------------

/**
 * Download ffmpeg (and ffprobe) to binDir/ffmpeg/.
 * @param {string} binDir
 * @param {(msg: string, downloaded?: number, total?: number) => void} [onProgress]
 * @returns {Promise<void>}
 */
// GyanD/codexffmpeg ships two Windows builds per release: "essentials" and
// "full". Only the "full" build bundles libdav1d — the fast VideoLAN AV1
// decoder. Without it, AV1 software decode falls back to FFmpeg's native
// decoder, ~2.4x slower (measured 4K AV1 scene detection: ~21 min vs ~9 min).
// Pick the full build. The local .version marker carries the variant so an
// existing "essentials" install (marker "8.1") re-downloads on upgrade.
const FFMPEG_VARIANT = 'full';

async function downloadFFmpeg(binDir, onProgress, force = false) {
  const platform = process.platform;
  const ffmpegDir = path.join(binDir, 'ffmpeg');
  const expectedTag = TOOL_VERSIONS.ffmpeg;
  // Local version marker: release tag + build variant. Distinct from the
  // GitHub release tag (expectedTag) used for the API URL.
  const versionMarker = `${expectedTag}-${FFMPEG_VARIANT}`;

  // macOS/Linux: prefer system ffmpeg
  if (platform !== 'win32') {
    try {
      const sys = execSync('which ffmpeg', { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim();
      if (sys) { if (onProgress) onProgress(`Using system ffmpeg: ${sys}`); return; }
    } catch (_) {}
    if (onProgress) onProgress('ffmpeg not found. Please install via your system package manager.');
    return;
  }

  if (!needsDownload(ffmpegDir, versionMarker, force)) {
    if (onProgress) onProgress('ffmpeg up to date, skipping.');
    return;
  }

  if (onProgress) onProgress('Fetching ffmpeg release info...');
  const releaseInfo = await fetchJSON(
    `https://api.github.com/repos/GyanD/codexffmpeg/releases/tags/${expectedTag}`
  );

  const assets = releaseInfo.assets || [];
  // Static "full" build: name contains full_build, .zip, NOT the -shared variant.
  const asset = assets.find(a =>
    a.name.includes('full_build') && a.name.endsWith('.zip') && !a.name.includes('shared')
  );
  if (!asset) throw new Error(`Could not find ffmpeg full_build asset for tag ${expectedTag}`);

  const tmpZip = path.join(os.tmpdir(), `ffmpeg_${Date.now()}.zip`);
  if (onProgress) onProgress(`Downloading ffmpeg ${expectedTag} (${FFMPEG_VARIANT})...`);
  await downloadFile(asset.browser_download_url, tmpZip, (dl, total) => {
    if (onProgress) onProgress('FFmpeg', dl, total);
  });

  if (onProgress) onProgress('Extracting ffmpeg...');
  fs.mkdirSync(ffmpegDir, { recursive: true });
  await extractZip(tmpZip, ffmpegDir, ['ffmpeg.exe', 'ffprobe.exe']);
  try { fs.unlinkSync(tmpZip); } catch (_) {}

  fs.writeFileSync(path.join(ffmpegDir, '.version'), JSON.stringify({ tag: versionMarker }), 'utf8');
  if (onProgress) onProgress('ffmpeg installed.');
}

// ---------------------------------------------------------------------------
// 6. downloadYtDlp(binDir, onProgress, force)
// ---------------------------------------------------------------------------

/**
 * Download yt-dlp frozen single-file binary to binDir/yt-dlp/.
 * Windows: yt-dlp.exe; macOS: yt-dlp_macos (renamed yt-dlp); Linux: prefers system install.
 * @param {string} binDir
 * @param {(msg: string, downloaded?: number, total?: number) => void} [onProgress]
 * @param {boolean} [force]
 * @returns {Promise<void>}
 */
async function downloadYtDlp(binDir, onProgress, force = false) {
  const platform = process.platform;
  const ytdlpDir = path.join(binDir, 'yt-dlp');
  const expectedTag = TOOL_VERSIONS.ytdlp;

  // Linux: the plain `yt-dlp` asset needs a system Python — prefer system install.
  if (platform === 'linux') {
    try {
      const sys = execSync('which yt-dlp', { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim();
      if (sys) { if (onProgress) onProgress(`Using system yt-dlp: ${sys}`); return; }
    } catch (_) {}
    if (onProgress) onProgress('yt-dlp not found. Install via your package manager (e.g. pipx install yt-dlp).');
    return;
  }

  if (!needsDownload(ytdlpDir, expectedTag, force)) {
    if (onProgress) onProgress('yt-dlp up to date, skipping.');
    return;
  }

  // Frozen single-file builds (bundle their own Python — no extraction needed).
  const assetName = platform === 'win32' ? 'yt-dlp.exe' : 'yt-dlp_macos';
  const exeName = platform === 'win32' ? 'yt-dlp.exe' : 'yt-dlp';

  if (onProgress) onProgress('Fetching yt-dlp release info...');
  const releaseInfo = await fetchJSON(
    `https://api.github.com/repos/yt-dlp/yt-dlp/releases/tags/${expectedTag}`
  );
  const assets = releaseInfo.assets || [];
  const asset = assets.find(a => a.name === assetName);
  if (!asset) throw new Error(`Could not find yt-dlp asset ${assetName} for tag ${expectedTag}`);

  fs.mkdirSync(ytdlpDir, { recursive: true });
  const exePath = path.join(ytdlpDir, exeName);
  if (onProgress) onProgress(`Downloading yt-dlp ${expectedTag}...`);
  await downloadFile(asset.browser_download_url, exePath, (dl, total) => {
    if (onProgress) onProgress('yt-dlp', dl, total);
  });

  if (platform !== 'win32') {
    try { fs.chmodSync(exePath, 0o755); } catch (_) {}
  }
  fs.writeFileSync(path.join(ytdlpDir, '.version'), JSON.stringify({ tag: expectedTag }), 'utf8');
  if (onProgress) onProgress('yt-dlp installed.');
}

// ---------------------------------------------------------------------------
// 7. downloadSoundfonts(binDir, onProgress)
// ---------------------------------------------------------------------------

const SOUNDFONT_BASE_URL = 'https://raw.githubusercontent.com/gleitz/midi-js-soundfonts/gh-pages/MusyngKite';

const GM_INSTRUMENTS = [
  'acoustic_grand_piano','bright_acoustic_piano','electric_grand_piano','honkytonk_piano',
  'electric_piano_1','electric_piano_2','harpsichord','clavinet',
  'celesta','glockenspiel','music_box','vibraphone','marimba','xylophone','tubular_bells','dulcimer',
  'drawbar_organ','percussive_organ','rock_organ','church_organ','reed_organ','accordion','harmonica','tango_accordion',
  'acoustic_guitar_nylon','acoustic_guitar_steel','electric_guitar_jazz','electric_guitar_clean',
  'electric_guitar_muted','overdriven_guitar','distortion_guitar','guitar_harmonics',
  'acoustic_bass','electric_bass_finger','electric_bass_pick','fretless_bass',
  'slap_bass_1','slap_bass_2','synth_bass_1','synth_bass_2',
  'violin','viola','cello','contrabass','tremolo_strings','pizzicato_strings','orchestral_harp','timpani',
  'string_ensemble_1','string_ensemble_2','synth_strings_1','synth_strings_2',
  'choir_aahs','voice_oohs','synth_choir','orchestra_hit',
  'trumpet','trombone','tuba','muted_trumpet','french_horn','brass_section','synth_brass_1','synth_brass_2',
  'soprano_sax','alto_sax','tenor_sax','baritone_sax','oboe','english_horn','bassoon','clarinet',
  'piccolo','flute','recorder','pan_flute','blown_bottle','shakuhachi','whistle','ocarina',
  'lead_1_square','lead_2_sawtooth','lead_3_calliope','lead_4_chiff',
  'lead_5_charang','lead_6_voice','lead_7_fifths','lead_8_bass__lead',
  'pad_1_new_age','pad_2_warm','pad_3_polysynth','pad_4_choir',
  'pad_5_bowed','pad_6_metallic','pad_7_halo','pad_8_sweep',
  'fx_1_rain','fx_2_soundtrack','fx_3_crystal','fx_4_atmosphere',
  'fx_5_brightness','fx_6_goblins','fx_7_echoes','fx_8_scifi',
  'sitar','banjo','shamisen','koto','kalimba','bagpipe','fiddle','shanai',
  'tinkle_bell','agogo','steel_drums','woodblock','taiko_drum','melodic_tom','synth_drum','reverse_cymbal',
  'guitar_fret_noise','breath_noise','seashore','bird_tweet',
  'telephone_ring','helicopter','applause','gunshot',
];

/**
 * Download MusyngKite GM instrument samples from GitHub and save as individual MP3 files.
 * Each instrument JS file contains base64-encoded MP3 samples in MIDI.js format.
 * Files are saved to binDir/soundfonts/musyngkite/{instrument_name}-mp3/
 * @param {string} binDir
 * @param {(msg: string, downloaded?: number, total?: number) => void} [onProgress]
 * @param {boolean} [force]
 * @returns {Promise<void>}
 */
async function downloadSoundfonts(binDir, onProgress, force = false) {
  const soundfontsDir = path.join(binDir, 'soundfonts', 'musyngkite');
  const expectedTag = TOOL_VERSIONS.soundfonts;
  const totalInstruments = GM_INSTRUMENTS.length;

  // Note: musyngkite is cross-platform — no platform check needed

  if (!needsDownload(soundfontsDir, expectedTag, force)) {
    if (onProgress) onProgress('Soundfonts up to date.');
    return;
  }

  fs.mkdirSync(soundfontsDir, { recursive: true });

  // Regex to extract note → base64 data URI mappings from MIDI.js JS format
  const NOTE_REGEX = /["']([A-G][b#]?\d)["']\s*:\s*["'](data:audio\/mp3;base64,([^"']+))["']/g;

  for (let i = 0; i < totalInstruments; i++) {
    const instrument = GM_INSTRUMENTS[i];
    const jsUrl = `${SOUNDFONT_BASE_URL}/${instrument}-mp3.js`;
    const instrumentDir = path.join(soundfontsDir, `${instrument}-mp3`);

    if (onProgress) onProgress(`${instrument} (${i + 1}/${totalInstruments})`);

    // Download the JS file to a temp path
    const tmpJs = path.join(os.tmpdir(), `soundfont_${instrument}_${Date.now()}.js`);
    try {
      await downloadFile(jsUrl, tmpJs, null);

      const jsContent = fs.readFileSync(tmpJs, 'utf-8');

      // Parse all note entries
      fs.mkdirSync(instrumentDir, { recursive: true });
      let match;
      NOTE_REGEX.lastIndex = 0;
      while ((match = NOTE_REGEX.exec(jsContent)) !== null) {
        const note = match[1];    // e.g. "A4"
        const base64Data = match[3]; // raw base64 string
        const mp3Path = path.join(instrumentDir, `${note}.mp3`);
        const buffer = Buffer.from(base64Data.trim(), 'base64');
        fs.writeFileSync(mp3Path, buffer);
      }
    } catch (err) {
      console.warn(`[soundfonts] Failed to download ${instrument}: ${err.message}`);
    } finally {
      try { fs.unlinkSync(tmpJs); } catch (_) {}
    }
  }

  // Download GM drum kit from WebAudioFont (notes 35-81)
  const drumDir = path.join(soundfontsDir, 'drums-mp3');
  fs.mkdirSync(drumDir, { recursive: true });
  const DRUM_BASE_URL = 'https://surikov.github.io/webaudiofontdata/sound';
  const FILE_REGEX = /file\s*:\s*'([A-Za-z0-9+/=]+)'/;

  for (let note = 35; note <= 81; note++) {
    const mp3Path = path.join(drumDir, `${note}.mp3`);
    if (fs.existsSync(mp3Path) && !force) continue;

    const jsUrl = `${DRUM_BASE_URL}/128${note}_0_FluidR3_GM_sf2_file.js`;
    const tmpJs = path.join(os.tmpdir(), `drum_${note}_${Date.now()}.js`);
    try {
      await downloadFile(jsUrl, tmpJs, null);
      const content = fs.readFileSync(tmpJs, 'utf-8');
      const match = FILE_REGEX.exec(content);
      if (match) {
        fs.writeFileSync(mp3Path, Buffer.from(match[1], 'base64'));
      }
    } catch (err) {
      console.warn(`[soundfonts] Failed to download drum note ${note}: ${err.message}`);
    } finally {
      try { fs.unlinkSync(tmpJs); } catch (_) {}
    }
  }
  if (onProgress) onProgress(`Drum kit downloaded`);

  fs.writeFileSync(path.join(soundfontsDir, '.version'), JSON.stringify({ tag: expectedTag }), 'utf8');
  if (onProgress) onProgress('Soundfonts installed.');
}

// ---------------------------------------------------------------------------
// 7. downloadLlamaServer(binDir, gpuInfo, onProgress)
// ---------------------------------------------------------------------------

/**
 * Select the best llama.cpp release asset name based on GPU info and platform.
 * @param {{ type: string, variant?: string, driverVersion?: number, computeCap?: number|null }} gpuInfo
 * @param {string[]} assetNames  List of asset filenames from the GitHub release
 * @returns {string|null}  Chosen asset name, or null if nothing suitable found
 */
function selectLlamaAsset(gpuInfo, assetNames) {
  const platform = process.platform;
  const arch = process.arch === 'arm64' ? 'arm64' : 'x64';

  // Helper: find first asset whose name includes all given substrings (excluding cudart)
  const find = (...parts) =>
    assetNames.find(n => {
      const lower = n.toLowerCase();
      return !lower.startsWith('cudart') && parts.every(p => lower.includes(p.toLowerCase()));
    });

  if (platform === 'win32') {
    const dv = gpuInfo.driverVersion || 0;

    if (gpuInfo.type === 'nvidia') {
      const cc = gpuInfo.computeCap;
      // Below Turing (7.5): Maxwell/Pascal/Volta — CUDA 13 dropped support for
      // these archs, so a cuda-13 build won't initialize on the GPU. Use cuda-12.
      if (cc != null && cc < 7.5) {
        return find('win', 'cuda-12.4') || find('win', 'cuda-12') || find('win', 'vulkan') || null;
      }
      if (dv >= 570) return find('win', 'cuda-13.1') || find('win', 'cuda-13') || find('win', 'vulkan') || null;
      if (dv >= 550) return find('win', 'cuda-12.4') || find('win', 'cuda-12') || find('win', 'vulkan') || null;
      return find('win', 'vulkan') || null;
    }
    if (gpuInfo.type === 'amd' || gpuInfo.type === 'intel') {
      return find('win', 'vulkan') || null;
    }
    // No GPU
    return find('win', 'cpu', 'x64') || find('win-cpu') || null;
  }

  if (platform === 'darwin') {
    if (arch === 'arm64') return find('macos', 'arm64') || find('macos') || null;
    return find('macos', 'x64') || find('macos') || null;
  }

  // Linux
  const hasGpu = gpuInfo.type !== 'none' && gpuInfo.variant !== 'cpu';
  if (hasGpu) {
    return find('ubuntu', 'vulkan', arch) || find('ubuntu', arch) || null;
  }
  // No GPU — avoid vulkan and rocm builds
  const candidate = assetNames.find(n =>
    n.toLowerCase().includes('ubuntu') &&
    n.toLowerCase().includes(arch) &&
    !n.toLowerCase().includes('vulkan') &&
    !n.toLowerCase().includes('rocm') &&
    !n.toLowerCase().includes('cuda')
  );
  return candidate || find('ubuntu', arch) || null;
}

/**
 * Download llama-server binary to binDir/llama/.
 * @param {string} binDir
 * @param {{ type: string, variant?: string, driverVersion?: number }} gpuInfo
 * @param {(msg: string, downloaded?: number, total?: number) => void} [onProgress]
 * @returns {Promise<void>}
 */
async function downloadLlamaServer(binDir, gpuInfo, onProgress, force = false) {
  const platform = process.platform;
  const llamaDir  = path.join(binDir, 'llama');
  const expectedTag = TOOL_VERSIONS.llama;

  if (!needsDownload(llamaDir, expectedTag, force)) {
    if (onProgress) onProgress('llama-server up to date, skipping.');
    return;
  }

  if (onProgress) onProgress('Fetching llama.cpp release info...');
  const releaseInfo = await fetchJSON(
    `https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/${expectedTag}`
  );

  const assets     = releaseInfo.assets || [];
  const assetNames = assets.map(a => a.name);

  const chosen = selectLlamaAsset(gpuInfo, assetNames);
  if (!chosen) {
    throw new Error(
      `Could not find a suitable llama.cpp asset for platform=${platform} gpu=${JSON.stringify(gpuInfo)}.\n` +
      `Available: ${assetNames.slice(0, 20).join(', ')}`
    );
  }

  const asset = assets.find(a => a.name === chosen);
  if (!asset) throw new Error(`Asset '${chosen}' not found in release.`);

  const isTarGz = asset.name.endsWith('.tar.gz');
  const ext     = isTarGz ? '.tar.gz' : '.zip';
  const tmpFile = path.join(os.tmpdir(), `llama_${Date.now()}${ext}`);

  if (onProgress) onProgress(`Downloading llama-server: ${asset.name}`);
  await downloadFile(asset.browser_download_url, tmpFile, (dl, total) => {
    if (onProgress) onProgress('Downloading llama-server...', dl, total);
  });

  const dlSize = fs.statSync(tmpFile).size;
  console.log(`[setup] Downloaded llama zip: ${tmpFile} (${Math.round(dlSize / 1024 / 1024)} MB)`);
  if (dlSize < 1000) throw new Error(`Downloaded file too small (${dlSize} bytes), likely corrupted`);
  if (onProgress) onProgress('Extracting llama-server...');
  fs.mkdirSync(llamaDir, { recursive: true });

  if (isTarGz) {
    await extractTarGz(tmpFile, llamaDir, null);
  } else {
    await extractZip(tmpFile, llamaDir, null);
  }

  try { fs.unlinkSync(tmpFile); } catch (_) {}

  // Ensure the binary is executable on Unix
  if (platform !== 'win32' && fs.existsSync(destExe)) {
    try { fs.chmodSync(destExe, 0o755); } catch (_) {}
  }

  // Extract variant from asset name (e.g. "llama-b8665-bin-win-cuda-12.4-x64.zip" → "cuda-12.4")
  const variantMatch = chosen.match(/(cuda-[\d.]+|vulkan|cpu)/);
  const llamaVariant = variantMatch ? variantMatch[1] : 'unknown';
  fs.writeFileSync(path.join(llamaDir, '.version'), JSON.stringify({
    tag: releaseInfo.tag_name || 'latest',
    variant: llamaVariant,
    asset: chosen,
  }), 'utf8');
  if (onProgress) onProgress('llama-server installed.');
}

/**
 * Download CUDA runtime DLLs for llama-server (Windows NVIDIA only).
 * @param {string} binDir
 * @param {{ type: string, driverVersion?: number, computeCap?: number|null }} gpuInfo
 * @param {(msg: string, downloaded?: number, total?: number) => void} [onProgress]
 * @returns {Promise<void>}
 */
async function downloadLlamaCudart(binDir, gpuInfo, onProgress, force = false) {
  const platform = process.platform;
  if (platform !== 'win32' || gpuInfo.type !== 'nvidia') return;

  const llamaDir = path.join(binDir, 'llama');
  if (!force) {
    const existingDlls = fs.existsSync(llamaDir)
      ? fs.readdirSync(llamaDir).filter(f => f.startsWith('cudart'))
      : [];
    if (existingDlls.length > 0) {
      if (onProgress) onProgress('CUDA runtime already present, skipping.');
      return;
    }
  }

  if (onProgress) onProgress('Fetching llama.cpp release info...');
  const releaseInfo = await fetchJSON(
    `https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/${TOOL_VERSIONS.llama}`
  );
  const assets = releaseInfo.assets || [];

  const dv = gpuInfo.driverVersion || 0;
  const cc = gpuInfo.computeCap;
  // Match the build selectLlamaAsset chose: old GPUs (cc < 7.5) run the cuda-12
  // build, so they need the cuda-12 runtime — never cuda-13 (mismatched DLLs).
  const cudaVariant = (cc != null && cc < 7.5)
    ? 'cuda-12'
    : (dv >= 570 ? 'cuda-13' : 'cuda-12');

  const cudartAsset = assets.find(a =>
    a.name.toLowerCase().includes('cudart') &&
    a.name.toLowerCase().includes('win') &&
    a.name.toLowerCase().includes(cudaVariant)
  );

  if (!cudartAsset) {
    if (onProgress) onProgress('No matching CUDA runtime asset found, skipping.');
    return;
  }

  if (onProgress) onProgress(`Downloading ${cudartAsset.name}...`);
  const tmpCudart = path.join(os.tmpdir(), `cudart_${Date.now()}.zip`);

  await downloadFile(cudartAsset.browser_download_url, tmpCudart, (dl, total) => {
    if (onProgress) onProgress('Downloading CUDA Runtime...', dl, total);
  });

  if (onProgress) onProgress('Extracting CUDA runtime DLLs...');
  fs.mkdirSync(llamaDir, { recursive: true });
  await extractZip(tmpCudart, llamaDir, null);
  try { fs.unlinkSync(tmpCudart); } catch (_) {}

  if (onProgress) onProgress('CUDA runtime installed.');
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

module.exports = {
  detectGPU,
  updatePyprojectSources,
  runUvSync,
  fetchJSON,
  downloadFile,
  extractZip,
  extractTarGz,
  selectLlamaAsset,
  downloadFFmpeg,
  downloadYtDlp,
  downloadSoundfonts,
  downloadLlamaServer,
  downloadLlamaCudart,
};
