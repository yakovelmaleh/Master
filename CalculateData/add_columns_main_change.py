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

    run_query(cursor, mysql_con, f'ALTER TABLE {dbName}.main_table_os ADD COLUMN time_status_close datetime')

    run_query(cursor, mysql_con, f'ALTER TABLE {dbName}.all_changes_os ADD COLUMN time_add_to_sprint datetime')
    run_query(cursor, mysql_con, f'ALTER TABLE {dbName}.all_changes_os ADD COLUMN is_after_sprint int(10)')
    run_query(cursor, mysql_con, f'ALTER TABLE {dbName}.all_changes_os ADD COLUMN time_from_sprint float')
    run_query(cursor, mysql_con, f'ALTER TABLE {dbName}.all_changes_os ADD COLUMN is_after_close INT(10)')

    run_query(cursor, mysql_con, 'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.all_changes_os t1
        INNER JOIN {dbName}.main_table_os t2 ON t1.issue_key = t2.issue_key and (t1.field='summary' or t1.field='description' or 
        t1.field='Acceptance Criteria' or t1.field='sprint' or t1.field='story points' or t1.field='link')
        SET t1.time_add_to_sprint = t2.time_add_to_sprint
        """)

    run_query(cursor, mysql_con, 'SET SQL_SAFE_UPDATES = 0')
    run_query(cursor, mysql_con, f"""
        UPDATE {dbName}.all_changes_os SET is_after_sprint= 
        CASE
            WHEN time_add_to_sprint < created then 1
            ELSE 0
        END
        """)

    run_query(cursor, mysql_con, f'UPDATE {dbName}.all_changes_os'
                      ' SET time_from_sprint= TIMESTAMPDIFF(minute, time_add_to_sprint, created)/60')


if __name__ == '__main__':
    with open('../Source/jira_data_for_instability.json') as f:
        jira_data_sources = json.load(f)

    for jira_name, jira_obj in jira_data_sources.items():
        print("start add_columns_main_change, DB: ", jira_name)
        start(jira_name)
    print("finish to add_columns_main_change")
