import { RGBA, TextAttributes, type ColorInput, type LayoutNode, type TextProps } from "./types"
import { ScreenBuffer, ANSI } from "./screen"
import { LayoutEngine, type BoxStyle } from "./layout"
import { InputHandler, type MouseEvent, type KeyboardEvent, MouseButton } from "./input"

export type { ColorInput, LayoutNode, TextProps }

export interface BoxProps extends BoxStyle {
  children?: any
  onMouseDown?: (event: MouseEvent) => void
  onMouseUp?: (event: MouseEvent) => void
  onMouseOver?: (event: MouseEvent) => void
  onMouseOut?: (event: MouseEvent) => void
  onClick?: () => void
}

export interface RenderOptions {
  targetFps?: number
  gatherStats?: boolean
  exitOnCtrlC?: boolean
  useKittyKeyboard?: boolean
  autoFocus?: boolean
}

interface Element {
  type: string
  props: any
  id?: number
}

interface ClipRect {
  x: number
  y: number
  width: number
  height: number
}

let _idCounter = 0

export class TUI {
  private screen: ScreenBuffer
  private input: InputHandler
  private width: number
  private height: number
  private running = false
  private renderCallbacks: Array<() => void> = []
  private keyHandlers: Array<(evt: KeyboardEvent) => void> = []
  private elementMap: Map<number, Element> = new Map()
  private renderableMap: Map<number, any> = new Map()
  private focusedElement: number | null = null
  private rootNode: LayoutNode | null = null
  private backgroundColor: RGBA = RGBA.fromHex("#000000")
  private terminalRestored = false
  private processExitHandler: (() => void) | null = null
  private sigtermHandler: (() => void) | null = null
  private uncaughtExceptionHandler: ((error: Error) => void) | null = null
  options: RenderOptions

  constructor(options: RenderOptions = {}) {
    this.options = options
    this.width = process.stdout.columns || 80
    this.height = process.stdout.rows || 24
    this.screen = new ScreenBuffer(this.width, this.height)
    this.input = new InputHandler()

    this.setupResizeHandler()
    this.setupInputHandlers()
  }

  private setupResizeHandler(): void {
    let debounceTimer: NodeJS.Timeout | null = null
    process.stdout.on("resize", () => {
      if (debounceTimer) clearTimeout(debounceTimer)
      debounceTimer = setTimeout(() => {
        this.width = process.stdout.columns || 80
        this.height = process.stdout.rows || 24
        this.screen = new ScreenBuffer(this.width, this.height)
        this.scheduleRender()
      }, 100)
    })
  }

  private setupInputHandlers(): void {
    this.input.onKey((evt) => {
      for (const handler of this.keyHandlers) {
        handler(evt)
        if (evt._handled) {
          break
        }
      }

      for (const handler of this.renderCallbacks) {
        handler()
      }

      if (this.options.exitOnCtrlC && evt.ctrl && evt.name === "c") {
        this.stop()
      }
    })

    this.input.onMouse((evt) => {
      const target = this.findElementAt(evt.x, evt.y)
      if (target) {
        const element = this.elementMap.get(target)
        if (element?.props) {
          if (evt.action === "down") {
            element.props.onMouseDown?.(evt)
          } else if (evt.action === "up") {
            element.props.onMouseUp?.(evt)
            if (evt.button === MouseButton.LEFT) {
              element.props.onClick?.()
            }
          }
        }
      }
    })

    let prevHoverTarget: number | null = null
    this.input.onMouseMove((evt) => {
      const target = this.findElementAt(evt.x, evt.y)
      if (target !== prevHoverTarget) {
        if (prevHoverTarget) {
          const prev = this.elementMap.get(prevHoverTarget)
          prev?.props?.onMouseOut?.(evt)
        }
        if (target) {
          const curr = this.elementMap.get(target)
          curr?.props?.onMouseOver?.(evt)
        }
        prevHoverTarget = target
      }
    })
  }

  private findElementAt(x: number, y: number): number | null {
    for (const [id] of this.elementMap) {
      const node = this.renderableMap.get(id)
      if (
        node?.rect &&
        x >= node.rect.x &&
        x < node.rect.x + node.rect.width &&
        y >= node.rect.y &&
        y < node.rect.y + node.rect.height
      ) {
        return id
      }
    }
    return null
  }

  start(): void {
    if (this.running) return
    this.running = true
    this.terminalRestored = false
    this.input.start()
    this.installProcessHandlers()
    process.stdout.write(ANSI.hideCursor() + ANSI.clear())
    this.scheduleRender()
  }

  stop(exitCode: number = 0): void {
    this.running = false
    this.restoreTerminalState()
    this.uninstallProcessHandlers()
    process.exit(exitCode)
  }

  scheduleRender(): void {
    if (!this.running) return
    setTimeout(() => this.render(), 0)
  }

  private render(): void {
    if (!this.running) return

    const output = this.screen.render()
    if (output) {
      process.stdout.write(output)
    }
  }

  renderElement(element: Element): void {
    this.elementMap.clear()
    this.renderableMap.clear()
    this.screen.clear()

    const root = this.buildLayoutTree(element)
    if (!root) return

    this.rootNode = root
    const container = { x: 0, y: 0, width: this.width, height: this.height }
    LayoutEngine.calculate(root, container)

    this.drawNode(root, this.backgroundColor, { x: 0, y: 0, width: this.width, height: this.height })

    const output = this.screen.render()
    if (output) {
      process.stdout.write(output)
    }
  }

  private buildLayoutTree(element: Element): LayoutNode | null {
    if (!element) return null

    const id = ++_idCounter
    element.id = id
    this.elementMap.set(id, element)

    if (element.type === "box") {
      const children: LayoutNode[] = []
      const childElements = this.toArray(element.props.children)
      for (const child of childElements) {
        const childNode = this.buildLayoutTree(child)
        if (childNode) children.push(childNode)
      }

      const node = LayoutEngine.fromStyle(element.props, children)

      // Add implicit padding for borders
      if (element.props.border) {
        const sides = new Set<string>(
          element.props.border === true
            ? ["top", "bottom", "left", "right"]
            : Array.isArray(element.props.border)
              ? element.props.border
              : [],
        )
        if (sides.has("top")) node.paddingTop = (node.paddingTop ?? node.padding ?? 0) + 1
        if (sides.has("bottom")) node.paddingBottom = (node.paddingBottom ?? node.padding ?? 0) + 1
        if (sides.has("left")) node.paddingLeft = (node.paddingLeft ?? node.padding ?? 0) + 1
        if (sides.has("right")) node.paddingRight = (node.paddingRight ?? node.padding ?? 0) + 1
      }

      this.renderableMap.set(id, node)
      return node
    }

    if (element.type === "text") {
      const node: LayoutNode = {
        rect: { x: 0, y: 0, width: this.calculateTextWidth(element), height: 1 },
        flexGrow: 0,
        flexShrink: 0,
        flexBasis: 0,
        flexDirection: "row",
        alignItems: "flex-start",
        justifyContent: "flex-start",
        gap: 0,
        padding: 0,
        paddingTop: 0,
        paddingBottom: 0,
        paddingLeft: 0,
        paddingRight: 0,
        margin: 0,
        marginTop: 0,
        marginBottom: 0,
        marginLeft: 0,
        marginRight: 0,
        children: [],
      }
      this.renderableMap.set(id, node)
      return node
    }

    return null
  }

  private calculateTextWidth(element: Element): number {
    const text = String(element.props.children ?? "")
    return text.length
  }

  private intersectRect(a: ClipRect, b: ClipRect): ClipRect | null {
    const x1 = Math.max(a.x, b.x)
    const y1 = Math.max(a.y, b.y)
    const x2 = Math.min(a.x + a.width, b.x + b.width)
    const y2 = Math.min(a.y + a.height, b.y + b.height)
    if (x2 <= x1 || y2 <= y1) return null
    return { x: x1, y: y1, width: x2 - x1, height: y2 - y1 }
  }

  private drawNode(node: LayoutNode, parentBg: RGBA, clipRect: ClipRect): void {
    const element = this.findElementByNode(node)
    if (!element) return

    if (element.type === "box") {
      const bg = element.props.backgroundColor
        ? element.props.backgroundColor instanceof RGBA
          ? element.props.backgroundColor
          : RGBA.fromHex(element.props.backgroundColor as string)
        : parentBg

      const boxClip = this.intersectRect(clipRect, node.rect)
      if (!boxClip) return

      const startY = Math.max(0, boxClip.y)
      const endY = Math.min(boxClip.y + boxClip.height, this.height)
      const startX = Math.max(0, boxClip.x)
      const endX = Math.min(boxClip.x + boxClip.width, this.width)
      for (let y = startY; y < endY; y++) {
        for (let x = startX; x < endX; x++) {
          this.screen.setCell(x, y, " ", RGBA.fromHex("#000000"), bg, 0)
        }
      }

      // Draw border if specified
      if (element.props.border) {
        this.drawBorder(node, element, bg, boxClip)
      }

      const contentClip = this.intersectRect(boxClip, {
        x: node.rect.x + node.paddingLeft,
        y: node.rect.y + node.paddingTop,
        width: Math.max(0, node.rect.width - node.paddingLeft - node.paddingRight),
        height: Math.max(0, node.rect.height - node.paddingTop - node.paddingBottom),
      })

      for (const child of node.children) {
        if (contentClip) this.drawNode(child, bg, contentClip)
      }
    }

    if (element.type === "text") {
      const text = String(element.props.children ?? "")
      const fg = element.props.fg
        ? element.props.fg instanceof RGBA
          ? element.props.fg
          : RGBA.fromHex(element.props.fg as string)
        : RGBA.fromHex("#ffffff")
      const bg = element.props.bg
        ? element.props.bg instanceof RGBA
          ? element.props.bg
          : RGBA.fromHex(element.props.bg as string)
        : parentBg
      const attrs = element.props.attributes ?? 0

      const rect = node.rect
      const textClip = this.intersectRect(clipRect, rect)
      if (!textClip) return

      for (let i = 0; i < text.length && rect.x + i < this.width; i++) {
        const x = rect.x + i
        const y = rect.y
        if (y >= textClip.y && y < textClip.y + textClip.height && x >= textClip.x && x < textClip.x + textClip.width) {
          this.screen.setCell(x, y, text[i], fg, bg, attrs)
        }
      }
    }
  }

  private drawBorder(node: LayoutNode, element: Element, bg: RGBA, clipRect: ClipRect): void {
    const border = element.props.border
    const sides = new Set<string>(
      border === true ? ["top", "bottom", "left", "right"] : Array.isArray(border) ? border : [],
    )
    if (sides.size === 0) return

    const borderColor = element.props.borderColor
      ? element.props.borderColor instanceof RGBA
        ? element.props.borderColor
        : RGBA.fromHex(element.props.borderColor as string)
      : RGBA.fromHex("#444466")

    const chars = element.props.customBorderChars ?? {}
    const tl = chars.topLeft ?? "┌"
    const tr = chars.topRight ?? "┐"
    const bl = chars.bottomLeft ?? "└"
    const br = chars.bottomRight ?? "┘"
    const hz = chars.horizontal ?? "─"
    const vt = chars.vertical ?? "│"

    const { x, y, width: w, height: h } = node.rect

    if (sides.has("top") && y >= clipRect.y && y < clipRect.y + clipRect.height && y < this.height) {
      for (let i = 1; i < w - 1 && x + i < this.width; i++) {
        if (x + i < clipRect.x || x + i >= clipRect.x + clipRect.width) continue
        this.screen.setCell(x + i, y, hz, borderColor, bg, 0)
      }
      if (sides.has("left") && x >= clipRect.x && x < clipRect.x + clipRect.width && x < this.width)
        this.screen.setCell(x, y, tl, borderColor, bg, 0)
      if (sides.has("right") && x + w - 1 >= clipRect.x && x + w - 1 < clipRect.x + clipRect.width && x + w - 1 < this.width)
        this.screen.setCell(x + w - 1, y, tr, borderColor, bg, 0)
    }

    if (sides.has("bottom") && y + h - 1 >= clipRect.y && y + h - 1 < clipRect.y + clipRect.height && y + h - 1 < this.height) {
      for (let i = 1; i < w - 1 && x + i < this.width; i++) {
        if (x + i < clipRect.x || x + i >= clipRect.x + clipRect.width) continue
        this.screen.setCell(x + i, y + h - 1, hz, borderColor, bg, 0)
      }
      if (sides.has("left") && x >= clipRect.x && x < clipRect.x + clipRect.width && x < this.width)
        this.screen.setCell(x, y + h - 1, bl, borderColor, bg, 0)
      if (sides.has("right") && x + w - 1 >= clipRect.x && x + w - 1 < clipRect.x + clipRect.width && x + w - 1 < this.width)
        this.screen.setCell(x + w - 1, y + h - 1, br, borderColor, bg, 0)
    }

    if (sides.has("left") && x >= clipRect.x && x < clipRect.x + clipRect.width && x < this.width) {
      for (let i = 1; i < h - 1 && y + i < this.height; i++) {
        if (y + i < clipRect.y || y + i >= clipRect.y + clipRect.height) continue
        this.screen.setCell(x, y + i, vt, borderColor, bg, 0)
      }
    }

    if (sides.has("right") && x + w - 1 >= clipRect.x && x + w - 1 < clipRect.x + clipRect.width && x + w - 1 < this.width) {
      for (let i = 1; i < h - 1 && y + i < this.height; i++) {
        if (y + i < clipRect.y || y + i >= clipRect.y + clipRect.height) continue
        this.screen.setCell(x + w - 1, y + i, vt, borderColor, bg, 0)
      }
    }

    // Draw title on top border
    const title = element.props.title as string | undefined
    if (title && sides.has("top") && y >= 0 && y < this.height) {
      const label = ` ${title} `
      const startX = x + 2
      for (let i = 0; i < label.length && startX + i < this.width && startX + i < x + w - 1; i++) {
        if (startX + i < clipRect.x || startX + i >= clipRect.x + clipRect.width) continue
        this.screen.setCell(startX + i, y, label[i], borderColor, bg, 0)
      }
    }
  }

  private findElementByNode(node: LayoutNode): Element | null {
    for (const [id, element] of this.elementMap) {
      const n = this.renderableMap.get(id)
      if (n === node) return element
    }
    return null
  }

  private toArray(value: any): any[] {
    if (value === undefined || value === null) return []
    if (Array.isArray(value)) return value.flat(Infinity).filter((v: any) => v != null)
    return [value]
  }

  getTerminalDimensions(): { width: number; height: number } {
    return { width: this.width, height: this.height }
  }

  setBackground(color: ColorInput): void {
    if (typeof color === "string") {
      this.backgroundColor = RGBA.fromHex(color)
    } else {
      this.backgroundColor = color
    }
  }

  onKey(handler: (evt: KeyboardEvent) => void): () => void {
    this.keyHandlers.push(handler)
    return () => {
      this.keyHandlers = this.keyHandlers.filter((h) => h !== handler)
    }
  }

  private restoreTerminalState(): void {
    if (this.terminalRestored) return
    this.terminalRestored = true
    this.input.stop()
    process.stdout.write(ANSI.RESET + ANSI.showCursor() + ANSI.clear())
  }

  private installProcessHandlers(): void {
    if (!this.processExitHandler) {
      this.processExitHandler = () => {
        this.restoreTerminalState()
      }
      process.on("exit", this.processExitHandler)
    }

    if (!this.sigtermHandler) {
      this.sigtermHandler = () => {
        this.running = false
        this.restoreTerminalState()
        this.uninstallProcessHandlers()
        process.exit(0)
      }
      process.on("SIGTERM", this.sigtermHandler)
    }

    if (!this.uncaughtExceptionHandler) {
      this.uncaughtExceptionHandler = (error: Error) => {
        this.running = false
        this.restoreTerminalState()
        this.uninstallProcessHandlers()
        const message = error?.stack ?? error?.message ?? String(error)
        process.stderr.write(`${message}\n`)
        process.exit(1)
      }
      process.on("uncaughtException", this.uncaughtExceptionHandler)
    }
  }

  private uninstallProcessHandlers(): void {
    if (this.processExitHandler) {
      process.off("exit", this.processExitHandler)
      this.processExitHandler = null
    }

    if (this.sigtermHandler) {
      process.off("SIGTERM", this.sigtermHandler)
      this.sigtermHandler = null
    }

    if (this.uncaughtExceptionHandler) {
      process.off("uncaughtException", this.uncaughtExceptionHandler)
      this.uncaughtExceptionHandler = null
    }
  }
}

export function createTUI(options?: RenderOptions): TUI {
  return new TUI(options)
}
