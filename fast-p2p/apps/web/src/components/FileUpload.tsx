type FileUploadProps = {
  peerConnected: boolean
  onFileSelect: (file: File) => void
}

export function FileUpload({ peerConnected, onFileSelect }: FileUploadProps) {
  return (
    <label
      className={`upload-surface${peerConnected ? "" : " disabled"}`}
      tabIndex={peerConnected ? 0 : -1}
      onKeyDown={(e) => {
        if ((e.key === "Enter" || e.key === " ") && peerConnected) {
          e.preventDefault()
          document.getElementById("file-input")?.click()
        }
      }}
      role="button"
      aria-label={peerConnected ? "选择要发送的文件" : "请等待对端连接后再发送文件"}
      aria-disabled={!peerConnected}
    >
      <div className="upload-copy">
        <strong>选择文件</strong>
        <span>{peerConnected ? "准备好后立即发送" : "等待对端加入"}</span>
      </div>
      <span className="upload-cta">发送</span>
      <input
        id="file-input"
        type="file"
        onChange={(event) => {
          const file = event.target.files?.[0]
          if (file) {
            onFileSelect(file)
            event.currentTarget.value = ""
          }
        }}
        disabled={!peerConnected}
        aria-label="文件选择"
      />
    </label>
  )
}
