import { describe, it, expect } from 'vitest'
import { expandDropItems, hasDirectoryItem } from '../dropEntries'

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
