import BERT.run_fit_setfit_bert as run_setfit_bert
import BERT.run_test_setfit_bert as run_test_setfit_bert
import BERT.Classic_BERT as Classic_BERT
import Utils.CombineResults as CombineResults

if __name__ == '__main__':
    """
    run_setfit_bert.start('Apache', 'Master/')
    run_test_setfit_bert.start('Apache', 'Master/')
    Classic_BERT.start('Apache', 'Master/')
    """
    print('Start combine_BERT APACHE')
    CombineResults.combineResultsBert('Apache', 'Master/')

