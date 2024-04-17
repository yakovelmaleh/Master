import Run_Instability_Model.run_Model as run_Model
import os
import Robert_Course.Previous_Labels_Models.Data_Preparation as Previous_labels


def run_N_previous_Model(jira_name, main_path, N):
    main_path = f'{main_path}/{N}_Previous_Labels_Models'
    if not os.path.exists(main_path):
        os.mkdir(f'{main_path}')
        open(f'{main_path}/file.txt', 'x')

    features_data_optimization_train_list, features_data_optimization_valid_list \
        = Previous_labels.get_train_valid_sets_for_optimize(jira_name, 'Master/', N)

    labels_optimization_train_list, labels_optimization_valid_list \
        = Previous_labels.get_train_valid_labels_for_optimize(jira_name, 'Master/')

    features_data_train_list = Previous_labels.get_train_sets_for_prediction(jira_name, 'Master/', N)
    features_data_test_list = Previous_labels.get_test_sets_for_prediction(jira_name, 'Master/', N)

    labels_train_list = Previous_labels.get_train_labels_for_prediction(jira_name, 'Master/')
    labels_test_list = Previous_labels.get_test_labels_for_prediction(jira_name, 'Master/')

    run_Model.start(features_data_optimization_train=features_data_optimization_train_list,
                    features_data_optimization_valid=features_data_optimization_valid_list,
                    labels_optimization_train=labels_optimization_train_list,
                    labels_optimization_valid=labels_optimization_valid_list,
                    main_path=main_path,
                    features_data_train=features_data_train_list,
                    features_data_test=features_data_test_list,
                    labels_train=labels_train_list,
                    labels_test=labels_test_list,
                    jira_name=jira_name)


def run(main_path, jira_name):
    main_path = f'{main_path}Robert_Course/Only_Previous_Label_Models/{jira_name}'
    if not os.path.exists(main_path):
        os.mkdir(f'{main_path}')
        open(f'{main_path}/file.txt', 'x')
    for N in [1, 5, 10, 50, 100]:
        run_N_previous_Model(jira_name, main_path, N)
