import json
from typing import List


import pandas as pd
import Using_CSV_files.FilesActivity as FilesActivity
import Using_CSV_files.Load_Data_From_Jira_To_CSV.TableColumns as TableColumns
import Using_CSV_files.Load_Data_From_Jira_To_CSV.Logger as Logger
import Using_CSV_files.Load_Data_From_Jira_To_CSV.Create_DB as Create_DB


def start(path_to_load, path_to_save):

    Create_DB.create_DB(path_to_save)
    logger = Logger.get_logger_with_path_and_name(path_to_save, "add_columns_main_change")

    mainDf = pd.read_csv(f'{path_to_load}\\{FilesActivity.filesNames[TableColumns.MainTableOS]}')
    mainObjectList: List[TableColumns.MainTableOS] =\
        [TableColumns.createMainObjectFromDataFrame(row) for index, row in mainDf.iterrows()]

    allChangesDf = pd.read_csv(f'{path_to_load}\\{FilesActivity.filesNames[TableColumns.AllChangesOS]}')
    allChangeObjectList: List[TableColumns.AllChangesOS] =\
        [TableColumns.createAllChangesOSObjectFromDataFrame(row) for index, row in allChangesDf.iterrows()]

    for change in allChangeObjectList:
        change: TableColumns.AllChangesOS
        for mainObject in mainObjectList:
            mainObject: TableColumns.MainTableOS
            if change.issue_key == mainObject.issue_key:
                change.time_add_to_sprint = mainObject.time_add_to_sprint
                change.is_after_sprint = change.time_add_to_sprint < change.created

                if change.time_add_to_sprint > change.created:
                    change.time_from_sprint = (change.time_add_to_sprint - change.created).total_seconds() / 60
                    change.is_after_sprint = 1
                else:
                    change.time_from_sprint = (change.created - change.time_add_to_sprint).total_seconds() / 60
                    change.is_after_sprint = 0

                change.is_after_close = 1 if mainObject.resolution_date < change.created else 0

                FilesActivity.insert_element(path_to_save, TableColumns.AllChangesOS, change, logger)
                break

    FilesActivity.copy_files_with_black_list(path_to_load=path_to_load,
                                             path_to_save=path_to_save,
                                             blackList=[TableColumns.AllChangesOS])


if __name__ == '__main__':
    with open('../Source/jira_data_for_instability.json') as f:
        jira_data_sources = json.load(f)

    for jira_name, jira_obj in jira_data_sources.items():
        print("start add_columns_main_change, DB: ", jira_name)
        start(jira_name)
    print("finish to add_columns_main_change")
