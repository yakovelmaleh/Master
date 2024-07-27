import json
import os.path
import pandas as pd
import Using_CSV_files.Load_Data_From_Jira_To_CSV.Create_DB as Create_DB

def add_relevant_column(feature_table: pd.DataFrame, column_name: str, ratio_column_name: str = None,
                        value: str = None):
    feature_table[column_name] = 0
    if value is None:
        feature_table_help = feature_table[['issue_key', 'created', 'creator']]
        for index, row in feature_table.iterrows():
            # Create the condition
            condition = (
                    (feature_table_help['issue_key'] == feature_table['issue_key']) &
                    (feature_table_help['created'] > row['created']) &
                    (feature_table_help['creator'] == row['creator'])
            )
            feature_table.at[index, column_name] = condition.sum()
    else:
        feature_table_help = feature_table[['issue_key', 'created', 'creator', value]]
        feature_table[ratio_column_name] = 0
        for index, row in feature_table.iterrows():
            # Create the condition
            condition = (
                    (feature_table_help['issue_key'] == feature_table['issue_key']) &
                    (feature_table_help['created'] > row['created']) &
                    (feature_table_help['creator'] == row['creator']) &
                    (feature_table_help[value] > 0)
            )

            feature_table.at[index, column_name] = condition.sum()
            if row['num_issues_cretor_prev'] == 0:
                feature_table.at[index, ratio_column_name] = 0
            else:
                feature_table.at[index, ratio_column_name] = \
                    condition.sum() / row['num_issues_cretor_prev']

    return feature_table


def add_relevant_columns_startWith(feature_table: pd.DataFrame, soffix: int):
    return add_relevant_column(feature_table=feature_table,
                               column_name=f'num_unusable_issues_cretor_prev_text_word_{soffix}',
                               ratio_column_name=f'num_unusable_issues_cretor_prev_text_word_{soffix}_ratio',
                               value=f'is_change_text_num_words_{soffix}')


def start(path_to_load, path_to_save):
    Create_DB.create_DB(path_to_save)
    feature_table = pd.read_csv(os.path.join(path_to_load, "feature_table.csv"))

    """
    ###################################################################
    /* create the calculate features num "bad" issues to writer and 
    general num issues to writer for this calculation we will help in 
    more table */
    ###################################################################
    """

    feature_table = add_relevant_column(feature_table=feature_table,
                                        column_name='num_issues_cretor_prev')

    for k_unstable in [1, 5, 10, 15, 20]:
        feature_table = add_relevant_columns_startWith(feature_table, k_unstable)

    feature_table.to_csv(os.path.join(path_to_save, "feature_table.csv"))


if __name__ == '__main__':
    with open('../Source/jira_data_for_instability.json') as f:
        jira_data_sources = json.load(f)

    for jira_name, jira_obj in jira_data_sources.items():
        print("start calculate_features_all_num_bad_issue, DB: ", jira_name)
        start(jira_name)
    print("finish to calculate_features_all_num_bad_issue")
