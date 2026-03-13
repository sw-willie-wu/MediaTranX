<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  text: string
  format: 'md' | 'txt'
}>()

function escHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function isSepRow(line: string): boolean {
  return /^\s*\|[\s:|-]+\|\s*$/.test(line)
}

function parseCells(line: string): string[] {
  return line.replace(/^\s*\|/, '').replace(/\|\s*$/, '').split('|').map(c => c.trim())
}

const renderedHtml = computed(() => {
  if (props.format === 'txt') {
    return `<pre class="ocr-plain">${escHtml(props.text)}</pre>`
  }

  const lines = props.text.split('\n')
  const out: string[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]
    if (line.trim().startsWith('|')) {
      const tlines: string[] = []
      while (i < lines.length && lines[i].trim().startsWith('|')) { tlines.push(lines[i++]) }
      const rows = tlines.filter(l => !isSepRow(l))
      if (rows.length > 0) {
        let html = '<table class="ocr-table"><thead><tr>'
        for (const c of parseCells(rows[0])) html += `<th>${escHtml(c)}</th>`
        html += '</tr></thead>'
        if (rows.length > 1) {
          html += '<tbody>'
          for (const r of rows.slice(1)) {
            html += '<tr>'
            for (const c of parseCells(r)) html += `<td>${escHtml(c)}</td>`
            html += '</tr>'
          }
          html += '</tbody>'
        }
        out.push(html + '</table>')
      }
    } else if (line.trim().startsWith('#')) {
      const lvl = line.match(/^#{1,6}/)?.[0].length ?? 1
      out.push(`<h${lvl} class="ocr-heading">${escHtml(line.replace(/^#+\s*/, ''))}</h${lvl}>`)
      i++
    } else if (line.trim()) {
      out.push(`<p class="ocr-para">${escHtml(line)}</p>`)
      i++
    } else { i++ }
  }
  return out.join('')
})
</script>

<template>
  <div class="markdown-renderer" v-html="renderedHtml"></div>
</template>

<style>
/* non-scoped：v-html 無法被 scoped 選到 */
.ocr-modal-body .ocr-plain {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  font-size: inherit;
  color: inherit;
}

.ocr-modal-body .ocr-para { margin: 0 0 0.6em; }
.ocr-modal-body .ocr-para:last-child { margin-bottom: 0; }

.ocr-modal-body .ocr-heading {
  margin: 0.75em 0 0.35em;
  font-weight: 600;
  color: var(--text-primary);
}
.ocr-modal-body .ocr-heading:first-child { margin-top: 0; }

.ocr-modal-body .ocr-table {
  width: 100%;
  border-collapse: collapse;
  margin: 0.75em 0;
  font-size: 0.875rem;
}

.ocr-modal-body .ocr-table th,
.ocr-modal-body .ocr-table td {
  padding: 0.45rem 0.8rem;
  border: 1px solid var(--input-border);
  text-align: left;
  word-break: break-word;
}

.ocr-modal-body .ocr-table th {
  background: rgba(255,255,255,0.06);
  font-weight: 600;
  color: var(--text-primary);
}

.ocr-modal-body .ocr-table td { color: var(--text-secondary); }

.ocr-modal-body .ocr-table tr:nth-child(even) td {
  background: rgba(255,255,255,0.02);
}

[data-theme="light"] .ocr-modal-body .ocr-table th {
  background: rgba(0,0,0,0.04);
}

[data-theme="light"] .ocr-modal-body .ocr-table tr:nth-child(even) td {
  background: rgba(0,0,0,0.02);
}
</style>
