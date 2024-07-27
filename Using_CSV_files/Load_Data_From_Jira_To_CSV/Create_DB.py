import os
import pandas as pd
import Using_CSV_files.Load_Data_From_Jira_To_CSV.TableColumns as TableColumns
import argparse


def create_DB(path, production=True):
    # Validate Path is valid

    if os.path.join("Using_CSV_files", "Data") not in path:
        raise Exception(f"path contains Using_CSV_files folder: {path}")

    if production and os.path.exists(path):
        raise Exception("DB name already exist!")
    if not os.path.exists(path):
        os.makedirs(path)

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.AllChangesOS))
    df.set_index(["issue_key", "chronological_number"], inplace=True)
    df.to_csv(os.path.join(path, "all_changes_os.csv"), index=True)

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.ChangesDescriptionOS))
    df.set_index(["issue_key", "chronological_number"], inplace=True)
    df.to_csv(os.path.join(path, "changes_description_os.csv"), index=True)

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.ChangesSprintOS))
    df.set_index(["issue_key", "chronological_number"], inplace=True)
    df.to_csv(os.path.join(path, "changes_sprint_os.csv"), index=True)

    #############################
    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.ChangesSummaryOS))
    df.set_index(["issue_key", "chronological_number"], inplace=True)
    df.to_csv(os.path.join(path, "changes_summary_os.csv"), index=True)

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.ChangesStoryPointsOS))
    df.set_index(["issue_key", "chronological_number"], inplace=True)
    df.to_csv(os.path.join(path, "changes_story_points_os.csv"), index=True)

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.ChangesCriteriaOS))
    df.set_index(["issue_key", "chronological_number"], inplace=True)
    df.to_csv(os.path.join(path, "changes_criteria_os.csv"), index=True)

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.CommentsOS))
    df.set_index(["issue_key", "id"], inplace=True)
    df.to_csv(os.path.join(path, "comments_os.csv"), index=True)

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.CommitsInfoOS))
    df.set_index(["issue_key", "commit"], inplace=True)
    df.to_csv(os.path.join(path, "commits_info_os.csv"), index=True)

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.ComponentsOS))
    df.set_index(["issue_key", "component"], inplace=True)
    df.to_csv(os.path.join(path, "components_os.csv"), index=True)

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.FixVersionsOS))
    df.set_index(["issue_key", "fix_version"], inplace=True)
    df.to_csv(os.path.join(path, "fix_versions_os.csv"), index=True)

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.IssueLinksOS))
    df.set_index(["issue_key", "issue_link"], inplace=True)
    df.to_csv(os.path.join(path, "issue_links_os.csv"), index=True)

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.LabelsOS))
    df.set_index(["issue_key", "label"], inplace=True)
    df.to_csv(os.path.join(path, "labels_os.csv"), index=True)

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.MainTableOS))
    df.set_index(["issue_key", "issue_id"], inplace=True)
    df.to_csv(os.path.join(path, "main_table_os.csv"), index=True)

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.NamesBugsIssueLinksOS))
    df.set_index(["issue_key", "bug_issue_link"], inplace=True)
    df.to_csv(os.path.join(path, "names_bugs_issue_links_os.csv"), index=True)

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.SubTaskNamesOS))
    df.set_index(["issue_key", "sub_task_name"], inplace=True)
    df.to_csv(os.path.join(path, "sub_task_names_os.csv"), index=True)

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.SprintsOS))
    df.set_index(["issue_key", "sprint_name"], inplace=True)
    df.to_csv(os.path.join(path, "sprints_os.csv"), index=True)

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.VersionsOS))
    df.set_index(["issue_key", "version"], inplace=True)
    df.to_csv(os.path.join(path, "versions_os.csv"), index=True)

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.GitHubOS))
    df.set_index(["issue_key", "project_key", "URL"], inplace=True)
    df.to_csv(os.path.join(path, "gitHubLinks_os.csv"), index=True)

    df = pd.DataFrame(columns=TableColumns.get_properties(TableColumns.AttachmentOS))
    df.set_index(["issue_key", "attachment_id", "project_key"], inplace=True)
    df.to_csv(os.path.join(path, "attachment_os.csv"), index=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--jiraName', help='Jira repo Name')
    parser.add_argument('--path', type=str, help='path')
    args = parser.parse_args()

    print(args.jiraName)
    print(args.path)
    """
    test_path = os.getcwd()
    path = "Using_CSV_files/Data/Using_CSV_files"
    create_DB(test_path, "test")
    """
