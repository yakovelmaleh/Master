import Utils.NLP_Models.run_Model as run_Model
import Utils.NLP_Models.GPT2 as GPT2
import Utils.GetNLPData as GetData
import os


def run_normal(jira_name, main_path='Master/'):
    model_name = 'Normal'
    main_path_to_save = f'{main_path}NLP_Models_Current/{model_name}'
    if not os.path.exists(main_path_to_save):
        os.mkdir(f'{main_path_to_save}')
        open(f'{main_path_to_save}/file.txt', 'x')

    data_train_list = get_train_data_list(jira_name, main_path)
    data_test_list = get_test_data_list(jira_name, main_path)
    model_to_run = lambda path_to_save: GPT2.start(jira_name=jira_name, model_name=model_name,
                                                   train_data_list=data_train_list, test_data_list=data_test_list,
                                                   path_to_save=path_to_save)

    run_Model.run_NLP_Model(main_path=main_path_to_save, jira_name=jira_name, model_to_run=model_to_run)


def get_test_data_list(project_name, main_path='Master/'):
    output = dict()
    for k_unstable in [5, 10, 15, 20]:
        output[f'{k_unstable}'] = \
            GetData.get_test_data(project_name, main_path, k_unstable)

    return output


def get_train_data_list(project_name, main_path='Master/'):
    output = dict()
    for k_unstable in [5, 10, 15, 20]:
        output[f'{k_unstable}'] = GetData.get_data_train(project_name, main_path, k_unstable)

    return output

