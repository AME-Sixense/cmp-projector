# Change Log

## [2.0.0]

### Changed

- **Breaking:** `config.yaml`'s per-project `project` key is renamed to `project-id`; a new, separate `project-name` key was added (a human-readable name shown in generated outputs, e.g. the interactive map's title bar). Existing `config.yaml` files must be updated to the new key name before running.

### Added

- Interactive map: a thin branded top bar (project name on the left, Sixense logo on the right, with a subtle "Generated `<date>`" timestamp).
- Interactive map: a global "Labels" toggle in the sidebar, off by default, alongside the existing per-group Targets/Lines toggles.
- TUI: the version number moved from the header title to a subtle, left-aligned label sharing the footer bar with the navigation hints.

### Fixed

- Interactive map: the total-station marker icon was rendered squeezed (forced into a square box despite its non-square source image); it now keeps its correct aspect ratio.

## [1.2.0]

### Added

- Two new export formats: `static_map` (a georeferenced PNG plus a matching `.pgw` world file) and `interactive_map` (a single self-contained HTML file with a Leaflet-based map), both showing the same Group/Instrument/Targets/Lines structure as the KMZ output, on an Esri World Street Map basemap.
- `core/exporters/geo_common.py`: a shared module that builds that Group/Instrument/Targets/Lines structure (and converts KMZ line colors to CSS) once, in memory, for reuse by both new exporters within a single run.
- `static_map` can be limited to a subset of a project's groups, zoomed to fit just that selection — pick them interactively in a new TUI screen (shown after choosing outputs, when `static_map` is selected) or via the CLI's new `--groups` flag.
- New dependencies: `matplotlib`, `contextily`, `truststore`.
- Leaflet 1.9.4 vendored under `assets/vendor/leaflet/`, so the interactive map's app shell is fully self-contained (only its basemap tiles require a live connection).

### Fixed

- Basemap tiles are now sourced from Esri's free `World_Street_Map` service instead of `tile.openstreetmap.org` (whose anti-bulk-scraping policy actively blocks this kind of use) or CARTO (whose free tier now requires a signed-up API key).
- A TLS-inspecting network proxy re-signs certificates with its own CA, which the OS trust store already trusts but Python's bundled `certifi` list didn't — fixed by verifying against the OS trust store instead (`truststore`).
- Deep zoom levels no longer show Esri's "Map data not yet available" placeholder — both outputs cap real tile requests at a reliably-covered zoom depth, with the interactive map blurring/upscaling its basemap past that point instead of requesting missing tiles.

## [1.1.0]

### Added

- KMZ output now splits each instrument's points and lines into separate "Targets" and "Lines" subfolders, instead of mixing them together in one folder.

## [1.0.0]

First tracked release.

### Added

- Interactive TUI (`tui.py`) for selecting a project, choosing which export modules to run for that invocation, and optionally persisting that selection back to `config.yaml` (comment-preserving targeted edit, with a per-session backup).
- Standalone CLI (`cli.py`) with `--verbose`, `--outputs`, and `--version` flags.
- `core/exporters/to_csv.py` as a proper export module (previously an ad-hoc CSV dump), alongside the existing KMZ exporter, via a registry in `core/pipeline.py` that makes adding future export formats a one-file addition.
- Quality-flag filtering of `.cmp` files (`BadEllips`, `BadSigmas`, `BadSigma0`, `Indet`, `UnderRef`), with per-file detail available in verbose mode and summary counts otherwise.
- Loud validation when a project on a local coordinate system has a group with no configured anchor, instead of silently emitting invalid coordinates.

### Fixed

- Points were being read from the pre-adjustment "Coordonnées initiales" table instead of the final, network-adjusted "Coordonnées compensées" table used for the anchor — every non-anchor point in every project was off by its adjustment residual.
- `walk_files()` had no `return` for the "commons" pass, so the dataframe of shared/common tie-points was always silently empty; every point's "Common" classification had always evaluated to `False`.
- A project's per-point instrument association was derived from the point's own name rather than the resolved station name, which broke for naming conventions where a point's prefix doesn't match its station's literal name.

### Changed

- Restructured the project: `modules/` → `core/` (with `core/exporters/` as the one subpackage), static assets moved into `assets/`, and the pipeline logic extracted into an importable `core/pipeline.run_project()` used by both `cli.py` and `tui.py`.
