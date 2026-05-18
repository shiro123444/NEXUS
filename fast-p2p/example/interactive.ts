import { createTUI, RGBA } from "../src"

const theme = {
  background: RGBA.fromHex("#0a0a0a"),
  foreground: RGBA.fromHex("#ffffff"),
  text: RGBA.fromHex("#ffffff"),
  textMuted: RGBA.fromHex("#808080"),
  primary: RGBA.fromHex("#fab283"),
  secondary: RGBA.fromHex("#3b7dd8"),
  accent: RGBA.fromHex("#50fa7b"),
  error: RGBA.fromHex("#ff5555"),
  backgroundElement: RGBA.fromHex("#1a1a1a"),
}

const tui = createTUI({ targetFps: 30, exitOnCtrlC: true })
tui.start()
tui.setBackground(theme.background)

let selected = 0

const menuItems = [
  { label: "New Session", shortcut: "Ctrl+N" },
  { label: "Open Project", shortcut: "Ctrl+O" },
  { label: "Settings", shortcut: "Ctrl+," },
]

function App() {
  const { width, height } = tui.getTerminalDimensions()

  return {
    type: "box",
    props: {
      width,
      height,
      backgroundColor: theme.background,
      children: [
        { type: "text", props: { fg: theme.primary, children: "Interactive TUI Demo" } },
        { type: "text", props: { fg: theme.textMuted, children: "Use Tab to cycle, Enter to activate" } },
        {
          type: "box",
          props: {
            flexDirection: "column",
            gap: 1,
            marginTop: 2,
            children: menuItems.map((item, i) => ({
              type: "box",
              props: {
                flexDirection: "row",
                gap: 2,
                backgroundColor: selected === i ? theme.backgroundElement : undefined,
                padding: 1,
                children: [
                  {
                    type: "text",
                    props: { fg: selected === i ? theme.primary : theme.text, children: selected === i ? "▶ " : "  " },
                  },
                  { type: "text", props: { fg: selected === i ? theme.text : theme.textMuted, children: item.label } },
                  { type: "text", props: { fg: theme.textMuted, children: item.shortcut } },
                ],
              },
            })),
          },
        },
        {
          type: "box",
          props: {
            flexDirection: "row",
            gap: 1,
            marginTop: 2,
            children: [
              { type: "text", props: { fg: theme.primary, children: "[ Primary ]" } },
              { type: "text", props: { fg: theme.secondary, children: "[ Secondary ]" } },
              { type: "text", props: { fg: theme.error, children: "[ Danger ]" } },
            ],
          },
        },
        { type: "text", props: { fg: theme.textMuted, children: "Press ESC to exit" } },
      ],
    },
  }
}

tui.onKey((evt) => {
  if (evt.name === "escape") {
    console.log("[App] Exit")
    tui.stop(0)
    return
  }
  if (evt.name === "tab") {
    selected = (selected + 1) % menuItems.length
    tui.renderElement(App())
    return
  }
  if (evt.name === "return") {
    console.log("[Menu] Selected:", menuItems[selected].label)
    tui.renderElement(App())
    return
  }
  if (evt.name === "up" && selected > 0) {
    selected--
    tui.renderElement(App())
    return
  }
  if (evt.name === "down" && selected < menuItems.length - 1) {
    selected++
    tui.renderElement(App())
  }
})

tui.renderElement(App())
console.log("[Demo] Interactive TUI. Tab/Up/Down to navigate, Enter to select, ESC to exit.")
