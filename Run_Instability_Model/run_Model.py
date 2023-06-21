import Run_Instability_Model.run_train_val_optimization as run_train_val_optimization
import Run_Instability_Model.run_train_tes_best_parameters as run_train_tes_best_parameters
import os


def start(features_data_optimization_train,
          features_data_optimization_valid,
          labels_optimization_train,
          labels_optimization_valid,
          main_path,
          auc_PRC_optimization_path,
          features_data_train,
          features_data_test,
          labels_train,
          labels_test,
          auc_PRC_path,
          jira_name=None):

    for dirName in ['Parameters', 'Results']:
        if not os.path.exists(f'{main_path}/{dirName}'):
            os.mkdir(f'{main_path}/{dirName}')
            open(f'{main_path}/{dirName}/file.txt', 'x')

    run_train_val_optimization.start(features_data_train=features_data_optimization_train,
                                     features_data_valid=features_data_optimization_valid,
                                     labels_train=labels_optimization_train,
                                     labels_valid=labels_optimization_valid,
                                     path_to_save=main_path,
                                     auc_PRC_path=auc_PRC_optimization_path)

    if jira_name is not None:
        path_to_save = f'{main_path}/Results/{jira_name}'
        if not os.path.exists(path_to_save):
            os.mkdir(path_to_save)
            open(f'{path_to_save}/file.txt', 'x')
    else:
        path_to_save = f'{main_path}/Results'

    run_train_tes_best_parameters.start(features_data_train=features_data_train,
                                        features_data_test=features_data_test,
                                        labels_train=labels_train,
                                        labels_test=labels_test,
                                        path_to_save=path_to_save,
                                        parameters_path=f'{main_path}/Parameters',
                                        auc_PRC_path=auc_PRC_path)
