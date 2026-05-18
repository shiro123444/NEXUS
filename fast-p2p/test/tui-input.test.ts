import { test } from "node:test"
import assert from "node:assert/strict"
import { RGBA } from "../src/core"
import { InputHandler, isPrintableInputChar } from "../src/core/input"
import { ScreenBuffer } from "../src/core/screen"

test("input handler maps Windows backspace to backspace", () => {
  const input = new InputHandler() as any
  assert.equal(input.parseKey("\x08").name, "backspace")
  assert.equal(input.parseKey("\x7f").name, "backspace")
})

test("printable input guard rejects control characters", () => {
  assert.equal(isPrintableInputChar("/"), true)
  assert.equal(isPrintableInputChar("A"), true)
  assert.equal(isPrintableInputChar("\x08"), false)
  assert.equal(isPrintableInputChar("\x1b"), false)
})

test("screen buffer never emits raw control characters from cells", () => {
  const screen = new ScreenBuffer(2, 1)
  const white = RGBA.fromHex("#ffffff")
  const black = RGBA.fromHex("#000000")

  screen.setCell(0, 0, "\x08", white, black, 0)
  screen.setCell(1, 0, "A", white, black, 0)

  const output = screen.render()
  assert.equal(output.includes("\x08"), false)
})
