import os.path
from typing import List
import pandas as pd
import re
import Using_CSV_files.FilesActivity as FilesActivity
import Using_CSV_files.Load_Data_From_Jira_To_CSV.TableColumns as TableColumns
import Using_CSV_files.Load_Data_From_Jira_To_CSV.Create_DB as Create_DB
import Using_CSV_files.Load_Data_From_Jira_To_CSV.Logger as Logger


def start(path_to_load, path_to_save):

    Create_DB.create_DB(path_to_save)
    logger = Logger.get_logger_with_path_and_name(path_to_save, "add_body_clean_comments")

    comments_data_df = pd.read_csv(os.path.join(path_to_load, FilesActivity.filesNames[TableColumns.CommentsOS]))
    comments_data: List[TableColumns.CommentsOS] =\
        [TableColumns.createCommentsOSObjectFromDataFrame(row) for index, row in comments_data_df.iterrows()]

    for index, comment in enumerate(comments_data):
        clean_body = None
        body = comment.body
        if body is not None:
            clean_body = re.sub(r'<.+?>', "", body)
            clean_body = re.sub(r'&nbsp;', " ", clean_body)
            clean_body = re.sub(r"http\S+", "URL", clean_body)

        comment.body = clean_body

        FilesActivity.insert_element(path_to_save, comment, TableColumns.CommentsOS, logger)
        logger.debug(f"Insert {comment} with clean body")

        if index % 100 == 0:
            logger.info("Insert {i} items")

    FilesActivity.copy_files_with_black_list(path_to_load=path_to_load,
                                             path_to_save=path_to_save,
                                             blackList=[TableColumns.CommentsOS])


if __name__ == '__main__':
    jira_name = 'Hyperledger'
    start(jira_name)
    

