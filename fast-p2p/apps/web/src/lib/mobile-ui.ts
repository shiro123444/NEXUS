export type MobileActionId = "create-room" | "join-room" | "pick-file" | "copy-link" | "leave-room"

export type MobileAction = {
  id: MobileActionId
  label: string
}

export type MobileActionContext = {
  roomCode: string
  hasRoomLink: boolean
  peerConnected: boolean
}

export function getInitialCommandInput(_initialRoom: string): string {
  return ""
}

export function getMobilePrimaryActions(context: MobileActionContext): MobileAction[] {
  if (!context.roomCode) {
    return [
      { id: "create-room", label: "创建房间" },
      { id: "join-room", label: "加入房间" },
    ]
  }

  const actions: MobileAction[] = []
  if (context.peerConnected) {
    actions.push({ id: "pick-file", label: "发送文件" })
  }
  if (context.hasRoomLink) {
    actions.push({ id: "copy-link", label: "复制链接" })
  }
  actions.push({ id: "leave-room", label: "离开房间" })
  return actions
}
