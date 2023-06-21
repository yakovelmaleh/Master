import Run_Instability_Model.run_train_val_optimization as run_train_val_optimization
import Run_Instability_Model.run_train_tes_best_parameters as run_train_tes_best_parameters
import os


def start(features_data_optimization_train,
          features_data_optimization_valid,
          labels_optimization_train,
          labels_optimization_valid,
          main_path,
          features_data_train,
          features_data_test,
          labels_train,
          labels_test,
          jira_name=None):

    for dirName in ['Parameters', 'Results']:
        if not os.path.exists(f'{main_path}/{dirName}'):
            os.mkdir(f'{main_path}/{dirName}')
            open(f'{main_path}/{dirName}/file.txt', 'x')

        if jira_name is not None:
            path = f'{main_path}/{dirName}/{jira_name}'
            if not os.path.exists(path):
                os.mkdir(path)
                open(f'{path}/file.txt', 'x')

    path_to_save_optimization = f'{main_path}/Parameters'\
        if jira_name is None else f'{main_path}/Parameters/{jira_name}'
    auc_PRC_optimization_path = f'{main_path}/Parameters'\
        if jira_name is None else f'{main_path}/Parameters/{jira_name}'

    auc_PRC_path = f'{main_path}/Results'\
        if jira_name is None else f'{main_path}/Results/{jira_name}'
    path_to_save = f'{main_path}/Results'\
        if jira_name is None else f'{main_path}/Results/{jira_name}'

    run_train_val_optimization.start(features_data_train_list=features_data_optimization_train,
                                     features_data_valid_list=features_data_optimization_valid,
                                     labels_valid_list=labels_optimization_train,
                                     labels_train_list=labels_optimization_valid,
                                     path_to_save=path_to_save_optimization,
                                     auc_PRC_path=auc_PRC_optimization_path)

    run_train_tes_best_parameters.start(features_data_train_list=features_data_train,
                                        features_data_test_list=features_data_test,
                                        labels_train_list=labels_train,
                                        labels_test_list=labels_test,
                                        path_to_save=path_to_save,
                                        parameters_path=path_to_save_optimization,
                                        auc_PRC_path=auc_PRC_path)
