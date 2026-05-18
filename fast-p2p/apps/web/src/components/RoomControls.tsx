import { normalizeRoomCode } from "@fast-p2p/shared"

type RoomControlsProps = {
  joinCode: string
  roomCode: string
  peerConnected: boolean
  onJoinCodeChange: (code: string) => void
  onCreateRoom: () => void
  onJoinRoom: () => void
  onLeaveRoom: () => void
}

export function RoomControls({
  joinCode,
  roomCode,
  peerConnected,
  onJoinCodeChange,
  onCreateRoom,
  onJoinRoom,
  onLeaveRoom,
}: RoomControlsProps) {
  return (
    <div className="panel-stack-surface">
      <label className="text-field" htmlFor="room-code-input">
        <span>房间码</span>
        <input
          id="room-code-input"
          value={joinCode}
          onChange={(event) => onJoinCodeChange(normalizeRoomCode(event.target.value))}
          placeholder="输入房间码"
          aria-label="输入房间码并加入"
          aria-describedby="room-code-hint"
        />
      </label>
      <span id="room-code-hint" className="visually-hidden">
        输入房间码加入现有房间，或者直接创建一个新房间
      </span>

      <div className="inline-actions">
        <button
          className="action-button action-button-primary"
          onClick={onCreateRoom}
          aria-label="创建新房间"
        >
          创建
        </button>
        <button
          className="action-button action-button-secondary"
          onClick={onJoinRoom}
          aria-label="加入房间"
          disabled={!joinCode}
        >
          加入
        </button>
        {roomCode ? (
          <button className="action-button action-button-ghost" onClick={onLeaveRoom} aria-label="离开当前房间">
            离开
          </button>
        ) : null}
      </div>

      <div className="metric-line">
        <span>{roomCode || "尚未建房"}</span>
        <span>{peerConnected ? "对端已连接" : "等待对端加入"}</span>
      </div>
    </div>
  )
}
