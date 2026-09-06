# Information Architecture spec — Executive IA (EI-1)

This document is the source of truth for the dashboard's screen map,
navigation and design tokens. It is public-repo safe: it contains no real
money figures, supplier names or project numbers.

## Principles

1. **5-second answer.** Every screen answers exactly one question, and the
   answer is visible without scrolling: a KPI number, a verdict, or a chart
   with a one-line takeaway above it. If a screen needs a paragraph of
   explanation before the reader understands the point, split it.
2. **One question per screen.** A screen's `<h2>` is the question it answers
   ("Where does the money go?", "When did each style move through
   production?"). Supporting detail lives in collapsible fallback tables,
   never mixed onto a second topic.
3. **Breadcrumbs everywhere.** Every screen shows `Home › … › …` directly
   under the header, and a persistent **← Back** button targeting the
   parent crumb. The current screen is the last crumb (plain text, not a
   link); every earlier crumb is a link.

## Screen map

```
Home = Stage menu (#/home, default)
├── Stage detail (#/stage/<stage_id>)   ×12 stages
└── Deep dive
    ├── Cost structure      (#/tab/cost)
    ├── Product timelines   (#/tab/timelines)
    ├── Suppliers           (#/tab/suppliers)
    ├── Benchmarks          (#/tab/benchmarks)
    ├── Optimizations       (#/tab/optimizations)
    └── Glossary            (#/tab/glossary)
```

- **Home = Stage menu** — "How is a figure made?" The 10 numbered
  production stages in process order (admin & unclassified collapsed under
  "Other"), each entry opening its stage detail page. Nothing else on this
  screen; data-quality callouts live on Cost structure.
- **Stage detail** — "What did one stage cost, when, and to whom?"
  Monthly/daily charts, top suppliers/styles, and a not-booked explainer
  plate for stages tracked outside this ledger.
- **Deep dive tabs** — unchanged content from the previous tab layout;
  only their addresses moved under `#/tab/<name>`.

## Routing

| Hash | Screen |
| --- | --- |
| `#/home` (or empty / unknown) | Home — the stage menu |
| `#/tab/<name>` | Deep-dive tab (`cost`, `timelines`, `suppliers`, `benchmarks`, `optimizations`, `glossary`) |
| `#/stage/<id>` | Stage detail page |

- The route table ships inside the JSON payload (`ia` section), so nav,
  breadcrumbs and the client-side router render from one source.
- **Backwards compatibility:** old addresses redirect (via
  `location.replace`, so no dead history entry): `#/overview` →
  `#/home` (the stage menu lives there now). Old in-page tab links never
  had hashes; they now map to `#/tab/<name>`.
- Back/forward browser buttons work (the router listens to `hashchange`).

## Breadcrumb rules

| Screen | Trail | Back target |
| --- | --- | --- |
| Home | `Home` | — (`#/home`) |
| Tab | `Home › <Tab title>` | `#/home` |
| Stage detail | `Home › Process › <Stage label>` | `#/home` |

## Design tokens

Declared once as CSS variables on `:root` in the dashboard template and
reused by every rule (no raw font sizes/spacing re-declared):

| Token | Value | Used for |
| --- | --- | --- |
| `--kpi-size` | 44px (40–48px band) | reserved — large KPI numbers (no KPI tiles in the current IA) |
| `--kpi-label-size` | 12px | reserved — KPI captions |
| `--tile-num-size` | 24px | regular tile numbers |
| `--h2-size` / `h3` | 26px / 17px | screen / section headings |
| `--text-base` / `--text-sm` | 15px / 13.5px | body / hints & tables |
| `--space-1…4` | 8 / 12 / 16 / 24px | paddings and gaps |
| `--card-bg/-radius/-shadow` | #fff / 10px / soft | card surfaces |
| `--status-good/-warn/-bad/-neutral` | green/amber/red/gray | verdicts, data-quality notes |
| `--accent` | blue | links, active nav |

A dark theme is out of scope here; print mode is tracked separately
(PE-5 follow-ups).
