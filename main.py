import json
import os

import RunModels.select_num_topic_model as select_num_topic_model
import RunModels.select_length_doc_vector as select_length_doc_vector
import RunModels.create_train_val_tes as create_train_val_tes
import RunModels.chi_square as chi_square
import RunModels.remove_features as remove_features
import RunModels.feature_selection_groups as feature_selection_groups
import Normal_instability.run_train_val_optimization as run_train_val_optimization
import Normal_instability.run_train_tes_best_parameters as run_train_tes_best_parameters
import pandas as pd
# import Utils.DataBase as DB
import Utils.CombineResults as CombineResults
import BERT.run_fit_setfit_bert as run_fit_setfit_bert
import BERT.run_test_setfit_bert as run_test_setfit_bert
import BERT.Classic_BERT as Classic_BERT


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
    print('Start BERT')
    with open('Master/Source/jira_data_for_instability_cluster.json') as f:
        jira_data_sources = json.load(f)

    print('START ALL')
    for jira_name, jira_obj in jira_data_sources.items():
        print(f"start: {jira_name} Instability without BERT")
        run_train_val_optimization.start(jira_name)
        run_train_tes_best_parameters.start(jira_name)
        print(f'finish {jira_name}')
    print('FINISH ALL')
