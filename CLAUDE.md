# ActionKit Templatesets

## Companion assets repo: `pubstatic` (ALWAYS check it)

The CSS and JS these templates depend on do **not** live in this repo — they live in
**`pubstatic`** (`/Users/lucas/Work/projects/pubstatic`, git `ssh://git@gitlab.wemove.eu:2222/internal/pubstatic.git`).

- The JS bundle is `wemove-main.bundle.min.js`, built from `pubstatic/projects/action-kit/src/js/`,
  entry point `wemove-main.js` (which lists exactly which modules are bundled).
- The CSS is `wemove.css` (Tailwind here drives classes the bundle/styles consume).
- Templates wire to the bundle via `window.*` globals (e.g. `window.blueskyShareText`),
  `data-wm-*` attributes (e.g. `data-wm-share-content`, `data-wm-skip-button`), and `wemove.*` /
  `wemove.utilities.*` helpers.

**Rule:** before claiming any `window.*` var, `data-wm-*` hook, or `wemove.*` helper is unused/dead,
or before explaining how a template behavior works, **read the consumer in `pubstatic` first** —
check `wemove-main.js` imports and the built bundle, not just `src/`. A module sitting in
`modules/obsolete/` and not imported by `wemove-main.js` is NOT in the bundle.

## Supported Languages

The project supports seven languages:

- `en` — English
- `es` — Spanish
- `pl` — Polish
- `nl` — Dutch
- `de` — German
- `fr` — French
- `it` — Italian
