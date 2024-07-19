import json

import nltk
import mysql
import pandas as pd
import mysql.connector
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

    data = pd.read_sql(f"SELECT * FROM {dbName}.main_table_os2", con=mysql_con)
    sql_update_columns = f"""UPDATE {dbName}.main_table_os2 SET num_different_words_all_text_sprint_new =%s,
                            num_ratio_words_all_text_sprint_new =%s
                           WHERE (issue_key=%s)"""

    if jira_name == 'Qt':
        init = 5000
    else:
        init = 0

    for i in range(init, len(data)):
        try:
            issue_key = data['issue_key'][i]
            original_text = data['original_summary_description_acceptance_sprint'][i]
            text_last = data['summary_description_acceptance'][i]
            different = nltk.edit_distance(original_text.split(), text_last.split())
            length_text_original = len(original_text.split())
            if length_text_original == 0:
                length_text_original = 1
            ratio = different/length_text_original

            # update the results in the SQL table
            try:
                cursor = mysql_con.cursor()
                cursor.execute(sql_update_columns, (int(different), float(ratio), issue_key))
                mysql_con.commit()
                cursor.close()
            except mysql.connector.IntegrityError:
                print("ERROR: Kumquat already exists!")
            except Exception as e:
                print(f"ERROR: issueKey = {issue_key}\n" + e)
            if i % 100 == 0:
                with open("logs.txt", "a") as myfile:
                    myfile.write(f'{i}\n')
                print(i)
        except Exception as e:
            with open("logs.txt", "a") as myfile:
                myfile.write(f'ERROR: index:{i}\n issue_key: {data["issue_key"][i]}\n error massage: {e}')
            print(i)


if __name__ == "__main__":
    with open('../Source/jira_data_for_instability.json') as f:
        jira_data_sources = json.load(f)

    for jira_name, jira_obj in jira_data_sources.items():
        print("start calculate_ratio_nltk, DB: ", jira_name)
        start(jira_name)
    print("finish to calculate_ratio_nltk")


