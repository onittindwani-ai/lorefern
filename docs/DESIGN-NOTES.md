# Design notes

Written before any CSS of Lorefern, as the quality gates ask. Everything here is original to this repo.

## What Lorefern feels like
A calm reading room. People come with a question, they need the answer, the proof and the way to the source in one glance. The accent is teal: a muted blue green that reads as "checked" without shouting. Red is kept for real alarms (a restricted preview, a stuck task past its date, the kill switch).

## Palette (60, 30, 10)
60 percent warm neutrals from the kit (cream, oat), 30 percent coffee ink and borders, 10 percent teal for the one action on a screen, the highlight on a cited passage and the active navigation row. Coverage colours of the SOP map follow meaning, not decoration: covered is the teal family, stale is amber, gap is the danger tone. Contrast is checked by the kit's contrast test and by axe in both themes.

## Type and spacing
Geist for interface and numbers, Instrument Serif for the page title and the hero number. Spacing 8, 13, 21, 34, 55, 89. The Ask screen splits 61.8 to 38.2: the answer left, its evidence right. Body width stays near 65 characters.

## Signature: ask anything
Cmd or Ctrl plus K opens one bar on every screen. Type a question, press Enter, and the answer appears in the bar with citation cards: document title, section, the exact passage with the cited words highlighted, and a button that opens the source viewer on the same words. With an empty bar the same key lists pages to jump to, so one shortcut does both. The bar never writes anything.

## Micro interactions (from the shared catalogue)
Every button presses, shows a spinner, then a tick. Approving a proposed task slides the card to Open and shows a toast with Undo for 8 seconds. The meter and counts count up once. Citation cards lift 2 px on pointer devices only. The treemap tiles grow in with a 30 ms stagger. Cards in the board lift while dragged and the old place dims. Skeletons match the final layout. Empty states always name the next action. Errors say what happened and how to fix it.

## Restricted views
An owner can preview the app as a narrower audience (staff, finance, leadership). A warning banner stays on screen, every change button is disabled, and nothing can be widened. Tags are shown as small labels so a person always sees why a row is visible.

## Motion
Tokens from the kit: out easing for entrances, press 120 to 160 ms, popovers 180 to 240 ms, sheets 240 to 320 ms, charts 600 to 800 ms once. Only transform and opacity animate. Reduced motion keeps fades and removes movement.

## What is not in the base and is built here
Treemap (CSS grid, no library), source viewer with highlight, transcript viewer with highlighted action items, citation card, review document renderer, tree view for the company folder. Each is a small component in `apps/web/src/components`.
