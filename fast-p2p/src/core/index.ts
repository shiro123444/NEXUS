export * from "./types"
import type { ColorInput } from "./types"

export function t(strings: TemplateStringsArray, ...values: any[]): string {
  return strings.reduce((acc, str, i) => acc + str + (values[i] ?? ""), "")
}

export function fg(color: ColorInput): { fg: ColorInput } {
  return { fg: color }
}

export function dim(text: string): string {
  return text
}

export function decodePasteBytes(bytes: Uint8Array): string {
  return new TextDecoder().decode(bytes)
}

export { TUI, createTUI } from "./tui"
export { ScreenBuffer, ANSI } from "./screen"
export { LayoutEngine } from "./layout"
export { InputHandler, isPrintableInputChar } from "./input"
