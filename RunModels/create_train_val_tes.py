import json
import os
import pandas as pd
import Utils.clean_text_create_features as clean_text_create_features
import Utils.create_topic_model as create_topic_model
import Utils.create_doc_vec as create_doc_vec
from pathlib import Path
import Utils.create_issue_link as create_issue_link


def split_train_valid_test(data_to_split):
    """
    function who get the data, split it to train, validation and test set (0.6,0.2,0.2), and return it
    """
    data_to_split = data_to_split.sort_values(by=['time_add_to_sprint'])
    data_to_split = data_to_split.reset_index(drop=True)
    # with validation
    num_rows_train = round(0.6*len(data_to_split))
    num_rows_valid = round(0.8*len(data_to_split))

    train = data_to_split.loc[0:num_rows_train-1, :].reset_index(drop=True)
    valid = data_to_split.loc[num_rows_train:num_rows_valid-1, :].reset_index(drop=True)
    test = data_to_split.loc[num_rows_valid:, :].reset_index(drop=True)
    return train, valid, test

def addPath(path):
    return str(Path(os.getcwd()).joinpath(path))


def start(jira_name):
    """
    dbName = f"{DB.DB_NAME}_{jira_name.lower()}"
    mysql_con = DB.connectToSpecificDB(dbName)
    cursor = mysql_con.cursor()
    print(f'connected to DB: {DB.DB_NAME}_{jira_name.lower()}')

    # Enforce UTF-8 for the connection
    cursor.execute('SET NAMES utf8mb4')
    cursor.execute("SET CHARACTER SET utf8mb4")
    cursor.execute("SET character_set_connection=utf8mb4")
    data = pd.read_sql(f"select t3.issue_key as issue_key1, t2.issue_key as issue_key2,
                                      t3.time_add_to_sprint, t2.created, t2.from_string, t2.to_string, t2.field, 
                                      t3.time_add_to_sprint>t2.created as if_before from 
                                      data_base_os_apache.features_labels_table_os t3 left join 
                                      data_base_os_apache.all_changes_os t2 ON t3.issue_key = t2.issue_key 
                                      and t2.field = 'Link' where t3.issue_key is not null", con=mysql_con)
    data.to_csv(path)
    """
    path = addPath(f'Master/Data/{jira_name}')

    data = pd.read_csv(f'{path}/features_labels_table_os.csv')
    print(f"size of {jira_name} data: {len(data)}")

    data = create_issue_link.create_issue_links_all(data, f'{path}/create_issue_link_data.csv')

    text_type = 'original_summary_description_acceptance_sprint'

    dict_labels = {'is_change_text_num_words_5': 'num_unusable_issues_cretor_prev_text_word_5_ratio',
                   'is_change_text_num_words_10': 'num_unusable_issues_cretor_prev_text_word_10_ratio',
                   'is_change_text_num_words_15': 'num_unusable_issues_cretor_prev_text_word_15_ratio',
                   'is_change_text_num_words_20': 'num_unusable_issues_cretor_prev_text_word_20_ratio'}

    optimal_values = {
        'Apache': [3, 15],
        'Hyperledger': [2, 15],
        'IntelDAOS': [4, 10],
        'Jira': [2, 20],
        'MariaDB': [2, 20],
    }

    num_topics = optimal_values[jira_name][0]
    size_vec = optimal_values[jira_name][1]

    # split to train validation and test set
    train, valid, test = split_train_valid_test(data)

    # ############################ clean text and create all features ######################
    features_data_train_val = clean_text_create_features.create_feature_data(train, text_type, jira_name)
    features_data_valid = clean_text_create_features.create_feature_data(valid, text_type, jira_name)
    features_data_train_test = pd.concat([features_data_train_val, features_data_valid],ignore_index=True)
    #features_data_train_test = features_data_train_val.append(features_data_valid, ignore_index=True)

    features_data_test = clean_text_create_features.create_feature_data(test, text_type, jira_name)
    # ########### create doc vec with the script create_doc_vec ################
    train_vec, valid_vec = create_doc_vec.create_doc_to_vec(train, valid, True, size_vec, jira_name, 'Validation')
    features_data_train_val = pd.concat([features_data_train_val, train_vec], axis=1)
    features_data_valid = pd.concat([features_data_valid, valid_vec], axis=1)

    #train_val = train.append(valid, ignore_index=True)
    train_val = pd.concat([train,valid], ignore_index=True)
    train_test_vec, test_vec = create_doc_vec.create_doc_to_vec(train_val, test, True, size_vec, jira_name, 'Test')
    features_data_train_test = pd.concat([features_data_train_test, train_test_vec], axis=1)
    features_data_test = pd.concat([features_data_test, test_vec], axis=1)
    # ########### add topic model with the script create_topic_model ################
    # train val
    dominant_topic_train_val, dominant_topic_valid = create_topic_model.create_topic_model(train, valid, num_topics,
                                                                                           jira_name)
    dominant_topic_train_val = dominant_topic_train_val.reset_index(drop=True)
    dominant_topic_valid = dominant_topic_valid.reset_index(drop=True)
    features_data_train_val['dominant_topic'] = dominant_topic_train_val['Dominant_Topic']
    features_data_valid['dominant_topic'] = dominant_topic_valid['Dominant_Topic']

    # train test
    dominant_topic_train_test, dominant_topic_test = create_topic_model.create_topic_model(train_val, test,
                                                                                           num_topics, jira_name)
    dominant_topic_train_test = dominant_topic_train_test.reset_index(drop=True)
    dominant_topic_test = dominant_topic_test.reset_index(drop=True)
    features_data_train_test['dominant_topic'] = dominant_topic_train_test['Dominant_Topic']
    features_data_test['dominant_topic'] = dominant_topic_test['Dominant_Topic']

    project_key = jira_name
    for label_name in dict_labels.items():
        # save label date to every set
        print("data {}: \n, \n label_name.key: {}, \n".format(project_key, label_name[0]))
        labels_train_val = pd.DataFrame()
        labels_valid = pd.DataFrame()
        labels_train_test = pd.DataFrame()
        labels_test = pd.DataFrame()
        labels_train_val['usability_label'] = train['{}'.format(label_name[0])]
        labels_valid['usability_label'] = valid['{}'.format(label_name[0])]
        labels_train_test['usability_label'] = train_val['{}'.format(label_name[0])]
        labels_test['usability_label'] = test['{}'.format(label_name[0])]
        labels_train_val['issue_key'] = train['issue_key']
        labels_valid['issue_key'] = valid['issue_key']
        labels_train_test['issue_key'] = train_val['issue_key']
        labels_test['issue_key'] = test['issue_key']
        print("size: ", features_data_train_val.shape)
        print("train size: ", train.shape)
        print("train: ", train)
        print("train_labels: ", train.columns.values)
        print("label_name: ", label_name)
        features_data_train_val['ratio_unusable_issues_text_by_previous'] = train['{label}'.format(label=label_name[1])]
        features_data_valid['ratio_unusable_issues_text_by_previous'] = valid['{label}'.format(label=label_name[1])]
        features_data_train_test['ratio_unusable_issues_text_by_previous'] = train_val[
            '{label}'.format(label=label_name[1])]
        features_data_test['ratio_unusable_issues_text_by_previous'] = test['{label}'.format(label=label_name[1])]

        # ################################### save the feature table  ####################################
        # train val
        path = addPath(f'Master/Models/train_val/{jira_name}')

        features_data_train_val.to_csv(
            f'{path}/features_data_train_{jira_name}_{label_name[0]}.csv', index=False)
        features_data_valid.to_csv(
            f'{path}/features_data_valid_{jira_name}_{label_name[0]}.csv', index=False)

        labels_train_val.to_csv(
            f'{path}/labels_train_{jira_name}_{label_name[0]}.csv', index=False)
        labels_valid.to_csv(
            f'{path}/labels_valid_{jira_name}_{label_name[0]}.csv', index=False)

        # train test
        path = addPath(f'Master/Models/train_test/{jira_name}')

        features_data_train_test.to_csv(
            f'{path}/features_data_train_{jira_name}_{label_name[0]}.csv', index=False)
        features_data_test.to_csv(
            f'{path}/features_data_test_{jira_name}_{label_name[0]}.csv', index=False)

        labels_train_test.to_csv(
            f'{path}/labels_train_{jira_name}_{label_name[0]}.csv', index=False)
        labels_test.to_csv(
            f'{path}/labels_test_{jira_name}_{label_name[0]}.csv', index=False)


if __name__ == "__main__":
    with open('../Source/jira_data_for_instability.json') as f:
        jira_data_sources = json.load(f)

    for jira_name, jira_obj in jira_data_sources.items():
        print("start create_train_val_tes, DB: ", jira_name)
        start(jira_name)
    print("finish to create_train_val_tes")