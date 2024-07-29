import json
import os.path

import pandas as pd
import datetime
import Using_CSV_files.Load_Data_From_Jira_To_CSV.Logger as Logger
import Using_CSV_files.FilesActivity as FilesActivity
import Using_CSV_files.Load_Data_From_Jira_To_CSV.TableColumns as TableColumns
import Using_CSV_files.Load_Data_From_Jira_To_CSV.Create_DB as Create_DB
from typing import List


def add_column_time_add_to_sprint(path_to_save, main_object_list: List[TableColumns.MainTableOS],
                                  changes_sprint_object_list: List[TableColumns.ChangesSprintOS],
                                  sprints_object_list: List[TableColumns.SprintsOS]):
    '''
    function which calculate the time that the USI enter to sprint
    input: sql connection, the sql query which update the database with the results, the main table with the data, the change sprint table, the sprint table
    there is no ouptut, the function calculate the time and write it to the new column in main table
    '''
    logger = Logger.get_logger_with_path_and_name(path_to_save, "calculate_time_add_sprint")

    for index, main_tableObject in enumerate(main_object_list):
        issue_name = main_tableObject.issue_key

        change_sprint_filter_df_by_issueKey = list(filter(lambda comment: comment.issue_key == issue_name,
                                                          changes_sprint_object_list))

        # the type of change_sprint_filter_df_by_issueKey[different_time_from_creat] is floatType
        min_val_of_different_time_from_creat = 0 if len(change_sprint_filter_df_by_issueKey) == 0 \
            else min([change.different_time_from_creat] for change in change_sprint_filter_df_by_issueKey)

        change_sprint_issue: List[TableColumns.ChangesSprintOS] = \
            [] if min_val_of_different_time_from_creat == 0 else list(filter(lambda comment: comment.different_time_from_creat == min_val_of_different_time_from_creat, change_sprint_filter_df_by_issueKey))

        sprint_issue: List[TableColumns.SprintsOS] = (
            list(filter(lambda sprint: sprint.issue_key == issue_name, sprints_object_list)))

        if len(sprint_issue) > 0 and sprint_issue[0].start_date is not None:
            time_add_to_sprint = sprint_issue[0].start_date

        elif len(change_sprint_issue) > 0 and change_sprint_issue[0].created:
            time_add_to_sprint = change_sprint_issue[0].created

        else:
            time_add_to_sprint = main_tableObject.created

        main_tableObject.time_add_to_sprint = time_add_to_sprint

        FilesActivity.insert_element(path_to_save, TableColumns.MainTableOS, main_tableObject, logger)

        if index % 100 == 0:
            logger.info(f'project: {main_tableObject.project_key} updated {index} USIs')


def start(path_to_load, path_to_save):
    Create_DB.create_DB(path_to_save)

    main_data = pd.read_csv(os.path.join(path_to_load, 'main_table_os.csv'))
    main_object_list: List[TableColumns.MainTableOS] = \
        [TableColumns.createMainObjectFromDataFrame(row) for index, row in main_data.iterrows()]

    changes_sprint = pd.read_csv(os.path.join(path_to_load, 'changes_sprint_os.csv'))
    changes_sprint_object_list: List[TableColumns.ChangesSprintOS] = \
        [TableColumns.createChangesSprintOSObjectFromDataFrame(row) for index, row in changes_sprint.iterrows()]

    sprints = pd.read_csv(os.path.join(path_to_load, 'sprints_os.csv'))
    sprints_object_list: List[TableColumns.SprintsOS] = \
        [TableColumns.createSprintsOSObjectFromDataFrame(row) for index, row in sprints.iterrows()]

    add_column_time_add_to_sprint(path_to_save, main_object_list, changes_sprint_object_list,
                                  sprints_object_list)

    FilesActivity.copy_files_with_black_list(path_to_load, path_to_save, [TableColumns.MainTableOS])


if __name__ == '__main__':
    with open('../Source/jira_data_for_instability.json') as f:
        jira_data_sources = json.load(f)

    for jira_name, jira_obj in jira_data_sources.items():
        print("start calculate time add spint, DB: ", jira_name)
        start(jira_name)
    print("finish to calculate time add spint")
