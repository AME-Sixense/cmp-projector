"""Shared data-prep helpers for the map-based exporters (to_static_map.py,
to_interactive_map.py). Both need the same Group -> Inst -> Targets/Lines
grouping and the same KMZ color rules that to_kmz.py already uses, so it's
built once here and cached in memory for the life of the process (never
written to disk) so a run that produces both outputs doesn't recompute it."""

_layer_cache = {}


def kml_color_to_css(kml_aabbggrr):
    """Convert a KML AABBGGRR hex color (e.g. "ff0000ff") to a CSS/matplotlib
    "#rrggbb" string. The alpha channel is dropped since neither consumer
    needs it here."""
    s = kml_aabbggrr.strip()
    if len(s) != 8:
        raise ValueError(f"Expected 8-char AABBGGRR hex, got {s!r}")
    _aa, bb, gg, rr = s[0:2], s[2:4], s[4:6], s[6:8]
    return f"#{rr}{gg}{bb}"


def build_geojson_layers(df, project_config):
    """Group df the same way to_kmz.py's make_kmz_structure does, returning:

    {"groups": {"<group>": {"instruments": {"<inst>": {
        "targets": [{point, lon, lat, alt, is_instrument, type, common}, ...],
        "lines":   [{point, color, from: [lon, lat, alt], to: [lon, lat, alt]}, ...]
    }}}}}
    """
    key = (id(df), len(df))
    cached = _layer_cache.get(key)
    if cached is not None:
        return cached

    mon_color = kml_color_to_css(project_config["vector-colors"][0]["mon_color"])
    ref_color = kml_color_to_css(project_config["vector-colors"][1]["ref_color"])
    com_color = kml_color_to_css(project_config["vector-colors"][2]["com_color"])

    groups = {}
    for group, gdf in df.groupby("Group"):
        instruments = {}
        for inst, idf in gdf.groupby("Inst"):
            targets = []
            lines = []
            for _, row in idf.iterrows():
                is_instrument = row["Point"] == row["Inst"]
                targets.append({
                    "point": row["Point"],
                    "lon": row["Longitude"],
                    "lat": row["Latitude"],
                    "alt": row["Altitude"],
                    "is_instrument": is_instrument,
                    "type": row["Type"],
                    "common": bool(row["Common"]),
                })

                if not is_instrument:
                    inst_row = idf.loc[idf["Point"] == row["Inst"]].iloc[0]
                    color = (
                        com_color if row["Common"] else
                        mon_color if row["Type"] == "MON" else
                        ref_color
                    )
                    lines.append({
                        "point": row["Point"],
                        "color": color,
                        "from": [inst_row["Longitude"], inst_row["Latitude"], inst_row["Altitude"]],
                        "to": [row["Longitude"], row["Latitude"], row["Altitude"]],
                    })

            instruments[inst] = {"targets": targets, "lines": lines}
        groups[str(group)] = {"instruments": instruments}

    layers = {"groups": groups}
    _layer_cache.clear()
    _layer_cache[key] = layers
    return layers
