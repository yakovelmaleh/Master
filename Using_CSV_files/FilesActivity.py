from Using_CSV_files.Load_Data_From_Jira_To_CSV import TableColumns, Logger
import pandas as pd
import os
import shutil


filesNames = {
    TableColumns.AllChangesOS: "all_changes_os.csv",
    TableColumns.ChangesDescriptionOS: "changes_description_os.csv",
    TableColumns.ChangesSprintOS: "changes_sprint_os.csv",
    TableColumns.ChangesSummaryOS: "changes_summary_os.csv",
    TableColumns.ChangesStoryPointsOS: "changes_story_points_os.csv",
    TableColumns.ChangesCriteriaOS: "changes_criteria_os.csv",
    TableColumns.CommentsOS: "comments_os.csv",
    TableColumns.CommitsInfoOS: "commits_info_os.csv",
    TableColumns.ComponentsOS: "components_os.csv",
    TableColumns.FixVersionsOS: "fix_versions_os.csv",
    TableColumns.IssueLinksOS: "issue_links_os.csv",
    TableColumns.LabelsOS: "labels_os.csv",
    TableColumns.MainTableOS: "main_table_os.csv",
    TableColumns.NamesBugsIssueLinksOS: "names_bugs_issue_links_os.csv",
    TableColumns.SubTaskNamesOS: "sab_task_names_os.csv",
    TableColumns.SprintsOS: "sprints_os.csv",
    TableColumns.VersionsOS: "versions_os.csv",
    TableColumns.AttachmentOS: "attachment_os.csv",
    TableColumns.GitHubOS: "gitHubLinks_os.csv",
}

primaryKeys = {
    TableColumns.AllChangesOS: ["issue_key", "chronological_number", "project_key"],
    TableColumns.ChangesDescriptionOS: ["issue_key", "chronological_number", "project_key"],
    TableColumns.ChangesSprintOS: ["issue_key", "chronological_number", "project_key"],
    TableColumns.ChangesSummaryOS: ["issue_key", "chronological_number", "project_key"],
    TableColumns.ChangesStoryPointsOS: ["issue_key", "chronological_number", "project_key"],
    TableColumns.ChangesCriteriaOS: ["issue_key", "chronological_number", "project_key"],
    TableColumns.CommentsOS: ["issue_key", "id", "project_key"],
    TableColumns.CommitsInfoOS: ["issue_key", "commit", "project_key"],
    TableColumns.ComponentsOS: ["issue_key", "component", "project_key"],
    TableColumns.FixVersionsOS: ["issue_key", "fix_version", "project_key"],
    TableColumns.IssueLinksOS: ["issue_key", "issue_link", "project_key"],
    TableColumns.LabelsOS: ["issue_key", "label", "project_key"],
    TableColumns.MainTableOS: ["issue_key", "issue_id", "project_key"],
    TableColumns.NamesBugsIssueLinksOS: ["issue_key", "bug_issue_link", "project_key"],
    TableColumns.SubTaskNamesOS: ["issue_key", "sub_task_name", "project_key"],
    TableColumns.SprintsOS: ["issue_key", "sprint_name", "project_key"],
    TableColumns.VersionsOS: ["issue_key", "version", "project_key"],
    TableColumns.AttachmentOS: ["issue_key", "attachment_id", "project_key"],
    TableColumns.GitHubOS: ["issue_key", "project_key", "URL"]
}


def get_File(path, className):
    return pd.read_csv(os.path.join(path, filesNames[className]), index_col=primaryKeys[className])


# def get element
# def get elements

def insert_element(path, className, element, logger) -> bool:
    logger.debug(f"Insert to {filesNames[className]} new element {element}")
    if not isinstance(element, className):
        logger.error(f"Insert Error: can not insert an element {element} not from type {className}")
        return False
    else:
        new_row = pd.DataFrame([element.__dict__])
        new_row.set_index(primaryKeys[className], inplace=True)
        new_row.to_csv(os.path.join(path, filesNames[className]), mode='a', index=True, header=False)
        logger.info(f"Element {element} in {filesNames[className]}")
        return True


def insert_elements(path, className, elements: list, logger) -> int:
    logger.debug(f"Insert to {filesNames[className]} new {len(elements)} elements")
    secures_insertions = 0
    for element in elements:
        if insert_element(path, className, element, logger):
            secures_insertions += 1
    return secures_insertions


def copy_file(path_to_load, path_to_save, fileName):
    source_file = os.path.join(path_to_load, fileName)
    destination_file = os.path.join(path_to_save, fileName)

    shutil.copyfile(source_file, destination_file)


def copy_files_with_black_list(path_to_load, path_to_save, blackList):
    blackListFileNames = [filesNames[fileName] for fileName in blackList]

    files = os.listdir(path_to_load)
    files = [file for file in files if os.path.isfile(os.path.join(path_to_load, file))]

    for file in files:
        if file not in blackListFileNames:
            copy_file(path_to_load, path_to_save, file)


if __name__ == '__main__':
    path = f'{os.getcwd()}\\test'
    print("Hi")
