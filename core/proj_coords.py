import math
import pandas as pd
from pyproj import Transformer, CRS

def apply_offsets(df, group_offsets, in_proj=None):
    # A local/arbitrary coordinate system has no meaning outside its own group's
    # anchor-based transform, so a group with no configured anchor can't be
    # reprojected at all — passing it through unchanged would silently emit
    # bogus lat/long. Groups on a real (already-surveyed) CRS are fine to pass
    # through unchanged, since their raw coordinates are already meaningful.
    is_local = isinstance(in_proj, str) and in_proj.startswith("local")

    adjusted_rows = []
    skipped_groups = set()

    for _, row in df.iterrows():
        group_id = str(row["Group"])
        anchor = group_offsets.get(group_id)

        if not anchor:
            if is_local:
                skipped_groups.add(group_id)
                continue
            # No override for this group; skip adjustment
            adjusted_rows.append(row)
            continue

        # Original local position
        dx = row["Easting"] - row["Anchor_E"]
        dy = row["Northing"] - row["Anchor_N"]
        dz = row["Elevation"] - row["Anchor_Z"]

        # Rotation in radians (negative for clockwise in standard coordinate systems)
        theta_rad = -anchor["rotation"] * math.pi / 200

        # Rotate around anchor
        x_rot = dx * math.cos(theta_rad) - dy * math.sin(theta_rad)
        y_rot = dx * math.sin(theta_rad) + dy * math.cos(theta_rad)

        # Translate to final coordinates
        new_row = row.copy()
        new_row["Easting"] = anchor["easting"] + x_rot
        new_row["Northing"] = anchor["northing"] + y_rot
        new_row["Elevation"] = anchor["elevation"] + dz
        adjusted_rows.append(new_row)

    for group_id in sorted(skipped_groups):
        print(
            f"WARNING: Group {group_id} uses a local coordinate system but has no "
            f"anchor configured in config.yaml — skipping its points to avoid "
            f"emitting invalid coordinates."
        )

    if not adjusted_rows:
        # Preserve the original columns even when every row was skipped, so
        # trans_coords() downstream doesn't fail on a missing "Easting" column.
        return pd.DataFrame(columns=df.columns)

    return pd.DataFrame(adjusted_rows)

def trans_coords(in_proj, out_proj, df, scale):
    # If local system, we skip projection and just apply factor
    if isinstance(in_proj, str) and in_proj.startswith("local"):
        df["Easting"] = df["Easting"] * scale
        df["Northing"] = df["Northing"] * scale
        df["Elevation"] = df["Elevation"] * scale

    # Project to geographic coordinates if out_proj is defined
    if isinstance(out_proj, CRS):
        transformer = Transformer.from_crs(out_proj, "EPSG:4326", always_xy=True)
        lons, lats = transformer.transform(df["Easting"].values, df["Northing"].values)
        df["Longitude"] = lons
        df["Latitude"] = lats
        df["Altitude"] = df["Elevation"]
    else:
        df["Longitude"] = None
        df["Latitude"] = None
        df["Altitude"] = df["Elevation"]

    return df
