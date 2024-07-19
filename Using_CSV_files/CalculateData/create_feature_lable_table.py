import json

import mysql

import Utils.DataBase as DB


def run_query(cursor, mysql_con, query):
    try:
        cursor.execute(query)
        mysql_con.commit()
    except mysql.connector.IntegrityError:
        print("ERROR: Kumquat already exists!")
    except Exception as e:
        print(f"ERROR: query: {query}\n {e}")


def start(jira_name):
    dbName = f"{DB.DB_NAME}_{jira_name.lower()}"
    mysql_con = DB.connectToSpecificDB(dbName)
    cursor = mysql_con.cursor()
    print(f'connected to DB: {DB.DB_NAME}_{jira_name.lower()}')

    # Enforce UTF-8 for the connection
    cursor.execute('SET NAMES utf8mb4')
    cursor.execute("SET CHARACTER SET utf8mb4")
    cursor.execute("SET character_set_connection=utf8mb4")

    """
    #################################################################################################
    /* create new table in the database which include all the relevant features for the model */
    #################################################################################################
    """
    

    run_query(cursor, mysql_con, f""" CREATE TABLE features_labels_table_os AS SELECT issue_key, issue_type, 
    project_key, created, epic_link, has_change_story_point_sprint, summary, description, 
    acceptance_criteria, summary_description_acceptance, original_story_points_sprint, creator, reporter, priority, 
    num_all_changes, story_point, num_bugs_issue_link, num_comments, num_issue_links, num_sprints, 
    num_changes_story_points_new, num_changes_summary_description_acceptance, num_sub_tasks, num_changes_sprint, 
    num_changes_story_points_new_sprint, num_comments_before_sprint, num_comments_after_sprint, 
    num_changes_text_before_sprint, num_changes_story_point_before_sprint, 
    time_add_to_sprint, original_summary_sprint,original_description_sprint, original_acceptance_criteria_sprint,
    num_changes_summary_new_sprint as num_changes_summary_sprint, num_changes_description_new_sprint as 
    num_changes_description_sprint, num_changes_acceptance_criteria_new_sprint as 
    num_changes_acceptance_criteria_sprint, num_different_words_all_text_sprint, num_ratio_words_all_text_sprint_new 
    as num_ratio_words_all_text_sprint FROM {dbName}.main_table_os2; """)

    """
    ########################################################################################################
    /* calculted fields in the feature table (combination of the text fields, number of changes and more) */
    ########################################################################################################
    """
    run_query(cursor, mysql_con, f'Alter table {dbName}.features_labels_table_os add column '
                                 f'original_summary_description_acceptance_sprint MEDIUMTEXT')

    run_query(cursor, mysql_con, f'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.features_labels_table_os SET original_summary_description_acceptance_sprint= 
        CASE
            WHEN original_description_sprint is null then CONCAT(original_summary_sprint, " ", "$end$") 
            ELSE CONCAT(original_summary_sprint, " ", "$end$", " ", original_description_sprint) 
        END
        """)

    run_query(cursor, mysql_con, f'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.features_labels_table_os SET original_summary_description_acceptance_sprint= 
        CASE
            WHEN original_acceptance_criteria_sprint is null then CONCAT(original_summary_description_acceptance_sprint, " ", "$acceptance criteria:$")
            ELSE CONCAT(original_summary_description_acceptance_sprint, " ", "$acceptance criteria:$", " ", original_acceptance_criteria_sprint) 
        END
        """)

    run_query(cursor, mysql_con, f'Alter table {dbName}.features_labels_table_os add column '
                                 f'num_changes_summary_description_acceptance_sprint INT(11)')

    run_query(cursor, mysql_con, f'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.features_labels_table_os SET num_changes_summary_description_acceptance_sprint= 
        CASE
            WHEN num_changes_summary_sprint > 0 or num_changes_description_sprint > 0  or num_changes_acceptance_criteria_sprint > 0 
            then num_changes_summary_sprint + num_changes_description_sprint + num_changes_acceptance_criteria_sprint
            ELSE 0
        END
        """)

    run_query(cursor, mysql_con, f'Alter table {dbName}.features_labels_table_os add column '
                                 f'is_change_text_num_words_1 INT(11)')

    run_query(cursor, mysql_con, f'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.features_labels_table_os SET is_change_text_num_words_1= 
        CASE
            WHEN num_different_words_all_text_sprint >0 and num_changes_summary_description_acceptance_sprint>0 then 1
            ELSE 0
        END
        """)

    run_query(cursor, mysql_con, f'Alter table {dbName}.features_labels_table_os add column '
                                 f'is_change_text_num_words_5 INT(11)')

    run_query(cursor, mysql_con, f'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.features_labels_table_os SET is_change_text_num_words_5= 
        CASE
            WHEN num_different_words_all_text_sprint >=5 and num_changes_summary_description_acceptance_sprint>0 then 1
            ELSE 0
        END
        """)

    run_query(cursor, mysql_con, f'Alter table {dbName}.features_labels_table_os add column '
                                 f'is_change_text_num_words_10 INT(11)')

    run_query(cursor, mysql_con, f'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.features_labels_table_os SET is_change_text_num_words_10= 
        CASE
            WHEN num_different_words_all_text_sprint >=10 and num_changes_summary_description_acceptance_sprint>0 then 1
            ELSE 0
        END
        """)

    run_query(cursor, mysql_con, f'Alter table {dbName}.features_labels_table_os add column '
                                 f'is_change_text_num_words_15 INT(11)')

    run_query(cursor, mysql_con, f'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.features_labels_table_os SET is_change_text_num_words_15= 
        CASE
            WHEN num_different_words_all_text_sprint >=15 and num_changes_summary_description_acceptance_sprint>0 then 1
            ELSE 0
        END
        """)

    run_query(cursor, mysql_con, f'Alter table {dbName}.features_labels_table_os add column '
                                 f'is_change_text_num_words_20 INT(11)')

    run_query(cursor, mysql_con, f'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.features_labels_table_os SET is_change_text_num_words_20= 
        CASE
            WHEN num_different_words_all_text_sprint >=20 and num_changes_summary_description_acceptance_sprint>0 then 1
            ELSE 0
        END
        """)

    run_query(cursor, mysql_con, f'Alter table {dbName}.features_labels_table_os add column '
                                 f'is_change_text_sp_sprint INT(11)')

    run_query(cursor, mysql_con, f'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.features_labels_table_os SET is_change_text_sp_sprint= 
        CASE
            WHEN is_change_text_num_words_5 > 0 or num_changes_story_points_new_sprint > 0 or num_sprints > 1 then 1
            ELSE 0
        END
        """)

    run_query(cursor, mysql_con, f'Alter table {dbName}.features_labels_table_os add column '
                                 f'time_until_add_to_sprint float')

    run_query(cursor, mysql_con, f'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.features_labels_table_os SET time_until_add_to_sprint= 
        TIMESTAMPDIFF(minute, created, time_add_to_sprint)/60
        """)

    run_query(cursor, mysql_con, f'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.features_labels_table_os SET time_until_add_to_sprint= 
        CASE
            WHEN time_until_add_to_sprint is null then 0
            ELSE time_until_add_to_sprint
        END
        """)


if __name__ == '__main__':
    with open('../Source/jira_data_for_instability.json') as f:
        jira_data_sources = json.load(f)

    for jira_name, jira_obj in jira_data_sources.items():
        print("start create_feature_lable_table, DB: ", jira_name)
        start(jira_name)
    print("finish to create_feature_lable_table")
