import json
import NLP_Models_Current.Run_gpt2 as run_model

if __name__ == '__main__':
    """
    run_setfit_bert.start('Apache', 'Master/')
    run_test_setfit_bert.start('Apache', 'Master/')
    Classic_BERT.start('Apache', 'Master/')
    
    
    """
    print('Start Classic BERT')
    with open('Master/Source/jira_data_for_instability_cluster.json') as f:
        jira_data_sources = json.load(f)

    print('START')
    for jira_name, jira_obj in jira_data_sources.items():
        print("start: ", jira_name)
        run_model.run_over_sampling(jira_name)
    print('FINISH ALL')

