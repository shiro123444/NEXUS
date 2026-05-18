# 视频背景文件

将你的背景视频文件放在这个目录中。

## 推荐规格：

- **格式**: MP4 (H.264) 或 WebM (VP9)
- **分辨率**: 1920x1080 (Full HD) 或更高
- **时长**: 10-30秒循环视频
- **文件大小**: 建议 < 5MB（优化压缩）
- **帧率**: 24-30 FPS

## 文件命名：

- `background.mp4` - 主视频文件
- `background.webm` - 备用格式（可选）

## 使用方法：

1. 将视频文件复制到此目录
2. 打开 `src/routes/home-page.tsx`
3. 找到视频标签，取消注释 `<source>` 行：

```tsx
<source src="/videos/background.mp4" type="video/mp4" />
<source src="/videos/background.webm" type="video/webm" />
```

## 视频优化建议：

使用 FFmpeg 压缩视频：

```bash
# MP4 压缩
ffmpeg -i input.mp4 -vcodec libx264 -crf 28 -preset slow -vf scale=1920:1080 background.mp4

# WebM 压缩
ffmpeg -i input.mp4 -c:v libvpx-vp9 -crf 30 -b:v 0 -vf scale=1920:1080 background.webm
```

## 免费视频资源：

- [Pexels Videos](https://www.pexels.com/videos/)
- [Pixabay Videos](https://pixabay.com/videos/)
- [Coverr](https://coverr.co/)
- [Videvo](https://www.videvo.net/)

推荐搜索关键词：
- abstract motion
- particles
- technology
- data flow
- digital background
