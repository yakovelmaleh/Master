import json
import os.path

import Using_CSV_files.CalculateData.start_calculation as start_calculation
import Data_Analysis.JQL_Queries as JQL


def Simple_Data(master: str = None):
    if master is None:
        path_to_Data_folder = os.path.join(os.getcwd(), "Using_CSV_files", "Data")
    else:
        path_to_Data_folder = os.path.join(os.getcwd(), master, "Using_CSV_files", "Data")
    current_dir = "Simple_Data"
    json_file_name = "jira_data_for_instability.json"

    with open(os.path.join(path_to_Data_folder, current_dir, json_file_name)) as f:
        jira_data_sources = json.load(f)

    for jira_name, jira_obj in jira_data_sources.items():
        query = (f'{JQL.filter_by_noBugs()}'
                 f' AND ({JQL.filter_by_status(jira_name)} OR {JQL.filter_by_resolution(jira_name)})'
                 f' AND {JQL.filter_byOptionalPR(jira_name)}')

        start_calculation.start(path=path_to_Data_folder,
                                jira_name=jira_name,
                                data_path=current_dir,
                                jira_object=jira_obj,
                                query=query)


if __name__ == '__main__':
    path_prefix = "Master"
    Simple_Data(path_prefix)