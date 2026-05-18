import { TUI, RGBA, h, createTUI } from "../src"

const tui = createTUI({ targetFps: 1, exitOnCtrlC: true })

const theme = {
  bg: RGBA.fromHex("#0a0a12"),
  primary: RGBA.fromHex("#00d4ff"),
  text: RGBA.fromHex("#e0e0e0"),
  warning: RGBA.fromHex("#ffaa00"),
}

tui.start()
tui.setBackground(theme.bg)

function App() {
  const dims = tui.getTerminalDimensions()

  return h(
    "box",
    {
      width: dims.width,
      height: dims.height,
      backgroundColor: theme.bg,
      flexDirection: "column",
      gap: 0,
    },
    h("text", { fg: theme.primary }, "HELLO WORLD"),
    h("text", { fg: theme.text }, "Terminal: " + dims.width + "x" + dims.height),
    h("text", { fg: theme.primary }, "ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
    h("text", { fg: theme.primary }, "abcdefghijklmnopqrstuvwxyz"),
    h("text", { fg: theme.text }, "0123456789"),
    h("text", { fg: theme.warning }, "Press Ctrl+C to quit"),
  )
}

tui.renderElement(App())

const dims = tui.getTerminalDimensions()
console.error(`[DEBUG] Terminal: ${dims.width}x${dims.height}`)
console.error("[P2P] Test complete!")
