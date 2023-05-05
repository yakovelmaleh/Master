import json
import Utils.DataBase as DB

import pandas as pd
import requests
import time
import math
import mysql.connector
import difflib
import datetime
import re
import pandasql as ps
import Utils.DataBase as DB
import sqldf


# add columns in the changes table of time since first updated
"""
        a = main_data[main_data.issue_key == issue_name]['time_add_to_sprint']
        b = change_summary[change_summary.issue_key == issue_name][change_summary.different_time_from_creat > 1][
            change_summary.created > a.time_add_to_sprint]
        b = main_data.query(f'issue_key == "{issue_name}"')
"""

def add_cal_columns_(mysql_con, sql_add_columns, main_data, change_summary, change_description, change_story_point,
                     changes_acceptance, comments, dbName):
    """
    function who add columns of original summary and original description and num_changes_summary_new and
    num_changes_description_new (if change is in the first hour and distance is less than 10 so num changes = 0
    and original description  = description.
    input- sql connection, sql query, the neseccary tables with the data and indicator of looking on sprint or status (True means sprint, the second not in use)
    """

    init_value = 0
    if dbName == 'data_base_os_apache':
        init_value = 7300
    if dbName == 'data_base_os_qt':
        init_value = 5000
    for i in range(init_value, len(main_data)):
        issue_name = main_data['issue_key'][i]
        try:
            # summary
            change_sum_issue_sprint = (ps.sqldf(f"""select from_string, different_time_from_creat, 
                            num_different_word_minus_last, num_different_word_plus_last
                            from change_summary where different_time_from_creat = (select min(different_time_from_creat) 
                            from change_summary where issue_key = '{issue_name}' and different_time_from_creat > 1 
                            and created > (select time_add_to_sprint from main_data where issue_key = '{issue_name}'))
                            and (issue_key = '{issue_name}')""", (locals())))

            change_sum_issue = (ps.sqldf("""select from_string, different_time_from_creat, 
                            num_different_word_minus_last, num_different_word_plus_last
                            from change_summary where   different_time_from_creat = (select min(different_time_from_creat) 
                            from change_summary where issue_key = '{}' and different_time_from_creat > 1)
                            and (issue_key = '{}')""".format(issue_name, issue_name), (locals())))

            if len(change_sum_issue_sprint) == 0 or change_sum_issue_sprint['from_string'][0] is None:
                original_summary_sprint = main_data['summary'][i]
                num_changes_summary_new_sprint = 0
                num_different_word_minus_last_summary_new_sprint = 0
                num_different_word_plus_last_summary_new_sprint = 0
            else:
                original_summary_sprint = change_sum_issue_sprint['from_string'][0]
                num_different_word_minus_last_summary_new_sprint =\
                    change_sum_issue_sprint['num_different_word_minus_last'][0]
                num_different_word_plus_last_summary_new_sprint =\
                    change_sum_issue_sprint['num_different_word_plus_last'][0]
                num_changes_summary_new_sprint = (ps.sqldf("""select count(*) as count from change_summary
                                                        where different_time_from_creat > 1 
                                        and created > (select time_add_to_sprint from main_data where issue_key = '{}')
                                            and (issue_key = '{}')""".format(issue_name, issue_name), (locals())))
                num_changes_summary_new_sprint = num_changes_summary_new_sprint['count'][0]

            if len(change_sum_issue) == 0 or change_sum_issue['from_string'][0] is None:
                original_summary = main_data['summary'][i]
                num_changes_summary_new = 0
                num_different_word_minus_last_summary_new = 0
                num_different_word_plus_last_summary_new = 0
            else:
                original_summary = change_sum_issue['from_string'][0]
                num_different_word_minus_last_summary_new = change_sum_issue['num_different_word_minus_last'][0]
                num_different_word_plus_last_summary_new = change_sum_issue['num_different_word_plus_last'][0]
                num_changes_summary_new = (ps.sqldf("""select count(*) as count
                                    from change_summary
                                    where different_time_from_creat > 1
                                    and (issue_key = '{}')""".format(issue_name), (locals())))
                num_changes_summary_new = num_changes_summary_new['count'][0]

            # description
            change_des_issue_sprint = (ps.sqldf("""select from_string, different_time_from_creat, 
                    num_different_word_minus_last, num_different_word_plus_last
                    from change_description where different_time_from_creat = (select min(different_time_from_creat) 
                    from change_description where issue_key = '{}' and different_time_from_creat > 1
                    and is_first_setup = 0 and created > (select time_add_to_sprint from main_data where issue_key = '{}'))
                     and (issue_key = '{}')""".format(issue_name, issue_name, issue_name), (locals())))
            change_des_issue = (ps.sqldf("""select from_string, different_time_from_creat, 
                            num_different_word_minus_last, num_different_word_plus_last
                            from change_description where different_time_from_creat = (select min(different_time_from_creat) 
                            from change_description where issue_key = '{}' and different_time_from_creat > 1 
                            and is_first_setup = 0) and (issue_key = '{}')""".format(issue_name, issue_name), (locals())))

            if len(change_des_issue_sprint) == 0 or change_des_issue_sprint['from_string'][0] is None:
                original_description_sprint = main_data['description'][i]
                num_changes_description_new_sprint = 0
                num_different_word_minus_last_description_new_sprint = 0
                num_different_word_plus_last_description_new_sprint = 0
            else:
                original_description_sprint = change_des_issue_sprint['from_string'][0]
                num_different_word_minus_last_description_new_sprint = \
                    change_des_issue_sprint['num_different_word_minus_last'][0]
                num_different_word_plus_last_description_new_sprint = \
                    change_des_issue_sprint['num_different_word_plus_last'][0]
                # sprint
                num_changes_description_new_sprint = (ps.sqldf("""select count(*) as count from change_description
                                        where different_time_from_creat > 1 
                                        and created > (select time_add_to_sprint from main_data where issue_key = '{}')
                                         and (issue_key = '{}')""".format(issue_name, issue_name), (locals())))
                num_changes_description_new_sprint = num_changes_description_new_sprint['count'][0]

            if len(change_des_issue) == 0 or change_des_issue['from_string'][0] is None:
                original_description = main_data['description'][i]
                num_changes_description_new = 0
                num_different_word_minus_last_description_new = 0
                num_different_word_plus_last_description_new = 0
            else:
                original_description = change_des_issue['from_string'][0]
                num_different_word_minus_last_description_new = change_des_issue['num_different_word_minus_last'][0]
                num_different_word_plus_last_description_new = change_des_issue['num_different_word_plus_last'][0]
                # no sprint
                num_changes_description_new = (ps.sqldf("""select count(*) as count from change_description
                                                        where different_time_from_creat > 1
                                                        and (issue_key = '{}')""".format(issue_name), (locals())))
                num_changes_description_new = num_changes_description_new['count'][0]

            # story point
            change_sto_issue_sprint = (ps.sqldf("""select from_string, different_time_from_creat
                                from change_story_point
                                where different_time_from_creat = (select min(different_time_from_creat) 
                                from change_story_point where issue_key = '{}'
                                and different_time_from_creat > 1 and is_first_setup = 0 
                                and created > (select time_add_to_sprint from main_data where issue_key = '{}'))
                                and (issue_key = '{}')""".format(issue_name, issue_name,
                                                                 issue_name), (locals())))

            change_sto_issue = (ps.sqldf("""select from_string, different_time_from_creat
                                        from change_story_point
                                        where different_time_from_creat = (select min(different_time_from_creat) 
                                        from change_story_point where issue_key = '{}' and
                                        different_time_from_creat > 1 and is_first_setup = 0)
                                        and (issue_key = '{}')""".format(issue_name, issue_name), (locals())))

            if len(change_sto_issue_sprint) == 0 or change_sto_issue_sprint['from_string'][0] is None:
                original_story_points_sprint = main_data['story_point'][i]
                num_changes_story_points_new_sprint = 0
            else:
                original_story_points_sprint = change_sto_issue_sprint['from_string'][0]
                num_changes_story_points_new_sprint = (ps.sqldf("""select count(*) as count
                                                            from change_story_point
                                where different_time_from_creat > 1 
                                and created > (select time_add_to_sprint from main_data where issue_key = '{}')
                                and (issue_key = '{}')""".format(issue_name, issue_name), (locals())))
                num_changes_story_points_new_sprint = num_changes_story_points_new_sprint['count'][0]

            if len(change_sto_issue) == 0 or change_sto_issue['from_string'][0] is None:
                original_story_points = main_data['story_point'][i]
                num_changes_story_points_new = 0
            else:
                original_story_points = change_sto_issue['from_string'][0]
                num_changes_story_points_new = (ps.sqldf("""select count(*) as count
                                        from change_story_point where different_time_from_creat > 1
                                        and (issue_key = '{}')""".format(issue_name), (locals())))
                num_changes_story_points_new = num_changes_story_points_new['count'][0]

            try:
                if math.isnan(float(original_story_points_sprint)):
                    original_story_points_sprint = None
                else:
                    original_story_points_sprint = float(original_story_points_sprint)
            except TypeError:
                original_story_points_sprint = None
            try:
                if math.isnan(float(original_story_points)):
                    original_story_points = None
                else:
                    original_story_points = float(original_story_points)
            except TypeError:
                original_story_points = None

            # changes_acceptance
            change_acce_issue_sprint = (ps.sqldf("""select from_string, different_time_from_creat, 
                            num_different_word_minus_last, num_different_word_plus_last
                            from changes_acceptance
                            where different_time_from_creat = (select min(different_time_from_creat) 
                            from changes_acceptance where issue_key = '{}'
                            and different_time_from_creat > 1 
                            and created > (select time_add_to_sprint from main_data where issue_key = '{}'))
                            and (issue_key = '{}')""".format(issue_name, issue_name, issue_name), (locals())))

            change_acce_issue = (ps.sqldf("""select from_string, different_time_from_creat, 
                                        num_different_word_minus_last, num_different_word_plus_last
                                        from changes_acceptance
                                        where different_time_from_creat = (select min(different_time_from_creat) 
                                        from changes_acceptance where issue_key = '{}'
                                        and different_time_from_creat > 1)
                                        and (issue_key = '{}')""".format(issue_name, issue_name), (locals())))

            if len(change_acce_issue_sprint) == 0:
                original_acceptance_sprint = main_data['acceptance_criteria'][i]
                num_changes_acceptance_new_sprint = 0
                num_different_word_minus_last_acceptance_criteria_new_sprint = 0
                num_different_word_plus_last_acceptance_criteria_new_sprint = 0
            elif change_acce_issue_sprint['from_string'][0] is None:
                original_acceptance_sprint = main_data['acceptance_criteria'][i]
                num_changes_acceptance_new_sprint = 0
                num_different_word_minus_last_acceptance_criteria_new_sprint = 0
                num_different_word_plus_last_acceptance_criteria_new_sprint = 0
            else:
                original_acceptance_sprint = change_acce_issue_sprint['from_string'][0]
                num_different_word_minus_last_acceptance_criteria_new_sprint = \
                    change_acce_issue_sprint['num_different_word_minus_last'][0]
                num_different_word_plus_last_acceptance_criteria_new_sprint = \
                    change_acce_issue_sprint['num_different_word_plus_last'][0]
                num_changes_acceptance_new_sprint = (ps.sqldf("""select count(*) as count from changes_acceptance
                                                    where different_time_from_creat > 1 
                                                    and created > (select time_add_to_sprint from main_data where issue_key = '{}')
                                                    and (issue_key = '{}')""".format(issue_name, issue_name), (locals())))
                num_changes_acceptance_new_sprint = num_changes_acceptance_new_sprint['count'][0]
            if len(change_acce_issue) == 0:
                original_acceptance = main_data['acceptance_criteria'][i]
                num_changes_acceptance_new = 0
                num_different_word_minus_last_acceptance_criteria_new = 0
                num_different_word_plus_last_acceptance_criteria_new = 0
            elif change_acce_issue['from_string'][0] is None:
                original_acceptance = main_data['acceptance_criteria'][i]
                num_changes_acceptance_new = 0
                num_different_word_minus_last_acceptance_criteria_new = 0
                num_different_word_plus_last_acceptance_criteria_new = 0
            else:
                original_acceptance = change_acce_issue['from_string'][0]
                num_different_word_minus_last_acceptance_criteria_new = change_acce_issue['num_different_word_minus_last'][
                    0]
                num_different_word_plus_last_acceptance_criteria_new = change_acce_issue['num_different_word_plus_last'][0]
                num_changes_acceptance_new = (ps.sqldf("""select count(*) as count
                                        from changes_acceptance
                                        where different_time_from_creat > 1
                                        and (issue_key = '{}')""".format(issue_name), (locals())))
                num_changes_acceptance_new = num_changes_acceptance_new['count'][0]

            if num_changes_summary_new_sprint > 0:
                is_changes_summary_sprint = 1
            else:
                is_changes_summary_sprint = 0
            if num_changes_description_new_sprint > 0:
                is_changes_description_sprint = 1
            else:
                is_changes_description_sprint = 0
            if num_changes_story_points_new_sprint > 0:
                is_changes_story_point_sprint = 1
            else:
                is_changes_story_point_sprint = 0
            if num_changes_acceptance_new_sprint > 0:
                is_changes_acceptance_sprint = 1
            else:
                is_changes_acceptance_sprint = 0

            if num_changes_summary_new > 0:
                is_changes_summary = 1
            else:
                is_changes_summary = 0
            if num_changes_description_new > 0:
                is_changes_description = 1
            else:
                is_changes_description = 0
            if num_changes_story_points_new > 0:
                is_changes_story_point = 1
            else:
                is_changes_story_point = 0
            if num_changes_acceptance_new > 0:
                is_changes_acceptance = 1
            else:
                is_changes_acceptance = 0

            # comments
            time_add_to_sprint = main_data['time_add_to_sprint'][i]

            # after sprint
            num_comments_after_new_sprint = (ps.sqldf("""select count(*) as count from comments
                                    where created > '{}'
                                    and (issue_key = '{}')""".format(time_add_to_sprint, issue_name), (locals())))
            num_comments_after_new_sprint = num_comments_after_new_sprint['count'][0]
            # no after sprint:
            num_comments_before_new_sprint = (ps.sqldf("""select count(*) as count from comments
                                                where created <=  '{}'
                                        and (issue_key = '{}')""".format(time_add_to_sprint, issue_name), (locals())))
            num_comments_before_new_sprint = num_comments_before_new_sprint['count'][0]
            if num_comments_before_new_sprint > 0:
                is_comments_before_new_sprint = 1
            else:
                is_comments_before_new_sprint = 0
            if num_comments_after_new_sprint > 0:
                is_comments_after_new_sprint = 1
            else:
                is_comments_after_new_sprint = 0

            mycursor = mysql_con.cursor()
            try:
                mycursor.execute(sql_add_columns, (
                    original_summary_sprint, int(num_changes_summary_new_sprint), original_description_sprint,
                    int(num_changes_description_new_sprint), original_story_points_sprint,
                    int(num_changes_story_points_new_sprint), original_acceptance_sprint,
                    int(num_changes_acceptance_new_sprint), int(is_changes_summary_sprint),
                    int(is_changes_description_sprint), int(is_changes_story_point_sprint),
                    int(is_changes_acceptance_sprint),
                    int(num_different_word_minus_last_summary_new_sprint),
                    int(num_different_word_plus_last_summary_new_sprint),
                    int(num_different_word_minus_last_description_new_sprint),
                    int(num_different_word_plus_last_description_new_sprint),
                    int(num_different_word_minus_last_acceptance_criteria_new_sprint),
                    int(num_different_word_plus_last_acceptance_criteria_new_sprint),

                    original_summary, int(num_changes_summary_new), original_description,
                    int(num_changes_description_new), original_story_points,
                    int(num_changes_story_points_new), original_acceptance,
                    int(num_changes_acceptance_new), int(is_changes_summary),
                    int(is_changes_description), int(is_changes_story_point),
                    int(is_changes_acceptance),
                    int(num_different_word_minus_last_summary_new),
                    int(num_different_word_plus_last_summary_new),
                    int(num_different_word_minus_last_description_new),
                    int(num_different_word_plus_last_description_new),
                    int(num_different_word_minus_last_acceptance_criteria_new),
                    int(num_different_word_plus_last_acceptance_criteria_new),

                    int(num_comments_before_new_sprint),
                    int(num_comments_after_new_sprint),
                    main_data['issue_key'][i]))
                mysql_con.commit()
                mycursor.close()
            except mysql.connector.IntegrityError:
                print("ERROR: Kumquat already exists!")
            if i % 100 == 0:
                with open("logs.txt", "a") as myfile:
                    myfile.write(f'{i}\n')
                print(i)
        except Exception as e:
            with open("logs.txt", "a") as myfile:
                myfile.write(f'ERROR: index:{i}, issue_key:{issue_name}\n', e)

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
    changes_summary = pd.read_sql(f'SELECT * FROM {dbName}.changes_summary_os', con=mysql_con)
    changes_description = pd.read_sql(f'SELECT * FROM {dbName}.changes_description_os', con=mysql_con)
    changes_story_points = pd.read_sql(f'SELECT * FROM {dbName}.changes_story_points_os', con=mysql_con)
    changes_acceptance = pd.read_sql(f'SELECT * FROM {dbName}.changes_criteria_os', con=mysql_con)
    comments = pd.read_sql(f'SELECT * FROM {dbName}.comments_os', con=mysql_con)

    # sql queries to add the data
    sql_add_columns = f"""
    UPDATE {dbName}.main_table_os SET 
    original_summary_sprint =%s, num_changes_summary_new_sprint=%s, 
    original_description_sprint=%s, num_changes_description_new_sprint=%s, original_story_points_sprint=%s, 
    num_changes_story_points_new_sprint=%s, original_acceptance_criteria_sprint =%s, 
    num_changes_acceptance_criteria_new_sprint=%s, has_change_summary_sprint=%s,
    has_change_description_sprint=%s, has_change_story_point_sprint=%s, has_change_acceptance_criteria_sprint=%s, 
    different_words_minus_summary_sprint = %s, different_words_plus_summary_sprint = %s, 
    different_words_minus_description_sprint = %s, different_words_plus_description_sprint = %s, 
    different_words_minus_acceptance_criteria_sprint = %s, different_words_plus_acceptance_criteria_sprint = %s,

    original_summary =%s, num_changes_summary_new=%s, original_description=%s,
    num_changes_description_new=%s, original_story_points=%s, num_changes_story_points_new=%s, 
    original_acceptance_criteria =%s, num_changes_acceptance_criteria_new=%s, has_change_summary=%s,
    has_change_description=%s, has_change_story_point=%s, has_change_acceptance_criteria=%s, 
    different_words_minus_summary = %s, different_words_plus_summary = %s, different_words_minus_description = %s,
    different_words_plus_description = %s, different_words_minus_acceptance_criteria = %s,
    different_words_plus_acceptance_criteria = %s, 

    num_comments_before_sprint =%s, num_comments_after_sprint=%s 

    WHERE (issue_key=%s)"""

    add_cal_columns_(mysql_con, sql_add_columns, main_data, changes_summary, changes_description, changes_story_points,
                     changes_acceptance, comments, dbName)


if __name__ == '__main__':
    with open('../Source/jira_data_for_instability.json') as f:
        jira_data_sources = json.load(f)

    for jira_name, jira_obj in jira_data_sources.items():
        print("start prepare_data_sql, DB: ", jira_name)
        start(jira_name)
    print("finish prepare_data_sql")

