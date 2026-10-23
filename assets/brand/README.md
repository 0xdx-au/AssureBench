# AssureBench — DevSecOps Logo Kit (v2)

The primary mark depicts the continuous DevOps loop, with **source code** (left), an **assurance shield** (centre), and **evidence/scan output** (right). It works at website-header size and on printable reports without implying that static scanning proves a repository is secure.

## Files

- `assurebench-horizontal-dark.svg` — transparent wordmark for dark backgrounds. “Bench” is pale green-white, so do not place it on a light background.
- `assurebench-horizontal-light.svg` — transparent wordmark for white or light backgrounds and report covers.
- `favicon.svg` — simplified shield/check mark for browser tabs and small displays.

These are the three logo files currently included in this folder. There are no monochrome, mark-only, PNG, or preview-board exports.

## Use

Use the matching wordmark for the background. Both horizontal SVGs have a 1060×166 viewBox and render at half size in the dashboard.

**Dark website:**
```html
<img src="/assets/brand/assurebench-horizontal-dark.svg" alt="AssureBench" width="530" height="83">
<link rel="icon" href="/assets/brand/favicon.svg" type="image/svg+xml">
```

**README, PDF, or light page:** Use `assurebench-horizontal-light.svg`. The assets have transparent backgrounds; the dark variant has light lettering that will disappear against white. Keep the 1060:166 aspect ratio and do not stretch the image.

## Change the logo later

1. Keep the files in `assets/brand/` and update their references in `index.html`, `app.js`, and `server.py` together if you rename them.
2. The loop, shield, and evidence bars are editable SVG paths. `Assure` and `Bench` are live SVG text. Edit the SVG in a text editor or a vector editor such as Inkscape.
3. Keep the dark wordmark on a dark background and the light wordmark on a light background. If changing colors, edit the explicit `stroke`, `fill`, and `color` values in both wordmarks and check the contrast on their intended background.
4. The favicon uses only the shield and check so it remains recognizable at 16–32 pixels.
5. SVG lettering uses Inter / Inter Display with Arial fallback. Keep the SVG as the editable source if making a raster export for a tool that cannot display SVG.

The logo has **no third-party dependencies, linked fonts, external images, or embedded bitmap elements**. The wordmarks render transparently.
