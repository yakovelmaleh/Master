import pandas as pd
import json


def get_test_data(jira_name, main_path, k_unstable):
    path = f'{main_path}Models/train_test_after_all_but/{jira_name}/'
    features_data_test = pd.read_csv(
        f'{path}/features_data_test_{jira_name}_{k_unstable}.csv', low_memory=False)

    return features_data_test


def get_data_train_valid(jira_name, main_path, k_unstable):
    path = f'{main_path}Models/train_val_after_all_but/{jira_name}'
    features_data_train = pd.read_csv(
        f'{path}/features_data_train_{jira_name}_{k_unstable}.csv', low_memory=False)
    features_data_valid = pd.read_csv(
        f'{path}/features_data_valid_{jira_name}_{k_unstable}.csv', low_memory=False)

    return features_data_train, features_data_valid


def get_label_train_valid(jira_name, main_path, k_unstable):
    path = f'{main_path}Models/train_val/{jira_name}'
    labels_train = pd.read_csv(
        f'{path}/labels_train_{jira_name}_{k_unstable}.csv', low_memory=False)
    labels_valid = pd.read_csv(
        f'{path}/labels_valid_{jira_name}_{k_unstable}.csv', low_memory=False)

    return labels_train, labels_valid


def get_label_train(jira_name, main_path, k_unstable):
    path = f'{main_path}Models/train_test/{jira_name}'
    labels_train = pd.read_csv(
        f'{path}/labels_train_{jira_name}_{k_unstable}.csv', low_memory=False)

    return labels_train


def get_label_test(jira_name, main_path, k_unstable):
    path = f'{main_path}Models/train_test/{jira_name}'
    labels_test = pd.read_csv(
        f'{path}/labels_test_{jira_name}_{k_unstable}.csv', low_memory=False)

    return labels_test


def get_data_train(jira_name, main_path, k_unstable):
    path = f'{main_path}Models/train_test_after_all_but/{jira_name}/'
    features_data_train = pd.read_csv(
        f'{path}/features_data_train_{jira_name}_{k_unstable}.csv', low_memory=False)

    return features_data_train


def get_data_all_train_valid(main_path, k_unstable):
    train_data = pd.DataFrame(columns=['idx', 'sentence', 'label'])
    valid_data = pd.DataFrame(columns=['idx', 'sentence', 'label'])
    with open('Master/Source/jira_data_for_instability_cluster.json') as f:
        jira_data_sources = json.load(f)

    for jira_name, jira_obj in jira_data_sources.items():
        temp_train, temp_valid = get_data_train_valid(jira_name, main_path, k_unstable)
        if len(train_data) == 0:
            train_data = temp_train
            valid_data = temp_valid
        else:
            train_data = pd.concat([train_data, temp_train], ignore_index=True)
            valid_data = pd.concat([valid_data, temp_valid], ignore_index=True)

    return train_data, valid_data


def get_all_labels_train_valid(main_path, k_unstable):
    train_data = pd.DataFrame(columns=['idx', 'sentence', 'label'])
    valid_data = pd.DataFrame(columns=['idx', 'sentence', 'label'])
    with open('Master/Source/jira_data_for_instability_cluster.json') as f:
        jira_data_sources = json.load(f)

    for jira_name, jira_obj in jira_data_sources.items():
        temp_train, temp_valid = get_label_train_valid(jira_name, main_path, k_unstable)
        if len(train_data) == 0:
            train_data = temp_train
            valid_data = temp_valid
        else:
            train_data = pd.concat([train_data, temp_train], ignore_index=True)
            valid_data = pd.concat([valid_data, temp_valid], ignore_index=True)

    return train_data, valid_data


def get_data_all_test(main_path, k_unstable):
    test_data = pd.DataFrame(columns=['idx', 'sentence', 'label'])
    with open('Master/Source/jira_data_for_instability_cluster.json') as f:
        jira_data_sources = json.load(f)

    for jira_name, jira_obj in jira_data_sources.items():
        temp = get_test_data(jira_name, main_path, k_unstable)
        if len(test_data) == 0:
            test_data = temp
        else:
            test_data = pd.concat([test_data, temp], ignore_index=True)

    return test_data


def get_label_all_test(main_path, k_unstable):
    test_data = pd.DataFrame(columns=['idx', 'sentence', 'label'])
    with open('Master/Source/jira_data_for_instability_cluster.json') as f:
        jira_data_sources = json.load(f)

    for jira_name, jira_obj in jira_data_sources.items():
        temp = get_label_test(jira_name, main_path, k_unstable)
        if len(test_data) == 0:
            test_data = temp
        else:
            test_data = pd.concat([test_data, temp], ignore_index=True)

    return test_data


def get_data_all_train(main_path, k_unstable):
    train_data = pd.DataFrame(columns=['idx', 'sentence', 'label'])
    with open('Master/Source/jira_data_for_instability_cluster.json') as f:
        jira_data_sources = json.load(f)

    for jira_name, jira_obj in jira_data_sources.items():
        temp_train = get_data_train(jira_name, main_path, k_unstable)
        if len(train_data) == 0:
            train_data = temp_train
        else:
            train_data = pd.concat([train_data, temp_train], ignore_index=True)

    return train_data


def get_label_all_train(main_path, k_unstable):
    train_data = pd.DataFrame(columns=['idx', 'sentence', 'label'])
    with open('Master/Source/jira_data_for_instability_cluster.json') as f:
        jira_data_sources = json.load(f)

    for jira_name, jira_obj in jira_data_sources.items():
        temp_train = get_label_train(jira_name, main_path, k_unstable)
        if len(train_data) == 0:
            train_data = temp_train
        else:
            train_data = pd.concat([train_data, temp_train], ignore_index=True)

    return train_data
