declare module '*.vue' {
    import { DefineComponent } from 'vue'
    const component: DefineComponent<{}, {}, any>
    export default component
  }

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
  }
}