// SHA-256 hex digest of a string's UTF-8 bytes, matching Python's
// hashlib.sha256(s.encode('utf-8', 'replace')).hexdigest(). The mod runs without Node
// crypto, and the Stop gate's working-tree digest must equal the one Python writes to the
// shared state file, so this is a straight FIPS 180-4 implementation.

const K = [
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]

/** UTF-8 bytes; a lone surrogate becomes '?' as with Python's encode('utf-8', 'replace'). */
export const utf8 = (s: string): number[] => {
  const out: number[] = []
  for (const ch of s) {
    const c = ch.codePointAt(0) ?? 0
    if (c >= 0xd800 && c <= 0xdfff) out.push(0x3f)
    else if (c < 0x80) out.push(c)
    else if (c < 0x800) out.push(0xc0 | (c >> 6), 0x80 | (c & 63))
    else if (c < 0x10000) out.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 63), 0x80 | (c & 63))
    else out.push(0xf0 | (c >> 18), 0x80 | ((c >> 12) & 63), 0x80 | ((c >> 6) & 63), 0x80 | (c & 63))
  }
  return out
}

const rotr = (x: number, n: number): number => ((x >>> n) | (x << (32 - n))) >>> 0
const at = (a: ArrayLike<number>, i: number): number => a[i] ?? 0

export const sha256Hex = (text: string): string => {
  const bytes = utf8(text)
  const bitLen = bytes.length * 8
  bytes.push(0x80)
  while (bytes.length % 64 !== 56) bytes.push(0)
  const hi = Math.floor(bitLen / 0x100000000)
  const lo = bitLen >>> 0
  bytes.push((hi >>> 24) & 255, (hi >>> 16) & 255, (hi >>> 8) & 255, hi & 255,
    (lo >>> 24) & 255, (lo >>> 16) & 255, (lo >>> 8) & 255, lo & 255)
  const h = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab,
    0x5be0cd19]
  const w = new Array<number>(64).fill(0)
  for (let off = 0; off < bytes.length; off += 64) {
    for (let i = 0; i < 16; i += 1) {
      const j = off + i * 4
      w[i] = ((at(bytes, j) << 24) | (at(bytes, j + 1) << 16) | (at(bytes, j + 2) << 8)
        | at(bytes, j + 3)) >>> 0
    }
    for (let i = 16; i < 64; i += 1) {
      const x = at(w, i - 15)
      const y = at(w, i - 2)
      const s0 = rotr(x, 7) ^ rotr(x, 18) ^ (x >>> 3)
      const s1 = rotr(y, 17) ^ rotr(y, 19) ^ (y >>> 10)
      w[i] = (at(w, i - 16) + s0 + at(w, i - 7) + s1) >>> 0
    }
    let a = at(h, 0)
    let b = at(h, 1)
    let c = at(h, 2)
    let d = at(h, 3)
    let e = at(h, 4)
    let f = at(h, 5)
    let g = at(h, 6)
    let k = at(h, 7)
    for (let i = 0; i < 64; i += 1) {
      const S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)
      const ch = (e & f) ^ (~e & g)
      const t1 = (k + S1 + ch + at(K, i) + at(w, i)) >>> 0
      const S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)
      const maj = (a & b) ^ (a & c) ^ (b & c)
      const t2 = (S0 + maj) >>> 0
      k = g
      g = f
      f = e
      e = (d + t1) >>> 0
      d = c
      c = b
      b = a
      a = (t1 + t2) >>> 0
    }
    const add = [a, b, c, d, e, f, g, k]
    for (let i = 0; i < 8; i += 1) h[i] = (at(h, i) + at(add, i)) >>> 0
  }
  return h.map(x => x.toString(16).padStart(8, '0')).join('')
}
