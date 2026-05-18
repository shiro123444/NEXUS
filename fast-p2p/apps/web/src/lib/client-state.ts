import type { TransferState } from "../components/TransferItem"

export function buildRoomLink(origin: string, roomCode: string): string {
  return roomCode ? `${origin}/?room=${roomCode}` : ""
}

export function createOutgoingTransfer(id: string, name: string, size: number): TransferState {
  return {
    id,
    name,
    size,
    direction: "send",
    status: "pending",
    progress: 0,
    detail: "等待发送",
  }
}

export function createIncomingTransfer(id: string, name: string, size: number): TransferState {
  return {
    id,
    name,
    size,
    direction: "receive",
    status: "pending",
    progress: 0,
    detail: "等待接收",
  }
}

export function patchTransferList(
  current: TransferState[],
  id: string,
  patch: Partial<TransferState>,
  seed?: TransferState,
): TransferState[] {
  const index = current.findIndex((transfer) => transfer.id === id)
  if (index === -1) {
    if (!seed) return current
    return [{ ...seed, ...patch, id }, ...current]
  }

  const next = current.slice()
  next[index] = { ...next[index], ...patch, id }
  return next
}

export function removeTransfer(current: TransferState[], id: string): TransferState[] {
  return current.filter((transfer) => transfer.id !== id)
}

export function resolveStageLabel(roomCode: string, peerConnected: boolean): string {
  if (peerConnected) return "对端已就绪"
  if (roomCode) return "等待对端"
  return "创建房间"
}
