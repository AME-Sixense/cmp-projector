# Change Log

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
