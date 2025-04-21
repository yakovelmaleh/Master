import os
import shutil


def delete_temp_directory(path: str, temp_name: str) -> None:
    last_folder = os.path.basename(os.path.normpath(path))

    if last_folder == temp_name and os.path.isdir(path):
        shutil.rmtree(path)
    else:
        print(f"Not deleting: Last folder is '{last_folder}', not 'Temp'")
