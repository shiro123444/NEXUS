export * from "./core"
export * from "./solid"
export * from "./components"

import { TUI, RGBA, TextAttributes, MouseButton } from "./core"

let globalTUI: TUI | null = null

export function createTUI(options?: any): TUI {
  globalTUI = new TUI(options)
  return globalTUI
}

export function getGlobalTUI(): TUI | null {
  return globalTUI
}

export function h(type: string, props: any, ...children: any[]): any {
  // Flatten nested arrays (from .map() calls)
  const flatChildren = children.flat(Infinity).filter((c) => c != null)

  return {
    type,
    props: {
      ...props,
      // Prefer explicit rest children; fall back to props.children
      children:
        flatChildren.length > 0
          ? flatChildren.length === 1
            ? flatChildren[0]
            : flatChildren
          : props?.children,
    },
  }
}

export function render(app: () => any, options?: any): void {
  const tui = createTUI(options)
  tui.start()

  function renderLoop() {
    const element = app()
    tui.renderElement(element)
    setTimeout(renderLoop, 1000 / (options?.targetFps ?? 30))
  }

  renderLoop()
}

export { RGBA, TextAttributes, MouseButton }
