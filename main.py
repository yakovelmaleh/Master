import pandas as pd
import RunModels.select_num_topic_model as select_topic
import RunModels.select_length_doc_vector as select_doc_vec
import RunModels.create_train_val_tes as create_train_val_tes
import RunModels.chi_square as chi_square
import RunModels.remove_features as remove_features
import RunModels.feature_selection_groups as feature_selection_groups
import RunModels.run_train_val_optimization as run_train_val_optimization
import RunModels.run_train_tes_best_parameters as run_train_tes_best_parameters

if __name__ == '__main__':
    """
    select_topic.start('Apache')
    select_doc_vec.start('Apache')
    create_train_val_tes.start('Apache')
    chi_square.start('Apache')
    remove_features.start('Apache')
    feature_selection_groups.start('Apache')
    run_train_val_optimization.start('Apache')
    """
    print('start Apache')
    run_train_tes_best_parameters.start('Apache')
    print('finish Apache')