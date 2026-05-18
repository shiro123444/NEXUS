import { parseRelayJoinToken } from "@fast-p2p/shared"

export type CommandContext = {
  roomCode: string
  peerConnected: boolean
  hasRoomLink: boolean
}

export type ParsedCommand =
  | { kind: "create-room" }
  | { kind: "join-room"; roomCode: string; sessionSecret?: string | null }
  | { kind: "copy-link" }
  | { kind: "copy-room-code" }
  | { kind: "pick-file" }
  | { kind: "leave-room" }
  | { kind: "invalid"; reason: string }

export type CommandSuggestion = {
  label: string
  command: string
  hint: string
  behavior: "execute" | "prefill"
}

const globalSuggestions: CommandSuggestion[] = [
  { label: "创建房间", command: "创建房间", hint: "生成一个新的临时房间", behavior: "execute" },
  { label: "加入房间", command: "加入 ", hint: "输入房间码加入现有会话", behavior: "prefill" },
]

const sessionSuggestions: CommandSuggestion[] = [
  { label: "复制链接", command: "复制链接", hint: "把当前房间链接发给对方", behavior: "execute" },
  { label: "复制房间码", command: "复制房间码", hint: "快速分享短码", behavior: "execute" },
  { label: "发送文件", command: "发送文件", hint: "选择文件后立即传输", behavior: "execute" },
  { label: "离开房间", command: "离开房间", hint: "结束当前会话并返回首页", behavior: "execute" },
]

function normalizeInput(value: string): string {
  return value.trim().replace(/\s+/g, " ")
}

function extractJoinTarget(value: string) {
  const normalized = value.trim()
  if (normalized.startsWith("/join")) {
    return parseRelayJoinToken(normalized.slice("/join".length).trim())
  }
  if (normalized.startsWith("加入")) {
    return parseRelayJoinToken(normalized.slice("加入".length).trim())
  }
  return null
}

export function parseCommandInput(rawValue: string, context: CommandContext): ParsedCommand {
  const value = normalizeInput(rawValue)
  const normalized = value.toLowerCase()

  if (!value) {
    return { kind: "invalid", reason: "请输入命令" }
  }

  if (normalized === "/create" || normalized === "创建房间" || normalized === "新建房间") {
    return { kind: "create-room" }
  }

  if (normalized.startsWith("/join") || normalized.startsWith("加入")) {
    const target = extractJoinTarget(value)
    return target?.roomCode
      ? { kind: "join-room", roomCode: target.roomCode, sessionSecret: target.sessionSecret }
      : { kind: "invalid", reason: "请输入要加入的房间码" }
  }

  if (normalized === "复制链接" || normalized === "copy link") {
    return context.hasRoomLink ? { kind: "copy-link" } : { kind: "invalid", reason: "当前还没有可复制的链接" }
  }

  if (normalized === "复制房间码" || normalized === "复制房间") {
    return context.roomCode ? { kind: "copy-room-code" } : { kind: "invalid", reason: "当前还没有房间码" }
  }

  if (normalized === "发送文件" || normalized === "选择文件" || normalized === "/send") {
    if (!context.roomCode) return { kind: "invalid", reason: "请先创建或加入房间" }
    if (!context.peerConnected) return { kind: "invalid", reason: "请先等待对端接入房间" }
    return { kind: "pick-file" }
  }

  if (normalized === "离开房间" || normalized === "退出房间" || normalized === "/leave") {
    return context.roomCode ? { kind: "leave-room" } : { kind: "invalid", reason: "当前不在任何房间中" }
  }

  return { kind: "invalid", reason: "未识别的命令" }
}

export function getCommandSuggestions(input: string, context: CommandContext): CommandSuggestion[] {
  const value = normalizeInput(input)
  const source = context.roomCode ? [...globalSuggestions, ...sessionSuggestions] : globalSuggestions

  const available = source.filter((item) => {
    if (item.label === "复制链接") return context.hasRoomLink
    if (item.label === "复制房间码") return Boolean(context.roomCode)
    if (item.label === "发送文件") return Boolean(context.roomCode)
    if (item.label === "离开房间") return Boolean(context.roomCode)
    return true
  })

  if (!value) return available

  return available.filter((item) => item.label.startsWith(value) || item.command.toLowerCase().startsWith(value.toLowerCase()))
}
