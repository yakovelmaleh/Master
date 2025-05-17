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


def summarize_rows_by_issue_key(save_output_path: str):
    for program_language in ProgramLanguage:

        for state in StateImplementation:

            path = os.path.join(save_output_path, f'{program_language.value}_{state.value}.csv')

            if os.path.isfile(path):
                summarize_by_issue_key(path)


def summarize_code_smells_across_program_languages(input_files_path: str, output_files_path):

    for state in StateImplementation:
        dfs_per_state = []

        for program_language in ProgramLanguage:
            path = os.path.join(input_files_path, f'{program_language.value}_{state.value}.csv')

            if os.path.exists(path):
                df = pd.read_csv(path)
                dfs_per_state.append(df)

        if dfs_per_state:
            combined_df = pd.concat(dfs_per_state, ignore_index=True)
            summary_df = combined_df.groupby("issue_key").sum(numeric_only=True).reset_index()

            output_path = os.path.join(output_files_path, f"{state.value}_code_smells.csv")

            summary_df.to_csv(output_path, index=False, header=True)


