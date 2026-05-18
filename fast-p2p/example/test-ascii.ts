import { TUI, RGBA, h, createTUI } from "../src"

const tui = createTUI({ targetFps: 1, exitOnCtrlC: true })

const theme = {
  bg: RGBA.fromHex("#0a0a12"),
  primary: RGBA.fromHex("#00d4ff"),
  text: RGBA.fromHex("#e0e0e0"),
}

tui.start()
tui.setBackground(theme.bg)

const asciiLogo = [
  "██████╗ ███████╗████████╗██████╗  ██████╗ ",
  "██╔══██╗██╔════╝╚══██╔══╝██╔══██╗██╔═══██╗",
  "██████╔╝█████╗     ██║   ██████╔╝██║   ██║",
  "██╔══██╗██╔══╝     ██║   ██╔══██╗██║   ██║",
  "██║  ██║███████╗   ██║   ██║  ██║╚██████╔╝",
  "╚═╝  ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ",
]

function App() {
  const dims = tui.getTerminalDimensions()

  return h("box", {
    width: dims.width,
    height: dims.height,
    backgroundColor: theme.bg,
    flexDirection: "column",
    gap: 0,
    children: [
      // Title
      h("text", {
        fg: theme.primary,
        children: "═══════════════════════════════════════",
      }),
      h("text", {
        fg: theme.primary,
        children: "          F A S T   P 2 P",
      }),
      h("text", {
        fg: theme.primary,
        children: "═══════════════════════════════════════",
      }),
      h("text", { fg: theme.text, children: " " }),
      // ASCII Art
      ...asciiLogo.map((line) => h("text", { fg: theme.primary, children: line })),
      h("text", { fg: theme.text, children: " " }),
      h("text", { fg: theme.text, children: "Terminal: " + dims.width + "x" + dims.height }),
      h("text", { fg: theme.text, children: "Press Ctrl+C to quit" }),
    ],
  })
}

tui.renderElement(App())
console.error("[P2P] Test complete!")
