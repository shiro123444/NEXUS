import { useEffect, useRef, type RefObject } from "react"
import {
  DoubleSide,
  Group,
  Mesh,
  MeshBasicMaterial,
  PerspectiveCamera,
  PlaneGeometry,
  Scene,
  SRGBColorSpace,
  TextureLoader,
  WebGLRenderer,
} from "three"
import { Text as TroikaText } from "troika-three-text"

type ThreeTitleStageProps = {
  hostRef: RefObject<HTMLElement | null>
}

type SceneSnapshot = {
  ahead: number
  behind: number
  progress: number
  pass: number
  presence: number
  focus: number
}

const CAMERA_Z = 800
const TROIKA_FONT_URL = "/fonts/noto-sans-sc-chinese-simplified-700-normal.woff"

function loadTexture(url: string) {
  return new Promise<ReturnType<TextureLoader["load"]>>((resolve, reject) => {
    const loader = new TextureLoader()
    loader.load(
      url,
      (texture) => {
        texture.colorSpace = SRGBColorSpace
        resolve(texture)
      },
      undefined,
      reject,
    )
  })
}

function parseVar(style: CSSStyleDeclaration, property: string) {
  const raw = style.getPropertyValue(property).trim()
  if (!raw) return 0
  const value = Number.parseFloat(raw)
  return Number.isFinite(value) ? value : 0
}

function createSnapshot(style: CSSStyleDeclaration): SceneSnapshot {
  return {
    ahead: parseVar(style, "--scene-ahead"),
    behind: parseVar(style, "--scene-behind"),
    progress: parseVar(style, "--scene-title-progress"),
    pass: parseVar(style, "--scene-title-pass"),
    presence: parseVar(style, "--scene-title-presence"),
    focus: parseVar(style, "--scene-focus"),
  }
}

type TroikaTitleResult = {
  group: Group
  ready: Promise<boolean>
}

function syncTroikaText(text: any, label: string) {
  return new Promise<boolean>((resolve) => {
    let settled = false
    const timer = setTimeout(() => {
      if (settled) return
      settled = true
      console.warn(`Timed out syncing ${label}`)
      resolve(false)
    }, 5000)

    try {
      text.sync(() => {
        if (settled) return
        clearTimeout(timer)
        settled = true
        resolve(true)
      })
    } catch (error) {
      clearTimeout(timer)
      settled = true
      console.error(`Failed to sync ${label}`, error)
      resolve(false)
    }
  })
}

function createTroikaTitle(
  lines: string[],
  {
    fontSize,
    lineGap,
    label,
  }: {
    fontSize: number
    lineGap: number
    label: string
  },
): TroikaTitleResult {
  const group = new Group()
  const syncs: Array<Promise<boolean>> = []

  lines.forEach((line, index) => {
    const text = new TroikaText()
    text.text = line
    text.font = TROIKA_FONT_URL
    text.fontSize = fontSize
    text.color = 0x101419
    text.anchorX = "center"
    text.anchorY = "middle"
    text.position.set(0, ((lines.length - 1) / 2 - index) * lineGap, 0)
    text.outlineWidth = 0.5
    text.outlineColor = 0x101419
    text.depthOffset = -1
    syncs.push(syncTroikaText(text, `${label} line ${index + 1}`))
    group.add(text)
  })

  return {
    group,
    ready: syncs.length === 0 ? Promise.resolve(false) : Promise.all(syncs).then((results) => results.every(Boolean)),
  }
}

function createSecurityTitle(lines: string[]) {
  return createTroikaTitle(lines, {
    fontSize: 84,
    lineGap: 110,
    label: "security title",
  })
}

function createRoomTitle(lines: string[]) {
  return createTroikaTitle(lines, {
    fontSize: 82,
    lineGap: 108,
    label: "room title",
  })
}

function createShareTitle(lines: string[]) {
  return createTroikaTitle(lines, {
    fontSize: 82,
    lineGap: 108,
    label: "share title",
  })
}

function createTransferTitle(lines: string[]) {
  return createTroikaTitle(lines, {
    fontSize: 82,
    lineGap: 108,
    label: "transfer title",
  })
}

function createFutureTitle(lines: string[]) {
  return createTroikaTitle(lines, {
    fontSize: 82,
    lineGap: 108,
    label: "future title",
  })
}

function createPlane(texture: Awaited<ReturnType<typeof loadTexture>>, width: number, height: number) {
  const geometry = new PlaneGeometry(width, height)
  const material = new MeshBasicMaterial({
    map: texture,
    transparent: true,
    side: DoubleSide,
  })
  return new Mesh(geometry, material)
}

function setMaterialOpacity(object: Group | Mesh, opacity: number) {
  object.traverse((child) => {
    if (child instanceof Mesh && child.material instanceof MeshBasicMaterial) {
      child.material.opacity = opacity
    } else if (child instanceof TroikaText) {
      ;(child as unknown as { fillOpacity?: number; strokeOpacity?: number }).fillOpacity = opacity
      ;(child as unknown as { fillOpacity?: number; strokeOpacity?: number }).strokeOpacity = opacity
    }
  })
}

function disposeNode(node: Group | Mesh) {
  node.traverse((child) => {
    if (child instanceof Mesh) {
      child.geometry.dispose()
      if (Array.isArray(child.material)) {
        child.material.forEach((material) => material.dispose())
      } else {
        child.material.dispose()
      }
    } else if (child instanceof TroikaText) {
      ;(child as unknown as { dispose?: () => void }).dispose?.()
    }
  })
}

export function ThreeTitleStage({ hostRef }: ThreeTitleStageProps) {
  const mountRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const host = hostRef.current
    const mount = mountRef.current
    if (!host || !mount) return

    const heroScene = host.querySelector<HTMLElement>(".depth-scene-hero")
    const securityScene = host.querySelector<HTMLElement>(".depth-scene-security")
    const roomScene = host.querySelector<HTMLElement>(".depth-scene-room")
    const shareScene = host.querySelector<HTMLElement>(".depth-scene-share")
    const transferScene = host.querySelector<HTMLElement>(".depth-scene-transfer")
    const futureScene = host.querySelector<HTMLElement>(".depth-scene-future")

    const securityTitleEl = host.querySelector<HTMLElement>(".scene-heading-layer-security .scene-title")
    const roomTitleEl = host.querySelector<HTMLElement>(".scene-heading-layer-room .scene-title")
    const shareTitleEl = host.querySelector<HTMLElement>(".scene-heading-layer-share .scene-title")
    const transferTitleEl = host.querySelector<HTMLElement>(".scene-heading-layer-transfer .scene-title")
    const futureTitleEl = host.querySelector<HTMLElement>(".scene-heading-layer-future .scene-title")

    if (!heroScene || !securityScene || !roomScene || !shareScene || !transferScene || !futureScene) return
    if (!securityTitleEl || !roomTitleEl || !shareTitleEl || !transferTitleEl || !futureTitleEl) return

    let frame = 0
    let disposed = false
    const readyClasses = [
      "has-three-title-security",
      "has-three-title-room",
      "has-three-title-share",
      "has-three-title-transfer",
      "has-three-title-future",
    ]

    const scene = new Scene()
    const camera = new PerspectiveCamera(60, 1, 1, 12000)
    camera.position.set(0, 0, CAMERA_Z)

    const renderer = new WebGLRenderer({
      alpha: true,
      antialias: true,
    })
    renderer.outputColorSpace = SRGBColorSpace
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5))
    mount.appendChild(renderer.domElement)

    const resize = () => {
      const width = mount.clientWidth || window.innerWidth
      const height = mount.clientHeight || window.innerHeight
      const fov = (180 * (2 * Math.atan(height / 2 / CAMERA_Z))) / Math.PI
      camera.fov = fov
      camera.aspect = width / Math.max(height, 1)
      camera.updateProjectionMatrix()
      renderer.setSize(width, height, false)
    }

    Promise.all([
      loadTexture("/reference/assets/intro/ok.png"),
      loadTexture("/reference/assets/feb/camera-culture.jpg"),
      loadTexture("/reference/assets/jan/iceland_dribbble.jpg"),
      loadTexture("/reference/assets/mar/certificate-when-to-travel-sotd.jpg"),
      loadTexture("/reference/assets/mar/asia-office.jpg"),
      loadTexture("/reference/assets/sep/nfl_screens_4x.jpg"),
      loadTexture("/reference/assets/nov/adobe_xd_mockup.jpg"),
    ])
      .then(([
        introTexture,
        cameraTexture,
        icelandTexture,
        certificateTexture,
        officeTexture,
        roomScreenTexture,
        roomMockupTexture,
      ]) => {
        if (disposed) return

        const securityTitle = createSecurityTitle(
          Array.from(securityTitleEl.querySelectorAll<HTMLElement>(".scene-title-line"))
            .map((node) => (node.textContent ?? "").trim())
            .filter(Boolean),
        )
        const roomTitle = createRoomTitle(
          Array.from(roomTitleEl.querySelectorAll<HTMLElement>(".scene-title-line"))
            .map((node) => (node.textContent ?? "").trim())
            .filter(Boolean),
        )
        const shareTitle = createShareTitle(
          Array.from(shareTitleEl.querySelectorAll<HTMLElement>(".scene-title-line"))
            .map((node) => (node.textContent ?? "").trim())
            .filter(Boolean),
        )
        const transferTitle = createTransferTitle(
          Array.from(transferTitleEl.querySelectorAll<HTMLElement>(".scene-title-line"))
            .map((node) => (node.textContent ?? "").trim())
            .filter(Boolean),
        )
        const futureTitle = createFutureTitle(
          Array.from(futureTitleEl.querySelectorAll<HTMLElement>(".scene-title-line"))
            .map((node) => (node.textContent ?? "").trim())
            .filter(Boolean),
        )

        const heroIntroCard = createPlane(introTexture, 180, 180)
        const heroCameraCard = createPlane(cameraTexture, 180, 118)
        const heroIcelandCard = createPlane(icelandTexture, 220, 150)
        const securityCertificateCard = createPlane(certificateTexture, 180, 120)
        const securityOfficeCard = createPlane(officeTexture, 166, 118)
        const roomScreenCard = createPlane(roomScreenTexture, 194, 136)
        const roomMockupCard = createPlane(roomMockupTexture, 176, 126)

        scene.add(securityTitle.group)
        scene.add(roomTitle.group)
        scene.add(shareTitle.group)
        scene.add(transferTitle.group)
        scene.add(futureTitle.group)
        scene.add(heroIntroCard)
        scene.add(heroCameraCard)
        scene.add(heroIcelandCard)
        scene.add(securityCertificateCard)
        scene.add(securityOfficeCard)
        scene.add(roomScreenCard)
        scene.add(roomMockupCard)
        host.classList.add("has-three-title-stage")
        const titleReadyMap: Array<[string, Promise<boolean>]> = [
          ["has-three-title-security", securityTitle.ready],
          ["has-three-title-room", roomTitle.ready],
          ["has-three-title-share", shareTitle.ready],
          ["has-three-title-transfer", transferTitle.ready],
          ["has-three-title-future", futureTitle.ready],
        ]

        titleReadyMap.forEach(([className, ready]) => {
          ready.then((isReady) => {
            if (disposed || !isReady) return
            host.classList.add(className)
          })
        })
        resize()

        const tick = () => {
          const hostStyle = getComputedStyle(host)
          const mouseX = parseVar(hostStyle, "--mouse-x")
          const mouseY = parseVar(hostStyle, "--mouse-y")
          const lensX = parseVar(hostStyle, "--lens-x")
          const lensY = parseVar(hostStyle, "--lens-y")

          camera.rotation.x += (mouseY * -0.12 - camera.rotation.x) * 0.08
          camera.rotation.y += (mouseX * -0.12 - camera.rotation.y) * 0.08

          const heroSnapshot = createSnapshot(getComputedStyle(heroScene))
          const securitySnapshot = createSnapshot(getComputedStyle(securityScene))
          const roomSnapshot = createSnapshot(getComputedStyle(roomScene))
          const shareSnapshot = createSnapshot(getComputedStyle(shareScene))
          const transferSnapshot = createSnapshot(getComputedStyle(transferScene))
          const futureSnapshot = createSnapshot(getComputedStyle(futureScene))

          const heroZ = -5800 * heroSnapshot.ahead + 40 * heroSnapshot.behind + 640 * heroSnapshot.progress + 140 * heroSnapshot.pass

          heroIntroCard.visible = heroSnapshot.presence > 0.06
          heroIntroCard.position.set(-270 + lensX * -22, 198 + lensY * 14, heroZ - 120)
          heroIntroCard.rotation.set(-0.12, 0.18, 0)
          heroIntroCard.scale.setScalar(0.92 + heroSnapshot.focus * 0.08)
          setMaterialOpacity(heroIntroCard, heroSnapshot.presence)

          heroCameraCard.visible = heroSnapshot.presence > 0.08
          heroCameraCard.position.set(-210 + lensX * 12, -220 + lensY * -10, heroZ + 180)
          heroCameraCard.rotation.set(-0.08, 0.12, 0.02)
          heroCameraCard.scale.setScalar(0.8 + heroSnapshot.focus * 0.14)
          setMaterialOpacity(heroCameraCard, heroSnapshot.presence * 0.92)

          heroIcelandCard.visible = heroSnapshot.presence > 0.08
          heroIcelandCard.position.set(312 + lensX * -18, -92 + lensY * 12, heroZ + 280)
          heroIcelandCard.rotation.set(0.08, -0.14, -0.02)
          heroIcelandCard.scale.setScalar(0.88 + heroSnapshot.focus * 0.12)
          setMaterialOpacity(heroIcelandCard, heroSnapshot.presence * 0.94)

          const securityZ =
            -4200 * securitySnapshot.ahead +
            120 * securitySnapshot.behind +
            1480 * securitySnapshot.progress +
            520 * securitySnapshot.pass
          securityTitle.group.visible = securitySnapshot.presence > 0.001
          securityTitle.group.position.set(18 + mouseX * -7, -14 + mouseY * 5, securityZ)
          securityTitle.group.scale.setScalar(0.56 + securitySnapshot.progress * 0.22 + securitySnapshot.pass * 0.12)
          setMaterialOpacity(securityTitle.group, securitySnapshot.presence)

          securityCertificateCard.visible = securitySnapshot.presence > 0.08
          securityCertificateCard.position.set(274 + lensX * -18, 164 + lensY * 10, securityZ + 260)
          securityCertificateCard.rotation.set(0.06, -0.14, 0.01)
          securityCertificateCard.scale.setScalar(0.82 + securitySnapshot.focus * 0.1)
          setMaterialOpacity(securityCertificateCard, securitySnapshot.presence * 0.92)

          securityOfficeCard.visible = securitySnapshot.presence > 0.08
          securityOfficeCard.position.set(-236 + lensX * 16, -186 + lensY * -8, securityZ + 140)
          securityOfficeCard.rotation.set(-0.08, 0.14, -0.01)
          securityOfficeCard.scale.setScalar(0.78 + securitySnapshot.focus * 0.12)
          setMaterialOpacity(securityOfficeCard, securitySnapshot.presence * 0.88)

          const roomZ =
            -3600 * roomSnapshot.ahead +
            160 * roomSnapshot.behind +
            1380 * roomSnapshot.progress +
            540 * roomSnapshot.pass
          roomTitle.group.visible = roomSnapshot.presence > 0.001
          roomTitle.group.position.set(-18 + mouseX * -6, 10 + mouseY * 5, roomZ)
          roomTitle.group.scale.setScalar(0.52 + roomSnapshot.progress * 0.22 + roomSnapshot.pass * 0.08)
          setMaterialOpacity(roomTitle.group, roomSnapshot.presence)

          roomScreenCard.visible = roomSnapshot.presence > 0.08
          roomScreenCard.position.set(286 + lensX * -16, 146 + lensY * 10, roomZ + 240)
          roomScreenCard.rotation.set(0.04, -0.12, 0.02)
          roomScreenCard.scale.setScalar(0.8 + roomSnapshot.focus * 0.08)
          setMaterialOpacity(roomScreenCard, roomSnapshot.presence * 0.9)

          roomMockupCard.visible = roomSnapshot.presence > 0.08
          roomMockupCard.position.set(-248 + lensX * 14, -188 + lensY * -8, roomZ + 120)
          roomMockupCard.rotation.set(-0.06, 0.12, -0.02)
          roomMockupCard.scale.setScalar(0.76 + roomSnapshot.focus * 0.1)
          setMaterialOpacity(roomMockupCard, roomSnapshot.presence * 0.86)

          const shareZ =
            -3400 * shareSnapshot.ahead +
            140 * shareSnapshot.behind +
            1320 * shareSnapshot.progress +
            500 * shareSnapshot.pass
          shareTitle.group.visible = shareSnapshot.presence > 0.001
          shareTitle.group.position.set(16 + mouseX * -6, -8 + mouseY * 5, shareZ)
          shareTitle.group.scale.setScalar(0.5 + shareSnapshot.progress * 0.22 + shareSnapshot.pass * 0.08)
          setMaterialOpacity(shareTitle.group, shareSnapshot.presence)

          const transferZ =
            -3200 * transferSnapshot.ahead +
            120 * transferSnapshot.behind +
            1280 * transferSnapshot.progress +
            480 * transferSnapshot.pass
          transferTitle.group.visible = transferSnapshot.presence > 0.001
          transferTitle.group.position.set(-16 + mouseX * -6, 10 + mouseY * 5, transferZ)
          transferTitle.group.scale.setScalar(0.5 + transferSnapshot.progress * 0.22 + transferSnapshot.pass * 0.08)
          setMaterialOpacity(transferTitle.group, transferSnapshot.presence)

          const futureZ =
            -3000 * futureSnapshot.ahead +
            100 * futureSnapshot.behind +
            1240 * futureSnapshot.progress +
            460 * futureSnapshot.pass
          futureTitle.group.visible = futureSnapshot.presence > 0.001
          futureTitle.group.position.set(14 + mouseX * -6, -6 + mouseY * 5, futureZ)
          futureTitle.group.scale.setScalar(0.5 + futureSnapshot.progress * 0.22 + futureSnapshot.pass * 0.08)
          setMaterialOpacity(futureTitle.group, futureSnapshot.presence)

          renderer.render(scene, camera)
          frame = requestAnimationFrame(tick)
        }

        tick()
      })
      .catch((error) => {
        console.error("Failed to initialize three hero stage", error)
      })

    window.addEventListener("resize", resize)

    return () => {
      disposed = true
      window.removeEventListener("resize", resize)
      cancelAnimationFrame(frame)
      renderer.dispose()
      scene.children.forEach((child) => {
        if (child instanceof Group || child instanceof Mesh) {
          disposeNode(child)
        }
      })
      mount.innerHTML = ""
      host.classList.remove("has-three-title-stage")
      host.classList.remove(...readyClasses)
    }
  }, [hostRef])

  return <div className="three-title-stage" ref={mountRef} aria-hidden="true" />
}
