# CMP Projector

**Version 1.0.0**

CMP Projector parses `.cmp` total-station survey files (output from the IGN/ENSG geodesic network-adjustment tool), reprojects each project's monitoring points from their survey coordinate system to latitude/longitude, and exports the result — currently to KMZ (for Google Earth) and CSV, with the export step designed to be extended with additional formats over time.

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

1. Copy `config.example.yaml` to `config.yaml` and fill in your own project(s) — see the comments in that file for what each field means. `config.yaml` is gitignored, since it holds real survey control coordinates.
2. Put each project's `.cmp` files under `import/<project-name>/` (subfolders are fine and are walked recursively — the project name in `config.yaml` must match this folder name).
3. Exported KMZ/CSV files land under `output/<project-name>/`.

## Usage

**Interactive (recommended):**

```
python tui.py
```

Select a project (↑/↓, Enter), then choose which outputs to run for that invocation on the next screen (↑/↓ to navigate, Enter to toggle a row or activate Run). Checking "Save to config.yaml" persists that selection for next time — only the affected project's `outputs:` line is rewritten, and everything else in the file (including comments) is left untouched. The first save each session backs up the pre-session file to `config.yaml.bak`.

**Direct/scriptable:**

```
python cli.py <project> [--verbose] [--outputs kmz,csv] [--version]
```

- `--verbose` prints the specific reason for every skipped file, instead of just summary counts.
- `--outputs` overrides `config.yaml`'s configured list for this run only, without changing the file.

## Project structure

```
tui.py                 interactive entry point
cli.py                 direct/scriptable entry point
config.yaml             your real project config (gitignored)
config.example.yaml      template to copy from
assets/                 static assets (Textual CSS, KMZ icons)
core/
  pipeline.py            run_project(proj_name, config) — the actual pipeline logic
  import_cmp.py           .cmp parsing
  proj_coords.py           anchor offset/rotation + reprojection
  exporters/
    to_kmz.py, to_csv.py    one module per output format
import/<project>/       your input .cmp files (gitignored)
output/<project>/       generated exports (gitignored)
```

### Adding a new export format

Write `core/exporters/to_<name>.py` with a function `(df, proj_name, export_folder, project_config) -> None`, add it to the `EXPORTERS` dict in `core/pipeline.py`, and add its name to whichever project's `outputs:` list should use it (or select it per-run from the TUI/`--outputs`).

## License

This software is the proprietary information of Sixense North America. Unauthorized copying, distribution, or modification of this software, via any medium, is strictly prohibited. All rights reserved.
