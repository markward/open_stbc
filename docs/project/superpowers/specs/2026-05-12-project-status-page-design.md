# Project status page — design

## Purpose

A single static HTML page advertising the **Star Trek: Bridge Commander —
Dauntless** project, showing roadmap progress and framing the work
explicitly as an experimental, AI-assisted (Claude) rebuild of a legacy
game engine. Hosted on GitHub Pages.

## Output

- File: `gh-pages/project-status.html`
- Image directory: `gh-pages/img/` (currently empty; `latest.png` slot
  referenced from the page).
- No JS dependencies (the only script is an inline `onerror` fallback on
  the `<img>` tag). No build step.
- External dependencies: Google Fonts (Antonio + JetBrains Mono). No CSS
  frameworks, no analytics, no trackers.

## Naming & framing

- **Public name:** "Star Trek: Bridge Commander — Dauntless" (or
  "Project Dauntless" in copy). The repo name `open_stbc` is treated as
  internal.
- **Motto:** "May the wind be at our backs" — borrowed from the closing
  line of Lawrence Holland's foreword in the original 2002 manual.
  Appears under the hero and in the footer.
- **Framing:** experimental, Claude-assisted rebuild of a legacy engine.
  The page leads with the experimental nature: "we don't know how it ends",
  "as far as we know, the first serious attempt at this with an LLM as
  primary collaborator". Honesty about uncertainty is the tone target.

## Visual style

LCARS-inspired, modeled on the same design language used in the
project's "BC manual" reference document. Key elements:

- Top sticky bar with a left orange corner (rounded inner cutout) and
  coloured bar-segments.
- Sticky left navigation rail of coloured "rail-blocks" linking to
  in-page sections.
- Main content column max-width ~1100 px.
- Bottom bar mirroring the top.
- Starfield background via stacked `radial-gradient`s on `body::before`.
- Palette uses LCARS standards: orange, peach, red, pink, purple,
  violet, blue, light-blue, yellow, green; black background; peach text.
- Fonts: Antonio (display) + JetBrains Mono (eyebrows, stardates, codes).

## Page sections

1. **Top bar** — corner + segment bar + animated "Project Dauntless ·
   Engineering Log" stardate slot.

2. **Hero** — big tri-line title (`Star Trek` / `Bridge Commander` /
   `Dauntless`), eyebrow `Experimental Reconstruction Project · 2026`,
   subtitle making clear the experimental + Claude-assisted nature, the
   motto, and a row of meta pills (`Phase 03 · Active`, `Claude-Assisted`,
   `C++ · CPython embedded`, `macOS · Linux · Windows`, `Fan Project`).

3. **The Experiment** — three paragraphs framing the project honestly:
   what it is, that Claude wrote the bulk of the code as pair-programmer,
   that it might fail. Plus an experimental-note callout.

4. **Mission** — what we're building, with four cards: runs original
   scripts, renders natively, crosses platforms, stays open.

5. **Latest Signal** — two-column block. Left: hand-written narrative
   summary of recent progress, stamped with the date. Right:
   `img/latest.png` slot + caption. `onerror` falls back to a styled
   placeholder block if the file is missing.

6. **Phase roadmap** — 15 phase cards in a 2-column grid (1-col on
   narrow). Each card: phase number, title, one-line summary, status
   badge. States: `Complete` (green), `In Progress` (orange),
   `Standby` (muted). Followed by a status-note callout warning that
   phases past 05 are educated guesses.

7. **Under the Hood** — LCARS specs-block listing host, renderer,
   physics, audio, UI, asset pipeline, platforms, source material.
   Followed by a "How Claude Fits" subsection describing the brainstorm
   → spec → plan → implement loop and the human review gate.

8. **Who's Building This** — three crew cards: Captain (Mark Ward),
   Engineering (Claude), Original Crew (Totally Games / Activision).
   Includes a pull quote from Lawrence Holland's foreword.

9. **Disclaimer** — non-commercial fan project; not affiliated with
   Activision, Totally Games, Paramount, or CBS. No original game assets
   distributed. AI-assisted authorship disclosed.

10. **Bottom bar** — mirrors the top; footer text repeats the motto.

## Phase list (locked)

```
01 Headless logic engine        COMPLETE
02 Native renderer + flight     COMPLETE
03 UI framework                 ACTIVE
04 AI scripts online            STANDBY
05 Targeting & combat           STANDBY
06 Audio engine                 STANDBY
07 Bridge interior              STANDBY
08 Save & load                  STANDBY
09 Quick Battle                 STANDBY
10 UI polish pass               STANDBY
11 Character animation          STANDBY
12 Voice & cinematics           STANDBY
13 Single-player campaign       STANDBY
14 1.0 release                  STANDBY
15 Mod & SDK compatibility      STANDBY
```

## Layout & responsiveness

- Desktop: rail (180 px) + main (max 1100 px).
- ≤900 px: rail collapses to icon-only column; phases and specs grids
  collapse to one column; latest section stacks.
- ≤600 px: rail hidden entirely; top/bottom corners hidden; hero scaled
  down.

## Out of scope

- No dynamic content (RSS, JSON feeds, GitHub API). "Latest" is hand-
  edited.
- No build pipeline. Editing the HTML directly is the workflow.
- No analytics, no service-worker, no PWA manifest.
- No alternate themes. LCARS only.

## Maintenance

- "Latest Signal" is updated by hand when there's something worth
  showing. There is no automation.
- Phase statuses change by editing the `class` on the relevant
  `<article class="phase …">` block.
- Active-phase pill in the hero is hard-coded; update when phase 3
  closes.
- Screenshot is dropped into `gh-pages/img/latest.png` (filename fixed
  so updates don't need an HTML edit).
