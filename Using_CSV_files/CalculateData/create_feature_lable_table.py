import os
import pandas as pd
import Using_CSV_files.Load_Data_From_Jira_To_CSV.Create_DB as Create_DB
import Using_CSV_files.Load_Data_From_Jira_To_CSV.TableColumns as TableColumns
import Using_CSV_files.FilesActivity as FilesActivity
import Using_CSV_files.Load_Data_From_Jira_To_CSV.ChooseFeaturesColumns as CreateFeatureTable


def start(path_to_load, path_to_save):
    Create_DB.create_DB(path_to_save)
    main_data = pd.read_csv(os.path.join(path_to_load, FilesActivity.filesNames[TableColumns.MainTableOS]))
    """
    #################################################################################################
    /* create new table in the database which include all the relevant features for the model */
    #################################################################################################
    """

    feature_table = CreateFeatureTable.get_information_from_main(main_data)
    path = os.path.join(path_to_save, 'feature_table.csv')
    feature_table.to_csv(path)
