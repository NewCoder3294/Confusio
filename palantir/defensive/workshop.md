# Mendacity Defensive — Foundry Workshop: Verify Console

**Audience:** Nicolas, in Foundry Workshop.
**Purpose:** click-through reference for building the "Verify Console" Workshop module.
Designed so you can build without re-reading the spec — every column, binding, and
section is pre-named to match `palantir/defensive/ontology.md`.

**Module name:** `Verify Console`
**Compass folder:** `Mendacity/Defensive`
**Ontology types used:** `InboundArtifact`, `InboundDetection` (via the
`InboundArtifactToDetections` link)

---

## 0. One module, two pages

Create a new Workshop module named **`Verify Console`**.

Two pages inside it, in this nav order:

1. **Verification Log** (default landing — the paginated artifact table)
2. **Artifact Detail** (drill-down from a row click; do not put this in the top nav —
   it is reached only by row selection)

Top-of-module banner (a single Markdown widget, full width):

```
MENDACITY VERIFY CONSOLE — DEFENSIVE ANALYSIS — READ-ONLY
{{operator}}  ·  {{wall_clock}}
```

Wire `{{operator}}` to the Workshop session user. `{{wall_clock}}` is a `now()` formula.

This module is **read-only**. Do not surface any Create / Edit / Delete actions in the
UI. All data arrives via `defensive/persistence/foundry_writer.py`.

---

## 1. Page: Verification Log

**Layout:** single full-width Object Table on `InboundArtifact`.

### 1.1 Table configuration

- **Object type:** `InboundArtifact`
- **Sort:** `submitted_at` descending (newest first)
- **Pagination:** enabled, 50 rows per page
- **Row click action:** navigate to the Artifact Detail page, passing
  `InboundArtifact.artifact_id` as the page parameter `selectedArtifactId`

### 1.2 Columns

| Column header | Source | Display notes |
|---|---|---|
| Submitted At | `submitted_at` | Format: `YYYY-MM-DD HH:mm UTC`. Sort handle visible. |
| Operator | `operator` | Plain string. |
| Via | `submitted_via` | Plain string: `verify_tab`, `telegram_bot`, or `api_direct`. |
| SHA-256 | `sha256` | Truncated: show first 12 characters followed by `…` (use a derived/computed column or a Workshop column-format truncation). |
| Verdict | `verdict_level` | Rendered as a colored badge per §1.3 below. |
| Confidence | `verdict_confidence` | Formatted as a percentage (e.g. `81 %`) or two-decimal float. |

Omit `file_name`, `mime`, `bytes`, `verdict_summary`, and `thumbnail_uri` from the
table — those appear on the detail page where there is space.

### 1.3 Verdict badge color rule

Define a Workshop color rule on `InboundArtifact.verdict_level`:

| verdict_level | Text color | Background color | Label |
|---|---|---|---|
| `AUTHENTIC` | `#1a9d4f` | `#0e2818` | AUTHENTIC |
| `SUSPECT` | `#c79100` | `#2a2010` | SUSPECT |
| `SYNTHETIC` | `#c4302b` | `#2a1010` | SYNTHETIC |

### 1.4 Empty state

If no rows:

> No verifications recorded yet.

Single italic line, left-aligned, no illustration.

### 1.5 Top-of-page stat strip (optional but recommended)

Three metric tiles above the table:

| Tile | Formula | Label |
|---|---|---|
| Total verifications | `count(InboundArtifact)` | TOTAL |
| Synthetic | `count(InboundArtifact where verdict_level = 'SYNTHETIC')` | SYNTHETIC |
| Authentic | `count(InboundArtifact where verdict_level = 'AUTHENTIC')` | AUTHENTIC |

If Workshop formula syntax makes this awkward, skip — the table alone is sufficient
for the demo.

---

## 2. Page: Artifact Detail

**Reached by:** row click on Verification Log (passes `selectedArtifactId`).
**Layout:** three stacked sections.

### 2.1 Section 1 — Artifact header

A metadata header strip. Bind to the `InboundArtifact` whose `artifact_id` matches
the `selectedArtifactId` page parameter.

```
ARTIFACT  {artifact_id}                   [Verdict badge]
sha256:       {sha256}
operator:     {operator}
submitted:    {submitted_at}  via {submitted_via}
file:         {file_name}  ·  {mime}  ·  {bytes} bytes
summary:      {verdict_summary}
```

- `artifact_id` in monospace.
- `sha256` full value in monospace.
- Verdict badge uses the same color rules as §1.3.
- `file_name` shows `—` (em dash) when null.
- `thumbnail_uri`: if non-null, render a thumbnail image widget using the Foundry
  media-set URI. If null or Workshop can't render the URI inline, omit the thumbnail
  row silently.

### 2.2 Section 2 — Detection signals table

A child Object Table on `InboundDetection`, filtered to rows where
`artifact_id = selectedArtifactId`. Use the `InboundArtifactToDetections` link to
populate — select the linked objects from the artifact rather than filtering manually
(this avoids re-specifying the join key in Workshop).

**Columns:**

| Column header | Source | Display notes |
|---|---|---|
| Detector | `detector_name` | Monospace. One of: c2pa, synthid, titan, ai_classifier, exif, ela, phash. |
| Severity | `severity` | Colored badge per §2.3. |
| Score | `score` | Show `—` when null. Two decimal places when present. |
| Evidence | `evidence` | Full string, wrapping allowed. |
| Latency | `latency_ms` | Format as `{n} ms`. |
| Ran At | `ran_at` | Format: `HH:mm:ss UTC`. |

Sort by `detector_name` ascending (alphabetical, deterministic order per page load).

### 2.3 Severity badge color rule

| severity | Text color | Background color | Label |
|---|---|---|---|
| `pass` | `#1a9d4f` | `#0e2818` | PASS |
| `warn` | `#c79100` | `#2a2010` | WARN |
| `fail` | `#c4302b` | `#2a1010` | FAIL |
| `n/a` | `#6b6b6b` | `#1f1f1f` | N/A |

### 2.4 Section 3 — Raw JSON drawer (collapsed by default)

A collapsible Markdown/JSON widget. Content bound to a computed field that serialises
the full artifact row (or, if Workshop supports it, bind to a Foundry Function that
returns the artifact JSON). Heading: `Raw artifact record (audit-source)`.

Collapsed by default. This is the "hide nothing" principle from `PRODUCT.md` — the
raw record is always accessible without cluttering the default view.

### 2.5 Back navigation

A "Back to log" button at the top of the detail page. Navigates to the Verification
Log page without clearing the sort/filter state.

---

## 3. Read-only enforcement

- Do not add any action buttons that call `Create`, `Edit`, or `Delete` on either type.
- Do not enable row-level edit in the Object Tables.
- If Workshop's default row click triggers an edit sheet, configure the row click to
  navigate to the Artifact Detail page instead (not the default edit modal).

---

## 4. Cross-cutting concerns

### 4.1 Empty states

- No rows in table: italic line, no illustration.
  - Verification Log: "No verifications recorded yet."
  - Detection signals: "No detection signals for this artifact." (rare; only if the
    Foundry writer failed mid-write)
- Error: one line in `#c4302b`. "Failed to load records (refresh to retry)."
- Loading: Workshop's default; do not add custom spinners.

### 4.2 Reduced motion

Workshop respects `prefers-reduced-motion` by default. Do not add custom transitions.

### 4.3 Module-level permissions

This module is read-only. Grant operators `Viewer` access in Workshop. Do not grant
`Editor` unless they are also responsible for ontology changes.

---

## 5. Build order

Estimated time given Ontology Manager already complete: 45–60 minutes.

1. (5 min) Create module skeleton: top banner, two blank pages.
2. (20 min) Verification Log page: Object Table with columns, sort, pagination,
   verdict badge color rule.
3. (5 min) Optional stat strip.
4. (20 min) Artifact Detail page: header strip, detection signals child table,
   severity badge color rule, raw JSON drawer.
5. (5 min) Row click navigation wiring + back button.
6. (5 min) Empty states, read-only check, smoke test.

---

## 6. Smoke test before the demo

1. Submit one verify call through `POST /v1/verify` with a test image.
2. Open Verification Log — the row appears, sorted newest first.
3. Click the row — Artifact Detail page opens with the correct artifact_id in the header.
4. Section 2 (Detection signals) shows the correct number of rows (up to 7).
5. Each severity badge renders with the correct color.
6. Collapse/expand the raw JSON drawer — it renders without error.
7. Confirm no Create / Edit / Delete buttons are visible anywhere.
