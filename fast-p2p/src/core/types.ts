export interface LayoutRect {
  x: number
  y: number
  width: number
  height: number
}

export interface LayoutNode {
  rect: LayoutRect
  position?: "flow" | "absolute"
  top?: number
  left?: number
  flexGrow: number
  flexShrink: number
  flexBasis: number
  flexDirection: "row" | "column"
  alignItems: "flex-start" | "center" | "flex-end" | "stretch"
  justifyContent: "flex-start" | "center" | "flex-end" | "space-between" | "space-around"
  gap: number
  padding: number
  paddingTop: number
  paddingBottom: number
  paddingLeft: number
  paddingRight: number
  margin: number
  marginTop: number
  marginBottom: number
  marginLeft: number
  marginRight: number
  children: LayoutNode[]
}

export type ColorInput = string | RGBA

export class RGBA {
  r: number
  g: number
  b: number
  a: number

  constructor(r: number, g: number, b: number, a: number = 1) {
    this.r = r
    this.g = g
    this.b = b
    this.a = a
  }

  static fromHex(hex: string): RGBA {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
    if (!result) return new RGBA(0, 0, 0, 1)
    return new RGBA(parseInt(result[1], 16) / 255, parseInt(result[2], 16) / 255, parseInt(result[3], 16) / 255, 1)
  }

  static fromInts(r: number, g: number, b: number, a: number = 255): RGBA {
    return new RGBA(r / 255, g / 255, b / 255, a / 255)
  }

  static fromValues(r: number, g: number, b: number, a: number): RGBA {
    return new RGBA(r, g, b, a)
  }

  equals(other: RGBA): boolean {
    return (
      Math.abs(this.r - other.r) < 0.001 &&
      Math.abs(this.g - other.g) < 0.001 &&
      Math.abs(this.b - other.b) < 0.001 &&
      Math.abs(this.a - other.a) < 0.001
    )
  }
}

export enum TextAttributes {
  NONE = 0,
  BOLD = 1,
  DIM = 2,
  ITALIC = 4,
  UNDERLINE = 8,
  BLINK = 16,
  REVERSE = 32,
  HIDDEN = 64,
  STRIKETHROUGH = 128,
}

export enum MouseButton {
  LEFT = 0,
  MIDDLE = 1,
  RIGHT = 2,
  BUTTON4 = 3,
  BUTTON5 = 4,
}

export interface ParsedKey {
  name: string
  ctrl?: boolean
  meta?: boolean
  shift?: boolean
  super?: boolean
}

export interface KeyBinding {
  name: string
  action: string
  ctrl?: boolean
  meta?: boolean
  shift?: boolean
  super?: boolean
}

export interface Renderable {
  id: number
  isDestroyed: boolean
  focus(): void
  blur(): void
  getLayoutNode(): LayoutNode
}

export interface BoxProps {
  width?: number | "100%"
  height?: number | "100%"
  position?: "absolute"
  top?: number
  left?: number
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
  alignItems?: "flex-start" | "center" | "flex-end" | "stretch"
  justifyContent?: "flex-start" | "center" | "flex-end" | "space-between" | "space-around"
  children?: any
  onMouseDown?: (event: any) => void
  onMouseUp?: (event: any) => void
  onMouseOver?: (event: any) => void
  onMouseOut?: (event: any) => void
  onClick?: () => void
}

export interface TextProps {
  children?: any
  fg?: ColorInput
  bg?: ColorInput
  attributes?: TextAttributes
  flexShrink?: number
  flexGrow?: number
  onMouseDown?: (event: any) => void
  onMouseUp?: (event: any) => void
  onMouseOver?: (event: any) => void
  onMouseOut?: (event: any) => void
  onClick?: () => void
}

export interface ScrollBoxProps extends BoxProps {
  scrollable?: boolean
  showScrollbar?: boolean
}

export interface TextareaRenderable extends Renderable {
  value: string
  cursorColor: ColorInput
  focusedBackgroundColor: ColorInput
  isFocused: boolean
  extmarks: ExtmarkRegistry
  insertText(text: string): void
  gotoBufferEnd(): void
  getSelection(): string | null
  setSelection(start: number, end: number): void
}

export interface ExtmarkRegistry {
  registerType(name: string): number
}

export interface MouseEvent {
  button: MouseButton
  action: "down" | "up" | "move"
  x: number
  y: number
  target?: Renderable
  preventDefault(): void
  stopPropagation(): void
}

export interface PasteEvent {
  text: string
}

export interface KeyboardEvent {
  name: string
  ctrl: boolean
  meta: boolean
  shift: boolean
  alt: boolean
  key: string
  code: string
  preventDefault(): void
  stopPropagation(): void
  _handled?: boolean
}

export interface TerminalDimensions {
  width: number
  height: number
}

export interface RenderOptions {
  targetFps?: number
  gatherStats?: boolean
  exitOnCtrlC?: boolean
  useKittyKeyboard?: boolean
  autoFocus?: boolean
  openConsoleOnError?: boolean
  consoleOptions?: ConsoleOptions
}

export interface ConsoleOptions {
  keyBindings?: Array<{ name: string; ctrl?: boolean; action: string }>
  onCopySelection?: (text: string) => void
}

export interface Renderer {
  requestRender(): void
  currentFocusedRenderable: Renderable | null
  getSelection(): string | null
  clearSelection(): void
  setTerminalTitle(title: string): void
  toggleDebugOverlay(): void
  suspend(): void
  resume(): void
  destroy(): void
  disableStdoutInterception(): void
  currentRenderBuffer: RenderBuffer
  console: ConsoleManager
}

export interface RenderBuffer {
  clear(): void
}

export interface ConsoleManager {
  onCopySelection?: (text: string) => void
  toggle(): void
}
