import os.path
from typing import List
import pandas as pd
import Using_CSV_files.FilesActivity as FilesActivity
import Using_CSV_files.Load_Data_From_Jira_To_CSV.TableColumns as TableColumns
import Using_CSV_files.Load_Data_From_Jira_To_CSV.Logger as Logger
import Using_CSV_files.Load_Data_From_Jira_To_CSV.Create_DB as Create_DB


def concatStringsWithEnd(stringConnect: str, existingString: str = None, newString: str = None):
    return (f'{existingString + " $end$" if existingString is not None else ""}'
            f' {stringConnect}: {newString if newString is not None else " "}')


def create_summary_description_acceptance(summary: str, description: str, acceptance_criteria: str):
    summary_description_acceptance = concatStringsWithEnd(stringConnect="Summary",
                                                          existingString=None,
                                                          newString=summary)

    summary_description_acceptance = concatStringsWithEnd(stringConnect="Description",
                                                          existingString=summary_description_acceptance,
                                                          newString=description)

    summary_description_acceptance = concatStringsWithEnd(stringConnect="Acceptance Criteria",
                                                          existingString=summary_description_acceptance,
                                                          newString=acceptance_criteria)
    return summary_description_acceptance


def start(path_to_load, path_to_save):
    Create_DB.create_DB(path_to_save)
    logger = Logger.get_logger_with_path_and_name(path_to_save, "create_combine_columns_summary_description")

    mainDf = pd.read_csv(os.path.join(path_to_load, FilesActivity.filesNames[TableColumns.MainTableOS]))
    mainObjectList: List[TableColumns.MainTableOS] = \
        [TableColumns.createMainObjectFromDataFrame(row) for index, row in mainDf.iterrows()]

    for index, mainObject in enumerate(mainObjectList):
        summary_description_acceptance =\
            create_summary_description_acceptance(summary=mainObject.summary,
                                                  description=mainObject.description,
                                                  acceptance_criteria=mainObject.acceptance_criteria)

        mainObject.summary_description_acceptance = summary_description_acceptance

        original_summary_description_acceptance =\
            create_summary_description_acceptance(summary=mainObject.original_summary,
                                                  description=mainObject.original_description,
                                                  acceptance_criteria=mainObject.original_acceptance_criteria)

        mainObject.original_summary_description_acceptance = original_summary_description_acceptance

        original_summary_description_acceptance_sprint =\
            create_summary_description_acceptance(summary=mainObject.original_summary_sprint,
                                                  description=mainObject.original_description_sprint,
                                                  acceptance_criteria=mainObject.original_acceptance_criteria_sprint)

        mainObject.original_summary_description_acceptance_sprint = original_summary_description_acceptance_sprint
        logger.debug(f'Finish with IssueKey: {mainObject.issue_key}')

        if index % 100 == 0:
            logger.info(f"Finish {index} User stories.")

    FilesActivity.insert_elements(path_to_save, TableColumns.MainTableOS, mainObjectList, logger)

    FilesActivity.copy_files_with_black_list(
        path_to_load=path_to_load,
        path_to_save=path_to_save,
        blackList=[TableColumns.MainTableOS])
