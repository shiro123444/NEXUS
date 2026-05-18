import type { ColorInput, RGBA } from "../core"

export interface Theme {
  background: RGBA
  foreground: RGBA
  text: RGBA
  textMuted: RGBA
  primary: RGBA
  secondary: RGBA
  accent: RGBA
  error: RGBA
  warning: RGBA
  success: RGBA
  backgroundElement: RGBA
}

export interface ThemeProvider {
  theme: Theme
  mode: "dark" | "light"
  setMode?: (mode: "dark" | "light") => void
  lock?: () => void
  unlock?: () => void
  locked?: () => boolean
}

export interface SpinnerOptions {
  frames?: string[]
  interval?: number
  color?: ColorInput
  children?: any
}

export interface BoxOptions {
  width?: number | "100%"
  height?: number | "100%"
  backgroundColor?: ColorInput
  foregroundColor?: ColorInput
  flexDirection?: "row" | "column"
  flexGrow?: number
  flexShrink?: number
  gap?: number
  padding?: number
  paddingTop?: number
  paddingBottom?: number
  paddingLeft?: number
  paddingRight?: number
  margin?: number
  marginTop?: number
  marginBottom?: number
  marginLeft?: number
  marginRight?: number
  border?: Array<"top" | "bottom" | "left" | "right">
  borderColor?: ColorInput
  customBorderChars?: Record<string, string>
  alignItems?: string
  justifyContent?: string
  children?: any
  onMouseDown?: (event: any) => void
  onMouseUp?: (event: any) => void
  onMouseOver?: (event: any) => void
  onMouseOut?: (event: any) => void
  onClick?: () => void
}

export interface TextOptions {
  children?: any
  fg?: ColorInput
  bg?: ColorInput
  bold?: boolean
  dim?: boolean
  italic?: boolean
  underline?: boolean
  onMouseDown?: (event: any) => void
  onMouseUp?: (event: any) => void
  onMouseOver?: (event: any) => void
  onMouseOut?: (event: any) => void
  onClick?: () => void
}

export interface ScrollBoxOptions extends BoxOptions {
  scrollable?: boolean
  showScrollbar?: boolean
}

export interface DialogOptions {
  title?: string
  message?: string
  onClose?: () => void
}

export interface ToastOptions {
  message: string
  title?: string
  variant?: "info" | "warning" | "error" | "success"
  duration?: number
}

export interface Toast {
  show(options: ToastOptions): void
  error(err: any): void
}

export interface KeybindHandler {
  all: Record<
    string,
    Array<{
      name: string
      ctrl?: boolean
      meta?: boolean
      shift?: boolean
      super?: boolean
    }>
  >
  leader: boolean
  print(action: string): string
}

export interface KeybindProvider {
  keybind: KeybindHandler
}

export interface KeyboardHandler {
  (event: any): void
}

export interface EventBus {
  publish(event: string, data?: any): void
  subscribe(event: string, handler: (data: any) => void): () => void
}
