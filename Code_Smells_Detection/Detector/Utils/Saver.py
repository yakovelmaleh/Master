import pandas as pd
from enum import Enum
import os


class StateImplementation(Enum):
    BEFORE_IMPLEMENTATION = "Before"
    AFTER_IMPLEMENTATION = "After"
    DELTA = "Delta"


class ProgramLanguage(Enum):
    JAVA = "java"
    PYTHON = "python"


def save(table_path: str, program_language: ProgramLanguage, state: StateImplementation, issue_key: str,
         code_smell_results: dict) -> None:
    code_smell_results["issue_key"] = issue_key

    new_row = pd.DataFrame([code_smell_results])

    relevant_table_path = os.path.join(table_path, f"{program_language.value}_{state.value}.csv")
    file_exists = os.path.exists(relevant_table_path)

    new_row.to_csv(relevant_table_path, mode='a', index=False, header=not file_exists)


def summarize_by_issue_key(table_path: str):

    (((pd.read_csv(table_path)
     .groupby("issue_key", as_index=False))
     .sum(numeric_only=True))
     .to_csv(table_path, index=False, header=True))
