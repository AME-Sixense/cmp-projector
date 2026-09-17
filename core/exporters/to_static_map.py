import math
import os
from datetime import datetime

import truststore
truststore.inject_into_ssl()  # trust the OS certificate store (e.g. for networks with a TLS-inspecting proxy), matching what curl/browsers already trust, instead of only certifi's bundled public CAs

import contextily as ctx
import matplotlib.pyplot as plt
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from pyproj import Transformer

from core.exporters.geo_common import build_geojson_layers

_TO_3857 = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)

# Esri's World Street Map tile pyramid technically goes to zoom 23, but Esri's
# own service description says imagery that deep only exists in "select urban
# areas" — requesting it elsewhere returns a "Map data not yet available"
# placeholder tile, which would get baked permanently into the saved PNG.
# Capping at 19 (Esri's documented reliably-covered depth) avoids that.
MAX_BASEMAP_ZOOM = 19


def _project(lon, lat):
    return _TO_3857.transform(lon, lat)


def _zoom_for_extent(xmin, xmax, width_px):
    """Web Mercator zoom level whose tile resolution roughly fills width_px
    pixels across the given EPSG:3857 extent, capped at MAX_BASEMAP_ZOOM."""
    resolution = (xmax - xmin) / width_px  # meters/pixel needed
    zoom = math.log2(156543.03392804097 / resolution)  # 156543... = equator meters/pixel at zoom 0
    return max(0, min(MAX_BASEMAP_ZOOM, round(zoom)))


def plot_layers(ax, groups, label):
    icon_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "assets", "icons", "total-station.png"
    ))
    ts_icon = plt.imread(icon_path)

    for group in groups.values():
        for idf in group["instruments"].values():
            for line in idf["lines"]:
                (fx, fy) = _project(line["from"][0], line["from"][1])
                (tx, ty) = _project(line["to"][0], line["to"][1])
                ax.plot([fx, tx], [fy, ty], color=line["color"], linewidth=1, zorder=2)

            target_x, target_y = [], []
            for t in idf["targets"]:
                x, y = _project(t["lon"], t["lat"])
                if t["is_instrument"]:
                    ab = AnnotationBbox(OffsetImage(ts_icon, zoom=0.05), (x, y), frameon=False, zorder=4)
                    ax.add_artist(ab)
                else:
                    target_x.append(x)
                    target_y.append(y)
                if label:
                    ax.annotate(t["point"], (x, y), fontsize=6, xytext=(3, 3),
                                textcoords="offset points", zorder=5)

            if target_x:
                ax.scatter(target_x, target_y, s=14, color="black",
                           edgecolors="white", linewidths=0.5, zorder=3)


def write_world_file(png_path, xmin, xmax, ymin, ymax, width_px, height_px):
    a = (xmax - xmin) / width_px
    e = -(ymax - ymin) / height_px
    c = xmin + a / 2
    f = ymax + e / 2
    pgw_path = os.path.splitext(png_path)[0] + ".pgw"
    with open(pgw_path, "w") as fh:
        fh.write(f"{a}\n0.0\n0.0\n{e}\n{c}\n{f}\n")


def export_to_static_map(df, proj_name, export_folder, project_config):
    os.makedirs(export_folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    png_path = os.path.join(export_folder, f"{proj_name}_{timestamp}.png")

    layers = build_geojson_layers(df, project_config)
    label = project_config["label"]

    groups = layers["groups"]
    group_filter = project_config.get("_group_filter")
    if group_filter:
        selected = set(group_filter)
        groups = {g: data for g, data in groups.items() if g in selected}
        if not groups:
            raise ValueError(
                f"None of the requested groups {sorted(selected)} exist for '{proj_name}' "
                f"(available: {sorted(layers['groups'])})"
            )

    xs, ys = [], []
    for group in groups.values():
        for idf in group["instruments"].values():
            for t in idf["targets"]:
                x, y = _project(t["lon"], t["lat"])
                xs.append(x)
                ys.append(y)

    pad_x = (max(xs) - min(xs)) * 0.1 or 50
    pad_y = (max(ys) - min(ys)) * 0.1 or 50
    xmin, xmax = min(xs) - pad_x, max(xs) + pad_x
    ymin, ymax = min(ys) - pad_y, max(ys) + pad_y

    dpi = 150
    fig = plt.figure(figsize=(10, 10), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_axis_off()

    width_px, height_px = fig.get_size_inches() * dpi
    zoom = _zoom_for_extent(xmin, xmax, width_px)

    plot_layers(ax, groups, label)
    ctx.add_basemap(ax, source=ctx.providers.Esri.WorldStreetMap, crs="EPSG:3857", zoom=zoom)

    fig.savefig(png_path, dpi=dpi)
    plt.close(fig)

    write_world_file(png_path, xmin, xmax, ymin, ymax, width_px, height_px)
