import Run_Instability_Model.run_Model as run_Model
import Utils.GetInstabilityData as GetInstabilityData
import os
import json


def run_all(function, main_path):
    with open(f'{main_path}Source/jira_data_for_instability_cluster.json') as f:
        jira_data_sources = list(json.load(f).keys())

    for i in range(0, len(jira_data_sources)):
        print(f"start: {jira_data_sources[i]}")
        function(jira_data_sources[i], jira_data_sources[(i+1) % len(jira_data_sources)], main_path)
        print(f'finish {jira_data_sources[i]}')


def run_whole_project_as_a_test(test_jira_name, validation_jira_name, main_path):
    main_path = f'{main_path}Only_Instability_Cross_Project/Classic'
    if not os.path.exists(main_path):
        os.mkdir(f'{main_path}')
        open(f'{main_path}/file.txt', 'x')

    features_data_optimization_train_list = \
        get_cross_project_train_data_except([test_jira_name, validation_jira_name])
    features_data_optimization_valid_list = get_all_train_data_project(validation_jira_name)

    labels_optimization_train_list = \
        get_cross_project_labels_except([test_jira_name, validation_jira_name])
    labels_optimization_valid_list = get_all_labels_project(validation_jira_name)

    features_data_train_list = get_cross_project_train_data_except([test_jira_name])
    features_data_test_list = get_all_train_data_project(test_jira_name)

    labels_train_list = get_cross_project_labels_except([test_jira_name])
    labels_test_list = get_all_labels_project(test_jira_name)

    run_Model.start(features_data_optimization_train=features_data_optimization_train_list,
                    features_data_optimization_valid=features_data_optimization_valid_list,
                    labels_optimization_train=labels_optimization_train_list,
                    labels_optimization_valid=labels_optimization_valid_list,
                    main_path=main_path,
                    features_data_train=features_data_train_list,
                    features_data_test=features_data_test_list,
                    labels_train=labels_train_list,
                    labels_test=labels_test_list,
                    jira_name=test_jira_name)


def run_only_test_project_as_a_test(test_jira_name, validation_jira_name, main_path):
    main_path = f'{main_path}Only_Instability_Cross_Project/Only_test_on_the_test_project'
    if not os.path.exists(main_path):
        os.mkdir(f'{main_path}')
        open(f'{main_path}/file.txt', 'x')

    features_data_optimization_train_list = \
        get_cross_project_train_data_except([test_jira_name, validation_jira_name])
    features_data_optimization_valid_list = get_all_train_data_project(validation_jira_name)

    labels_optimization_train_list = \
        get_cross_project_labels_except([test_jira_name, validation_jira_name])
    labels_optimization_valid_list = get_all_labels_project(validation_jira_name)

    features_data_train_list = get_cross_project_train_data_except([test_jira_name])
    features_data_test_list = get_specific_train_data_project(test_jira_name)

    labels_train_list = get_cross_project_labels_except([test_jira_name])
    labels_test_list = get_specific_labels_project(test_jira_name)

    run_Model.start(features_data_optimization_train=features_data_optimization_train_list,
                    features_data_optimization_valid=features_data_optimization_valid_list,
                    labels_optimization_train=labels_optimization_train_list,
                    labels_optimization_valid=labels_optimization_valid_list,
                    main_path=main_path,
                    features_data_train=features_data_train_list,
                    features_data_test=features_data_test_list,
                    labels_train=labels_train_list,
                    labels_test=labels_test_list,
                    jira_name=test_jira_name)


def get_cross_project_train_data_except(irrelevant_projects, main_path='Master/'):
    output = dict()
    for k_unstable in [5, 10, 15, 20]:
        output[f'{k_unstable}'] = GetInstabilityData. \
            get_all_data_except(main_path, k_unstable, irrelevant_projects)

    return output


def get_cross_project_labels_except(irrelevant_projects, main_path='Master/'):
    output = dict()
    for k_unstable in [5, 10, 15, 20]:
        output[f'{k_unstable}'] = GetInstabilityData. \
            get_all_label_except(main_path, k_unstable, irrelevant_projects)

    return output


def get_specific_labels_project(project_name, main_path='Master/'):
    output = dict()
    for k_unstable in [5, 10, 15, 20]:
        output[f'{k_unstable}'] = \
            GetInstabilityData.get_label_test(project_name, main_path, k_unstable)

    return output


def get_specific_train_data_project(project_name, main_path='Master/'):
    output = dict()
    for k_unstable in [5, 10, 15, 20]:
        output[f'{k_unstable}'] = \
            GetInstabilityData.get_test_data(project_name, main_path, k_unstable)

    return output


def get_all_train_data_project(project_name, main_path='Master/'):
    output = dict()
    for k_unstable in [5, 10, 15, 20]:
        output[f'{k_unstable}'] = \
            GetInstabilityData.get_all_data_project(project_name, main_path, k_unstable)

    return output


def get_all_labels_project(project_name, main_path='Master/'):
    output = dict()
    for k_unstable in [5, 10, 15, 20]:
        output[f'{k_unstable}'] = \
            GetInstabilityData.get_all_label_project(project_name, main_path, k_unstable)

    return output
