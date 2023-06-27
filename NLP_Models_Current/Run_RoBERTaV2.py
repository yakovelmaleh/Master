import Utils.NLP_Models.run_Model as run_Model
import Utils.NLP_Models.RoBERTaV2 as RoBERTaV2
import Utils.GetNLPData as GetData
import os


def start(jira_name, main_path):
    main_path = f'{main_path}NLP_Models_Current/Classic_Within_only_description'
    if not os.path.exists(main_path):
        os.mkdir(f'{main_path}')
        open(f'{main_path}/file.txt', 'x')

    data_train_list = get_train_data_list(jira_name)
    data_test_list = get_test_data_list(jira_name)
    model_to_run = lambda path_to_save: RoBERTaV2.start(jira_name=jira_name,
                                                        model_name="Classic_Within_only_description",
                                                        data_train_list=data_train_list, data_test_list=data_test_list,
                                                        path_to_save=path_to_save)

    run_Model.run_NLP_Model(main_path=main_path, jira_name=jira_name, model_to_run=model_to_run)


def get_test_data_list(project_name, main_path='Master/'):
    output = dict()
    for k_unstable in [5, 10, 15, 20]:
        output[f'{k_unstable}'] = \
            GetData.get(project_name, main_path, k_unstable)

    return output


def get_train_data_list(project_name, main_path='Master/'):
    output = dict()
    for k_unstable in [5, 10, 15, 20]:
        output[f'{k_unstable}'] = \
            GetData.get_data_train(project_name, main_path, k_unstable)

    return output
