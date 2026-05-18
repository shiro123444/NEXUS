import { TUI, RGBA, h, createTUI } from "../src"

const tui = createTUI({ targetFps: 1, exitOnCtrlC: true })

const theme = {
  bg: RGBA.fromHex("#0a0a12"),
  primary: RGBA.fromHex("#00d4ff"),
  text: RGBA.fromHex("#e0e0e0"),
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
    },
    h("text", { fg: theme.primary }, "=== SIMPLE COLUMN TEST ==="),
    h("text", { fg: theme.text }, "Line 2"),
    h("text", { fg: theme.primary }, "Line 3"),
    h("text", { fg: theme.text }, "Line 4"),
    h("text", { fg: theme.primary }, "Line 5"),
    h("text", { fg: theme.text }, "Line 6 - Footer"),
  )
}

tui.renderElement(App())
console.error("[TEST] Layout complete!")
