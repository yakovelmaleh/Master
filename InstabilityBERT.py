import json
import Data_60_20.run_train_tes_best_parameters as run_train_tes_best_parameters

if __name__ == '__main__':

    print('Start BERT')
    with open('Master/Source/jira_data_for_instability_cluster.json') as f:
        jira_data_sources = json.load(f)

    print('START ALL')
    for jira_name, jira_obj in jira_data_sources.items():
        print(f"start: {jira_name} Instability with Data_60_20")
        #run_train_val_optimization.start(jira_name)
        run_train_tes_best_parameters.start(jira_name)
        print(f'finish {jira_name}')
    print('FINISH ALL Instability with Data_60_20')