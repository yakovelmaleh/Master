import json

import BERT.Classic_BERT_512 as Classic_BERT_512

if __name__ == '__main__':

    print('Start BERT')
    with open('Master/Source/jira_data_for_instability_cluster.json') as f:
        jira_data_sources = json.load(f)

    print('START ALL')
    for jira_name, jira_obj in jira_data_sources.items():
        print(f"start: {jira_name} BERT 512")
        try:
            Classic_BERT_512.start(jira_name, 'Master/')
        except Exception as e:
            print(f"*****************************ERROR*****************************")
            print(e)
        print(f'finish {jira_name}')
    print('FINISH ALL')