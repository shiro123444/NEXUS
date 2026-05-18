# Layout Rules

## Core model

- Keep one pinned stage for desktop scenes.
- Keep each chapter isolated in its own scene container.
- Keep headings in DOM even when a canvas/WebGL layer exists.
- Keep desktop-only balancing columns optional and removable on mobile.

## Mobile flattening rules

- Convert heading overlays from `position: absolute` back to normal flow.
- Collapse scene grids to one column.
- Remove 3D transforms from:
  - stage wrappers
  - heading tracks
  - titles/glyph spans
  - supporting cards and stacks
- Reduce hero/title type sizes before reducing body copy size.
- Tighten card padding and vertical gaps before hiding important content.
- Hide decorative media clusters if they compete with readable content.

## Anti-flicker rules

- Prepaint theme on the root element in HTML before app bootstrap.
- Avoid visual initialization that mounts, disposes, and remounts on first paint.
- Delay scene auto-advance until intro is ready.
- During intro entrance, hide non-hero chapter headings and content.
- Do not let a canvas/WebGL title layer be the only visible text layer.

## Verification checklist

- Build succeeds.
- First paint matches the persisted theme.
- Intro entrance shows only hero content.
- Intro ready shows readable hero title/body without overlap.
- First scene advance keeps titles readable and cards non-overlapping.
- Mobile screenshots show title, body, and status cards in vertical order.
- Desktop still preserves the intended fixed-stage composition.
