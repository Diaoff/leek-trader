function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function sanitizeUrl(url: string): string {
  const normalized = url.trim()
  if (/^https?:\/\//i.test(normalized)) {
    return normalized
  }
  return '#'
}

function renderInline(value: string): string {
  let html = escapeHtml(value)
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label: string, url: string) => {
    return `<a href="${sanitizeUrl(url)}" target="_blank" rel="noreferrer">${label}</a>`
  })
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/(^|[^\*])\*([^*]+)\*/g, '$1<em>$2</em>')
  return html
}

function flushParagraph(blocks: string[], paragraphLines: string[]): void {
  if (paragraphLines.length === 0) {
    return
  }
  blocks.push(`<p>${renderInline(paragraphLines.join('<br>'))}</p>`)
  paragraphLines.length = 0
}

function flushList(blocks: string[], listType: 'ul' | 'ol' | null, listItems: string[]): 'ul' | 'ol' | null {
  if (!listType || listItems.length === 0) {
    listItems.length = 0
    return null
  }
  blocks.push(`<${listType}>${listItems.map((item) => `<li>${renderInline(item)}</li>`).join('')}</${listType}>`)
  listItems.length = 0
  return null
}

function flushQuote(blocks: string[], quoteLines: string[]): void {
  if (quoteLines.length === 0) {
    return
  }
  blocks.push(`<blockquote>${quoteLines.map((line) => renderInline(line)).join('<br>')}</blockquote>`)
  quoteLines.length = 0
}

export function renderMarkdown(value: string): string {
  const lines = value.replace(/\r\n/g, '\n').split('\n')
  const blocks: string[] = []
  const paragraphLines: string[] = []
  const listItems: string[] = []
  const quoteLines: string[] = []

  let listType: 'ul' | 'ol' | null = null
  let inCodeBlock = false
  let codeFenceLanguage = ''
  let codeLines: string[] = []

  for (const line of lines) {
    if (line.trim().startsWith('```')) {
      flushParagraph(blocks, paragraphLines)
      flushQuote(blocks, quoteLines)
      listType = flushList(blocks, listType, listItems)

      if (!inCodeBlock) {
        inCodeBlock = true
        codeFenceLanguage = line.trim().slice(3).trim()
        codeLines = []
      } else {
        const languageAttr = codeFenceLanguage ? ` data-language="${escapeHtml(codeFenceLanguage)}"` : ''
        blocks.push(`<pre><code${languageAttr}>${escapeHtml(codeLines.join('\n'))}</code></pre>`)
        inCodeBlock = false
        codeFenceLanguage = ''
        codeLines = []
      }
      continue
    }

    if (inCodeBlock) {
      codeLines.push(line)
      continue
    }

    if (!line.trim()) {
      flushParagraph(blocks, paragraphLines)
      flushQuote(blocks, quoteLines)
      listType = flushList(blocks, listType, listItems)
      continue
    }

    const headingMatch = line.match(/^(#{1,6})\s+(.*)$/)
    if (headingMatch) {
      flushParagraph(blocks, paragraphLines)
      flushQuote(blocks, quoteLines)
      listType = flushList(blocks, listType, listItems)
      const level = headingMatch[1].length
      blocks.push(`<h${level}>${renderInline(headingMatch[2])}</h${level}>`)
      continue
    }

    const quoteMatch = line.match(/^>\s?(.*)$/)
    if (quoteMatch) {
      flushParagraph(blocks, paragraphLines)
      listType = flushList(blocks, listType, listItems)
      quoteLines.push(quoteMatch[1])
      continue
    }

    const unorderedMatch = line.match(/^[-*+]\s+(.*)$/)
    if (unorderedMatch) {
      flushParagraph(blocks, paragraphLines)
      flushQuote(blocks, quoteLines)
      if (listType && listType !== 'ul') {
        listType = flushList(blocks, listType, listItems)
      }
      listType = 'ul'
      listItems.push(unorderedMatch[1])
      continue
    }

    const orderedMatch = line.match(/^\d+\.\s+(.*)$/)
    if (orderedMatch) {
      flushParagraph(blocks, paragraphLines)
      flushQuote(blocks, quoteLines)
      if (listType && listType !== 'ol') {
        listType = flushList(blocks, listType, listItems)
      }
      listType = 'ol'
      listItems.push(orderedMatch[1])
      continue
    }

    flushQuote(blocks, quoteLines)
    listType = flushList(blocks, listType, listItems)
    paragraphLines.push(line)
  }

  if (inCodeBlock) {
    const languageAttr = codeFenceLanguage ? ` data-language="${escapeHtml(codeFenceLanguage)}"` : ''
    blocks.push(`<pre><code${languageAttr}>${escapeHtml(codeLines.join('\n'))}</code></pre>`)
  }

  flushParagraph(blocks, paragraphLines)
  flushQuote(blocks, quoteLines)
  flushList(blocks, listType, listItems)

  return blocks.join('')
}
