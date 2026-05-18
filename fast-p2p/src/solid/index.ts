import type {
  KeyboardEvent,
  TerminalDimensions,
  RenderOptions,
  Renderer,
  BoxProps,
  TextProps,
  ScrollBoxProps,
  TextareaRenderable,
  Renderable,
  ColorInput,
} from "../core"

export interface TuiRootProps {
  children: any
  options?: RenderOptions
}

export interface BoxComponent {
  (props: BoxProps & { children?: any }): any
}

export interface TextComponent {
  (props: TextProps & { children?: any }): any
}

export interface ScrollBoxComponent {
  (props: ScrollBoxProps & { children?: any }): any
}

export interface SpinnerProps {
  frames?: string[]
  interval?: number
  color?: ColorInput
}

export interface SpinnerComponent {
  (props: SpinnerProps & { children?: any }): any
}

export interface TextareaProps {
  value?: string
  placeholder?: string
  cursorColor?: ColorInput
  focusedBackgroundColor?: ColorInput
  syntaxStyle?: any
  onInput?: (value: string) => void
  onKeyDown?: (event: KeyboardEvent) => void
  onPaste?: (text: string) => void
  ref?: (instance: TextareaRenderable) => void
  onMouseDown?: (event: any) => void
  children?: any
}

export interface TextareaComponent {
  (props: TextareaProps): any
}

export interface JSX {
  Element: any
  Node: any
  children?: any
}

export interface RenderableComponents {
  box: BoxComponent
  text: TextComponent
  scrollbox: ScrollBoxComponent
  spinner: SpinnerComponent
  textarea: TextareaComponent
}

export interface Hooks {
  useKeyboard(handler: (event: KeyboardEvent) => void): void
  useRenderer(): Renderer
  useTerminalDimensions(): TerminalDimensions
}

export interface Framework {
  render: (fn: () => JSX["Element"], options?: RenderOptions) => void
  useKeyboard: Hooks["useKeyboard"]
  useRenderer: Hooks["useRenderer"]
  useTerminalDimensions: Hooks["useTerminalDimensions"]
  box: BoxComponent
  text: TextComponent
  scrollbox: ScrollBoxComponent
  spinner: SpinnerComponent
  textarea: TextareaComponent
}
