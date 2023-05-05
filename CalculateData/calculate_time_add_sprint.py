import json

import pandas as pd
import time
import mysql.connector
import datetime
import pandasql as ps
import Utils.DataBase as DB


def add_column_time_add_to_sprint(mysql_con, sql_query, main_table, change_sprint, sprints):
    '''
    functio which calculate the time that the USI enter to sprint
    input: sql connection, the sql query which update the database with the results, the main table with the data, the change sprint table, the sprint table
    there is no ouptut, the function calculate the time and write it to the new column in main table
    '''
    main_table["time_add_to_sprint"] = ""
    for i in range(0, len(main_table)):
        issue_name = main_table['issue_key'][i]
        change_sprint_issue = (ps.sqldf("""select issue_key, from_string, to_string, different_time_from_creat, is_first_setup, chronological_number, 
                    created as created_change_sprint
                    from change_sprint
                    where different_time_from_creat = (select min(different_time_from_creat) from change_sprint where issue_key = '{}')
                    and (issue_key = '{}')""".format(issue_name, issue_name), (locals())))
        sprint_issue = (ps.sqldf("""select sprint_name
                    from sprints
                    where (issue_key = '{}')""".format(issue_name), (locals())))
        if len(sprint_issue) == 0:
            time_add_to_sprint = None
        else:
            if len(change_sprint_issue) == 0:
                if sprint_issue['sprint_name'][0] is not None:
                    time_add_to_sprint = datetime.datetime.strptime(str(main_table['created'][i]), '%Y-%m-%d %H:%M:%S')
                else:
                    time_add_to_sprint = None
            else:
                if change_sprint_issue['issue_key'][0] is None and sprint_issue['sprint_name'][0] is None:
                    time_add_to_sprint = None
                elif change_sprint_issue['issue_key'][0] is None and sprint_issue['sprint_name'][0] is not None:
                    time_add_to_sprint = datetime.datetime.strptime(str(main_table['created'][i]), '%Y-%m-%d %H:%M:%S')
                elif change_sprint_issue['issue_key'][0] is not None and sprint_issue['sprint_name'][0] is not None:
                    if change_sprint_issue['is_first_setup'][0] == 1:
                        time_add_to_sprint = datetime.datetime.strptime(change_sprint_issue['created_change_sprint'][0], '%Y-%m-%d %H:%M:%S.%f')
                    else:
                        time_add_to_sprint = datetime.datetime.strptime(str(main_table['created'][i]), '%Y-%m-%d %H:%M:%S')
                elif change_sprint_issue['issue_key'][0] is not None and sprint_issue['sprint_name'][0] is None:
                    time_add_to_sprint = None
        main_table.at[i, 'time_add_to_sprint'] = time_add_to_sprint

        if i % 100 == 0:
            with open("logs.txt", "a") as myfile:
                myfile.write(f'{i}\n')
            print(i)

        mycursor = mysql_con.cursor()
        try:
            mycursor.execute(sql_query, (time_add_to_sprint, issue_name))
            mysql_con.commit()
            mycursor.close()
        except mysql.connector.IntegrityError:
            print("ERROR: Kumquat already exists!")
        except Exception as e:
            print(f"ERROR: IssueKey: {issue_name} \n",e)
            

def start(jira_name):
    dbName = f"{DB.DB_NAME}_{jira_name.lower()}"
    mysql_con = DB.connectToSpecificDB(dbName)
    cursor = mysql_con.cursor()
    print(f'connected to DB: {DB.DB_NAME}_{jira_name.lower()}')

    # Enforce UTF-8 for the connection
    cursor.execute('SET NAMES utf8mb4')
    cursor.execute("SET CHARACTER SET utf8mb4")
    cursor.execute("SET character_set_connection=utf8mb4")

    main_data = pd.read_sql(f'SELECT * FROM {dbName}.main_table_os', con=mysql_con)
    changes_sprint = pd.read_sql(f'SELECT * FROM {dbName}.changes_sprint_os', con=mysql_con)
    sprints = pd.read_sql(f'SELECT * FROM {dbName}.sprints_os', con=mysql_con)
    change_status = pd.read_sql(f"SELECT * FROM {dbName}.all_changes_os where field = 'status'", con=mysql_con)

    sql_add_time_add_to_sprint = f"UPDATE {dbName}.main_table_os SET time_add_to_sprint =%s WHERE (issue_key=%s)"

    add_column_time_add_to_sprint(mysql_con, sql_add_time_add_to_sprint, main_data, changes_sprint, sprints)


if __name__ == '__main__':
    with open('../Source/jira_data_for_instability.json') as f:
        jira_data_sources = json.load(f)

    for jira_name, jira_obj in jira_data_sources.items():
        print("start calculate time add spint, DB: ", jira_name)
        start(jira_name)
    print("finish to calculate time add spint")






