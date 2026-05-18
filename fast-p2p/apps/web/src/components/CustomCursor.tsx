import { useEffect, useRef } from "react"

type CursorState = "pointer" | "eye" | "cross" | "move" | "none"

const EYE_TARGETS = [
  "a[href]",
  "button:not(:disabled)",
  "input:not(:disabled)",
  "textarea:not(:disabled)",
  "select:not(:disabled)",
  "label",
  "[role='button']",
  "[tabindex]:not([tabindex='-1'])",
  "[data-cursor-role='eye']",
].join(", ")

const CROSS_TARGETS = [
  ".action-button-ghost",
  ".text-button-error",
  "[data-cursor-role='cross']",
].join(", ")

function resolveCursorState(target: EventTarget | null): CursorState {
  if (!(target instanceof Element)) return "pointer"
  if (target.closest("[data-cursor-role='none']")) return "none"
  if (target.closest(CROSS_TARGETS)) return "cross"
  if (target.closest(EYE_TARGETS)) return "eye"
  return "pointer"
}

export function CustomCursor() {
  const cursorRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const cursor = cursorRef.current
    if (!cursor) return

    const pointerMedia = window.matchMedia("(hover: hover) and (pointer: fine)")
    let enabled = false
    let frame = 0
    let currentX = -120
    let currentY = -120
    let targetX = -120
    let targetY = -120
    let moveTimeout = 0
    let hoverScale = 1
    let currentScale = 1

    const setCursorState = (state: CursorState) => {
      cursor.dataset.cursor = state
      hoverScale = state === "move" ? 1.14 : state === "eye" ? 1.08 : 1
    }

    const settleState = () => {
      if (!enabled) {
        setCursorState("none")
        return
      }

      const element = document.elementFromPoint(targetX, targetY)
      setCursorState(resolveCursorState(element))
    }

    const tick = () => {
      currentX += (targetX - currentX) * 0.13
      currentY += (targetY - currentY) * 0.13
      currentScale += (hoverScale - currentScale) * 0.16
      cursor.style.transform = `translate3d(${currentX}px, ${currentY}px, 0) scale(${currentScale})`
      frame = requestAnimationFrame(tick)
    }

    const enableCursor = () => {
      enabled = pointerMedia.matches
      document.documentElement.classList.toggle("enable-cursor", enabled)
      setCursorState(enabled ? "pointer" : "none")
    }

    const handleMove = (event: MouseEvent) => {
      if (!enabled) return
      targetX = event.clientX
      targetY = event.clientY

      if (cursor.dataset.cursor !== "move") {
        setCursorState(resolveCursorState(event.target))
      }
    }

    const handleWheel = () => {
      if (!enabled) return

      setCursorState("move")
      window.clearTimeout(moveTimeout)
      moveTimeout = window.setTimeout(settleState, 320)
    }

    const handleWindowLeave = (event: MouseEvent) => {
      if (event.relatedTarget) return
      targetX = -120
      targetY = -120
      setCursorState("none")
    }

    const handleWindowEnter = () => {
      if (!enabled) return
      settleState()
    }

    enableCursor()
    frame = requestAnimationFrame(tick)

    pointerMedia.addEventListener?.("change", enableCursor)
    window.addEventListener("mousemove", handleMove, { passive: true })
    window.addEventListener("mouseover", handleMove, { passive: true })
    window.addEventListener("wheel", handleWheel, { passive: true })
    window.addEventListener("mouseout", handleWindowLeave)
    window.addEventListener("focus", handleWindowEnter)
    window.addEventListener("blur", handleWindowLeave as EventListener)

    return () => {
      cancelAnimationFrame(frame)
      window.clearTimeout(moveTimeout)
      pointerMedia.removeEventListener?.("change", enableCursor)
      window.removeEventListener("mousemove", handleMove)
      window.removeEventListener("mouseover", handleMove)
      window.removeEventListener("wheel", handleWheel)
      window.removeEventListener("mouseout", handleWindowLeave)
      window.removeEventListener("focus", handleWindowEnter)
      window.removeEventListener("blur", handleWindowLeave as EventListener)
      document.documentElement.classList.remove("enable-cursor")
    }
  }, [])

  return (
    <div className="custom-cursor" data-cursor="pointer" ref={cursorRef} aria-hidden="true">
      <div className="custom-cursor-shape custom-cursor-pointer">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300.42 490.25" role="presentation">
          <polyline
            className="cls-1"
            points="3 2.19 293.44 273.27 153.06 285.37 232.93 462.06 179.68 486.26 102.23 307.15 3 401.55 3 2.19"
          />
        </svg>
      </div>
      <div className="custom-cursor-shape custom-cursor-eye">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 546.01 296.28" role="presentation">
          <circle className="cls-1" cx="273" cy="148.14" r="20.73" />
          <circle className="cls-1" cx="273" cy="148.14" r="82.94" />
          <path
            className="cls-2"
            d="M273,3C86.39,3,3.46,148.14,3.46,148.14S86.39,293.28,273,293.28,542.55,148.14,542.55,148.14,459.61,3,273,3Z"
          />
        </svg>
      </div>
      <div className="custom-cursor-shape custom-cursor-cross">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 413.94 413.94" role="presentation">
          <polygon points="364.44 4.24 206.97 161.72 49.5 4.24 4.24 49.5 161.72 206.97 4.24 364.44 49.5 409.7 206.97 252.22 364.44 409.7 409.7 364.44 252.22 206.97 409.7 49.5 364.44 4.24" />
        </svg>
      </div>
      <div className="custom-cursor-shape custom-cursor-move">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="-2 -2 84 84" role="presentation">
          <path d="M 40 0 a 40 40 0 1 1 -4.898587196589413e-15 80 a 40 40 0 1 1 4.898587196589413e-15 -80 z" />
        </svg>
      </div>
    </div>
  )
}
