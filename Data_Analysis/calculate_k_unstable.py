import json

import Utils.DataBase as DB
import pandas as pd


def start(jira_name):
    # connect to SQL && Create a cursor
    dbName = f"{DB.DB_NAME}_{jira_name.lower()}"
    mysql_con = DB.connectToSpecificDB(dbName)

    cursor = mysql_con.cursor()
    print(f'connected to DB: {DB.DB_NAME}_{jira_name.lower()}')

    output = {
        'Dataset': jira_name
    }

    # total User Stories
    cursor.execute(f"SELECT count(*) FROM {DB.DB_NAME}_{jira_name.lower()}.features_labels_table_os")
    result = cursor.fetchall()

    output['Total'] = result[0][0]
    cursor.reset()

    sql_query = f"SELECT count(*) FROM {DB.DB_NAME}_{jira_name.lower()}.features_labels_table_os" \
                f" where is_change_text_num_words_5 = 1"

    # 5 unstable
    cursor.execute(sql_query)
    result = cursor.fetchall()
    output['5_unstable'] = result[0][0]
    cursor.reset()

    sql_query = f"SELECT count(*) FROM {DB.DB_NAME}_{jira_name.lower()}.features_labels_table_os" \
                f" where is_change_text_num_words_10 = 1"

    # 10 unstable
    cursor.execute(sql_query)
    result = cursor.fetchall()
    output['10_unstable'] = result[0][0]
    cursor.reset()

    sql_query = f"SELECT count(*) FROM {DB.DB_NAME}_{jira_name.lower()}.features_labels_table_os" \
                f" where is_change_text_num_words_15 = 1"

    # 15 unstable
    cursor.execute(sql_query)
    result = cursor.fetchall()
    output['15_unstable'] = result[0][0]
    cursor.reset()

    sql_query = f"SELECT count(*) FROM {DB.DB_NAME}_{jira_name.lower()}.features_labels_table_os" \
                f" where is_change_text_num_words_20 = 1"

    # 20 unstable
    cursor.execute(sql_query)
    result = cursor.fetchall()
    output['20_unstable'] = result[0][0]
    cursor.close()

    output = pd.DataFrame([output.values()], columns=output.keys())

    return output


if __name__ == '__main__':
    output = pd.DataFrame(columns=['Dataset', 'Total', '5_unstable', '10_unstable', '15_unstable', '20_unstable'])
    d = start('Apache')

    output = pd.concat([output, d], ignore_index=True)

    with open('../Source/jira_data_for_instability_cluster.json') as f:
        jira_data_sources = json.load(f)

    print('START ALL')
    for jira_name, jira_obj in jira_data_sources.items():
        print("start: ", jira_name)
        try:
            d = start(jira_name)
            output = pd.concat([output, d], ignore_index=True)
        except Exception as e:
            print(e)

    output.to_csv('k_unstable_division.csv')