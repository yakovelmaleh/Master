import json
import Cross_model_on_One.Electra as Electra

if __name__ == '__main__':
    """
    run_setfit_bert.start('Apache', 'Master/')
    run_test_setfit_bert.start('Apache', 'Master/')
    Classic_BERT.start('Apache', 'Master/')
    
    
    print('Start Classic BERT')
    with open('Master/Source/jira_data_for_instability_cluster.json') as f:
        jira_data_sources = json.load(f)

    print('START ALL Classic_BERT_2')
    for jira_name, jira_obj in jira_data_sources.items():
        print("start: ", jira_name)
        Classic_BERT_MSE_2.start(jira_name, 'Master/')
    print('FINISH ALL')
    """

    Electra.start('Apache')

