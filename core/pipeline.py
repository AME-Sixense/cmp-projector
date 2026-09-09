from pyproj import CRS
import pandas as pd

from core.import_cmp import Parse, import_dir, export_dir
from core.proj_coords import apply_offsets, trans_coords
from core.exporters.to_kmz import export_to_kmz
from core.exporters.to_csv import export_to_csv

# Registry of output modules. Each project's config.yaml "outputs" list
# selects which of these run; adding a new export format (e.g. QGIS) just
# means writing a core/exporters/to_<x>.py with this same
# (df, proj_name, export_folder, project_config) signature and registering
# it here — no other code needs to change.
EXPORTERS = {
    "kmz": export_to_kmz,
    "csv": export_to_csv,
}


def run_project(proj_name, config, verbose=False, outputs_override=None):
    """Run the full CMP Projector pipeline for one project: parse its .cmp
    files, apply group anchor offsets/rotation, reproject to lat/long, and
    run whichever export modules are selected.

    In standard mode (verbose=False), only summary counts are printed for
    skipped files (e.g. "Skipped 12 file(s) due to quality filter."). Passing
    verbose=True additionally prints the specific reason for every skipped
    file as it's encountered.

    By default the exported outputs are whichever the project's config.yaml
    "outputs" list selects. Passing outputs_override (a list of exporter
    names) uses that list instead for this run only, without needing to
    change config.yaml.

    Returns the final, exported dataframe.
    """
    project_config = next((proj for proj in config['projects'] if proj['project'] == proj_name), None)
    if project_config is None:
        raise ValueError(f"Project configuration not found for '{proj_name}'")

    export_folder = export_dir(proj_name)
    in_proj_raw = project_config["coordinate-systems"][0]["inProj"]
    if isinstance(in_proj_raw, int) or (isinstance(in_proj_raw, str) and in_proj_raw.isdigit()):
        in_proj = CRS.from_epsg(int(in_proj_raw))
    else:
        in_proj = in_proj_raw  # For local coordinate systems
    out_proj = CRS.from_epsg(int(project_config["coordinate-systems"][1]["outProj"]))
    scale = project_config['scale']
    xy_order = "NE" if project_config['xy_order'] == 0 else "EN"
    group_offsets = {str(g["name"]): g["anchor"] for g in project_config["coord_adjustments"]["groups"]}
    outputs = outputs_override if outputs_override is not None else project_config.get("outputs", ["kmz"])

    # Build commons dataframe
    print("Importing and averaging CMP coordinates")
    parser = Parse(import_dir(proj_name), verbose=verbose)
    commons_df = parser.walk_files('commons')

    # Reuse the same parser (and its cached file listing) for the coords pass
    parser.commons_df = commons_df
    parser.group_offsets = group_offsets
    coords_df = parser.walk_files('coords')
    assert isinstance(coords_df, pd.DataFrame), f"coords_df is {type(coords_df)}"

    print("Applying offsets and transforming coordinates")
    offset_df = apply_offsets(coords_df, group_offsets, in_proj_raw)
    assert isinstance(offset_df, pd.DataFrame), f"apply_offsets returned {type(offset_df)}"
    final_df = trans_coords(in_proj, out_proj, offset_df, scale)
    assert isinstance(final_df, pd.DataFrame), f"trans_coords returned {type(final_df)}"

    for output_name in outputs:
        exporter = EXPORTERS.get(output_name)
        if exporter is None:
            print(f"WARNING: Unknown output type '{output_name}' for project '{proj_name}' — skipping.")
            continue
        print(f"Creating {output_name} output")
        exporter(final_df, proj_name, export_folder, project_config)

    print("\nComplete!")

    return final_df
