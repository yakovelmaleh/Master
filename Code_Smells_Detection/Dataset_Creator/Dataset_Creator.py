import Code_Smells_Detection.Detector.Detector as Detectors
import Code_Smells_Detection.Detector.Utils.Saver as Saver
import Code_Smells_Detection.Extract_Files.Extract_files_from_PR as Extract_files_from_PR
import Code_Smells_Detection.Extract_Files.GitHubFileModel as GitHubFileModel
import Using_CSV_files.FilesActivity as FilesActivity
import Using_CSV_files.Load_Data_From_Jira_To_CSV.TableColumns as TableColumns

import os
import pandas as pd
from typing import List
import shutil

pull_type = "pull"
output_temp_directory = "Temp"


def get_current_file_path():
    current_file_path = os.path.abspath(__file__)
    return os.path.dirname(current_file_path)


def get_temp_folder_path():
    return os.path.join(get_current_file_path(), output_temp_directory)


def add_row_to_dataset_by_files(
        gitHubModels: List[GitHubFileModel.GitHubFileModel],
        table_path_to_save: str,
        state: Saver.StateImplementation,
        issue_key: str):
    temp_folder_path = get_temp_folder_path()
    os.makedirs(temp_folder_path, exist_ok=True)

    for getHubModel in gitHubModels:
        getHubModel.save_as_file(temp_folder_path)

    Detectors.run_detectors(
        input_path=temp_folder_path,
        table_path_to_save=table_path_to_save,
        state=state,
        issue_key=issue_key)

    shutil.rmtree(temp_folder_path)


def get_github_object_list(PRs_file_folder: str) -> List[TableColumns.GitHubOS] :
    PRs_file_name = FilesActivity.filesNames[TableColumns.GitHubOS]
    PRs_file_path = os.path.join(PRs_file_folder, PRs_file_name)

    PRs_df = pd.read_csv(PRs_file_path)
    gitHubObjectList: List[TableColumns.GitHubOS] = \
        [TableColumns.createGitHubOSObjectFromDataFrame(row) for index, row in PRs_df.iterrows()]

    return gitHubObjectList


def add_rows_to_dataset_by_PR_gitHubObject(pr_gitHubObject: TableColumns.GitHubOS, table_path_to_save: str):
    pr_url = pr_gitHubObject.URL[0] if isinstance(pr_gitHubObject.URL, tuple) else pr_gitHubObject.URL

    files_before_PR, files_after_PR = Extract_files_from_PR.get_changed_files_in_PR(pr_url)

    add_row_to_dataset_by_files(
        gitHubModels=files_before_PR,
        table_path_to_save=table_path_to_save,
        state=Saver.StateImplementation.BEFORE_IMPLEMENTATION,
        issue_key=pr_gitHubObject.issue_key)

    add_row_to_dataset_by_files(
        gitHubModels=files_after_PR,
        table_path_to_save=table_path_to_save,
        state=Saver.StateImplementation.AFTER_IMPLEMENTATION,
        issue_key=pr_gitHubObject.issue_key)


def summarize_rows_by_issue_key(save_output_path: str):
    for program_language in Saver.ProgramLanguage:

        for state in Saver.StateImplementation:

            path = os.path.join(save_output_path, f'{program_language.value}_{state.value}.csv')

            if os.path.isfile(path):
                Saver.summarize_by_issue_key(path)


def run(PRs_file_folder: str, save_output_path: str):

    gitHubObjectList: List[TableColumns.GitHubOS] = get_github_object_list(PRs_file_folder)

    for gitHubObject in gitHubObjectList:

        if gitHubObject.gitHubtype == pull_type:

            add_rows_to_dataset_by_PR_gitHubObject(gitHubObject, save_output_path)

    summarize_rows_by_issue_key(save_output_path)

    # summarize all the program languages


if __name__ == '__main__':
    run(
        "C:\\Users\\t-yelmaleh\\OneDrive - Microsoft\\Desktop\\Yakov\\Master\\Master\\Using_CSV_files\\test",
        "C:\\Users\\t-yelmaleh\\Downloads\\temp1")