import { normalizeRoomCode } from "./utils"

const SESSION_SECRET_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
const DEFAULT_SESSION_SECRET_LENGTH = 16

export type RelayInviteLocation = {
  search: string
  hash: string
}

export type RelayJoinTarget = {
  roomCode: string
  sessionSecret: string | null
}

function getCryptoApi(): Crypto | null {
  return typeof globalThis !== "undefined" && "crypto" in globalThis ? (globalThis.crypto as Crypto) : null
}

function randomIndex(max: number): number {
  const cryptoApi = getCryptoApi()
  if (cryptoApi?.getRandomValues) {
    const bytes = new Uint32Array(1)
    cryptoApi.getRandomValues(bytes)
    return bytes[0]! % max
  }

  return Math.floor(Math.random() * max)
}

function tryParseUrl(value: string): URL | null {
  try {
    return new URL(value)
  } catch {
    return null
  }
}

function parseHashSecret(hash: string): string | null {
  const normalizedHash = hash.startsWith("#") ? hash.slice(1) : hash
  if (!normalizedHash) return null

  const params = new URLSearchParams(normalizedHash)
  return normalizeRelaySessionSecret(params.get("key") ?? params.get("k") ?? "")
}

export function normalizeRelaySessionSecret(value: string): string {
  return value.trim().toUpperCase()
}

export function createRelaySessionSecret(length = DEFAULT_SESSION_SECRET_LENGTH): string {
  let output = ""
  for (let index = 0; index < length; index += 1) {
    output += SESSION_SECRET_ALPHABET[randomIndex(SESSION_SECRET_ALPHABET.length)]
  }
  return output
}

export function buildRelayJoinToken(roomCode: string, sessionSecret?: string | null): string {
  const normalizedRoom = normalizeRoomCode(roomCode)
  const normalizedSecret = normalizeRelaySessionSecret(sessionSecret ?? "")
  return normalizedSecret ? `${normalizedRoom} ${normalizedSecret}` : normalizedRoom
}

export function buildRelayInviteLink(origin: string, roomCode: string, sessionSecret?: string | null): string {
  const url = new URL(origin)
  const normalizedRoom = normalizeRoomCode(roomCode)
  const normalizedSecret = normalizeRelaySessionSecret(sessionSecret ?? "")

  if (normalizedRoom) {
    url.searchParams.set("room", normalizedRoom)
  } else {
    url.searchParams.delete("room")
  }

  url.hash = normalizedSecret ? `key=${normalizedSecret}` : ""
  return url.toString()
}

export function parseRelayInvite(location: RelayInviteLocation): RelayJoinTarget {
  const params = new URLSearchParams(location.search)
  return {
    roomCode: normalizeRoomCode(params.get("room") ?? ""),
    sessionSecret: parseHashSecret(location.hash),
  }
}

export function parseRelayJoinToken(value: string): RelayJoinTarget | null {
  const trimmed = value.trim()
  if (!trimmed) return null

  const maybeUrl = tryParseUrl(trimmed)
  if (maybeUrl) {
    const invite = parseRelayInvite({
      search: maybeUrl.search,
      hash: maybeUrl.hash,
    })
    return invite.roomCode ? invite : null
  }

  const [roomPart = "", secretPart = ""] = trimmed.split(/\s+/, 2)
  const roomWithInlineSecret = roomPart.split(":", 2)
  const roomCode = normalizeRoomCode(roomWithInlineSecret[0] ?? "")
  const sessionSecret = normalizeRelaySessionSecret(secretPart || roomWithInlineSecret[1] || parseHashSecret(roomPart) || "")

  if (!roomCode) return null

  return {
    roomCode,
    sessionSecret: sessionSecret || null,
  }
}
