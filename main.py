import json
import os

import pandas as pd

import Normal_instability.run_train_val_optimization as run_train_val_optimization
import Normal_instability.run_train_tes_best_parameters as run_train_tes_best_parameters

def createFolders(jira_name):
    os.mkdir(f'Data/{jira_name}')

    os.mkdir(f'Models/chi_square/{jira_name}')
    open(f'Models/chi_square/{jira_name}/file.txt', 'x')

    os.mkdir(f'Models/coherence_values/{jira_name}')
    open(f'Models/coherence_values/{jira_name}/file.txt', 'x')

    os.mkdir(f'Models/feature_selection/{jira_name}')
    open(f'Models/feature_selection/{jira_name}/file.txt', 'x')

    os.mkdir(f'Models/final_doc2vec_models/{jira_name}')
    open(f'Models/final_doc2vec_models/{jira_name}/file.txt', 'x')

    os.mkdir(f'Models/lda_models/{jira_name}')
    open(f'Models/lda_models/{jira_name}/file.txt', 'x')

    os.mkdir(f'Models/optimization_results/{jira_name}')
    open(f'Models/optimization_results/{jira_name}/file.txt', 'x')

    os.mkdir(f'Models/results_best_para/{jira_name}')
    open(f'Models/results_best_para/{jira_name}/file.txt', 'x')

    os.mkdir(f'Models/topic_model/{jira_name}')
    open(f'Models/topic_model/{jira_name}/file.txt', 'x')

    os.mkdir(f'Models/train_test/{jira_name}')
    open(f'Models/train_test/{jira_name}/file.txt', 'x')

    os.mkdir(f'Models/train_test_after_all_but/{jira_name}')
    open(f'Models/train_test_after_all_but/{jira_name}/file.txt', 'x')

    os.mkdir(f'Models/train_test_after_chi/{jira_name}')
    open(f'Models/train_test_after_chi/{jira_name}/file.txt', 'x')

    os.mkdir(f'Models/train_val/{jira_name}')
    open(f'Models/train_val/{jira_name}/file.txt', 'x')

    os.mkdir(f'Models/train_val_after_all_but/{jira_name}')
    open(f'Models/train_val_after_all_but/{jira_name}/file.txt', 'x')

    os.mkdir(f'Models/train_val_after_chi/{jira_name}')
    open(f'Models/train_val_after_chi/{jira_name}/file.txt', 'x')

    os.mkdir(f'Models/word_vector/{jira_name}')
    open(f'Models/word_vector/{jira_name}/file.txt', 'x')

    os.mkdir(f'BERT/Results/{jira_name}')
    open(f'BERT/Results/{jira_name}/file.txt', 'x')

    os.mkdir(f'BERT_With_Cleaning/Results/{jira_name}')
    open(f'BERT_With_Cleaning/Results/{jira_name}/file.txt', 'x')

    os.mkdir(f'Instability_With_BERT/Results/{jira_name}')
    open(f'Instability_With_BERT/Results/{jira_name}/file.txt', 'x')

    os.mkdir(f'Instability_With_BERT/Data/{jira_name}')
    open(f'Instability_With_BERT/Data/{jira_name}/file.txt', 'x')

    os.mkdir(f'Normal_instability/Results/{jira_name}')
    open(f'Normal_instability/Results/{jira_name}/file.txt', 'x')

    os.mkdir(f'Instability_With_BERT/Parameters/{jira_name}')
    open(f'Instability_With_BERT/Parameters/{jira_name}/file.txt', 'x')

    os.mkdir(f'BERT_Balance_Data/Results/{jira_name}')
    open(f'BERT_Balance_Data/Results/{jira_name}/file.txt', 'x')

    os.mkdir(f'Normal_instability/Parameters/{jira_name}')
    open(f'Normal_instability/Parameters/{jira_name}/file.txt', 'x')

    os.mkdir(f'Instability_sample_weight/Results/{jira_name}')
    open(f'Instability_sample_weight/Results/{jira_name}/file.txt', 'x')

    os.mkdir(f'Instability_sample_weight/Parameters/{jira_name}')
    open(f'Instability_sample_weight/Parameters/{jira_name}/file.txt', 'x')

    os.mkdir(f'Data_60_20/Results/{jira_name}')
    open(f'Data_60_20/Results/{jira_name}/file.txt', 'x')

    os.mkdir(f'NLP_Models/Results/{jira_name}')
    open(f'NLP_Models/Results/{jira_name}/file.txt', 'x')

def createBalanceFile():
    d = dict()
    for num in ['Half', 1, 2, 3, 4]:
        with open('Master/Source/jira_data_for_instability_cluster.json') as f:
            jira_data_sources = json.load(f)

        total = 0
        sum = 0
        for jira_name, jira_obj in jira_data_sources.items():
            try:
                results = pd.read_csv(f'Master/BERT_Balance_Data/Results/{jira_name}/Classic_result_5_ratio_{num}.csv')
                size = int(results['size'])
                total += size
                sum += (size * float(results['area_under_pre_recall_curve']))
            except:
                "s"

        d[f'{num}'] = sum / float(total)

    pd.DataFrame([d.values()], columns=d.keys()).to_csv('BERT_Balance_results.csv')




def create_feature_csv(jira_name):
    """
    dbName = f"{DB.DB_NAME}_{jira_name.lower()}"
    mysql_con = DB.connectToSpecificDB(dbName)

    #delete Attachment
    comments_data = pd.read_sql(f'SELECT * FROM {dbName}.features_labels_table_os', con=mysql_con)
    comments_data.to_csv(f'Data/{jira_name}/features_labels_table_os.csv')
    """


if __name__ == '__main__':
    """
    select_topic.start('Apache')
    select_doc_vec.start('Apache')
    create_train_val_tes.start('Apache')
    chi_square.start('Apache')
    remove_features.start('Apache')
    feature_selection_groups.start('Apache')
    run_train_val_optimization.start('Apache')
    run_train_tes_best_parameters.start(jira_name)
    
    with open('Master/Source/jira_data_for_instability_cluster.json') as f:
        jira_data_sources = json.load(f)

    print('START ALL')
    for jira_name, jira_obj in jira_data_sources.items():
        print("start: ", jira_name)
        try:
            #run_fit_setfit_bert.start(jira_name, 'Master/')
            #run_test_setfit_bert.start(jira_name, 'Master/')
            Classic_BERT.start(jira_name, 'Master/')
            #create_feature_csv(jira_name)
        except Exception as e:
            print(e)

    #run_train_tes_best_parameters.start('Apache')
    #createFolders('Hyperledger')
    """
    createBalanceFile()
