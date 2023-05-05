import pandas as pd
import RunModels.select_num_topic_model as select

if __name__ == '__main__':
    print('hello World')
    data = pd.read_csv('./Data/Apache/features_labels_table_os.csv')
    data.to_csv('./Models/topic_model/a.csv')