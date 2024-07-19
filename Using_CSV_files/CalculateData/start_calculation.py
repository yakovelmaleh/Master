import json
import calculate_time_add_sprint
import prepare_data_sql
import add_body_clean_comments
import add_columns_main_change
import delete_no_sprint_no_done
import create_combine_columns_summary_description
import calculate_ratio_nltk
import create_feature_lable_table
import calculate_features_all_num_bad_issue
import Using_CSV_files.Load_Data_From_Jira_To_CSV.SetUpData as SetUpData


def start(path, data_path, jiraName, jira_object):
    # Create the folders!!!!!!!!!!!!!
    print(f"********************start {jiraName}********************")
    print(f"********************start SetUpData********************")

    path_to_save_prefix = f'{path}\\{data_path}\\{jira_name}'
    path_to_save = f'{path_to_save_prefix}\\Downloaded_Data'
    SetUpData.start(path_to_save, jiraName, jira_object)

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
    create_combine_columns_summary_description.start(jira_name)

    print("********************start calculate_ratio_nltk********************")
    calculate_ratio_nltk.start(jira_name)

    print("********************start create_feature_lable_table********************")
    create_feature_lable_table.start(jira_name)

    print("********************start calculate_features_all_num_bad_issue********************")
    calculate_features_all_num_bad_issue.start(jira_name)

    print(f"********************finish {jiraName}********************")


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