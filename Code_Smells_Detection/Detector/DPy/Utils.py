import os

# Define the command and arguments
DPy_name = "DPy"
output_temp_directory = "Temp"


def get_current_file_path():
    current_file_path = os.path.abspath(__file__)
    return os.path.dirname(current_file_path)


def get_detection_output_path():
    return os.path.join(get_current_file_path(), output_temp_directory)


def get_detect_command(input_folder: str):
    return [
        os.path.join(get_current_file_path(), DPy_name), "analyze",
        "-i", input_folder,
        "-o", get_detection_output_path(),
        "-f", "csv"
    ]
