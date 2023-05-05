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


def delete_from_other_table(table, cursor, mysql_con, dbName):
    run_query(cursor, mysql_con, 'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        delete 
        from {dbName}.{table}
        where issue_key NOT IN (SELECT m.issue_key
                                FROM {dbName}.main_table_os m)
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
    ###################################################################################
    /* delete all the USI which are no done yet or not related to any sprint  from
    the main table */
    ###################################################################################
    """

    run_query(cursor, mysql_con, f"CREATE TABLE {dbName}.main_table_os2 SELECT * FROM {dbName}.main_table_os")

    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.main_table_os2 SET num_comments_before_sprint = (select count(*)
        from {dbName}.comments_os c1
        where created <= (select time_add_to_sprint 
        from {dbName}.main_table_os c2 
        where c2.issue_key = c1.issue_key))
        """)

    run_query(cursor, mysql_con, 'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        delete 
        from {dbName}.main_table_os2 
        where num_sprints = 0
        """)

    """###################################################################################
    /* delete also from the other tables  */
    ###################################################################################
    

    delete_from_other_table('changes_description_os', cursor, mysql_con, dbName)
    delete_from_other_table('changes_summary_os', cursor, mysql_con, dbName)
    delete_from_other_table('changes_story_points_os', cursor, mysql_con, dbName)
    delete_from_other_table('changes_criteria_os', cursor, mysql_con, dbName)
    delete_from_other_table('changes_criteria_os', cursor, mysql_con, dbName)
    delete_from_other_table('comments_os', cursor, mysql_con, dbName)
    delete_from_other_table('changes_sprint_os', cursor, mysql_con, dbName)
    delete_from_other_table('commits_info_os', cursor, mysql_con, dbName)
    delete_from_other_table('components_os', cursor, mysql_con, dbName)
    delete_from_other_table('fix_versions_os', cursor, mysql_con, dbName)
    delete_from_other_table('sprints_os', cursor, mysql_con, dbName)
    delete_from_other_table('issue_links_os', cursor, mysql_con, dbName)
    delete_from_other_table('names_bugs_issue_links_os', cursor, mysql_con, dbName)
    delete_from_other_table('sab_task_names_os', cursor, mysql_con, dbName)
    delete_from_other_table('labels_os', cursor, mysql_con, dbName)
    delete_from_other_table('versions_os', cursor, mysql_con, dbName)
    delete_from_other_table('all_changes_os', cursor, mysql_con, dbName)
    """


if __name__ == '__main__':
    with open('../Source/jira_data_for_instability_v1_for_Next.json') as f:
        jira_data_sources = json.load(f)

    for jira_name, jira_obj in jira_data_sources.items():
        print("start add_columns_main_change, DB: ", jira_name)
        start(jira_name)
    print("finish to add_columns_main_change")
