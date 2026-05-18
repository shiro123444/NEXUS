import os from "os"

function isPrivateIPv4(address: string): boolean {
  if (address.startsWith("10.")) return true
  if (address.startsWith("192.168.")) return true
  const parts = address.split(".").map((part) => Number(part))
  return parts.length === 4 && parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31
}

function isLikelyVirtualAdapter(name: string): boolean {
  return /(vmware|vmnet|virtual|veth|vethernet|hyper-v|zerotier|tailscale|docker|wsl|loopback)/i.test(name)
}

function isPreferredLanAdapter(name: string): boolean {
  return /(wlan|wi-?fi|wireless|ethernet|eth|en[0-9])/i.test(name)
}

export function pickLanIPv4(
  interfaces: NodeJS.Dict<os.NetworkInterfaceInfo[]>,
  preferredHost = process.env.FAST_P2P_HOST?.trim(),
): string {
  if (preferredHost) return preferredHost

  const candidates: Array<{ address: string; score: number }> = []

  for (const [name, infos] of Object.entries(interfaces)) {
    for (const info of infos ?? []) {
      if (info.family !== "IPv4" || info.internal) continue
      if (info.address.startsWith("169.254.")) continue

      let score = 0
      if (isPrivateIPv4(info.address)) score += 40
      if (isPreferredLanAdapter(name)) score += 30
      if (isLikelyVirtualAdapter(name)) score -= 60

      candidates.push({ address: info.address, score })
    }
  }

  candidates.sort((a, b) => b.score - a.score || a.address.localeCompare(b.address))
  return candidates[0]?.address ?? "127.0.0.1"
}
