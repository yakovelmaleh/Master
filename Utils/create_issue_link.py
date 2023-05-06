import pandas as pd
import pandasql as ps


"""
function which gets the issue link data and remove the unnecessary links
"""
def remove_extracted_links(link_data):

    for j in range(0, len(link_data)):
        for i in range(j, len(link_data)):
            try:
                if (link_data['if_before'][j] == 1 and link_data['if_before'][i] == 1 and
                        link_data['issue_key'][j] == link_data['issue_key'][i] and
                        link_data['to_string'][j] == link_data['from_string'][i] and
                        link_data['created_link'][j] < link_data['created_link'][i]):
                    link_data['to_string'][j] == ""
            except:
                a = 8

    return link_data


def check_if_link_in_string(is_before, link_str, word):
    """
    this function return 1 if the "word" excist in the link string, 0 else
    """
    try:
        for i in range(0, len(word)):
            if link_str.lower().count(word[i]) > 0 and is_before == 1:
                return 1
        return 0
    except:
        return 0


def create_issue_links_features(data_help, original_data):
    """
    this function get the project data (original and the help table), check for each USI how many link types excist for it. 
    the function add to the original data the features of how many issue links there is to each USI from the types of block, blocke by, 
    duplicate by, duplicate and realtes, and return the data with the added columns.
    """

    data_help['block'] = data_help.apply(lambda x: check_if_link_in_string(x['if_before'], x['to_string'], ['blocks',
                                                                'has to be done before', 'is triggering']), axis=1)
    data_help['block_by'] = data_help.apply(lambda x: check_if_link_in_string(x['if_before'], x['to_string'],
                                                                              ['has to be done after',
                      'is blocked by', 'is triggered by', 'depends on', 'depended on by', 'is depended on by']), axis=1)
    data_help['duplicate'] = data_help.apply(lambda x: check_if_link_in_string(x['if_before'], x['to_string'],
                                                                               ['clones', 'cloned from', 'duplicates',
                                                                                'is clone of']), axis=1)
    data_help['duplicate_by'] = data_help.apply(
        lambda x: check_if_link_in_string(x['if_before'], x['to_string'], ['cloned to', 'is cloned by',
                                                                           'is duplicated by']), axis=1)
    data_help['relates'] = data_help.apply(lambda x: check_if_link_in_string(x['if_before'], x['to_string'],
                                                                             ['relates to', 'is related to',
                                                                              'is related to by']), axis=1)

    data_help2 = (ps.sqldf("""select issue_key1, sum(block) as num_block, sum(block_by) as num_block_by, 
                              sum(duplicate) as num_duplicate, sum(duplicate_by) as num_duplicate_by,
                              sum(relates) as num_relates
                              from data_help
                              group by issue_key1 
                              """))

    original_data['block'] = data_help2['num_block']
    original_data['block_by'] = data_help2['num_block_by']
    original_data['duplicate_by'] = data_help2['num_duplicate_by']
    original_data['relates'] = data_help2['num_relates']
    original_data['duplicate'] = data_help2['num_duplicate']

    return original_data


def create_issue_links_all(data, path):
    """
    this function get all the projects data and for each one it extract the issue link data of it by another tables that we create by sql queries 
    """
    # extract data
    # creat the help tables for all the projects, which includes the issue links
    """
    help_data = pd.read_sql("select t3.issue_key as issue_key1, t2.issue_key as issue_key2, "
                                      "t3.time_add_to_sprint, t2.created, t2.from_string, t2.to_string, t2.field, "
                                      "t3.time_add_to_sprint>t2.created as if_before from "
                                      "data_base_os.features_labels_table_os2 t3 left join "
                                      "data_base_os.all_changes_os t2 ON t3.issue_key = t2.issue_key "
                                      "and t2.field = 'Link' where t3.issue_key is not null and "
                                      "t3.project_key = 'DEVELOPER' ", con=mysql_con_os)
    """

    help_data = pd.read_sql(path)
    # run 2 functions which added the number of issue link of each type to the original data
    help_data = remove_extracted_links(help_data)
    data = create_issue_links_features(help_data, data)

    return data
