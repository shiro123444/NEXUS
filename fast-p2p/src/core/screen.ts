import { RGBA, TextAttributes, type ColorInput } from "./types"

export interface ANSIOptions {
  reset?: boolean
  bold?: boolean
  dim?: boolean
  italic?: boolean
  underline?: boolean
  blink?: boolean
  reverse?: boolean
  hidden?: boolean
  strikethrough?: boolean
  fg?: ColorInput
  bg?: ColorInput
}

export const ANSI = {
  RESET: "\x1b[0m",
  BOLD: "\x1b[1m",
  DIM: "\x1b[2m",
  ITALIC: "\x1b[3m",
  UNDERLINE: "\x1b[4m",
  BLINK: "\x1b[5m",
  REVERSE: "\x1b[7m",
  HIDDEN: "\x1b[8m",
  STRIKETHROUGH: "\x1b[9m",

  moveTo(row: number, col: number): string {
    return `\x1b[${row};${col}H`
  },

  moveUp(n: number): string {
    return `\x1b[${n}A`
  },

  moveDown(n: number): string {
    return `\x1b[${n}B`
  },

  moveRight(n: number): string {
    return `\x1b[${n}C`
  },

  moveLeft(n: number): string {
    return `\x1b[${n}D`
  },

  saveCursor(): string {
    return "\x1b[s"
  },

  restoreCursor(): string {
    return "\x1b[u"
  },

  hideCursor(): string {
    return "\x1b[?25l"
  },

  showCursor(): string {
    return "\x1b[?25h"
  },

  clear(): string {
    return "\x1b[2J"
  },

  clearLine(): string {
    return "\x1b[2K"
  },

  fg(color: ColorInput): string {
    if (color === undefined) return ""
    if (typeof color === "string") {
      const rgba = RGBA.fromHex(color)
      return `\x1b[38;2;${Math.round(rgba.r * 255)};${Math.round(rgba.g * 255)};${Math.round(rgba.b * 255)}m`
    }
    return `\x1b[38;2;${Math.round(color.r * 255)};${Math.round(color.g * 255)};${Math.round(color.b * 255)}m`
  },

  bg(color: ColorInput): string {
    if (color === undefined) return ""
    if (typeof color === "string") {
      const rgba = RGBA.fromHex(color)
      return `\x1b[48;2;${Math.round(rgba.r * 255)};${Math.round(rgba.g * 255)};${Math.round(rgba.b * 255)}m`
    }
    return `\x1b[48;2;${Math.round(color.r * 255)};${Math.round(color.g * 255)};${Math.round(color.b * 255)}m`
  },

  attrs(attrs: TextAttributes): string {
    const parts: string[] = []
    if (attrs & TextAttributes.BOLD) parts.push(ANSI.BOLD)
    if (attrs & TextAttributes.DIM) parts.push(ANSI.DIM)
    if (attrs & TextAttributes.ITALIC) parts.push(ANSI.ITALIC)
    if (attrs & TextAttributes.UNDERLINE) parts.push(ANSI.UNDERLINE)
    if (attrs & TextAttributes.BLINK) parts.push(ANSI.BLINK)
    if (attrs & TextAttributes.REVERSE) parts.push(ANSI.REVERSE)
    if (attrs & TextAttributes.HIDDEN) parts.push(ANSI.HIDDEN)
    if (attrs & TextAttributes.STRIKETHROUGH) parts.push(ANSI.STRIKETHROUGH)
    return parts.join("")
  },

  apply(opts: ANSIOptions): string {
    const parts: string[] = []
    if (opts.bold) parts.push(ANSI.BOLD)
    if (opts.dim) parts.push(ANSI.DIM)
    if (opts.italic) parts.push(ANSI.ITALIC)
    if (opts.underline) parts.push(ANSI.UNDERLINE)
    if (opts.blink) parts.push(ANSI.BLINK)
    if (opts.reverse) parts.push(ANSI.REVERSE)
    if (opts.hidden) parts.push(ANSI.HIDDEN)
    if (opts.strikethrough) parts.push(ANSI.STRIKETHROUGH)
    if (opts.fg) parts.push(ANSI.fg(opts.fg))
    if (opts.bg) parts.push(ANSI.bg(opts.bg))
    if (opts.reset) parts.push(ANSI.RESET)
    return parts.join("")
  },
}

export interface Cell {
  char: string
  fg: RGBA
  bg: RGBA
  attrs: TextAttributes
}

export function sanitizeCellChar(char: string): string {
  const firstChar = Array.from(char)[0]
  if (!firstChar) return " "
  const code = firstChar.codePointAt(0)
  if (code === undefined) return " "
  if (code < 0x20) return " "
  if (code >= 0x7f && code <= 0x9f) return " "
  return firstChar
}

export class ScreenBuffer {
  width: number
  height: number
  cells: Cell[][]
  dirty: boolean
  dirtyRect: { x1: number; y1: number; x2: number; y2: number }

  constructor(width: number, height: number) {
    this.width = width
    this.height = height
    this.dirty = false
    this.dirtyRect = { x1: 0, y1: 0, x2: width - 1, y2: height - 1 }
    this.cells = Array.from({ length: height }, () =>
      Array.from({ length: width }, () => ({
        char: " ",
        fg: RGBA.fromHex("#000000"),
        bg: RGBA.fromHex("#000000"),
        attrs: 0,
      })),
    )
  }

  setCell(x: number, y: number, char: string, fg: RGBA, bg: RGBA, attrs: TextAttributes = 0): void {
    if (x < 0 || x >= this.width || y < 0 || y >= this.height) return
    if (!this.cells[y]) return
    const safeChar = sanitizeCellChar(char)
    const cell = this.cells[y][x]
    if (cell.char !== safeChar || !cell.fg.equals(fg) || !cell.bg.equals(bg) || cell.attrs !== attrs) {
      cell.char = safeChar
      cell.fg = fg
      cell.bg = bg
      cell.attrs = attrs
      this.markDirty(x, y)
    }
  }

  markDirty(x: number, y: number): void {
    this.dirty = true
    this.dirtyRect.x1 = Math.min(this.dirtyRect.x1, x)
    this.dirtyRect.y1 = Math.min(this.dirtyRect.y1, y)
    this.dirtyRect.x2 = Math.max(this.dirtyRect.x2, x)
    this.dirtyRect.y2 = Math.max(this.dirtyRect.y2, y)
  }

  markAllDirty(): void {
    this.dirty = true
    this.dirtyRect = { x1: 0, y1: 0, x2: this.width - 1, y2: this.height - 1 }
  }

  clear(): void {
    for (let y = 0; y < this.height; y++) {
      for (let x = 0; x < this.width; x++) {
        const cell = this.cells[y][x]
        cell.char = " "
        cell.fg = RGBA.fromHex("#000000")
        cell.bg = RGBA.fromHex("#000000")
        cell.attrs = 0
      }
    }
    this.markAllDirty()
  }

  render(): string {
    if (!this.dirty) return ""

    const { x1, y1, x2, y2 } = this.dirtyRect
    let output = ""

    let currentFg: RGBA | null = null
    let currentBg: RGBA | null = null
    let currentAttrs = -1

    for (let y = y1; y <= y2; y++) {
      output += ANSI.moveTo(y + 1, x1 + 1)

      for (let x = x1; x <= x2; x++) {
        const cell = this.cells[y][x]

        const fgChanged = !currentFg || !cell.fg.equals(currentFg)
        const bgChanged = !currentBg || !cell.bg.equals(currentBg)
        const attrsChanged = cell.attrs !== currentAttrs

        if (fgChanged || bgChanged || attrsChanged) {
          output += ANSI.RESET
          output += ANSI.fg(cell.fg)
          output += ANSI.bg(cell.bg)
          if (cell.attrs) output += ANSI.attrs(cell.attrs)
          currentFg = cell.fg
          currentBg = cell.bg
          currentAttrs = cell.attrs
        }

        output += cell.char
      }
    }

    output += ANSI.RESET
    this.dirty = false
    this.dirtyRect = { x1: 0, y1: 0, x2: this.width - 1, y2: this.height - 1 }

    return output
  }
}
