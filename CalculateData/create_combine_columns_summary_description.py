import json

import mysql

import Utils.DataBase as DB


def run_query(cursor,mysql_con, query):
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

    run_query(cursor, mysql_con,
              f'Alter table {dbName}.main_table_os2 add column summary_description_acceptance MEDIUMTEXT')

    run_query(cursor, mysql_con,
              f'Alter table {dbName}.main_table_os2 add column num_different_words_all_text_sprint_new int(11)'
              f' DEFAULT NULL')



    run_query(cursor, mysql_con, 'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.main_table_os2 SET summary_description_acceptance= 
        CASE
            WHEN {dbName}.main_table_os2.description is null then CONCAT(summary, " ", "$end$") 
            ELSE CONCAT(summary, " ", "$end$", " ", {dbName}.main_table_os2.description) 
        END
        """)

    run_query(cursor, mysql_con, 'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.main_table_os2 SET summary_description_acceptance= 
        CASE
            WHEN acceptance_criteria is null then CONCAT(summary_description_acceptance, " ", "$acceptance criteria:$")
            ELSE CONCAT(summary_description_acceptance, " ", "$acceptance criteria:$", " ", acceptance_criteria) 
        END
        """)

    """
    ###################################################################
    /* create new column which include the combination of the original
    summary test field and description text field to 1 text field */
    ###################################################################
    """

    run_query(cursor, mysql_con, f'Alter table {dbName}.main_table_os2 add column '
                                 f'original_summary_description_acceptance MEDIUMTEXT')

    run_query(cursor, mysql_con, 'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.main_table_os2 SET original_summary_description_acceptance= 
        CASE
            WHEN original_description is null then CONCAT(original_summary, " ", "$end$") 
            ELSE CONCAT(original_summary, " ", "$end$", " ", original_description) 
        END
        """)

    run_query(cursor, mysql_con, 'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.main_table_os2 SET original_summary_description_acceptance= 
        CASE
            WHEN original_acceptance_criteria is null then CONCAT(original_summary_description_acceptance, " ", "$acceptance criteria:$")
            ELSE CONCAT(original_summary_description_acceptance, " ", "$acceptance criteria:$", " ", original_acceptance_criteria) 
        END
        """)

    """
    ###################################################################
    /* create new column which calculated the number of changes in the 
    text fields */
    ###################################################################
    """
    run_query(cursor, mysql_con,
              f'Alter table {dbName}.main_table_os2 add column num_changes_summary_description_acceptance INT(11)')

    run_query(cursor, mysql_con, 'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.main_table_os2 SET num_changes_summary_description_acceptance= 
        CASE
            WHEN num_changes_summary_new > 0 or num_changes_description_new > 0  or num_changes_acceptance_criteria_new > 0
            then num_changes_summary_new + num_changes_description_new + num_changes_acceptance_criteria_new
            ELSE 0
        END
        """)

    """
    ###################################################################
    /* create new column which indicates if there were changes in the 
    text fields */
    ###################################################################
    """
    run_query(cursor, mysql_con,
              f'Alter table {dbName}.main_table_os2 add column has_changes_summary_description_acceptance INT(11)')

    run_query(cursor, mysql_con, 'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.main_table_os2 SET has_changes_summary_description_acceptance= 
        CASE
            WHEN num_changes_summary_description_acceptance > 0  then 1
            ELSE 0
        END
        """)

    """
    ###################################################################
    /* create new column which calculated the number of words in the 
    text fields */
    ###################################################################
    """
    run_query(cursor, mysql_con,
              f'Alter table {dbName}.main_table_os2 add column num_different_words_all_text INT(11)')

    run_query(cursor, mysql_con, 'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.main_table_os2 SET num_different_words_all_text = different_words_minus_summary + 
        different_words_plus_summary + different_words_minus_description + different_words_plus_description + 
        different_words_minus_acceptance_criteria + different_words_plus_acceptance_criteria
        """)

    """
    ###################################################################
    /* create new column which calculate the ratio difference
    in words between the first version of the text and the last */
    ###################################################################
    """
    run_query(cursor, mysql_con,
              f'Alter table {dbName}.main_table_os2 add column num_different_ratio_words_all_text FLOAT')

    run_query(cursor, mysql_con, 'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.main_table_os2 SET num_different_ratio_words_all_text = 
        case
            when original_acceptance_criteria is null and original_description is null then different_words_ratio_all_summary
            when original_acceptance_criteria is null and original_description is not null and (
            (LENGTH(original_summary) - LENGTH(replace(original_summary, ' ', '')))+ 
            (LENGTH(original_description) - LENGTH(replace(original_description, ' ', '')))) <> 0 then (different_words_ratio_all_summary*(LENGTH(original_summary) - LENGTH(replace(original_summary, ' ', '')))
            + different_words_ratio_all_description*(LENGTH(original_description) - LENGTH(replace(original_description, ' ', ''))))/(
            (LENGTH(original_summary) - LENGTH(replace(original_summary, ' ', '')))+ 
            (LENGTH(original_description) - LENGTH(replace(original_description, ' ', ''))))
            when original_acceptance_criteria is null and original_description is not null then (different_words_ratio_all_summary*(LENGTH(original_summary) - LENGTH(replace(original_summary, ' ', '')))
            + different_words_ratio_all_description*(LENGTH(original_description) - LENGTH(replace(original_description, ' ', ''))))
            when original_acceptance_criteria is not null and original_description is null and (
            (LENGTH(original_summary) - LENGTH(replace(original_summary, ' ', '')))+ 
            (LENGTH(original_acceptance_criteria) - LENGTH(replace(original_acceptance_criteria, ' ', '')))) <> 0 then (different_words_ratio_all_summary*(LENGTH(original_summary) - LENGTH(replace(original_summary, ' ', '')))
            + different_words_ratio_all_acceptance_criteria*(LENGTH(original_acceptance_criteria) - LENGTH(replace(original_acceptance_criteria, ' ', ''))))/(
            (LENGTH(original_summary) - LENGTH(replace(original_summary, ' ', '')))+ 
            (LENGTH(original_acceptance_criteria) - LENGTH(replace(original_acceptance_criteria, ' ', ''))))
            when original_acceptance_criteria is not null and original_description is null then (different_words_ratio_all_summary*(LENGTH(original_summary) - LENGTH(replace(original_summary, ' ', '')))
            + different_words_ratio_all_acceptance_criteria*(LENGTH(original_acceptance_criteria) - LENGTH(replace(original_acceptance_criteria, ' ', ''))))
            when (
            (LENGTH(original_summary) - LENGTH(replace(original_summary, ' ', '')))+ 
            (LENGTH(original_description) - LENGTH(replace(original_description, ' ', '')))+
            (LENGTH(original_acceptance_criteria) - LENGTH(replace(original_acceptance_criteria, ' ', '')))) <> 0 then (different_words_ratio_all_summary*(LENGTH(original_summary) - LENGTH(replace(original_summary, ' ', '')))
            + different_words_ratio_all_description*(LENGTH(original_description) - LENGTH(replace(original_description, ' ', '')))
            + different_words_ratio_all_acceptance_criteria*(LENGTH(original_acceptance_criteria) - LENGTH(replace(original_acceptance_criteria, ' ', ''))))/(
            (LENGTH(original_summary) - LENGTH(replace(original_summary, ' ', '')))+ 
            (LENGTH(original_description) - LENGTH(replace(original_description, ' ', '')))+
            (LENGTH(original_acceptance_criteria) - LENGTH(replace(original_acceptance_criteria, ' ', ''))))
            else (different_words_ratio_all_summary*(LENGTH(original_summary) - LENGTH(replace(original_summary, ' ', '')))
            + different_words_ratio_all_description*(LENGTH(original_description) - LENGTH(replace(original_description, ' ', '')))
            + different_words_ratio_all_acceptance_criteria*(LENGTH(original_acceptance_criteria) - LENGTH(replace(original_acceptance_criteria, ' ', ''))))
            
        end
        """)

    run_query(cursor, mysql_con, f'Alter table {dbName}.main_table_os2 add column '
                                 f'original_summary_description_acceptance_sprint MEDIUMTEXT')

    run_query(cursor, mysql_con, 'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.main_table_os2 SET original_summary_description_acceptance_sprint= 
        CASE
            WHEN original_description_sprint is null then CONCAT(original_summary_sprint, " ", "$end$") 
            ELSE CONCAT(original_summary_sprint, " ", "$end$", " ", original_description_sprint) 
        END
        """)

    run_query(cursor, mysql_con, 'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.main_table_os2 SET original_summary_description_acceptance_sprint= 
        CASE
            WHEN original_acceptance_criteria_sprint is null then CONCAT(original_summary_description_acceptance_sprint, " ", "$acceptance criteria:$")
            ELSE CONCAT(original_summary_description_acceptance_sprint, " ", "$acceptance criteria:$", " ", original_acceptance_criteria_sprint) 
        END
        """)

    run_query(cursor, mysql_con, f'Alter table {dbName}.main_table_os2 add column '
                      f'num_changes_summary_description_acceptance_sprint INT(11)')

    run_query(cursor, mysql_con, 'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.main_table_os2 SET num_changes_summary_description_acceptance_sprint= 
        CASE
            WHEN num_changes_summary_new_sprint > 0 or num_changes_description_new_sprint > 0  or num_changes_acceptance_criteria_new_sprint > 0 
            then num_changes_summary_new_sprint + num_changes_description_new_sprint + num_changes_acceptance_criteria_new_sprint
            ELSE 0
        END
        """)

    run_query(cursor, mysql_con, f'Alter table {dbName}.main_table_os2 add column '
                      f'has_changes_summary_description_acceptance_sprint INT(11)')

    run_query(cursor, mysql_con, 'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.main_table_os2 SET has_changes_summary_description_acceptance_sprint= 
        CASE
            WHEN num_changes_summary_description_acceptance_sprint > 0  then 1
            ELSE 0
        END
        """)

    run_query(cursor, mysql_con, f'Alter table {dbName}.main_table_os2 add column num_different_words_all_text_sprint INT(11)')

    run_query(cursor, mysql_con, 'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.main_table_os2 SET num_different_words_all_text_sprint = different_words_minus_summary_sprint + 
        different_words_plus_summary_sprint + different_words_minus_description_sprint + 
        different_words_plus_description_sprint + different_words_minus_acceptance_criteria_sprint +
         different_words_plus_acceptance_criteria_sprint
        """)

    run_query(cursor, mysql_con, f'Alter table {dbName}.main_table_os2 add column num_different_ratio_words_all_text_sprint FLOAT')

    run_query(cursor, mysql_con, 'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
    UPDATE main_table_os2 SET num_different_ratio_words_all_text_sprint = 
        case
            when original_acceptance_criteria_sprint is null and original_description_sprint is null then different_words_ratio_all_summary_sprint
            when original_acceptance_criteria_sprint is null and original_description_sprint is not null and (
            (LENGTH(original_summary_sprint) - LENGTH(replace(original_summary_sprint, ' ', '')))+ 
            (LENGTH(original_description_sprint) - LENGTH(replace(original_description_sprint, ' ', '')))) <> 0 then 
            (different_words_ratio_all_summary_sprint*(LENGTH(original_summary_sprint) - 
            LENGTH(replace(original_summary_sprint, ' ', '')))
            + different_words_ratio_all_description_sprint*(LENGTH(original_description_sprint) - 
            LENGTH(replace(original_description_sprint, ' ', ''))))/(
            (LENGTH(original_summary_sprint) - LENGTH(replace(original_summary_sprint, ' ', '')))+ 
            (LENGTH(original_description_sprint) - LENGTH(replace(original_description_sprint, ' ', ''))))
                when original_acceptance_criteria_sprint is null and original_description_sprint is not null then 
                (different_words_ratio_all_summary_sprint*(LENGTH(original_summary_sprint) - 
                LENGTH(replace(original_summary_sprint, ' ', '')))
            + different_words_ratio_all_description_sprint*(LENGTH(original_description_sprint) - 
            LENGTH(replace(original_description_sprint, ' ', ''))))
            when original_acceptance_criteria_sprint is not null and original_description_sprint is null and (
            (LENGTH(original_summary_sprint) - LENGTH(replace(original_summary_sprint, ' ', '')))+ 
            (LENGTH(original_acceptance_criteria_sprint) - 
            LENGTH(replace(original_acceptance_criteria_sprint, ' ', '')))) <> 0 then 
            (different_words_ratio_all_summary_sprint*(LENGTH(original_summary_sprint) - 
            LENGTH(replace(original_summary_sprint, ' ', '')))
            + different_words_ratio_all_acceptance_criteria_sprint*(LENGTH(original_acceptance_criteria_sprint) - 
            LENGTH(replace(original_acceptance_criteria_sprint, ' ', ''))))/(
            (LENGTH(original_summary_sprint) - LENGTH(replace(original_summary_sprint, ' ', '')))+ 
            (LENGTH(original_acceptance_criteria_sprint) - 
            LENGTH(replace(original_acceptance_criteria_sprint, ' ', ''))))
            when original_acceptance_criteria_sprint is not null and original_description_sprint is null then 
            (different_words_ratio_all_summary_sprint*(LENGTH(original_summary_sprint) - 
            LENGTH(replace(original_summary_sprint, ' ', '')))
            + different_words_ratio_all_acceptance_criteria_sprint*(LENGTH(original_acceptance_criteria_sprint) - 
            LENGTH(replace(original_acceptance_criteria_sprint, ' ', ''))))
            when (
            (LENGTH(original_summary_sprint) - LENGTH(replace(original_summary_sprint, ' ', '')))+ 
            (LENGTH(original_description_sprint) - LENGTH(replace(original_description_sprint, ' ', '')))+
            (LENGTH(original_acceptance_criteria_sprint) - 
            LENGTH(replace(original_acceptance_criteria_sprint, ' ', '')))) <> 0 then 
            (different_words_ratio_all_summary_sprint*(LENGTH(original_summary_sprint) - 
            LENGTH(replace(original_summary_sprint, ' ', '')))
            + different_words_ratio_all_description_sprint*(LENGTH(original_description_sprint) - 
            LENGTH(replace(original_description_sprint, ' ', '')))
            + different_words_ratio_all_acceptance_criteria_sprint*(LENGTH(original_acceptance_criteria_sprint) - 
            LENGTH(replace(original_acceptance_criteria_sprint, ' ', ''))))/(
            (LENGTH(original_summary_sprint) - LENGTH(replace(original_summary_sprint, ' ', '')))+ 
            (LENGTH(original_description_sprint) - LENGTH(replace(original_description_sprint, ' ', '')))+
            (LENGTH(original_acceptance_criteria_sprint) - 
            LENGTH(replace(original_acceptance_criteria_sprint, ' ', ''))))
            else (different_words_ratio_all_summary_sprint*(LENGTH(original_summary_sprint) - 
            LENGTH(replace(original_summary_sprint, ' ', '')))
            + different_words_ratio_all_description_sprint*(LENGTH(original_description_sprint) - 
            LENGTH(replace(original_description_sprint, ' ', '')))
            + different_words_ratio_all_acceptance_criteria_sprint*(LENGTH(original_acceptance_criteria_sprint) - 
            LENGTH(replace(original_acceptance_criteria_sprint, ' ', ''))))
            
        end;
        """)

    run_query(cursor, mysql_con,
              f'Alter table {dbName}.main_table_os2 add column num_ratio_words_all_text_sprint_new float DEFAULT NULL')

    run_query(cursor, mysql_con,
              f'Alter table {dbName}.main_table_os2 add column num_changes_text_before_sprint INT')

    run_query(cursor, mysql_con, 'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.main_table_os2 SET num_changes_text_before_sprint =
         (num_changes_summary_description_acceptance-num_changes_summary_description_acceptance_sprint);
        """)

    run_query(cursor, mysql_con,
              f'Alter table {dbName}.main_table_os2 add column num_changes_story_point_before_sprint INT')

    run_query(cursor, mysql_con, 'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.main_table_os2 SET num_changes_story_point_before_sprint =
         (num_changes_story_points_new-num_changes_story_points_new_sprint);
        """)

    cursor.close()
    mysql_con.close()


if __name__ == '__main__':
    with open('../Source/jira_data_for_instability.json') as f:
        jira_data_sources = json.load(f)

    for jira_name, jira_obj in jira_data_sources.items():
        print("start create_combine_columns_summary_description, DB: ", jira_name)
        start(jira_name)
    print("finish to create_combine_columns_summary_description")
