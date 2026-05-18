export function getCommandGuideExamples(hasRoom: boolean): string[] {
  return hasRoom
    ? ["发送文件", "复制链接", "离开房间"]
    : ["创建房间", "加入 ROOM01", "加入 6A8K2P"]
}
