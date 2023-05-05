import json

import pandas as pd
import mysql.connector
import re
import Utils.DataBase as DB


def start(jira_name):
    dbName = f"{DB.DB_NAME}_{jira_name.lower()}"
    mysql_con = DB.connectToSpecificDB(dbName)
    cursor = mysql_con.cursor()
    print(f'connected to DB: {DB.DB_NAME}_{jira_name.lower()}')

    # Enforce UTF-8 for the connection
    cursor.execute('SET NAMES utf8mb4')
    cursor.execute("SET CHARACTER SET utf8mb4")
    cursor.execute("SET character_set_connection=utf8mb4")

    comments_data = pd.read_sql(f'SELECT * FROM {dbName}.comments_os', con=mysql_con)

    # add new column in the table and clean the text of it
    sql_add_columns_first = f"""alter table {dbName}.comments_os add column clean_comment MEDIUMTEXT;"""
    try:
        cursor = mysql_con.cursor()
        cursor.execute(sql_add_columns_first)
        mysql_con.commit()
        cursor.close()
    except:
        ""

    sql_add_columns = f"""UPDATE {dbName}.comments_os SET clean_comment =%s
                       WHERE (issue_key=%s and chronological_number=%s)"""

    for i in range(0, len(comments_data)):
        body = comments_data['body'][i]
        issue_key = comments_data['issue_key'][i]
        chronological_number = comments_data['chronological_number'][i]
        if body is not None:
            clean_body = re.sub(r'<.+?>', "", body)
            clean_body = re.sub(r'&nbsp;', " ", clean_body)
            clean_body = re.sub(r"http\S+", "URL", clean_body)
        else:
            clean_body = body
        mycursor = mysql_con.cursor()
        try:
            mycursor.execute(sql_add_columns, (clean_body, issue_key, int(chronological_number)))
            mysql_con.commit()
            mycursor.close()
        except mysql.connector.IntegrityError:
            print("ERROR: Kumquat already exists!")
        except Exception as e:
            print(f"ERROR: issueKey: {issue_key}\n {e}")
        if i % 100 == 0:
            with open("logs.txt", "a") as myfile:
                myfile.write(f'{i}\n')
            print(i)



if __name__ == '__main__':
    jira_name = 'Hyperledger'
    start(jira_name)
    

