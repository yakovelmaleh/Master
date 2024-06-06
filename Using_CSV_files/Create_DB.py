import os
import pandas as pd
import Using_CSV_files.TableColumns as TableColumns


def create_DB(path, DB_name):
    # Validate Path is valid
    if not os.path.exists(path):
        raise Exception("Invalid path")

    if "Using_CSV_files" not in path:
        raise Exception(f"path contains Using_CSV_files folder: {path}")
    # Create directory for the DB files if not exist
    path = f'{path}\\{DB_name}'
    """
    if os.path.exists(path):
        raise Exception("DB name already exist!")
    os.mkdir(path)
    """

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.AllChangesOS))
    df.set_index(["issue_key", "chronological_number"], inplace=True)
    df.to_csv(f"{path}\\all_changes_os.csv")

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.ChangesDescriptionOS))
    df.set_index(["issue_key", "chronological_number"], inplace=True)
    df.to_csv(f"{path}\\changes_description_os.csv")

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.ChangesSprintOS))
    df.set_index(["issue_key", "chronological_number"], inplace=True)
    df.to_csv(f"{path}\\changes_sprint_os.csv")

    #############################
    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.ChangesSummaryOS))
    df.set_index(["issue_key", "chronological_number"], inplace=True)
    df.to_csv(f"{path}\\changes_summary_os.csv")

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.ChangesStoryPointsOS))
    df.set_index(["issue_key", "chronological_number"], inplace=True)
    df.to_csv(f"{path}\\changes_story_points_os.csv")

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.ChangesCriteriaOS))
    df.set_index(["issue_key", "chronological_number"], inplace=True)
    df.to_csv(f"{path}\\changes_criteria_os.csv")

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.CommentsOS))
    df.set_index(["issue_key", "id"], inplace=True)
    df.to_csv(f"{path}\\comments_os.csv")

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.CommitsInfoOS))
    df.set_index(["issue_key", "commit"], inplace=True)
    df.to_csv(f"{path}\\commits_info_os.csv")

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.ComponentsOS))
    df.set_index(["issue_key", "component"], inplace=True)
    df.to_csv(f"{path}\\components_os.csv")

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.FixVersionsOS))
    df.set_index(["issue_key", "fix_version"], inplace=True)
    df.to_csv(f"{path}\\fix_versions_os.csv")

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.IssueLinksOS))
    df.set_index(["issue_key", "issue_link"], inplace=True)
    df.to_csv(f"{path}\\issue_links_os.csv")

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.LabelsOS))
    df.set_index(["issue_key", "label"], inplace=True)
    df.to_csv(f"{path}\\labels_os.csv")

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.MainTableOS))
    df.set_index(["issue_key", "issue_id"], inplace=True)
    df.to_csv(f"{path}\\main_table_os.csv")

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.NamesBugsIssueLinksOS))
    df.set_index(["issue_key", "bug_issue_link"], inplace=True)
    df.to_csv(f"{path}\\names_bugs_issue_links_os.csv")

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.SabTaskNamesOS))
    df.set_index(["issue_key", "sub_task_name"], inplace=True)
    df.to_csv(f"{path}\\sab_task_names_os.csv")

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.SprintsOS))
    df.set_index(["issue_key", "sprint_name"], inplace=True)
    df.to_csv(f"{path}\\sprints_os.csv")

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.VersionsOS))
    df.set_index(["issue_key", "version"], inplace=True)
    df.to_csv(f"{path}\\versions_os.csv")

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.AttachmentOS))
    df.set_index(["issue_key", "attachment_id", "project_key"], inplace=True)
    df.to_csv(f"{path}\\attachment_os.csv")


if __name__ == '__main__':
    test_path = os.getcwd()
    create_DB(test_path, "test")
