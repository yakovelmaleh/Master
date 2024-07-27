import json
import os
import Using_CSV_files.CalculateData.calculate_time_add_sprint
import Using_CSV_files.CalculateData.prepare_data_sql
import Using_CSV_files.CalculateData.add_body_clean_comments
import Using_CSV_files.CalculateData.add_columns_main_change
import Using_CSV_files.CalculateData.delete_no_sprint_no_done
import Using_CSV_files.CalculateData.create_combine_columns_summary_description
import Using_CSV_files.CalculateData.calculate_ratio_nltk
import Using_CSV_files.CalculateData.create_feature_lable_table
import Using_CSV_files.CalculateData.calculate_features_all_num_bad_issue
import Using_CSV_files.Load_Data_From_Jira_To_CSV.SetUpData as SetUpData


def start(path, data_path, jira_object, query):
    # Create the folders!!!!!!!!!!!!!
    print(f"********************start SetUpData********************")

    path_to_save_prefix = os.path.join(path, data_path, jira_name)
    path_to_save = f'{path_to_save_prefix}\\Downloaded_Data'
    SetUpData.start(path_to_save, jira_object, query)

    print(f"********************start calculate_time_add_sprint********************")

    path_to_load = path_to_save
    path_to_save = f'{path_to_save_prefix}\\calculate_time_add_sprint'
    calculate_time_add_sprint.start(path_to_load, path_to_save)

    print("********************start prepare_data_sql********************")

    path_to_load = path_to_save
    path_to_save = f'{path_to_save_prefix}\\prepare_data_sql'
    prepare_data_sql.start(path_to_load, path_to_save)

    print("********************start add_body_clean_comments********************")

    path_to_load = path_to_save
    path_to_save = f'{path_to_save_prefix}\\add_body_clean_comments'
    add_body_clean_comments.start(path_to_load, path_to_save)

    print("********************start add_columns_main_change********************")
    path_to_load = path_to_save
    path_to_save = f'{path_to_save_prefix}\\add_columns_main_change'
    add_columns_main_change.start(path_to_load, path_to_save)

    print("********************start delete_no_sprint_no_done********************")
    path_to_load = path_to_save
    path_to_save = f'{path_to_save_prefix}\\delete_no_sprint_no_done'
    delete_no_sprint_no_done.start(path_to_load, path_to_save)

    print("********************start create_combine_columns_summary_description********************")
    path_to_load = path_to_save
    path_to_save = f'{path_to_save_prefix}\\create_combine_columns_summary_description'
    create_combine_columns_summary_description.start(path_to_load, path_to_save)

    print("********************start calculate_ratio_nltk********************")
    path_to_load = path_to_save
    path_to_save = f'{path_to_save_prefix}\\calculate_ratio_nltk'
    calculate_ratio_nltk.start(path_to_load, path_to_save)

    print("********************start create_feature_lable_table********************")
    path_to_load = path_to_save
    path_to_save = f'{path_to_save_prefix}\\create_feature_lable_table'
    create_feature_lable_table.start(path_to_load, path_to_save)

    print("********************start calculate_features_all_num_bad_issue********************")
    path_to_load = path_to_save
    path_to_save = f'{path_to_save_prefix}\\calculate_features_all_num_bad_issue'
    calculate_features_all_num_bad_issue.start(path_to_load, path_to_save)


if __name__ == '__main__':
    with open('../Source/jira_data_for_instability_v1_calculate.json') as f:
        jira_data_sources = json.load(f)

    for jira_name, jira_obj in jira_data_sources.items():
        try:
            print("start DB: ", jira_name)

            with open("logs.txt", "a") as myfile:
                myfile.write(f"start DB: {jira_name}\n")
                myfile.write(f"start calculate_time_add_sprint\n")
                calculate_time_add_sprint.start(jira_name)

            print("********************start prepare_data_sql********************")
            with open("logs.txt", "a") as myfile:
                myfile.write(f"start prepare_data_sql\n")
            prepare_data_sql.start(jira_name)

            print("********************start add_body_clean_comments********************")
            with open("logs.txt", "a") as myfile:
                myfile.write(f"start add_body_clean_comments\n")
            add_body_clean_comments.start(jira_name)

            with open("logs.txt", "a") as myfile:
                myfile.write(f"start add_columns_main_change\n")
            add_columns_main_change.start(jira_name)

            with open("logs.txt", "a") as myfile:
                myfile.write(f"start delete_no_sprint_no_done\n")
            delete_no_sprint_no_done.start(jira_name)

            with open("logs.txt", "a") as myfile:
                myfile.write(f"start create_combine_columns_summary_description\n")
            create_combine_columns_summary_description.start(jira_name)

            with open("logs.txt", "a") as myfile:
                myfile.write(f"start calculate_ratio_nltk\n")
            calculate_ratio_nltk.start(jira_name)

            with open("logs.txt", "a") as myfile:
                myfile.write(f"start create_feature_lable_table\n")
            create_feature_lable_table.start(jira_name)

            with open("logs.txt", "a") as myfile:
                myfile.write(f"start calculate_features_all_num_bad_issue\n")
            calculate_features_all_num_bad_issue.start(jira_name)

            with open("logs.txt", "a") as myfile:
                myfile.write(f"finish DB:{jira_name}\n\n")

        except Exception as e:
            print(f"Failed {jira_name}")
            print(e)
            with open("logs.txt", "a") as myfile:
                myfile.write(f"Failed {jira_name}\n")
                myfile.write(f"{e}\n\n")
    print("finish")
    with open("logs.txt", "a") as myfile:
        myfile.write(f"finish\n")