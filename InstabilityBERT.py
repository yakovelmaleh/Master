import json
import Instability_sample_weight.run_train_val_optimization as run_train_val_optimization
import KNN.KNN_Model as KNN_Model
import KNN.KNN_Model as KNN_Model

if __name__ == '__main__':

    print('Start BERT')
    with open('Master/Source/jira_data_for_instability_cluster.json') as f:
        jira_data_sources = json.load(f)

    print('START ALL')
    for jira_name, jira_obj in jira_data_sources.items():
        print(f"start: {jira_name} Instability with KNN_Model")
        KNN_Model.start(jira_name)
        print(f'finish {jira_name}')
    print('FINISH ALL Instability with KNN_Model')