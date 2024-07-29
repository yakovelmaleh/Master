import json
import os.path
import sys
import Using_CSV_files.CalculateData.start_calculation as start_calculation
import Data_Analysis.JQL_Queries as JQL


def Simple_Data(jira_name: str):
    path_to_Data_folder = os.path.join(os.getcwd(), "Master", "Using_CSV_files", "Data")
    current_dir = "Simple_Data"
    json_file_name = "jira_data_for_instability.json"

    with open(os.path.join(path_to_Data_folder, current_dir, json_file_name)) as f:
        jira_data_sources = json.load(f)

    jira_obj = jira_data_sources[jira_name]
    query = (f'{JQL.filter_by_noBugs()}'
             f' AND ({JQL.filter_by_status(jira_name)} OR {JQL.filter_by_resolution(jira_name)})'
             f' AND {JQL.filter_byOptionalPR(jira_name)}')

    start_calculation.start(path=path_to_Data_folder,
                            jira_name=jira_name,
                            data_path=current_dir,
                            jira_object=jira_obj,
                            query=query)


if __name__ == '__main__':
    Simple_Data(sys.argv[1])
