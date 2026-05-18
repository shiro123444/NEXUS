import { test } from "node:test"
import assert from "node:assert/strict"
import { getCommandGuideExamples } from "../apps/web/src/lib/command-guide"

test("getCommandGuideExamples returns onboarding examples before a room exists", () => {
  assert.deepEqual(getCommandGuideExamples(false), [
    "创建房间",
    "加入 ROOM01",
    "加入 6A8K2P",
  ])
})

test("getCommandGuideExamples returns session-oriented examples after room creation", () => {
  assert.deepEqual(getCommandGuideExamples(true), [
    "发送文件",
    "复制链接",
    "离开房间",
  ])
})
