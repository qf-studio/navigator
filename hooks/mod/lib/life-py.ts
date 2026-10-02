// Python-compatibility helpers for the lifecycle ops (TASK-84 step 5d). The Python ops these
// mirror format text with str methods and the json module; byte parity needs their exact
// rules: str.isspace whitespace, str.splitlines, text-mode universal newlines, CPython's C JSON
// scanner (error messages and positions), json.dumps (ensure_ascii, float repr, key order).
// Strings are compared and sliced in code points, as Python does.
import type { Io } from './types'

// ---- str methods -----------------------------------------------------------------------

/** Characters for which Python's str.isspace() is true. */
export const PY_SPACE =
  '\\t\\n\\x0b\\x0c\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000'
const LEAD = new RegExp(`^[${PY_SPACE}]+`, 'u')
const TRAIL = new RegExp(`[${PY_SPACE}]+$`, 'u')

export const strip = (s: string): string => s.replace(LEAD, '').replace(TRAIL, '')

/** str.strip(chars) / lstrip(chars) for a literal character set. */
export const stripChars = (s: string, chars: string, side: 'both' | 'left' = 'both'): string => {
  const set = new Set(Array.from(chars))
  const cps = Array.from(s)
  let a = 0
  let b = cps.length
  while (a < b && set.has(cps[a] as string)) a += 1
  if (side === 'both') while (b > a && set.has(cps[b - 1] as string)) b -= 1
  return cps.slice(a, b).join('')
}

/** str.splitlines() (no keepends). */
const LINE_BREAKS = new RegExp('\\r\\n|[\\n\\r\\x0b\\x0c\\x1c\\x1d\\x1e\\x85\\u2028\\u2029]', 'u')

export const splitlines = (s: string): string[] => {
  const parts = s.split(LINE_BREAKS)
  if (parts.length > 0 && parts[parts.length - 1] === '') parts.pop()
  return parts
}

/** Python str.split() with no arguments. */
export const splitWs = (s: string): string[] => s.split(new RegExp(`[${PY_SPACE}]+`, 'u')).filter(Boolean)

export const cpLen = (s: string): number => Array.from(s).length
export const cpSlice = (s: string, start: number, end?: number): string => {
  const cps = Array.from(s)
  const n = cps.length
  const norm = (i: number | undefined, dflt: number): number =>
    i === undefined ? dflt : i < 0 ? Math.max(0, n + i) : Math.min(i, n)
  return cps.slice(norm(start, 0), norm(end, n)).join('')
}

/** Text-mode read: CRLF and lone CR become LF (universal newlines). */
export const universalNewlines = (s: string): string => s.replace(/\r\n?/g, '\n')

type Stat = { kind: 'file' | 'dir' | 'other'; mtimeMs: number }

/** io.stat when wired, else the parent directory's listing. null when missing. */
export const statOf = async (io: Io, path: string): Promise<Stat | null> => {
  if (io.stat) {
    try {
      return await io.stat(path)
    } catch {
      return null
    }
  }
  const at = path.lastIndexOf('/')
  const dir = at <= 0 ? '/' : path.slice(0, at)
  const name = path.slice(at + 1)
  try {
    const hit = (await io.list(dir)).find(e => e.name === name)
    return hit === undefined ? null : { kind: hit.kind, mtimeMs: hit.mtimeMs }
  } catch {
    return null
  }
}

export const isFile = async (io: Io, path: string): Promise<boolean> =>
  (await statOf(io, path))?.kind === 'file'

/** hio.safe_read: text or null; `maxChars` head-truncates in code points. */
export const safeRead = async (io: Io, path: string, maxChars?: number): Promise<string | null> => {
  const st = await statOf(io, path)
  if (st === null || st.kind !== 'file') return null
  let text: string
  try {
    text = universalNewlines(await io.read(path))
  } catch {
    return null
  }
  return maxChars === undefined ? text : cpSlice(text, 0, maxChars)
}

/** hio.safe_json: a JSON object (PyDict) or null on missing/corrupt/non-object. */
export const safeJson = async (io: Io, path: string): Promise<PyDict | null> => {
  const raw = await safeRead(io, path)
  if (raw === null || !strip(raw)) return null
  try {
    const v = loads(raw)
    return v instanceof Map ? v : null
  } catch {
    return null
  }
}

/** Subprocess stdout in text mode (universal newlines). */
export const textOut = (stdout: string): string => universalNewlines(stdout)

// ---- Python values ---------------------------------------------------------------------

export class PyInt { constructor(readonly v: bigint) {} }
export class PyFloat { constructor(readonly v: number) {} }
export type PyDict = Map<string, PyValue>
export type PyValue = null | boolean | string | PyInt | PyFloat | PyValue[] | PyDict

export const isDict = (v: unknown): v is PyDict => v instanceof Map

/** Python truthiness. */
export const truthy = (v: PyValue | undefined): boolean => {
  if (v === null || v === undefined || v === false) return false
  if (v === true) return true
  if (typeof v === 'string') return v.length > 0
  if (v instanceof PyInt) return v.v !== 0n
  if (v instanceof PyFloat) return v.v !== 0
  if (Array.isArray(v)) return v.length > 0
  return v.size > 0
}

/** dict.get(key, default). */
export const get = (d: PyDict, key: string, dflt: PyValue = null): PyValue =>
  d.has(key) ? (d.get(key) as PyValue) : dflt

/** `(x or {}).get(key)`: Python raises AttributeError on a truthy non-dict. */
export const orEmptyGet = (v: PyValue, key: string): PyValue => {
  if (!truthy(v)) return null
  if (!isDict(v)) throw new TypeError("'object' has no attribute 'get'")
  return get(v, key)
}

/** Python `type(v).__name__`. */
export const typeName = (v: PyValue): string =>
  v === null ? 'NoneType' : typeof v === 'boolean' ? 'bool' : typeof v === 'string' ? 'str'
    : v instanceof PyInt ? 'int' : v instanceof PyFloat ? 'float' : Array.isArray(v) ? 'list' : 'dict'

/** float.__repr__. */
export const floatRepr = (x: number): string => {
  if (Number.isNaN(x)) return 'nan'
  if (x === Infinity) return 'inf'
  if (x === -Infinity) return '-inf'
  if (x === 0) return Object.is(x, -0) ? '-0.0' : '0.0'
  const sign = x < 0 ? '-' : ''
  const [mant, expStr] = Math.abs(x).toExponential().split('e')
  const digits = (mant ?? '').replace('.', '')
  const decpt = Number(expStr) + 1
  if (decpt > -4 && decpt <= 16) {
    if (decpt <= 0) return `${sign}0.${'0'.repeat(-decpt)}${digits}`
    if (decpt >= digits.length) return `${sign}${digits}${'0'.repeat(decpt - digits.length)}.0`
    return `${sign}${digits.slice(0, decpt)}.${digits.slice(decpt)}`
  }
  const e = decpt - 1
  const m = digits.length === 1 ? digits : `${digits[0]}.${digits.slice(1)}`
  return `${sign}${m}e${e < 0 ? '-' : '+'}${String(Math.abs(e)).padStart(2, '0')}`
}

/** str(v) for a PyValue (containers via repr). */
export const pyStr = (v: PyValue | undefined): string => {
  if (v === undefined || v === null) return 'None'
  if (v === true) return 'True'
  if (v === false) return 'False'
  if (typeof v === 'string') return v
  if (v instanceof PyInt) return v.v.toString()
  if (v instanceof PyFloat) return floatRepr(v.v)
  return pyRepr(v)
}

const strRepr = (s: string): string => {
  const quote = s.includes("'") && !s.includes('"') ? '"' : "'"
  let out = ''
  for (const ch of s) {
    const c = ch.codePointAt(0) as number
    if (ch === '\\') out += '\\\\'
    else if (ch === quote) out += `\\${quote}`
    else if (ch === '\n') out += '\\n'
    else if (ch === '\r') out += '\\r'
    else if (ch === '\t') out += '\\t'
    else if (c < 0x20 || c === 0x7f) out += `\\x${c.toString(16).padStart(2, '0')}`
    else out += ch
  }
  return quote + out + quote
}

/** repr(v) — enough for containers of JSON values. */
export const pyRepr = (v: PyValue): string => {
  if (typeof v === 'string') return strRepr(v)
  if (Array.isArray(v)) return `[${v.map(pyRepr).join(', ')}]`
  if (isDict(v)) return `{${[...v].map(([k, x]) => `${strRepr(k)}: ${pyRepr(x)}`).join(', ')}}`
  return pyStr(v)
}

/** A plain JS value (engine payload, layered config) as a PyValue. */
export const fromJs = (v: unknown): PyValue => {
  if (v === null || v === undefined) return null
  if (typeof v === 'boolean' || typeof v === 'string') return v
  if (typeof v === 'number') return Number.isInteger(v) ? new PyInt(BigInt(v)) : new PyFloat(v)
  if (Array.isArray(v)) return v.map(fromJs)
  if (typeof v === 'object') return new Map(Object.entries(v as object).map(([k, x]) => [k, fromJs(x)]))
  return String(v)
}

// ---- json.loads (CPython C scanner semantics) -------------------------------------------

export class JSONDecodeError extends Error {
  constructor(readonly msg: string, readonly doc: string[], readonly pos: number) {
    super(msg)
    const before = doc.slice(0, pos)
    this.lineno = before.filter(c => c === '\n').length + 1
    const last = before.lastIndexOf('\n')
    this.colno = pos - last
  }
  readonly lineno: number
  readonly colno: number
}

/** ValueError that is not a decode error (int conversion limit). */
export class PyValueError extends Error {}

class StopIteration { constructor(readonly value: number) {} }

const WS = new Set([' ', '\t', '\n', '\r'])
const isDigit = (c: string | undefined): boolean => c !== undefined && c >= '0' && c <= '9'
const HEX = /^[0-9a-fA-F]$/

export const loads = (text: string): PyValue => {
  const s = Array.from(text)
  const n = s.length
  const end = n - 1
  if (s[0] === '\ufeff') throw new JSONDecodeError('Unexpected UTF-8 BOM (decode using utf-8-sig)', s, 0)

  const scanString = (start: number): [string, number] => {
    const begin = start - 1
    let endIdx = start
    let out = ''
    for (;;) {
      let next = endIdx
      let c = ''
      for (; next < n; next += 1) {
        c = s[next] as string
        if (c === '"' || c === '\\') break
        if ((c.codePointAt(0) as number) <= 0x1f) throw new JSONDecodeError('Invalid control character at', s, next)
      }
      if (next >= n || (c !== '"' && c !== '\\')) throw new JSONDecodeError('Unterminated string starting at', s, begin)
      out += s.slice(endIdx, next).join('')
      next += 1
      if (c === '"') return [out, next]
      if (next === n) throw new JSONDecodeError('Unterminated string starting at', s, begin)
      const e = s[next] as string
      if (e !== 'u') {
        endIdx = next + 1
        const map: Record<string, string> = { '"': '"', '\\': '\\', '/': '/', b: '\b', f: '\f', n: '\n', r: '\r', t: '\t' }
        const ch = map[e]
        if (ch === undefined) throw new JSONDecodeError('Invalid \\escape', s, endIdx - 2)
        out += ch
        continue
      }
      next += 1
      endIdx = next + 4
      if (endIdx >= n) throw new JSONDecodeError('Invalid \\uXXXX escape', s, next - 1)
      const hex4 = (from: number, at: number): number => {
        const h = s.slice(from, from + 4)
        if (h.length < 4 || !h.every(x => HEX.test(x))) throw new JSONDecodeError('Invalid \\uXXXX escape', s, at)
        return Number.parseInt(h.join(''), 16)
      }
      let cp = hex4(next, endIdx - 5)
      next = endIdx
      if (cp >= 0xd800 && cp <= 0xdbff && endIdx + 6 < n && s[next] === '\\' && s[next + 1] === 'u') {
        const second = endIdx + 6
        const c2 = hex4(next + 2, second - 5)
        if (c2 >= 0xdc00 && c2 <= 0xdfff) {
          cp = 0x10000 + ((cp - 0xd800) << 10) + (c2 - 0xdc00)
          endIdx = second
        }
      }
      out += cp >= 0xd800 && cp <= 0xdfff ? String.fromCharCode(cp) : String.fromCodePoint(cp)
    }
  }

  const skipWs = (i: number): number => {
    let k = i
    while (k <= end && WS.has(s[k] as string)) k += 1
    return k
  }

  const matchNumber = (start: number): [PyValue, number] => {
    let idx = start
    if (s[idx] === '-') {
      idx += 1
      if (idx > end) throw new StopIteration(start)
    }
    if ((s[idx] as string) >= '1' && (s[idx] as string) <= '9') {
      idx += 1
      while (idx <= end && isDigit(s[idx])) idx += 1
    } else if (s[idx] === '0') idx += 1
    else throw new StopIteration(start)
    let isFloat = false
    if (idx < end && s[idx] === '.' && isDigit(s[idx + 1])) {
      isFloat = true
      idx += 2
      while (idx <= end && isDigit(s[idx])) idx += 1
    }
    if (idx < end && (s[idx] === 'e' || s[idx] === 'E')) {
      const eStart = idx
      idx += 1
      if (idx < end && (s[idx] === '-' || s[idx] === '+')) idx += 1
      while (idx <= end && isDigit(s[idx])) idx += 1
      if (isDigit(s[idx - 1])) isFloat = true
      else idx = eStart
    }
    const lit = s.slice(start, idx).join('')
    if (isFloat) return [new PyFloat(Number(lit)), idx]
    if (lit.replace('-', '').length > 4300) throw new PyValueError('Exceeds the limit (4300 digits)')
    return [new PyInt(BigInt(lit)), idx]
  }

  const word = (i: number, w: string): boolean => s.slice(i, i + w.length).join('') === w

  const scanOnce = (idx: number): [PyValue, number] => {
    if (idx < 0 || idx >= n) throw new StopIteration(idx)
    const c = s[idx]
    if (c === '"') return scanString(idx + 1)
    if (c === '{') return parseObject(idx + 1)
    if (c === '[') return parseArray(idx + 1)
    if (c === 'n' && word(idx, 'null')) return [null, idx + 4]
    if (c === 't' && word(idx, 'true')) return [true, idx + 4]
    if (c === 'f' && word(idx, 'false')) return [false, idx + 5]
    if (c === 'N' && word(idx, 'NaN')) return [new PyFloat(Number.NaN), idx + 3]
    if (c === 'I' && word(idx, 'Infinity')) return [new PyFloat(Infinity), idx + 8]
    if (c === '-' && word(idx, '-Infinity')) return [new PyFloat(-Infinity), idx + 9]
    return matchNumber(idx)
  }

  const parseObject = (start: number): [PyValue, number] => {
    const obj: PyDict = new Map()
    let idx = skipWs(start)
    if (idx > end || s[idx] !== '}') {
      for (;;) {
        if (idx > end || s[idx] !== '"') {
          throw new JSONDecodeError('Expecting property name enclosed in double quotes', s, idx)
        }
        const [key, afterKey] = scanString(idx + 1)
        idx = skipWs(afterKey)
        if (idx > end || s[idx] !== ':') throw new JSONDecodeError("Expecting ':' delimiter", s, idx)
        idx = skipWs(idx + 1)
        const [val, afterVal] = scanOnce(idx)
        obj.set(key, val)
        idx = skipWs(afterVal)
        if (idx <= end && s[idx] === '}') break
        if (idx > end || s[idx] !== ',') throw new JSONDecodeError("Expecting ',' delimiter", s, idx)
        const comma = idx
        idx = skipWs(idx + 1)
        if (idx <= end && s[idx] === '}') {
          throw new JSONDecodeError('Illegal trailing comma before end of object', s, comma)
        }
      }
    }
    return [obj, idx + 1]
  }

  const parseArray = (start: number): [PyValue, number] => {
    const arr: PyValue[] = []
    let idx = skipWs(start)
    if (idx > end || s[idx] !== ']') {
      for (;;) {
        const [val, after] = scanOnce(idx)
        arr.push(val)
        idx = skipWs(after)
        if (idx <= end && s[idx] === ']') break
        if (idx > end || s[idx] !== ',') throw new JSONDecodeError("Expecting ',' delimiter", s, idx)
        const comma = idx
        idx = skipWs(idx + 1)
        if (idx <= end && s[idx] === ']') {
          throw new JSONDecodeError('Illegal trailing comma before end of array', s, comma)
        }
      }
    }
    return [arr, idx + 1]
  }

  const decodeAt = (idx: number): [PyValue, number] => {
    try {
      return scanOnce(idx)
    } catch (e) {
      if (e instanceof StopIteration) throw new JSONDecodeError('Expecting value', s, e.value)
      throw e
    }
  }

  const [value, after] = decodeAt(skipWs(0))
  const tail = skipWs(after)
  if (tail !== n) throw new JSONDecodeError('Extra data', s, tail)
  return value
}

// ---- json.dumps ------------------------------------------------------------------------

const escapeAscii = (s: string): string => {
  let out = '"'
  for (let i = 0; i < s.length; i += 1) {
    const code = s.charCodeAt(i)
    const ch = s[i] as string
    if (ch === '\\') out += '\\\\'
    else if (ch === '"') out += '\\"'
    else if (ch === '\n') out += '\\n'
    else if (ch === '\r') out += '\\r'
    else if (ch === '\t') out += '\\t'
    else if (ch === '\b') out += '\\b'
    else if (ch === '\f') out += '\\f'
    else if (code < 0x20 || code > 0x7e) out += `\\u${code.toString(16).padStart(4, '0')}`
    else out += ch
  }
  return `${out}"`
}

const floatJson = (x: number): string =>
  Number.isNaN(x) ? 'NaN' : x === Infinity ? 'Infinity' : x === -Infinity ? '-Infinity' : floatRepr(x)

/** json.dumps(v, indent=?) with ensure_ascii=True; default separators. */
export const dumps = (v: PyValue, indent?: number): string => {
  const itemSep = indent === undefined ? ', ' : ','
  const enc = (x: PyValue, level: number): string => {
    if (x === null) return 'null'
    if (x === true) return 'true'
    if (x === false) return 'false'
    if (typeof x === 'string') return escapeAscii(x)
    if (x instanceof PyInt) return x.v.toString()
    if (x instanceof PyFloat) return floatJson(x.v)
    const items: string[] = Array.isArray(x)
      ? x.map(y => enc(y, level + 1))
      : [...x].map(([k, y]) => `${escapeAscii(k)}: ${enc(y, level + 1)}`)
    const [open, close] = Array.isArray(x) ? ['[', ']'] : ['{', '}']
    if (items.length === 0) return open + close
    if (indent === undefined) return open + items.join(itemSep) + close
    const inner = `\n${' '.repeat(indent * (level + 1))}`
    return open + inner + items.join(itemSep + inner) + `\n${' '.repeat(indent * level)}` + close
  }
  return enc(v, 0)
}
