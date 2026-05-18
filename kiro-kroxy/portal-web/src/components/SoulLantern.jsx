import React, { useEffect, useMemo, useState } from "react";

/**
 * SoulLantern —— pixel-art loader used across the app whenever we're
 * waiting on a long-ish async (世界生成 / CG 绘制 / 预推演).
 *
 * Rendered as inline SVG so it:
 *   - stays crisp at any size (pixel-perfect via shape-rendering)
 *   - costs zero network (no external image / no model token)
 *   - can swap colors per theme if we ever want to
 *
 * Motion is CSS; `prefers-reduced-motion` users get a still frame.
 *
 * Pair with <SoulLanternLoader> for the full "with-caption" UX; the bare
 * <SoulLantern> is handy when you need just the sprite inline.
 *
 * Props (both components):
 *   size?: number          pixel edge length (default 96)
 *   className?: string     extra wrapper classes
 * SoulLanternLoader adds:
 *   lines?: string[]       captions to rotate through
 *   lineMs?: number        ms per caption (default 2200)
 *   footnote?: ReactNode   small secondary line under the caption
 */

// Palette — warm paper lantern at dusk.
const PAL = {
  paper:       "#F3C67B",
  paperShade:  "#C88A3A",
  paperDeep:   "#8A5522",
  frame:       "#3B2411",
  wickGlowA:   "#FFE89C",
  wickGlowB:   "#FF9A3C",
  wickCore:    "#FFF5D1",
  handle:      "#7A5C38",
};

export function SoulLantern({ size = 96, className = "" }) {
  // 16-col pixel grid drawn as individual <rect>s.
  //  F = dark frame / outline
  //  P = paper mid
  //  S = paper shade
  //  D = paper deep shade
  //  H = handle rope
  //  G = wick outer glow
  //  g = wick inner glow
  //  W = wick core highlight
  const grid = [
    "      HH        ",
    "     H  H       ",
    "    H    H      ",
    "   FFFFFFFF     ",
    "   FPPPPPPF     ",
    "  FPPSPPPPPF    ",
    "  FPPPgGPPPF    ",
    "  FPPGgWGPPF    ",
    "  FPSGggGSPF    ",
    "  FPPGGGGPPF    ",
    "  FPPPPPPPPF    ",
    "  FPPSPPPSPF    ",
    "   FPSPPPSF     ",
    "   FFDDDDFF     ",
    "    FFFFFF      ",
    "     FFFF       ",
  ];

  const map = {
    F: PAL.frame,
    P: PAL.paper,
    S: PAL.paperShade,
    D: PAL.paperDeep,
    H: PAL.handle,
    G: PAL.wickGlowB,
    g: PAL.wickGlowA,
    W: PAL.wickCore,
  };

  const rects = [];
  for (let y = 0; y < grid.length; y += 1) {
    const row = grid[y];
    for (let x = 0; x < row.length; x += 1) {
      const ch = row[x];
      const fill = map[ch];
      if (!fill) continue;
      rects.push(
        <rect key={`${x}-${y}`} x={x} y={y} width={1} height={1} fill={fill} />
      );
    }
  }

  return (
    <div
      className={`soul-lantern-wrap ${className}`}
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <div className="soul-lantern-halo" />
      <svg
        viewBox="0 0 16 16"
        width={size}
        height={size}
        shapeRendering="crispEdges"
        className="soul-lantern-sprite"
      >
        {rects}
        {/* Flicker overlay: a single lighter rect on the wick core that
            fades in/out to simulate a candle. */}
        <rect
          x={7}
          y={7}
          width={2}
          height={2}
          fill={PAL.wickCore}
          className="soul-lantern-flicker"
        />
      </svg>
      {/* Embers drift upward on different phases. HTML spans rather than
          SVG so CSS alone drives the animation. */}
      <span className="soul-lantern-ember soul-lantern-ember-a" />
      <span className="soul-lantern-ember soul-lantern-ember-b" />
    </div>
  );
}

const DEFAULT_LINES = [
  "造物中 · 纸骨初成",
  "造物中 · 灯芯点火",
  "造物中 · 魂气将定",
];

export function SoulLanternLoader({
  size = 96,
  lines,
  lineMs = 2200,
  footnote,
  className = "",
}) {
  const pool = useMemo(
    () => (lines && lines.length > 0 ? lines : DEFAULT_LINES),
    [lines]
  );
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    if (pool.length <= 1) return;
    const id = setInterval(() => {
      setIdx((i) => (i + 1) % pool.length);
    }, lineMs);
    return () => clearInterval(id);
  }, [pool, lineMs]);

  return (
    <div className={`flex flex-col items-center gap-3 ${className}`}>
      <SoulLantern size={size} />
      <div
        key={pool[idx]}
        className="soul-lantern-caption pixel-font text-[11px] tracking-[0.25em] text-slate-300"
      >
        {pool[idx]}
      </div>
      {footnote && (
        <div className="pixel-font text-[10px] tracking-[0.3em] text-slate-500">
          {footnote}
        </div>
      )}
    </div>
  );
}
