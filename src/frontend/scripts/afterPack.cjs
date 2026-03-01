'use strict'

const { execFileSync } = require('child_process')
const path = require('path')
const fs = require('fs')

module.exports = async (context) => {
  if (context.electronPlatformName !== 'win32') return

  const rcedit = path.join(
    __dirname,
    '../node_modules/electron-winstaller/vendor/rcedit.exe'
  )

  if (!fs.existsSync(rcedit)) {
    console.warn('[afterPack] rcedit.exe not found, skipping icon embedding')
    return
  }

  const exePath = path.join(context.appOutDir, 'MediaTranX.exe')
  if (!fs.existsSync(exePath)) {
    console.warn('[afterPack] MediaTranX.exe not found at', exePath)
    return
  }

  const iconPath = path.join(__dirname, '../icon.ico')
  if (!fs.existsSync(iconPath)) {
    console.warn('[afterPack] icon.ico not found at', iconPath)
    return
  }

  console.log('[afterPack] Embedding icon into', exePath)
  execFileSync(rcedit, [exePath, '--set-icon', iconPath])
  console.log('[afterPack] Icon embedded successfully')
}
