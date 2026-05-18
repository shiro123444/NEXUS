import { TUI, RGBA, h } from "../src"

const tui = new TUI({ targetFps: 1, exitOnCtrlC: true })

const theme = {
  background: RGBA.fromHex("#1a1a2e"),
  text: RGBA.fromHex("#eeeeee"),
  primary: RGBA.fromHex("#fab283"),
}

tui.start()
tui.setBackground(theme.background)

const dims = tui.getTerminalDimensions()
const element = h("box", {
  width: dims.width,
  height: dims.height,
  backgroundColor: theme.background,
  children: [
    h("text", { fg: theme.primary, children: "╔═══════════════════════════════╗" }),
    h("text", { fg: theme.primary, children: "║   TUI Framework Test           ║" }),
    h("text", { fg: theme.primary, children: "╚═══════════════════════════════╝" }),
    h("text", { fg: theme.text, children: `Terminal: ${dims.width}x${dims.height}` }),
    h("text", { fg: theme.primary, children: "Press Ctrl+C to exit" }),
  ],
})

tui.renderElement(element)

console.error("\n[TUI Framework] Rendering complete!")
console.error("If you see this with ANSI codes above, the framework is working.")
