import { TUI, RGBA, h, createTUI } from "../src"

const tui = createTUI({ targetFps: 1, exitOnCtrlC: true })

const theme = {
  bg: RGBA.fromHex("#0a0a12"),
  primary: RGBA.fromHex("#00d4ff"),
  text: RGBA.fromHex("#e0e0e0"),
}

tui.start()
tui.setBackground(theme.bg)

let selectedItem = 0
const items = ["Apple", "Banana", "Cherry", "Date"]

function App() {
  const dims = tui.getTerminalDimensions()
  
  const menuBoxChildren = [
    h("text", { fg: theme.primary }, "Menu:"),
    h("text", { fg: selectedItem === 0 ? theme.primary : theme.text }, "▶ Apple"),
    h("text", { fg: selectedItem === 1 ? theme.primary : theme.text }, "▶ Banana"),
    h("text", { fg: selectedItem === 2 ? theme.primary : theme.text }, "▶ Cherry"),
    h("text", { fg: selectedItem === 3 ? theme.primary : theme.text }, "▶ Date"),
  ]
  
  return h(
    "box",
    {
      width: dims.width,
      height: dims.height,
      backgroundColor: theme.bg,
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
    },
    h(
      "box",
      {
        flexDirection: "column",
        width: 20,
        backgroundColor: RGBA.fromHex("#1a1a2e"),
        gap: 0,
      },
      h("text", { fg: theme.primary }, "Title"),
      h("text", { fg: theme.text }, "Item 1"),
      h("text", { fg: theme.text }, "Item 2"),
    ),
    h("text", { fg: theme.text }, "[Q] Quit"),
  )
}

tui.onKey((evt) => {
  console.error(`[KEY] ${evt.name}`)
  
  if (evt.name === "up" || evt.name === "k") {
    selectedItem = (selectedItem - 1 + items.length) % items.length
    console.error(`[UP] Selected: ${selectedItem} -> ${items[selectedItem]}`)
    evt.preventDefault()
  } else if (evt.name === "down" || evt.name === "j") {
    selectedItem = (selectedItem + 1) % items.length
    console.error(`[DOWN] Selected: ${selectedItem} -> ${items[selectedItem]}`)
    evt.preventDefault()
  } else if (evt.name === "q") {
    process.exit(0)
  }
  
  tui.renderElement(App())
})

tui.renderElement(App())
console.error("Test app ready. Press keys to navigate.")
