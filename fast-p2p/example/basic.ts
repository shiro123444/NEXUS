import { createTUI, RGBA } from "../src"

const theme = {
  background: RGBA.fromHex("#0a0a0a"),
  text: RGBA.fromHex("#ffffff"),
  textMuted: RGBA.fromHex("#808080"),
  primary: RGBA.fromHex("#fab283"),
  accent: RGBA.fromHex("#50fa7b"),
  error: RGBA.fromHex("#ff5555"),
}

const tui = createTUI({ targetFps: 60, exitOnCtrlC: false })
tui.start()
tui.setBackground(theme.background)

let counter = 0

function App() {
  const { width, height } = tui.getTerminalDimensions()

  return {
    type: "box",
    props: {
      width,
      height,
      backgroundColor: theme.background,
      children: [
        { type: "text", props: { fg: theme.primary, children: "TUI Framework Demo" } },
        {
          type: "box",
          props: {
            flexDirection: "column",
            gap: 1,
            padding: 1,
            children: [
              { type: "text", props: { fg: theme.textMuted, children: `Terminal: ${width}x${height}` } },
              { type: "text", props: { fg: theme.text, children: `Counter: ${counter}` } },
              { type: "text", props: { fg: theme.accent, children: "Press Ctrl+Q to quit" } },
            ],
          },
        },
      ],
    },
  }
}

tui.onKey((evt) => {
  if (evt.ctrl && evt.name === "q") {
    console.log("[App] Quit")
    tui.stop(0)
    return
  }
  if (evt.name === "up") counter++
  if (evt.name === "down") counter--
  if (evt.name === "r") counter = 0
  tui.renderElement(App())
})

tui.renderElement(App())
console.log("[Demo] Use Ctrl+Q to quit, Up/Down change counter, R to reset.")
