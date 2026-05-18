type RelayLocation = {
  explicit?: string
  search: string
  protocol: string
  hostname: string
  host: string
  port: string
}

export function deriveRelayUrl(location: RelayLocation): string {
  if (location.explicit) return location.explicit

  const params = new URLSearchParams(location.search)
  const relayFromQuery = params.get("relay")
  if (relayFromQuery) return relayFromQuery

  const protocol = location.protocol === "https:" ? "wss" : "ws"
  const relayPort = "3000"
  const frontendPort = location.port
  const isNonStandardFrontendPort =
    frontendPort !== "" &&
    frontendPort !== relayPort &&
    frontendPort !== "80" &&
    frontendPort !== "443"

  const host = isNonStandardFrontendPort ? `${location.hostname}:${relayPort}` : location.host
  return `${protocol}://${host}/ws`
}
