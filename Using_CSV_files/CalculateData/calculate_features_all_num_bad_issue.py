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


def addColumn(cursor, mysql_con, dbName, columnName, ratioName, value):
    run_query(cursor, mysql_con,
              f"""
            create table {dbName}.help_cal_features_bad_text select issue_key, created as created2, creator as creator2,
             (select count(*) from {dbName}.features_labels_table_os m
              WHERE (f.creator = m.creator and f.project_key = m.project_key 
                    and f.created > m.created and {value} > 0 )) as num_unusable_text
              from {dbName}.features_labels_table_os f
            """)

    run_query(cursor, mysql_con,
              f'Alter table {dbName}.features_labels_table_os add column {columnName} INT(11)')

    run_query(cursor, mysql_con, f"""
            UPDATE {dbName}.features_labels_table_os t1
            INNER JOIN {dbName}.help_cal_features_bad_text t2 ON t1.issue_key = t2.issue_key 
            SET t1.{columnName} = t2.num_unusable_text
            """)
    run_query(cursor, mysql_con, 'drop table help_cal_features_bad_text')

    run_query(cursor, mysql_con,
              f'Alter table {dbName}.features_labels_table_os add column {ratioName} float')

    run_query(cursor, mysql_con, 'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
            UPDATE {dbName}.features_labels_table_os SET {ratioName}= 
            CASE
                WHEN {columnName} = 0 then 0  
                ELSE {columnName}/num_issues_cretor_prev  
            END
            """)



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
    ###################################################################
    /* create the calculate features num "bad" issues to writer and 
    general num issues to writer for this calculation we will help in 
    more table */
    ###################################################################
    """

    ####################### add table and then combine to feature table #######################

    run_query(cursor, mysql_con, f"""
       create table {dbName}.help_cal_features select issue_key, created as created2, creator as creator2,
        (select count(*) from {dbName}.features_labels_table_os m
            WHERE (f.creator = m.creator and f.project_key = m.project_key 
            and f.created > m.created)) as num_issues
        from {dbName}.features_labels_table_os f
        """)

    run_query(cursor, mysql_con,
              f'Alter table {dbName}.features_labels_table_os add column num_issues_cretor_prev INT')

    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.features_labels_table_os t1
        INNER JOIN {dbName}.help_cal_features t2 ON t1.issue_key = t2.issue_key 
        SET t1.num_issues_cretor_prev = t2.num_issues
        """)
    run_query(cursor, mysql_con, 'drop table help_cal_features')

    addColumn(cursor, mysql_con, dbName, "num_unusable_issues_cretor_prev_text_word_1",
              "num_unusable_issues_cretor_prev_text_word_1_ratio", "is_change_text_num_words_1")

    addColumn(cursor, mysql_con, dbName, "num_unusable_issues_cretor_prev_text_word_5",
              "num_unusable_issues_cretor_prev_text_word_5_ratio", "is_change_text_num_words_5")

    addColumn(cursor, mysql_con, dbName, "num_unusable_issues_cretor_prev_text_word_10",
              "num_unusable_issues_cretor_prev_text_word_10_ratio", "is_change_text_num_words_10")

    addColumn(cursor, mysql_con, dbName, "num_unusable_issues_cretor_prev_text_word_15",
              "num_unusable_issues_cretor_prev_text_word_15_ratio", "is_change_text_num_words_15")

    addColumn(cursor, mysql_con, dbName, "num_unusable_issues_cretor_prev_text_word_20",
              "num_unusable_issues_cretor_prev_text_word_20_ratio", "is_change_text_num_words_20")


if __name__ == '__main__':
    with open('../Source/jira_data_for_instability.json') as f:
        jira_data_sources = json.load(f)

    for jira_name, jira_obj in jira_data_sources.items():
        print("start calculate_features_all_num_bad_issue, DB: ", jira_name)
        start(jira_name)
    print("finish to calculate_features_all_num_bad_issue")
