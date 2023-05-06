import pandas as pd
import RunModels.select_num_topic_model as select_topic
import RunModels.select_length_doc_vector as select_doc_vec
import RunModels.create_train_val_tes as create_train_val_tes
import RunModels.chi_square as chi_square

if __name__ == '__main__':
    """
    select_topic.start('Apache')
    select_doc_vec.start('Apache')
    create_train_val_tes.start('Apache')
    """
    print('start Apache')
    chi_square.start('Apache')
    print('finish Apache')