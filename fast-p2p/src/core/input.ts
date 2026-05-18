import { EventEmitter } from "events"
import * as readline from "readline"
import { MouseButton } from "./types"
import type { ParsedKey, KeyboardEvent, MouseEvent } from "./types"
export { MouseButton }
export type { ParsedKey, KeyboardEvent, MouseEvent }

const KEY_ALIASES: Record<string, string> = {
  "\x1b": "escape",
  "\r": "return",
  "\n": "return",
  "\t": "tab",
  " ": "space",
  "\x08": "backspace",
  "\x7f": "backspace",
  "\x03": "ctrl+c",
  "\x04": "ctrl+d",
  "\x1a": "ctrl+z",
}

export function isPrintableInputChar(value: string): boolean {
  if (Array.from(value).length !== 1) return false
  const code = value.codePointAt(0)
  if (code === undefined) return false
  if (code < 0x20) return false
  if (code >= 0x7f && code <= 0x9f) return false
  return true
}

function parseModifier(modifier?: number): { ctrl: boolean; meta: boolean; shift: boolean } {
  if (!modifier || modifier <= 1) {
    return { ctrl: false, meta: false, shift: false }
  }

  return {
    shift: modifier === 2 || modifier === 4 || modifier === 6 || modifier === 8,
    meta: modifier === 3 || modifier === 4 || modifier === 7 || modifier === 8,
    ctrl: modifier === 5 || modifier === 6 || modifier === 7 || modifier === 8,
  }
}

export class InputHandler extends EventEmitter {
  private isRawMode = false
  private mouseEnabled = false
  private keyboardHandlers: Array<(evt: KeyboardEvent) => void> = []
  private mouseHandlers: Array<(evt: MouseEvent) => void> = []
  private mouseMoveHandlers: Array<(evt: MouseEvent) => void> = []
  private dataListener: ((chunk: Buffer) => void) | null = null
  private sigintListener: (() => void) | null = null

  constructor() {
    super()
  }

  enableMouse(): void {
    if (this.mouseEnabled) return
    this.mouseEnabled = true
    process.stdout.write("\x1b[?1000h\x1b[?1002h\x1b[?1003h\x1b[?1006h")
  }

  disableMouse(): void {
    if (!this.mouseEnabled) return
    this.mouseEnabled = false
    process.stdout.write("\x1b[?1000l\x1b[?1002l\x1b[?1003l\x1b[?1006l\x1b[?1015l\x1b[?2004l")
  }

  enableRawMode(): void {
    if (this.isRawMode) return
    this.isRawMode = true
    try {
      if (typeof process.stdin.setRawMode === "function") {
        readline.emitKeypressEvents(process.stdin)
        process.stdin.setRawMode(true)
      }
    } catch (e) {
      // Bun or other runtime without raw mode support
    }
  }

  disableRawMode(): void {
    if (!this.isRawMode) return
    this.isRawMode = false
    try {
      if (typeof process.stdin.setRawMode === "function") {
        process.stdin.setRawMode(false)
      }
    } catch (e) {
      // ignore
    }
  }

  start(): void {
    this.enableRawMode()
    this.enableMouse()

    if (typeof process.stdin.on === "function" && !this.dataListener) {
      this.dataListener = (chunk: Buffer) => {
        const str = chunk.toString()

        if (str.startsWith("\x1b[M") || str.startsWith("\x1b[<")) {
          this.handleMouse(chunk)
          return
        }

        this.handleKey(chunk)
      }
      process.stdin.on("data", this.dataListener)
    }

    if (typeof process.on === "function" && !this.sigintListener) {
      this.sigintListener = () => {
        this.emit("interrupt")
      }
      process.on("SIGINT", this.sigintListener)
    }
  }

  stop(): void {
    this.disableRawMode()
    this.disableMouse()
    if (this.dataListener) {
      process.stdin.off("data", this.dataListener)
      this.dataListener = null
    }
    if (this.sigintListener) {
      process.off("SIGINT", this.sigintListener)
      this.sigintListener = null
    }
  }

  onKey(handler: (evt: KeyboardEvent) => void): void {
    this.keyboardHandlers.push(handler)
  }

  onMouse(handler: (evt: MouseEvent) => void): void {
    this.mouseHandlers.push(handler)
  }

  onMouseMove(handler: (evt: MouseEvent) => void): void {
    this.mouseMoveHandlers.push(handler)
  }

  private handleKey(chunk: Buffer): void {
    const str = chunk.toString()
    const key = this.parseKey(str)

    const evt: KeyboardEvent = {
      name: key.name,
      ctrl: key.ctrl ?? false,
      meta: key.meta ?? false,
      shift: key.shift ?? false,
      alt: key.meta ?? false,
      key: str,
      code: str,
      preventDefault() {
        this._handled = true
      },
      stopPropagation() {
        this._handled = true
      },
    }

    for (const handler of this.keyboardHandlers) {
      handler(evt)
      if (evt._handled) break
    }

    if (!evt._handled) {
      this.emit("key", evt)
    }
  }

  private handleMouse(chunk: Buffer): void {
    const sgr = chunk.toString().match(/^\x1b\[<(\d+);(\d+);(\d+)([mM])$/)
    if (sgr) {
      const code = parseInt(sgr[1], 10)
      const x = Math.max(0, parseInt(sgr[2], 10) - 1)
      const y = Math.max(0, parseInt(sgr[3], 10) - 1)
      const button = code & 0x03

      const action = sgr[4] === "M" ? "down" : "up"

      const evt: MouseEvent = {
        button,
        action,
        x,
        y,
        preventDefault() {},
        stopPropagation() {},
      }

      for (const handler of this.mouseHandlers) {
        handler(evt)
      }

      this.emit("mouse", evt)
      return
    }

    if (chunk.length < 6 || chunk[0] !== 0x1b || chunk[1] !== 0x5b || chunk[2] !== 0x4d) return

    const b = chunk[3]
    const button = b & 0x03
    const isMove = (b & 0x20) !== 0

    const x = chunk[4] - 33
    const y = chunk[5] - 33

    const evt: MouseEvent = {
      button,
      action: isMove ? "move" : "down",
      x,
      y,
      preventDefault() {},
      stopPropagation() {},
    }

    if (isMove) {
      for (const handler of this.mouseMoveHandlers) {
        handler(evt)
      }
      return
    }

    for (const handler of this.mouseHandlers) {
      handler(evt)
    }

    this.emit("mouse", evt)
  }

  private parseKey(str: string): ParsedKey {
    if (KEY_ALIASES[str]) {
      const name = KEY_ALIASES[str]
      if (name.startsWith("ctrl+")) {
        return { name: name.slice(5), ctrl: true, meta: false, shift: false, super: false }
      }
      return { name, ctrl: false, meta: false, shift: false, super: false }
    }

    if (str.startsWith("\x1b[") || str.startsWith("\x1bO")) {
      return this.parseEscapeSequence(str)
    }

    if (str.length === 1) {
      const code = str.charCodeAt(0)
      if (code >= 65 && code <= 90) {
        return { name: str.toLowerCase(), ctrl: false, meta: false, shift: true, super: false }
      }
      if (code >= 97 && code <= 122) {
        return { name: str, ctrl: false, meta: false, shift: false, super: false }
      }
    }

    return { name: str || "unknown", ctrl: false, meta: false, shift: false, super: false }
  }

  private parseEscapeSequence(str: string): ParsedKey {
    if (str.startsWith("\x1bO")) {
      const appSeq = str.slice(2)
      if (appSeq === "A") return { name: "up", ctrl: false, meta: false, shift: false, super: false }
      if (appSeq === "B") return { name: "down", ctrl: false, meta: false, shift: false, super: false }
      if (appSeq === "C") return { name: "right", ctrl: false, meta: false, shift: false, super: false }
      if (appSeq === "D") return { name: "left", ctrl: false, meta: false, shift: false, super: false }
      if (appSeq === "H") return { name: "home", ctrl: false, meta: false, shift: false, super: false }
      if (appSeq === "F") return { name: "end", ctrl: false, meta: false, shift: false, super: false }
    }

    const seq = str.startsWith("\x1b[") ? str.slice(2) : str
    const match = seq.match(/^([0-9;]*)([A-Za-z~])$/)

    if (!match) {
      return { name: "escape", ctrl: false, meta: false, shift: false, super: false }
    }

    const [, rawParams, final] = match
    const params = rawParams.length > 0 ? rawParams.split(";").map((v) => parseInt(v, 10) || 0) : []

    if (final === "A" || final === "B" || final === "C" || final === "D" || final === "H" || final === "F") {
      const modifier = params.length >= 2 ? params[1] : undefined
      const { ctrl, meta, shift } = parseModifier(modifier)

      if (final === "A") return { name: "up", ctrl, meta, shift, super: false }
      if (final === "B") return { name: "down", ctrl, meta, shift, super: false }
      if (final === "C") return { name: "right", ctrl, meta, shift, super: false }
      if (final === "D") return { name: "left", ctrl, meta, shift, super: false }
      if (final === "H") return { name: "home", ctrl, meta, shift, super: false }
      return { name: "end", ctrl, meta, shift, super: false }
    }

    if (final === "~") {
      const keyCode = params[0]
      const modifier = params.length >= 2 ? params[1] : undefined
      const { ctrl, meta, shift } = parseModifier(modifier)

      if (keyCode === 3) return { name: "delete", ctrl, meta, shift, super: false }
      if (keyCode === 5) return { name: "pageup", ctrl, meta, shift, super: false }
      if (keyCode === 6) return { name: "pagedown", ctrl, meta, shift, super: false }
    }

    return { name: "escape", ctrl: false, meta: false, shift: false, super: false }
  }
}
