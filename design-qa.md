# ViraData design QA

final result: passed

## Source visual truth

- Landing: `docs/reference/ChatGPT Image Oct 19, 2026, 03_21_18 PM.png`, 1189 × 753 px.
- Workspace: `docs/reference/ChatGPT Image Oct 19, 2026, 03_21_24 PM.png`, 1033 × 734 px.
- Both sources were opened. Final source and implementation images were presented together in the same comparison tool input.
- References are inspiration. RTL mirroring, Persian typography, actual financial demo data, validated spec ordering, and removal of nonfunctional controls are intentional adaptations. No pixel-perfect match is claimed.

## Implementation evidence

| State | Browser screenshot | CSS viewport / pixels |
| --- | --- | --- |
| Landing, reference comparison | `artifacts/after-landing-reference-size.png` | 1189 × 753 / 1189 × 753 |
| Workspace, reference comparison | `artifacts/after-workspace-reference-size.png` | 1033 × 734 / 1033 × 734 |
| Landing desktop | `artifacts/after-landing-desktop.png` | 1440 × 1000 / 1440 × 1000 |
| Answered workspace desktop | `artifacts/after-workspace-desktop.png` | 1440 × 1000 / 1440 × 1000 |
| Landing tablet | `artifacts/after-landing-tablet.png` | 834 × 1112 / full page |
| Workspace tablet | `artifacts/after-live-1-tablet.png` | 834 × 1112 / full page |
| Landing mobile | `artifacts/after-landing-mobile.png` | 390 × 844 / full page |
| Answered workspace mobile | `artifacts/after-live-1-mobile.png` | 390 × 844 / full page |

Desktop screenshots use CSS-pixel output, device density 1. No resampling was needed for the Landing reference comparison. Full-page captures extend vertically beyond the stated viewport. The workspace reference's compact market mockup and the implementation's actual KPI-bearing DashboardSpec have different content density; this difference is intentional and was not treated as a one-to-one content match.

## Full-view and focused comparisons

- Landing: black field, asymmetric headline, restrained warm orange, luminous narrow core, sparse particles, soft falloff and edge impact. Header sits on one line at desktop sizes. Mobile keeps readable text and a dimmer edge beam.
- Workspace: neutral dark cards, a bounded conversation column, orange action accents and independently colored series. Spec-defined content grows vertically; cards are not restricted to a fixed count.
- Fonts/typography: bundled variable Vazirmatn; Persian text and numeric units checked. Large values separate number from the unchanged unit text, without altering numeric calculations.
- Spacing/layout: 12-column spec grid, count-aware KPI spans, single-column charts in narrower workspace widths, vertical chat/dashboard flow below 760 px. No document-level overflow at 1440, 834 or 390 px.
- Colors/tokens: shared palette contains neutral surfaces and distinct orange/gold/purple/teal metric colors. Tooltip, legend, grid, focus and source controls use the theme.
- Imagery: no new raster assets were needed; the light is CSS, and the preview is the project's real report component backed by API data. Reference images remain references.
- Copy/content: Persian ViraData copy; synthetic demo dataset disclosed. No investment language, fabricated metrics or nonfunctional reference features were copied.
- Focused evidence: `artifacts/after-chart-mobile.png` verifies axes, Persian labels and legend; `artifacts/after-tooltip.png` verifies units and hover; `artifacts/after-kpi-detail.png` verifies the exact 135,000,000,000-toman value; `artifacts/after-source-rows.png` verifies real ledger rows and reconciliation.

## Comparison history

1. P2: legacy green controls leaked into KPI disclosures. Fixed specificity and neutral theme styling. Final desktop/mobile captures show the corrected controls.
2. P2: scroll-triggered insight opacity created blank regions in full-page captures. Replaced with bounded staggered fades. Final replay checks found zero hidden insights for all four responses and three viewports.
3. P2: `AnimatePresence initial={false}` suppressed descendant chart entrances. Removed the inherited suppression. Browser sampling confirmed a real internal SVG mask change from scaleX approximately 0.48 to 0.96 over 300 ms. No parent chart transform was added.
4. P2: four KPIs occupied three columns plus a second row, and unit text inflated the cards. Added count-aware spans, separate number/unit typography and a single details disclosure. Definition, exact value and source access remain available.
5. P2: removing obsolete Landing CSS exposed a hidden flex-layout dependency in the header. Added explicit flex alignment to the new header, restored round status dots and moved the light impact onto the preview edge. The final same-size Landing screenshot was reopened and compared with the reference.
6. Test harness correction: the report navigation check originally attempted to click a desktop-only navigation link while retaining a mobile viewport. Set the desktop viewport explicitly; final navigation and sample-report reconciliation checks passed.

Final images were captured again after these changes. No actionable P0/P1/P2 finding remains.

## Interaction and validation evidence

- Production TypeScript/Vite build passed in Docker; demo web/API/database healthy.
- 92 backend tests passed against isolated ephemeral PostgreSQL; one existing Starlette/httpx deprecation warning.
- Four explicit live model questions passed, including overview, shipping, strengths/weaknesses and a single-metric question.
- Final visual captures replay those actual captured answers; they are not additional live model calls. Test routes and sessionStorage are confined to browser automation.
- All 12 chart types rendered SVG marks at desktop and 390 px.
- Source drill-down returned three actual shipping rows, reconciled exactly, and closed correctly. Existing sample-report source actions also passed.
- Request error/retry, insufficient data and cancellation passed browser fault-injection checks.
- Beam opacity changed gently over time; reduced motion produced `animation: none` and `transform: none`.
- CTA hover produced translateY(-2px); keyboard focus-visible and Enter navigation passed.
- Typing and data disclosure preserved the original chart DOM instance. Tooltip displayed actual units.
- Anchor navigation and workspace skip link retained the correct route.
- Zero JavaScript page errors in final automated checks. A fresh Chrome session reported zero console errors/warnings. A real rejected model response (502) and an injected 503 were separately observed and are documented, not counted as a clean successful request.

## Follow-up polish and limits

- Optional P3: broader browser/device coverage and physical-laptop GPU/CPU profiling.
- External model composition can still fail validation; UI exposes retry. Backend validation, prompts and data contracts were preserved.
- No claim of exhaustive accessibility certification or cross-browser equivalence.

Full Persian delivery report: [docs/ui-redesign-report.md](docs/ui-redesign-report.md).
