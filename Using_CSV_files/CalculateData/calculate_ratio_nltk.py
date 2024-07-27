import os.path

import nltk
from typing import List
import pandas as pd
import Using_CSV_files.FilesActivity as FilesActivity
import Using_CSV_files.Load_Data_From_Jira_To_CSV.TableColumns as TableColumns
import Using_CSV_files.Load_Data_From_Jira_To_CSV.Logger as Logger
import Using_CSV_files.Load_Data_From_Jira_To_CSV.Create_DB as Create_DB


def start(path_to_load, path_to_save):
    Create_DB.create_DB(path_to_save)
    logger = Logger.get_logger_with_path_and_name(path_to_save, "calculate_ratio_nltk")

    mainDf = pd.read_csv(os.path.join(path_to_load, FilesActivity.filesNames[TableColumns.MainTableOS]))
    mainObjectList: List[TableColumns.MainTableOS] = \
        [TableColumns.createMainObjectFromDataFrame(row) for index, row in mainDf.iterrows()]

    for index, mainObject in enumerate(mainObjectList):
        try:
            original_text = mainObject.original_summary_description_acceptance_sprint
            text_last = mainObject.summary_description_acceptance
            different = nltk.edit_distance(original_text.split(), text_last.split())

            original_text_split_len = len(original_text.split())
            length_text_original = original_text_split_len if original_text_split_len > 0 else 1
            ratio = different / length_text_original

            mainObject.num_different_words_all_text_sprint_new = int(different)
            mainObject.num_ratio_words_all_text_sprint_new = float(ratio)

            logger.debug(f'Finish with issueKey: {mainObject.issue_key}')

            if index % 100 == 0:
                logger.info(f'Finish {index} issue keys')

        except Exception as e:
            logger.error(f"Error appears, Issuekey: {mainObject.issue_key}, error:{e} ")

    FilesActivity.insert_elements(path_to_save, TableColumns.MainTableOS, mainObjectList, logger)
    FilesActivity.copy_files_with_black_list(
        path_to_load=path_to_load,
        path_to_save=path_to_save,
        blackList=[TableColumns.MainTableOS])
