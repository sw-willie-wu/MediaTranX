/* eslint-disable @typescript-eslint/no-explicit-any */
declare module '*.vue' {
    import { DefineComponent } from 'vue'
    // eslint-disable-next-line @typescript-eslint/no-empty-object-type
    const component: DefineComponent<{}, {}, any>
    export default component
  }
/* eslint-enable @typescript-eslint/no-explicit-any */

interface SaveFileDialogOptions {
  title?: string
  defaultPath?: string
  filters?: { name: string; extensions: string[] }[]
}

interface Window {
  electron?: {
    minimize: () => void
    maximize: () => void
    close: () => void
    isMaximized: () => Promise<boolean>
    onMaximizeChange: (callback: (value: boolean) => void) => void
    selectFolder: () => Promise<string | null>
    saveFileDialog: (options: SaveFileDialogOptions) => Promise<string | null>
    getFileSourceDir: (name: string, size: number, lastModified: number) => string | null
    downloadToPath: (url: string, destPath: string, srcPath?: string) => Promise<void>
    showItemInFolder: (filePath: string) => void
    openPath: (filePath: string) => Promise<string>
    fileExists: (filePath: string) => Promise<boolean>
    readLocalFile: (filePath: string) => Promise<Uint8Array>
    restart: () => void
  }
}