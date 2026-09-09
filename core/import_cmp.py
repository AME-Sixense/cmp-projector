import os
import sys
import pandas as pd
import re
from datetime import datetime

# .cmp files carry quality-flag tokens in their filename (after the timestamp),
# e.g. "Group_10_20250804_053854_SubGroup_NoCon_Indet_BadEllips_BadSigmas.cmp".
# A file is rejected if any underscore-delimited token matches one of these exactly.
QUALITY_REJECT_TOKENS = {"BadEllips", "BadSigmas", "BadSigma0", "Indet", "UnderRef"}

# The files are produced by a DOS-era French geodesy tool and are actually encoded
# in CP850 (DOS Latin), not ISO-8859-1/cp1252.
CMP_ENCODING = "cp850"

def import_dir(proj_name):
    return os.path.join("import", proj_name)

def export_dir(proj_name):
    return os.path.join("output", proj_name)

class Parse:
    def __init__(self, directory, commons_df=None, verbose=False):
        self.dir = directory
        self.src_file = None
        self.commons_df = commons_df if commons_df is not None else pd.DataFrame()
        self.group_offsets = {}
        self.verbose = verbose
        self._eligible_files = None  # cached (root, file) pairs after quality filtering

    def _log(self, msg):
        """Per-file diagnostic detail — only shown in verbose mode."""
        if self.verbose:
            sys.stdout.write(f"\r   {msg}\n")
            sys.stdout.flush()

    def _collect_eligible_files(self):
        """Walk self.dir once, filtering out quality-flagged files, and cache
        the result so repeated walk_files() calls (once per dataframe_type)
        don't re-walk the directory or re-report the same skipped files."""
        if self._eligible_files is not None:
            return self._eligible_files

        eligible = []
        skipped = 0
        for root, _, files in os.walk(self.dir):
            for file in files:
                if not file.endswith('.cmp'):
                    continue

                # Skip low quality calculations, flagged via underscore-delimited
                # tokens in the filename (see QUALITY_REJECT_TOKENS above).
                name_tokens = set(os.path.splitext(file)[0].split("_"))
                if name_tokens & QUALITY_REJECT_TOKENS:
                    self._log(f"Skipping file due to quality filter: {file}")
                    skipped += 1
                    continue

                eligible.append((root, file))

        if skipped:
            print(f"Skipped {skipped} file(s) due to quality filter.")

        self._eligible_files = eligible
        return eligible

    def walk_files(self, dataframe_type):
        df_list = []
        no_data_skipped = 0
        for root, file in self._collect_eligible_files():
            self.src_file = file
            file_path = os.path.join(root, file)

            if dataframe_type == 'commons':
                df_list.append(self.parse_commons(file_path))
            else:
                df = self.parse_coords(file_path)
                if isinstance(df, pd.DataFrame) and not df.empty:
                    df_list.append(df)
                else:
                    no_data_skipped += 1

        if dataframe_type == 'coords' and no_data_skipped:
            print(f"Skipped {no_data_skipped} file(s) due to no data or anchor issues.")

        result = pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame()
        assert isinstance(result, pd.DataFrame), f"👻 Final result is not a DataFrame: {type(result)}"
        if dataframe_type == 'coords' and not result.empty:
            grouped = result.groupby(["Point", "Inst", "Group"], as_index=False).agg({
                "Easting": "mean",
                "Northing": "mean",
                "Elevation": "mean",
                "Timestamp": "mean",
                "Type": "first",
                "Common": "any",
                "Source File": "first",
                "Anchor_E": "first",
                "Anchor_N": "first",
                "Anchor_Z": "first"
            })
            result = grouped

            # Create missing anchors from coord_override if needed (No offsets or rotation are applied in this case)
            for group_id, ov in self.group_offsets.items():
                inst = ov.get("inst")
                if not inst:
                    continue

                # Look for a TS row in this group
                ts_exists = (
                    not result.empty and
                    ((result["Inst"] == inst) & (result["Group"] == group_id) & (result["Type"] == "TS")).any()
                )

                if not ts_exists:
                    e = ov.get("easting")
                    n = ov.get("northing")
                    z = ov.get("elevation")
                    if e is not None and n is not None and z is not None:
                        ts_row = {
                            "Timestamp": 0,
                            "Inst": inst,
                            "Group": group_id,
                            "Point": inst,
                            "Type": "TS",
                            "Common": False,
                            "Easting": e,
                            "Northing": n,
                            "Elevation": z,
                            "Source File": "config_override",
                            "Anchor_E": e,
                            "Anchor_N": n,
                            "Anchor_Z": z
                        }
                        result = pd.concat([result, pd.DataFrame([ts_row])], ignore_index=True)
                        sys.stdout.write(f"\r   Created missing group anchor {inst} for Group {group_id} from config\n")
                        sys.stdout.flush()

        return result

    def parse_commons(self, file_path):
        data_list = []
        with open(file_path, 'r', encoding=CMP_ENCODING) as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 3 and parts[2] == 'Gis':
                    data_list.append({
                        'Point A': parts[0],
                        'Point B': parts[1],
                        'CMP Filename': os.path.basename(file_path)
                    })
        return pd.DataFrame(data_list)

    def parse_coords(self, file_path):
        src_file = os.path.basename(file_path)
        group_id = src_file.split("_")[1]

        # Determine instrument name from config override or infer from group number
        override = self.group_offsets.get(group_id, {})
        inst_name = override.get("inst")

        # If not in config, default to 'C##' based on group number
        if not inst_name:
            inst_name = f"C{int(group_id):02d}"

        if override and isinstance(override, dict):
            inst_name = override.get("inst")

        if not inst_name:
            inst_name = self.get_station_name(file_path)

        if not inst_name:
            self._log(f"Could not determine instrument for {src_file}")
            return pd.DataFrame()

        # Extract anchor (local coordinates of total station)
        anchor_local = self.extract_anchor_local(file_path, inst_name)
        if anchor_local is None:
            self._log(f"Could not extract anchor for {inst_name} in {src_file}")
            return pd.DataFrame()


        # Extract all measured points
        points = self.extract_points(file_path)
        if not points:
            return pd.DataFrame()

        timestamp = self.extract_timestamp(src_file)
        results = []
        seen = set(p[0] for p in points)

        for name, e, n, z in points:
            # All points in a file belong to the one resolved station (inst_name)
            # for that setup — don't re-derive it from the point's own name
            # (name.split("_")[0]) as a proxy, since a point's naming convention
            # isn't guaranteed to start with the exact station name (e.g. a
            # station "CSX-C04" whose points are prefixed "C04_CSX_...").
            typ = "TS" if name == inst_name else ("REF" if "REF" in name else "MON")
            common = (
                name in self.commons_df["Point A"].values
                if not self.commons_df.empty
                else False
            )

            if name.endswith("F"):
                base = name[:-1]
                if base in seen:
                    continue
                else:
                    name = base

            results.append({
                "Timestamp": timestamp,
                "Inst": inst_name,
                "Group": group_id,
                "Point": name,
                "Type": typ,
                "Common": common,
                "Anchor_E": anchor_local[0],
                "Anchor_N": anchor_local[1],
                "Anchor_Z": anchor_local[2],
                "Easting": e,
                "Northing": n,
                "Elevation": z,
                "Source File": src_file
            })

        df = pd.DataFrame(results)

        return df

    def get_station_name(self, file_path):
        try:
            with open(file_path, "r", encoding=CMP_ENCODING) as f:
                lines = f.readlines()

            in_section = False
            for line in lines:
                if "Coordonnées compensées" in line or "Coordonn" in line:
                    in_section = True
                    continue

                if in_section:
                    parts = line.strip().split()
                    if len(parts) >= 4:
                        return parts[0]  # First entry after header
                    else:
                        continue
        except Exception as e:
            sys.stdout.write(f"\r   Error reading station name from {file_path}: {e}\n")
            sys.stdout.flush()

        return None

    def extract_anchor_local(self, file_path, inst_name):
        with open(file_path, 'r', encoding=CMP_ENCODING) as f:
            lines = f.readlines()

        in_section = False
        for line in lines:
            norm_line = line.lower()
            if not in_section:
                if "coordon" in norm_line and "compen" in norm_line:
                    in_section = True
                    continue
            else:
                parts = line.strip().split()
                # Skip header rows or empty lines
                if not parts or parts[0].lower() in {"point", "station"}:
                    continue
                # Try to match the instrument
                if parts[0] == inst_name and len(parts) >= 4:
                    try:
                        coords = tuple(map(float, parts[1:4]))
                        return coords
                    except ValueError:
                        return None
                # End section if the format breaks (e.g. different structure)
                if len(parts) > 0 and not re.match(r'^[A-Za-z0-9_-]+$', parts[0]):
                    break
        return None

    def extract_points(self, file_path):
        # Points must come from "Coordonnées compensées" (the final, network-
        # adjusted coordinates) so they're in the same reference state as the
        # anchor (extract_anchor_local reads the same section). The earlier
        # "Coordonnées initiales" table holds pre-adjustment coordinates and
        # must NOT be used here.
        collecting = False
        points = []
        with open(file_path, 'r', encoding=CMP_ENCODING) as f:
            for line in f:
                line = line.strip()
                norm_line = line.lower()
                if not collecting:
                    if "coordon" in norm_line and "compen" in norm_line:
                        collecting = True
                    continue
                # "Déplacements et résidus moyens" is the next section after
                # the compensated-coordinates table.
                if "placements" in norm_line:
                    break
                for prefix in ['XYZ ', 'XY ', 'Z ']:
                    line = line.replace(prefix, '')
                parts = line.split()
                if len(parts) >= 4:
                    try:
                        name = parts[0]
                        x, y, z = map(float, parts[1:4])
                        points.append((name, x, y, z))
                    except ValueError:
                        continue
        return points

    def extract_timestamp(self, filename):
        match = re.search(r'(\d{8}_\d{6})', filename)
        if match:
            try:
                return int(datetime.strptime(match.group(1), '%Y%m%d_%H%M%S').timestamp())
            except:
                return 0
        return 0
