import os
from datetime import datetime

def export_to_csv(df, proj_name, export_folder, project_config=None):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{proj_name}_{timestamp}.csv"
    filepath = os.path.join(export_folder, filename)

    os.makedirs(export_folder, exist_ok=True)
    df.to_csv(filepath, sep=',', index=False, header=True)
