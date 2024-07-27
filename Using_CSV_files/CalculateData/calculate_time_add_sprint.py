import json
import os.path

import pandas as pd
import datetime
import Using_CSV_files.Load_Data_From_Jira_To_CSV.Logger as Logger
import Using_CSV_files.FilesActivity as FilesActivity
import Using_CSV_files.Load_Data_From_Jira_To_CSV.TableColumns as TableColumns
import Using_CSV_files.Load_Data_From_Jira_To_CSV.Create_DB as Create_DB


def add_column_time_add_to_sprint(path_to_save, main_table, change_sprint, sprints):
    '''
    function which calculate the time that the USI enter to sprint
    input: sql connection, the sql query which update the database with the results, the main table with the data, the change sprint table, the sprint table
    there is no ouptut, the function calculate the time and write it to the new column in main table
    '''
    logger = Logger.get_logger_with_path_and_name(path_to_save, "calculate_time_add_sprint")
    main_table["time_add_to_sprint"] = None
    for i in range(0, len(main_table)):
        main_tableObject: TableColumns.MainTableOS = TableColumns.createMainObjectFromDataFrame(main_table.iloc[i])
        issue_name = main_tableObject.issue_key

        change_sprint_filter_df_by_issueKey = change_sprint[change_sprint['issue_key'] == issue_name]

        # the type of change_sprint_filter_df_by_issueKey[different_time_from_creat] is floatType
        min_val_of_different_time_from_creat = min(change_sprint_filter_df_by_issueKey['different_time_from_creat'])

        change_sprint_issue = \
            change_sprint_filter_df_by_issueKey[change_sprint_filter_df_by_issueKey['different_time_from_creat'] ==
                                                min_val_of_different_time_from_creat]

        sprint_issue = sprints[sprints['issue_key'] == issue_name]

        if len(sprint_issue) > 0 and sprint_issue['start_date'][0] is not None:
            time_add_to_sprint = (
                datetime.datetime.strptime(str(sprint_issue['start_date'][i]), '%Y-%m-%d %H:%M:%S'))

        elif len(change_sprint_issue) > 0 and change_sprint_issue['created'][0]:
            time_add_to_sprint = (
                datetime.datetime.strptime(str(change_sprint_issue['created'][i]), '%Y-%m-%d %H:%M:%S'))

        else:
            time_add_to_sprint = datetime.datetime.strptime(str(main_tableObject.created), '%Y-%m-%d %H:%M:%S')

        main_table.at[i, 'time_add_to_sprint'] = time_add_to_sprint

        FilesActivity.insert_element(path_to_save, TableColumns.MainTableOS, main_tableObject, logger)

        logger.debug(f"#{i} IssueKey: {issue_name} updated time_add_to_sprint to {time_add_to_sprint}")
        if i % 100 == 0:
            logger.info(f'project: {main_tableObject.project_key} updated {i} USIs')


def start(path_to_load, path_to_save):
    Create_DB.create_DB(path_to_save)

    main_data = pd.read_csv(os.path.join(path_to_load, 'main_table_os.csv'))
    changes_sprint = pd.read_csv(os.path.join(path_to_load, 'changes_sprint_os.csv'))
    sprints = pd.read_csv(os.path.join(path_to_load, 'sprints_os.csv'))

    add_column_time_add_to_sprint(path_to_save, main_data, changes_sprint, sprints)

    FilesActivity.copy_files_with_black_list(path_to_load, path_to_save, [TableColumns.MainTableOS])


if __name__ == '__main__':
    with open('../Source/jira_data_for_instability.json') as f:
        jira_data_sources = json.load(f)

    for jira_name, jira_obj in jira_data_sources.items():
        print("start calculate time add spint, DB: ", jira_name)
        start(jira_name)
    print("finish to calculate time add spint")
