import json

import KNN.KNN_Model_with_dropping as KNN_Model_with_dropping

if __name__ == '__main__':

    print('Start BERT')
    with open('Master/Source/jira_data_for_instability_cluster.json') as f:
        jira_data_sources = json.load(f)

    print('START ALL')
    for jira_name, jira_obj in jira_data_sources.items():
        print(f"start: {jira_name} KNN_Model_with_dropping")
        if jira_name not in ['Apache', 'Hyperledger', 'IntelDAOS']:
            KNN_Model_with_dropping.start(jira_name)
        print(f'finish {jira_name}')
    print('FINISH ALL KNN_Model_with_dropping')