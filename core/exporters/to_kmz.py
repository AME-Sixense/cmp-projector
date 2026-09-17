import os
import simplekml
from datetime import datetime
import shutil
import zipfile

def copy_icons(export_path):
    icon_src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "icons"))
    icon_dest = os.path.join(export_path, "icons")
    os.makedirs(icon_dest, exist_ok=True)
    for icon in ["total-station.png", "l-bar-prism.png"]:
        shutil.copy2(os.path.join(icon_src, icon), os.path.join(icon_dest, icon))

def make_kmz_structure(kmz, df, label, mon_color, ref_color, com_color):
    for group, gdf in df.groupby("Group"):
        group_folder = kmz.newfolder(name=f"Group {group}")
        for inst, idf in gdf.groupby("Inst"):
            inst_folder = group_folder.newfolder(name=inst)
            targets_folder = inst_folder.newfolder(name="Targets")
            lines_folder = inst_folder.newfolder(name="Lines")
            for _, row in idf.iterrows():
                pt = targets_folder.newpoint(
                    name=row["Point"] if label else None,
                    coords=[(row["Longitude"], row["Latitude"], row["Altitude"])]
                )
                pt.altitudemode = simplekml.AltitudeMode.absolute
                pt.style.iconstyle.icon.href = (
                    "icons/total-station.png" if row["Point"] == row["Inst"]
                    else "icons/l-bar-prism.png"
                )
                pt.style.labelstyle.scale = 1.2 if row["Point"] == row["Inst"] else 0.5

                if row["Point"] != row["Inst"]:
                    ln = lines_folder.newlinestring(
                        name=row["Point"],
                        coords=[
                            (idf.loc[idf['Point'] == row['Inst'], 'Longitude'].values[0],
                             idf.loc[idf['Point'] == row['Inst'], 'Latitude'].values[0],
                             idf.loc[idf['Point'] == row['Inst'], 'Altitude'].values[0]),
                            (row["Longitude"], row["Latitude"], row["Altitude"])
                        ]
                    )
                    ln.altitudemode = simplekml.AltitudeMode.absolute
                    ln.style.linestyle.color = (
                        com_color if row["Common"] else
                        mon_color if row["Type"] == "MON" else
                        ref_color
                    )

def export_to_kmz(df, proj_name, export_folder, project_config):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{proj_name}_{timestamp}.kml"
    filepath = os.path.join(export_folder, filename)

    os.makedirs(export_folder, exist_ok=True)
    copy_icons(export_folder)

    label = project_config["label"]
    mon_color = project_config["vector-colors"][0]["mon_color"]
    ref_color = project_config["vector-colors"][1]["ref_color"]
    com_color = project_config["vector-colors"][2]["com_color"]

    kmz = simplekml.Kml()
    make_kmz_structure(kmz, df, label, mon_color, ref_color, com_color)
    kmz.save(filepath)

    zipname = filepath.replace(".kml", ".kmz")
    with zipfile.ZipFile(zipname, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(filepath, os.path.basename(filepath))
        for icon in ["total-station.png", "l-bar-prism.png"]:
            icon_path = os.path.join(export_folder, "icons", icon)
            zf.write(icon_path, os.path.join("icons", icon))

    os.remove(filepath)
    shutil.rmtree(os.path.join(export_folder, "icons"))
