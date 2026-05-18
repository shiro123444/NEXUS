type ShareControlsProps = {
  roomLink: string
  roomCode: string
  onCopyLink: () => void
  onCopyCode: () => void
}

export function ShareControls({ roomLink, roomCode, onCopyLink, onCopyCode }: ShareControlsProps) {
  return (
    <div className="panel-stack-surface compact-surface">
      <label className="text-field" htmlFor="share-link-input">
        <span>分享链接</span>
        <input
          id="share-link-input"
          value={roomLink || "创建或加入房间后显示"}
          readOnly
          aria-label="房间分享链接"
        />
      </label>

      <label className="text-field" htmlFor="room-code-display">
        <span>房间码</span>
        <input id="room-code-display" value={roomCode || "尚未建房"} readOnly aria-label="房间码" />
      </label>

      <div className="share-copy-actions">
        <button
          className="text-button"
          onClick={onCopyLink}
          disabled={!roomLink}
          aria-label="复制分享链接"
        >
          复制链接
        </button>
        <button
          className="text-button"
          onClick={onCopyCode}
          disabled={!roomCode}
          aria-label="复制房间码"
        >
          复制房间码
        </button>
      </div>
    </div>
  )
}
