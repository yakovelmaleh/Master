import Code_Smells_Detection.Detector.DPy.Utils as Utils
import pandas as pd
import os

code_smells_names = [
    "Complex Conditional",
    "Complex Method",
    "Empty catch clause",
    "Long Identifier",
    "Long Method",
    "Long Parameter List",
    "Long Statement",
    "Magic Number",
    "Missing default",
    "Long lambda function",
    "Long message chain"
]


code_smells_file_name = "Temp_implementation_smells.csv"
code_smells_column = "Smell"


def get_code_smells_implementation() -> str:
    return os.path.join(Utils.get_detection_output_path(), code_smells_file_name)


def count_code_smells() -> dict:

    code_smells_df = pd.read_csv(get_code_smells_implementation())

    code_smell_counts = code_smells_df[code_smells_column].value_counts()

    code_smell_counts = dict((k.lower(), v) for k, v in code_smell_counts.items())

    return {name: code_smell_counts.get(name.lower(), 0) for name in code_smells_names}

