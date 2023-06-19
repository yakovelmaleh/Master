import json

import Instability_sample_weight.run_train_tes_best_parameters as run_train_tes_best_parameters
import Instability_sample_weight.run_train_val_optimization as run_train_val_optimization

if __name__ == '__main__':
    """
    print('Start BERT')
    
    """
    with open('Master/Source/jira_data_for_instability_cluster.json') as f:
        jira_data_sources = json.load(f)

    print('START ALL')
    for jira_name, jira_obj in jira_data_sources.items():
        print(f"start: {jira_name} KNN_Model_with_dropping")
        if jira_name != 'Apache':
            run_train_val_optimization.start(jira_name, False)
        run_train_tes_best_parameters.start(jira_name, False)
        print(f'finish {jira_name}')
    print('FINISH ALL KNN_Model_with_dropping')





