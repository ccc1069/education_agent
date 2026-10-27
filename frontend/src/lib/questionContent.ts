/** 题目 content 归一化与展示文案(兼容 stem / question / 字符串 JSON)。 */

export interface ParsedOption {
  key: string
  text: string
}

export interface ParsedQuestionContent {
  stem: string
  options: ParsedOption[]
  raw: Record<string, unknown> | null
}

function tryParseObject(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>
  }
  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (!trimmed) return null
    if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
      try {
        const parsed = JSON.parse(trimmed) as unknown
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          return parsed as Record<string, unknown>
        }
      } catch {
        return null
      }
    }
  }
  return null
}

function normalizeOption(raw: unknown, index: number): ParsedOption | null {
  const fallbackKey = String.fromCharCode(65 + index)
  if (typeof raw === 'string') {
    const text = raw.trim()
    return text ? { key: fallbackKey, text } : null
  }
  if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    const o = raw as Record<string, unknown>
    const text = [o.text, o.label, o.value, o.content]
      .find((v): v is string => typeof v === 'string' && v.trim().length > 0)
      ?.trim()
    if (!text) return null
    const key =
      typeof o.key === 'string' && o.key.trim()
        ? o.key.trim().toUpperCase()
        : fallbackKey
    return { key, text }
  }
  return null
}

export function parseQuestionContent(content: unknown): ParsedQuestionContent {
  const obj = tryParseObject(content)
  if (obj) {
    const stemCandidates = [obj.stem, obj.question, obj.prompt, obj.text, obj.title]
    const stem =
      stemCandidates.find((v): v is string => typeof v === 'string' && v.trim().length > 0) ?? ''
    const options = Array.isArray(obj.options)
      ? obj.options
          .map((o, i) => normalizeOption(o, i))
          .filter((o): o is ParsedOption => o != null)
      : []
    return { stem, options, raw: obj }
  }
  if (typeof content === 'string') {
    return { stem: content, options: [], raw: null }
  }
  return { stem: '', options: [], raw: null }
}

export function previewQuestionText(content: unknown, maxLen = 80): string {
  const { stem } = parseQuestionContent(content)
  if (!stem) return ''
  return stem.length > maxLen ? `${stem.slice(0, maxLen)}…` : stem
}
