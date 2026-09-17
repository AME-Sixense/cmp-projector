# CMP Projector

**Version 2.0.0**

CMP Projector parses `.cmp` total-station survey files (output from the IGN/ENSG geodesic network-adjustment tool), reprojects each project's monitoring points from their survey coordinate system to latitude/longitude, and exports the result — currently to KMZ (for Google Earth), CSV, a static georeferenced map image, and an interactive standalone web map, with the export step designed to be extended with additional formats over time.

## How it works

For each configured project:

1. All `.cmp` files under `import/<project>/` are parsed, averaging repeated shots of the same point across every file found (a full-history snapshot, not a time series).
2. Files whose filenames carry a quality-flag token (`BadEllips`, `BadSigmas`, `BadSigma0`, `Indet`, `UnderRef`) are excluded.
3. Each survey group's local point cloud is rotated and translated onto its configured real-world anchor (an instrument's known position and orientation), which is required for any project surveyed in an arbitrary local coordinate system.
4. The result is reprojected to WGS84 (lat/long) and handed to whichever export modules that project selects.

## Requirements

- Python 3.12+ (a virtual environment is recommended)
- Dependencies in `requirements.txt`:

```
pip install -r requirements.txt
```

## Setup

1. Copy `config.example.yaml` to `config.yaml` and fill in your own project(s) — see the comments in that file for what each field means. `config.yaml` is gitignored, since it holds real survey control coordinates. Each project has a `project-id` (must match its `import/`/`output/` folder name, and what you pass to the CLI/select in the TUI) and a separate, human-readable `project-name` (shown in generated outputs, e.g. the interactive map's title bar).
2. Put each project's `.cmp` files under `import/<project-id>/` (subfolders are fine and are walked recursively).
3. Exported files land under `output/<project-id>/`.

The static map output (`static_map`) is a `.png` plus a matching `.pgw` world file, both in EPSG:3857 (Web Mercator) — when loading the PNG into QGIS/ArcGIS as a georeferenced raster, assign it that CRS manually, since a `.pgw` file carries no CRS identifier of its own. The interactive map output (`interactive_map`) is a single self-contained `.html` file with a thin branded top bar (the project's `project-name` on the left, the Sixense logo on the right) — open it directly in a browser (no server needed); it only needs a live internet connection to fetch the Esri basemap tiles.

`static_map` can be limited to a subset of a project's groups (the map is then zoomed to fit just that selection) — pick them interactively in the TUI's group-selection screen (shown right after choosing outputs, only when `static_map` is selected), or pass `--groups` on the CLI (see below). This has no effect on any other output.

## Usage

**Interactive (recommended):**

```
python tui.py
```

Select a project (↑/↓, Enter), then choose which outputs to run for that invocation on the next screen (↑/↓ to navigate, Enter to toggle a row or activate Run). Checking "Save to config.yaml" persists that selection for next time — only the affected project's `outputs:` line is rewritten, and everything else in the file (including comments) is left untouched. The first save each session backs up the pre-session file to `config.yaml.bak`. If `static_map` is checked, hitting Run leads to one more screen to pick which groups to include (with a "Select All" row) before the export actually runs.

**Direct/scriptable:**

```
python cli.py <project> [--verbose] [--outputs kmz,csv] [--groups 1,3] [--version]
```

- `--verbose` prints the specific reason for every skipped file, instead of just summary counts.
- `--outputs` overrides `config.yaml`'s configured list for this run only, without changing the file.
- `--groups` limits the `static_map` output to just the listed groups, zoomed to fit them (default: all groups); it has no effect on any other output.

## Project structure

```
tui.py                 interactive entry point
cli.py                 direct/scriptable entry point
config.yaml             your real project config (gitignored)
config.example.yaml      template to copy from
assets/                 static assets (Textual CSS, KMZ icons, vendored Leaflet)
core/
  pipeline.py            run_project(proj_name, config) — the actual pipeline logic
  import_cmp.py           .cmp parsing
  proj_coords.py           anchor offset/rotation + reprojection
  exporters/
    to_kmz.py, to_csv.py, to_static_map.py, to_interactive_map.py   one module per output format
    geo_common.py           shared Group/Inst/Targets/Lines data prep used by the two map exporters
import/<project>/       your input .cmp files (gitignored)
output/<project>/       generated exports (gitignored)
```

### Adding a new export format

Write `core/exporters/to_<name>.py` with a function `(df, proj_name, export_folder, project_config) -> None`, add it to the `EXPORTERS` dict in `core/pipeline.py`, and add its name to whichever project's `outputs:` list should use it (or select it per-run from the TUI/`--outputs`).

## License

This software is the proprietary information of Sixense North America. Unauthorized copying, distribution, or modification of this software, via any medium, is strictly prohibited. All rights reserved.
