import json
from typing import List
import pandas as pd
import Using_CSV_files.FilesActivity as FilesActivity
import Using_CSV_files.Load_Data_From_Jira_To_CSV.TableColumns as TableColumns
import Using_CSV_files.Load_Data_From_Jira_To_CSV.Logger as Logger
import Using_CSV_files.Load_Data_From_Jira_To_CSV.Create_DB as Create_DB


def start(path_to_load, path_to_save):
    Create_DB.create_DB(path_to_save)
    logger = Logger.get_logger_with_path_and_name(path_to_save, "delete_no_sprint_no_done")

    """
    ###################################################################################
    /* delete all the USI which are no done yet or not related to any sprint  from
    the main table */
    ###################################################################################
    """

    mainDf = pd.read_csv(f'{path_to_load}\\{FilesActivity.filesNames[TableColumns.MainTableOS]}')
    mainObjectList: List[TableColumns.MainTableOS] = \
        [TableColumns.createMainObjectFromDataFrame(row) for index, row in mainDf.iterrows()]

    commentDf = pd.read_csv(f'{path_to_load}\\{FilesActivity.filesNames[TableColumns.CommentsOS]}')
    commentObjectList: List[TableColumns.CommentsOS] = \
        [TableColumns.createCommentsOSObjectFromDataFrame(row) for index, row in commentDf.iterrows()]

    for mainObject in mainObjectList:
        time_add_to_sprint = mainObject.time_add_to_sprint
        comment_before_adding_to_sprint = \
            list(filter(lambda comment: comment.issue_key == mainObject.issue_key and
                                        comment.created <= time_add_to_sprint,
                        commentObjectList))

        mainObject.num_comments_before_sprint = len(comment_before_adding_to_sprint)

    # main_table_os is not relevant anymore
    relevantMainObjectList = list(filter(lambda mainObject: mainObject.num_comments_before_sprint > 0, mainObjectList))

    for mainObject in relevantMainObjectList:
        issue_key = mainObject.issue_key

        insertFunction = get_insert_function(path_to_save, path_to_load, issue_key, logger)

        insertFunction(TableColumns.ChangesSummaryOS, TableColumns.createChangesDescriptionOSObjectFromDataFrame)
        insertFunction(TableColumns.ChangesDescriptionOS, TableColumns.createChangesDescriptionOSObjectFromDataFrame)
        insertFunction(TableColumns.ChangesStoryPointsOS, TableColumns.createChangesStoryPointsOSObjectFromDataFrame)
        insertFunction(TableColumns.ChangesCriteriaOS, TableColumns.createCChangesCriteriaOSObjectFromDataFrame)
        insertFunction(TableColumns.CommentsOS, TableColumns.createCommentsOSObjectFromDataFrame)
        insertFunction(TableColumns.ChangesSprintOS, TableColumns.createChangesSprintOSObjectFromDataFrame)
        insertFunction(TableColumns.CommitsInfoOS, TableColumns.createCommitsInfoOSObjectFromDataFrame)
        insertFunction(TableColumns.ComponentsOS, TableColumns.createComponentsOSObjectFromDataFrame)
        insertFunction(TableColumns.FixVersionsOS, TableColumns.createFixVersionsOSObjectFromDataFrame)
        insertFunction(TableColumns.SprintsOS, TableColumns.createSprintsOSObjectFromDataFrame)
        insertFunction(TableColumns.IssueLinksOS, TableColumns.createIssueLinksOSObjectFromDataFrame)
        insertFunction(TableColumns.NamesBugsIssueLinksOS, TableColumns.createNamesBugsIssueLinksOSObjectFromDataFrame)
        insertFunction(TableColumns.SubTaskNamesOS, TableColumns.createSubTaskNamesOSObjectFromDataFrame)
        insertFunction(TableColumns.LabelsOS, TableColumns.createLabelsOSObjectFromDataFrame)
        insertFunction(TableColumns.VersionsOS, TableColumns.createVersionsOSObjectFromDataFrame)
        insertFunction(TableColumns.AllChangesOS, TableColumns.createAllChangesOSObjectFromDataFrame)
        insertFunction(TableColumns.GitHubOS, TableColumns.createGitHubOSObjectFromDataFrame)
        insertFunction(TableColumns.AttachmentOS, TableColumns.createAttachmentOSObjectFromDataFrame)

    FilesActivity.insert_elements(path_to_save, TableColumns.MainTableOS, relevantMainObjectList, logger)


def get_insert_function(path_to_save, path_to_load, issue_key, logger):
    def eqIssueKey(element):
        return element.issue_key == issue_key

    def insertElements(classType, classFunction):
        df = pd.read_csv(f'{path_to_load}\\{FilesActivity.filesNames[classType]}')
        objectList: List[classType] = \
            [classFunction(row)
             for index, row in df.iterrows()]
        FilesActivity.insert_elements(path_to_save, classType,
                                      list(filter(eqIssueKey, objectList)), logger)

    return insertElements


if __name__ == '__main__':
    with open('../Source/jira_data_for_instability_v1_for_Next.json') as f:
        jira_data_sources = json.load(f)

    for jira_name, jira_obj in jira_data_sources.items():
        print("start add_columns_main_change, DB: ", jira_name)
        start(jira_name)
    print("finish to add_columns_main_change")
