import os

# Define the command and arguments
java_jar_name = "DesigniteJavaCommunity.jar"
output_temp_directory = "Temp"


def get_current_file_path():
    current_file_path = os.path.abspath(__file__)
    return os.path.dirname(current_file_path)


def get_detection_output_path():
    return os.path.join(get_current_file_path(), output_temp_directory)


def get_detect_command(input_folder: str):
    return [
        "java", "-jar", os.path.join(get_current_file_path(), java_jar_name),
        "-i", input_folder,
        "-o", get_detection_output_path(),
    ]
