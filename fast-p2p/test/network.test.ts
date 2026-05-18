import { test } from "node:test"
import assert from "node:assert/strict"
import { pickLanIPv4 } from "../src/p2p/network"

test("pickLanIPv4 prefers the active LAN adapter over virtual adapters", () => {
  const interfaces = {
    "VMware Network Adapter VMnet8": [
      { address: "10.160.175.1", family: "IPv4", internal: false },
    ],
    WLAN: [
      { address: "192.168.31.226", family: "IPv4", internal: false },
    ],
  } as any

  assert.equal(pickLanIPv4(interfaces), "192.168.31.226")
})

test("pickLanIPv4 respects explicit host overrides", () => {
  assert.equal(pickLanIPv4({} as any, "192.168.0.20"), "192.168.0.20")
})
