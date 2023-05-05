import Utils.DataBase as DB
import mysql.connector
import CreateTables


def createTable(tableName, publish_commit, mysql_con):
    """
    Create Table for this DataBase
    :param tableName: Table name
    :param publish_commit: a commit for create a new specific Table
    :param mysql_con: Connection to DB
    :return: None
    """
    commit(f'DROP TABLE IF EXISTS `{tableName}`', mysql_con)
    commit('SET character_set_client = utf8mb4', mysql_con)
    commit(publish_commit, mysql_con)


def createDataBase(name, mysql_con):
    """
    Create Specific DB
    :param name: specific DB name
    :param mysql_con: connection to DB
    :return: None
    """
    publish_commit = f"CREATE DATABASE  IF NOT EXISTS `data_base_os_{name}` "
    commit(publish_commit, mysql_con)


def commit(publish_commit, mysql_con):
    cursor = mysql_con.cursor()
    try:
        cursor.execute(publish_commit)
        mysql_con.commit()
        cursor.close()

    except mysql.connector.IntegrityError:
        print(f"Failed to Do: {publish_commit}")


def create_DB(name):
    mysql_con = DB.conncetToDB()
    cursor = mysql_con.cursor()

    # Create DataBase
    createDataBase(name, mysql_con)
    cursor.execute(f'USE `data_base_os_{name.lower()}`')
    cursor.execute(f'SET NAMES utf8')
    cursor.close()
    print(f'connected to DB: {DB.DB_NAME}_{name.lower()}')

    # Create Tables
    createTable('all_changes_os', CreateTables.all_changes_os, mysql_con)
    createTable('changes_description_os', CreateTables.changes_description_os, mysql_con)
    createTable('changes_sprint_os', CreateTables.changes_sprint_os, mysql_con)
    createTable('changes_story_points_os', CreateTables.changes_story_points_os, mysql_con)
    createTable('changes_summary_os', CreateTables.changes_summary_os, mysql_con)
    createTable('changes_criteria_os', CreateTables.changes_criteria_os, mysql_con)
    createTable('comments_os', CreateTables.comments_os, mysql_con)
    createTable('commits_info_os', CreateTables.commits_info_os, mysql_con)
    createTable('components_os', CreateTables.components_os, mysql_con)
    createTable('fix_versions_os', CreateTables.fix_versions_os, mysql_con)
    createTable('issue_links_os', CreateTables.issue_links_os, mysql_con)
    createTable('labels_os', CreateTables.labels_os, mysql_con)
    createTable('main_table_os', CreateTables.main_table_os, mysql_con)
    createTable('names_bugs_issue_links_os', CreateTables.names_bugs_issue_links_os, mysql_con)
    createTable('sab_task_names_os', CreateTables.sab_task_names_os, mysql_con)
    createTable('sprints_os', CreateTables.sprints_os, mysql_con)
    createTable('versions_os', CreateTables.versions_os, mysql_con)
    createTable('attachment_os', CreateTables.attachment_os, mysql_con)

    print(f"Created DataBase and all the Tables for {name.lower()}")
    mysql_con.close()


def createAttachment(mysql_con):
    createTable('attachment_os', CreateTables.attachment_os, mysql_con)
    print("created Attachment")

def createAttachmentWithoutDrop(mysql_con):
    try:
        commit('SET character_set_client = utf8mb4', mysql_con)
        commit(CreateTables.attachment_os, mysql_con)
        print("created Attachment")
    except:
        print('didn"t created Attachment')

