---
name: cinema-scroll-layout
description: Build immersive single-page scrollytelling layouts with a fixed viewport stage, chapter-based scene transitions, hero-first intro gating, theme prepaint, and explicit mobile flattening. Use when implementing or refactoring landing pages/showcases that keep one stage pinned while desktop scenes animate in depth but mobile must degrade to a readable stacked layout without flicker, title loss, or theme flash.
---

# Cinema Scroll Layout

## Overview

Use this skill for fixed-stage showcase pages that animate chapter scenes inside one pinned viewport. Treat desktop depth effects as optional enhancement; make mobile an explicit flat layout instead of a scaled-down desktop overlay.

## Workflow

### 1. Define the stage model

- Keep one root shell and one stage container.
- Model each chapter as a `.depth-scene`-style unit with separate heading and content layers.
- Keep DOM text as the source of truth. Canvas/WebGL title rendering is optional enhancement, never the only readable copy.

### 2. Build desktop first

- Use absolute scenes, CSS variables, and transform-driven transitions for desktop depth.
- Keep scene media, heading, and surface cards on separate layers so each can be flattened later.
- Gate the intro so only hero content is visible before the page becomes interactive.

### 3. Flatten mobile intentionally

- Collapse multi-column scene grids to one column.
- Move heading layers back into normal flow on small screens.
- Remove transform dependency from titles, cards, and support surfaces on small screens.
- Reduce type scale and card padding so the chapter fits the viewport without overlap.
- Hide placeholder support columns that only exist to balance desktop composition.

### 4. Remove known flash paths

- Prepaint the theme in `index.html` before React mounts.
- Use `useLayoutEffect` or equivalent for theme synchronization after mount.
- Keep display-critical components off StrictMode-sensitive visual side effects, or remove them from the critical path.
- Delay automatic scene cursor movement until the intro is fully ready.
- Hide non-hero chapters during the intro entrance phase.

### 5. Verify before closing

- Run the project build.
- Run browser checks on desktop and mobile.
- Capture and inspect:
  - intro entrance
  - intro ready
  - first chapter advance
  - theme toggle
- If a canvas/WebGL enhancement is used, verify the page still reads correctly when that enhancement is disabled.

## Read This Reference

- Read [references/layout-rules.md](./references/layout-rules.md) when choosing selectors, deciding what must flatten on mobile, or running the anti-flicker checklist.
