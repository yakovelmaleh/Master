import json

import BERT_Unbalance_Data.ALBERT_2 as ALBERT_2

if __name__ == '__main__':

    print('Start BERT Unbalanced')
    with open('Master/Source/jira_data_for_instability_cluster.json') as f:
        jira_data_sources = json.load(f)

    print('START ALL')
    for jira_name, jira_obj in jira_data_sources.items():
        print(f"start: {jira_name} ALBERT")
        try:
            ALBERT_2.start(jira_name, 'Master/')
        except Exception as e:
            print(f"*****************************ERROR*****************************")
            print(e)
        print(f'finish {jira_name}')
    print('FINISH ALL')