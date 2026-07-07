import { describe, it, expect } from 'vitest'
import { expandDropItems, hasDirectoryItem, capFolderFiles } from '../dropEntries'

function mockFileEntry(name: string): FileSystemFileEntry {
  return {
    isFile: true, isDirectory: false, name,
    file: (cb: (f: File) => void) => cb(new File(['x'], name)),
  } as unknown as FileSystemFileEntry
}

function mockDirEntry(name: string, children: FileSystemEntry[], batchSize = 100): FileSystemDirectoryEntry {
  return {
    isFile: false, isDirectory: true, name,
    createReader: () => {
      let offset = 0
      return {
        readEntries: (cb: (es: FileSystemEntry[]) => void) => {
          const batch = children.slice(offset, offset + batchSize)
          offset += batch.length
          cb(batch)
        },
      }
    },
  } as unknown as FileSystemDirectoryEntry
}

function mockItems(entries: (FileSystemEntry | null)[]): DataTransferItemList {
  return {
    length: entries.length,
    ...Object.fromEntries(entries.map((e, i) => [i, { webkitGetAsEntry: () => e }])),
  } as unknown as DataTransferItemList
}

describe('expandDropItems', () => {
  it('expands a directory of files (readEntries batches)', async () => {
    const children = Array.from({ length: 150 }, (_, i) => mockFileEntry(`f${i}.png`))
    const { files, truncated } = await expandDropItems(mockItems([mockDirEntry('d', children)]))
    expect(files.length).toBe(150) // readEntries 迴圈需跑兩批
    expect(truncated).toBe(false)
  })

  it('mixes plain files and directories', async () => {
    const items = mockItems([mockFileEntry('a.png'), mockDirEntry('d', [mockFileEntry('b.png')])])
    const { files } = await expandDropItems(items)
    expect(files.map(f => f.name).sort()).toEqual(['a.png', 'b.png'])
  })

  it('truncates at 500 files', async () => {
    const children = Array.from({ length: 600 }, (_, i) => mockFileEntry(`f${i}.png`))
    const { files, truncated } = await expandDropItems(mockItems([mockDirEntry('d', children)]))
    expect(files.length).toBe(500)
    expect(truncated).toBe(true)
  })

  it('stops descending past depth 8', async () => {
    let leaf: FileSystemEntry = mockFileEntry('deep.png')
    for (let i = 0; i < 9; i++) leaf = mockDirEntry(`d${i}`, [leaf])
    const { files } = await expandDropItems(mockItems([leaf]))
    expect(files.length).toBe(0)
  })

  it('detects directory items', () => {
    expect(hasDirectoryItem(mockItems([mockDirEntry('d', [])]))).toBe(true)
    expect(hasDirectoryItem(mockItems([mockFileEntry('a.png')]))).toBe(false)
    expect(hasDirectoryItem(mockItems([null]))).toBe(false)
  })
})

function fakeFolderFile(name: string, relPath: string): File {
  const f = new File(['x'], name, { type: 'image/png' })
  Object.defineProperty(f, 'webkitRelativePath', { value: relPath })
  return f
}

describe('capFolderFiles', () => {
  it('keeps depth-8 files and filters depth-9 (boundary mirrors expandDropItems)', () => {
    // 'r/d1/../d7/a.png' → split('/').length - 1 = 8（收）；多一層 d8 = 9（濾）
    const depth8 = fakeFolderFile('a.png', 'r/d1/d2/d3/d4/d5/d6/d7/a.png')
    const depth9 = fakeFolderFile('b.png', 'r/d1/d2/d3/d4/d5/d6/d7/d8/b.png')
    const { files, truncated } = capFolderFiles([depth8, depth9])
    expect(files).toEqual([depth8])
    expect(truncated).toBe(false) // 深度濾除不算 truncated（對齊拖曳的靜默略過）
  })

  it('caps at 500 keeping the first 500 and sets truncated', () => {
    const many = Array.from({ length: 501 }, (_, i) => fakeFolderFile(`f${i}.png`, `r/f${i}.png`))
    const { files, truncated } = capFolderFiles(many)
    expect(files).toHaveLength(500)
    expect(files[0]).toBe(many[0])
    expect(files[499]).toBe(many[499])
    expect(truncated).toBe(true)
  })

  it('returns empty non-truncated result for empty input', () => {
    expect(capFolderFiles([])).toEqual({ files: [], truncated: false })
  })
})
