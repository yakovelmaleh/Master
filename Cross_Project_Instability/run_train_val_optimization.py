import json
import pandas as pd
import Cross_Project_Instability.ml_algorithms_optimization as ml_algorithms_optimization
from pathlib import Path
import os
import Utils.GetInstabilityData as GetInstabilityData


def addPath(path):
    return str(Path(os.getcwd()).joinpath(path))


def start():
    """
    this script read all the feature data (train and validation only), and run the optimization of the hyper parameters (ml_algorithms_optimization)
    """

    for k_unstable in [5, 10, 15, 20]:
        all_but_one_group = True
        # get data

        features_data_train, features_data_valid = GetInstabilityData.get_data_all_train_valid('Master/', k_unstable)
        labels_train, labels_valid = GetInstabilityData.get_all_labels_train_valid('Master/', k_unstable)

        names = list(features_data_train.columns.values)
        if 'dominant_topic' in names:
            features_data_train = pd.get_dummies(features_data_train, columns=['dominant_topic'],
                                                 drop_first=True)
            features_data_valid = pd.get_dummies(features_data_valid, columns=['dominant_topic'],
                                                 drop_first=True)
            # Get missing columns in the training test
            missing_cols = set(features_data_train.columns) - set(features_data_valid.columns)
            # Add a missing column in test set with default value equal to 0
            for c in missing_cols:
                features_data_valid[c] = 0
            # Ensure the order of column in the test set is in the same order than in train set
            features_data_valid = features_data_valid[features_data_train.columns]

        # get only train of the test set

        # run optimization:
        ml_algorithms_optimization.run_model_optimization(features_data_train, features_data_valid,
                                                          labels_train['usability_label'],
                                                          labels_valid['usability_label'], k_unstable,
                                                          all_but_one_group)


if __name__ == "__main__":
    """
    this script read all the feature data (train and validation only), and run the optimization of the hyper parameters (ml_algorithms_optimization)
    """
    print('Hello World')
