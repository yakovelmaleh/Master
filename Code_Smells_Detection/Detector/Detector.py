import Code_Smells_Detection.Detector.DesigniteJavaCommunity.JavaDetector as DesigniteJavaCommunityDetector
import Code_Smells_Detection.Detector.DPy.PythonDetector as PythonDetector
import Code_Smells_Detection.Detector.Utils.Saver as Saver
import subprocess


def run_detection(command: str):
    try:
        command = command
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print("Error occurred:", e.stderr)
        raise e


def run_detectors(input_path: str, table_path_to_save, state: Saver.StateImplementation, issue_key: str):

    # java
    DesigniteJavaCommunityDetector.run(input_path, table_path_to_save, state, issue_key)

    # Python
    PythonDetector.run(input_path,table_path_to_save,state,issue_key)

