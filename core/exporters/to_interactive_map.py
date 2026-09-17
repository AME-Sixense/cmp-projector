import base64
import html
import json
import os
import re
from datetime import datetime

from core.exporters.geo_common import build_geojson_layers

_VENDOR_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "vendor", "leaflet"))
_ICON_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "icons"))
_LOGO_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "Sixense_Logo_Horizontal.jpg"))


def _data_uri(path, mime="image/png"):
    with open(path, "rb") as f:
        return f"data:{mime};base64,{base64.b64encode(f.read()).decode('ascii')}"


def _inline_leaflet_css():
    css_path = os.path.join(_VENDOR_DIR, "leaflet.css")
    with open(css_path, "r", encoding="utf-8") as f:
        css = f.read()

    def _replace(match):
        image_path = os.path.join(_VENDOR_DIR, "images", match.group(1))
        return f"url({_data_uri(image_path)})"

    return re.sub(r"url\(images/([^)]+)\)", _replace, css)


def _inline_leaflet_js():
    js_path = os.path.join(_VENDOR_DIR, "leaflet.js")
    with open(js_path, "r", encoding="utf-8") as f:
        return f.read()


# Placeholders are replaced with str.replace() rather than str.format(), since
# the embedded JS is full of literal { } braces that would otherwise all need
# escaping.
_PAGE_TEMPLATE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>__TITLE__</title>
<style>
__LEAFLET_CSS__
html, body { height: 100%; margin: 0; }
body { display: flex; flex-direction: column; }
#topbar {
  flex: 0 0 auto; height: 44px; display: flex; align-items: center;
  justify-content: space-between; background: white; padding: 0 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.25); font-family: sans-serif;
  position: relative; z-index: 1001;
}
#topbar-left { display: flex; align-items: baseline; gap: 10px; }
#topbar-title { font-size: 15px; font-weight: bold; color: #1a1a1a; }
#topbar-date { font-size: 11px; color: #999; font-weight: normal; }
#topbar-logo { height: 24px; display: block; }
#map { flex: 1 1 auto; }
#sidebar {
  position: absolute; top: 54px; right: 10px; z-index: 1000;
  background: white; padding: 10px 14px; border-radius: 4px;
  box-shadow: 0 1px 5px rgba(0,0,0,0.4); font-family: sans-serif; font-size: 13px;
  max-height: calc(90% - 44px); overflow-y: auto;
}
#sidebar h4 { margin: 0 0 6px 0; }
#sidebar .labels-row { margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid #ddd; }
#sidebar .group-row { margin-bottom: 6px; }
#sidebar .child-row { margin-left: 18px; }
#sidebar label { cursor: pointer; user-select: none; }
body.labels-hidden .point-label { display: none !important; }
</style>
</head>
<body>
<div id="topbar">
  <div id="topbar-left">
    <span id="topbar-title">__PROJECT_NAME__</span>
    <span id="topbar-date">Generated __GENERATED_DATE__</span>
  </div>
  <img id="topbar-logo" src="__LOGO_URI__" alt="Sixense">
</div>
<div id="map"></div>
<div id="sidebar">
  <div class="labels-row"><label><input type="checkbox" id="labels-toggle"> Labels</label></div>
  <h4>Groups</h4>
  <div id="group-rows"></div>
</div>
<script>
__LEAFLET_JS__
</script>
<script>
const CMP_DATA = __DATA_JSON__;
const TS_ICON_URL = "__TS_ICON_URI__";
const PRISM_ICON_URL = "__PRISM_ICON_URI__";
const SHOW_LABELS = __SHOW_LABELS__;

const map = L.map('map');
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {
  maxZoom: 23,
  maxNativeZoom: 19,
  attribution: 'Tiles &copy; Esri &mdash; Source: Esri, DeLorme, NAVTEQ, USGS, Intermap, iPC, NRCAN, Esri Japan, METI, Esri China (Hong Kong), Esri (Thailand), TomTom'
}).addTo(map);

const tsIcon = L.icon({ iconUrl: TS_ICON_URL, iconSize: [52, 28], iconAnchor: [26, 14] });
const prismIcon = L.icon({ iconUrl: PRISM_ICON_URL, iconSize: [20, 20], iconAnchor: [10, 10] });

const labelsToggle = document.getElementById('labels-toggle');
labelsToggle.checked = SHOW_LABELS;
document.body.classList.toggle('labels-hidden', !SHOW_LABELS);
labelsToggle.addEventListener('change', () => {
  document.body.classList.toggle('labels-hidden', !labelsToggle.checked);
});

const groupRowsEl = document.getElementById('group-rows');
const allBounds = [];
const groupLayers = {};

function setLayerVisible(layerGroup, visible) {
  const onMap = map.hasLayer(layerGroup);
  if (visible && !onMap) layerGroup.addTo(map);
  else if (!visible && onMap) map.removeLayer(layerGroup);
}

for (const [groupId, groupData] of Object.entries(CMP_DATA.groups)) {
  const targetsLG = L.layerGroup();
  const linesLG = L.layerGroup();

  for (const inst of Object.values(groupData.instruments)) {
    for (const t of inst.targets) {
      const marker = L.marker([t.lat, t.lon], { icon: t.is_instrument ? tsIcon : prismIcon });
      marker.bindTooltip(t.point, { permanent: true, direction: 'right', className: 'point-label' });
      marker.addTo(targetsLG);
      allBounds.push([t.lat, t.lon]);
    }
    for (const l of inst.lines) {
      L.polyline([[l.from[1], l.from[0]], [l.to[1], l.to[0]]], { color: l.color, weight: 2 })
        .bindTooltip(l.point)
        .addTo(linesLG);
    }
  }

  targetsLG.addTo(map);
  linesLG.addTo(map);
  groupLayers[groupId] = { targets: targetsLG, lines: linesLG };

  const row = document.createElement('div');
  row.className = 'group-row';

  const parentLabel = document.createElement('label');
  const parentCb = document.createElement('input');
  parentCb.type = 'checkbox';
  parentCb.checked = true;
  parentLabel.appendChild(parentCb);
  parentLabel.appendChild(document.createTextNode(' Group ' + groupId));
  row.appendChild(parentLabel);

  const childrenDiv = document.createElement('div');

  const targetsRow = document.createElement('div');
  targetsRow.className = 'child-row';
  const targetsLabel = document.createElement('label');
  const targetsCb = document.createElement('input');
  targetsCb.type = 'checkbox';
  targetsCb.checked = true;
  targetsLabel.appendChild(targetsCb);
  targetsLabel.appendChild(document.createTextNode(' Targets'));
  targetsRow.appendChild(targetsLabel);
  childrenDiv.appendChild(targetsRow);

  const linesRow = document.createElement('div');
  linesRow.className = 'child-row';
  const linesLabel = document.createElement('label');
  const linesCb = document.createElement('input');
  linesCb.type = 'checkbox';
  linesCb.checked = true;
  linesLabel.appendChild(linesCb);
  linesLabel.appendChild(document.createTextNode(' Lines'));
  linesRow.appendChild(linesLabel);
  childrenDiv.appendChild(linesRow);

  row.appendChild(childrenDiv);
  groupRowsEl.appendChild(row);

  function refresh() {
    setLayerVisible(targetsLG, parentCb.checked && targetsCb.checked);
    setLayerVisible(linesLG, parentCb.checked && linesCb.checked);
    childrenDiv.style.display = parentCb.checked ? 'block' : 'none';
  }
  parentCb.addEventListener('change', refresh);
  targetsCb.addEventListener('change', refresh);
  linesCb.addEventListener('change', refresh);
}

if (allBounds.length) {
  map.fitBounds(allBounds, { padding: [20, 20] });
} else {
  map.setView([0, 0], 2);
}
</script>
</body>
</html>
"""


def export_to_interactive_map(df, proj_name, export_folder, project_config):
    os.makedirs(export_folder, exist_ok=True)
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
    html_path = os.path.join(export_folder, f"{proj_name}_{timestamp}.html")

    layers = build_geojson_layers(df, project_config)
    project_name = project_config.get("project-name", proj_name)

    page = (
        _PAGE_TEMPLATE
        .replace("__TITLE__", html.escape(f"{project_name} - Interactive Map"))
        .replace("__PROJECT_NAME__", html.escape(project_name))
        .replace("__GENERATED_DATE__", now.strftime("%Y-%m-%d %H:%M"))
        .replace("__LOGO_URI__", _data_uri(_LOGO_PATH, mime="image/jpeg"))
        .replace("__LEAFLET_CSS__", _inline_leaflet_css())
        .replace("__LEAFLET_JS__", _inline_leaflet_js())
        .replace("__DATA_JSON__", json.dumps(layers))
        .replace("__TS_ICON_URI__", _data_uri(os.path.join(_ICON_DIR, "total-station.png")))
        .replace("__PRISM_ICON_URI__", _data_uri(os.path.join(_ICON_DIR, "l-bar-prism.png")))
        # Labels default off here regardless of project_config["label"] (which still
        # governs the KMZ/static_map outputs) — the interactive map has a live
        # Labels toggle in the sidebar, so it opens uncluttered and the user can
        # switch labels on themselves.
        .replace("__SHOW_LABELS__", "false")
    )

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(page)
