import numpy as np
import pandas as pd
import tensorflow as tf
from transformers import RobertaTokenizer, TFRobertaModel
import Utils.NLP_Models.Get_Results as Get_Results

import warnings

warnings.filterwarnings("ignore")


def setUp():
    try:
        # TPU detection. No parameters necessary if TPU_NAME environment variable is set (always set in Kaggle)
        tpu = tf.distribute.cluster_resolver.TPUClusterResolver()
        tf.config.experimental_connect_to_cluster(tpu)
        tf.tpu.experimental.initialize_tpu_system(tpu)
        strategy = tf.distribute.experimental.TPUStrategy(tpu)
        print('Running on TPU ', tpu.master())
    except ValueError:
        # Default distribution strategy in Tensorflow. Works on CPU and single GPU.
        strategy = tf.distribute.get_strategy()

    print('Number of replicas:', strategy.num_replicas_in_sync)
    return strategy


def roberta_encode(texts, tokenizer, MAX_LEN):
    ct = len(texts)
    input_ids = np.ones((ct, MAX_LEN), dtype='int32')
    attention_mask = np.zeros((ct, MAX_LEN), dtype='int32')
    token_type_ids = np.zeros((ct, MAX_LEN), dtype='int32')  # Not used in text classification

    for k, text in enumerate(texts):
        # Tokenize
        tok_text = tokenizer.tokenize(text)

        # Truncate and convert tokens to numerical IDs
        enc_text = tokenizer.convert_tokens_to_ids(tok_text[:(MAX_LEN - 2)])

        input_length = len(enc_text) + 2
        input_length = input_length if input_length < MAX_LEN else MAX_LEN

        # Add tokens [CLS] and [SEP] at the beginning and the end
        input_ids[k, :input_length] = np.asarray([0] + enc_text + [2], dtype='int32')

        # Set to 1s in the attention input
        attention_mask[k, :input_length] = 1

    return {
        'input_word_ids': input_ids,
        'input_mask': attention_mask,
        'input_type_ids': token_type_ids
    }


def build_model(n_categories, strategy, MAX_LEN, MODEL_NAME):
    with strategy.scope():
        input_word_ids = tf.keras.Input(shape=(MAX_LEN,), dtype=tf.int32, name='input_word_ids')
        input_mask = tf.keras.Input(shape=(MAX_LEN,), dtype=tf.int32, name='input_mask')
        input_type_ids = tf.keras.Input(shape=(MAX_LEN,), dtype=tf.int32, name='input_type_ids')

        # Import RoBERTa model from HuggingFace
        roberta_model = TFRobertaModel.from_pretrained(MODEL_NAME)
        x = roberta_model(input_word_ids, attention_mask=input_mask, token_type_ids=input_type_ids)

        # Huggingface transformers have multiple outputs, embeddings are the first one,
        # so let's slice out the first position
        x = x[0]

        x = tf.keras.layers.Dropout(0.1)(x)
        x = tf.keras.layers.Flatten()(x)
        x = tf.keras.layers.Dense(256, activation='relu')(x)
        x = tf.keras.layers.Dense(n_categories, activation='softmax')(x)

        model = tf.keras.Model(inputs=[input_word_ids, input_mask, input_type_ids], outputs=x)
        model.compile(
            optimizer=tf.keras.optimizers.Adam(lr=1e-5),
            loss='sparse_categorical_crossentropy',
            metrics=['accuracy'])

        return model


def start(jira_name, model_name, data_train_list, data_test_list, path_to_save):
    results = pd.DataFrame(columns=['project_key', 'usability_label',
                                       'accuracy', 'confusion_matrix', 'classification_report',
                                       'area_under_pre_recall_curve', 'avg_precision',
                                       'area_under_roc_curve', 'y_pred'])

    strategy = setUp()
    MODEL_NAME = 'roberta-base'
    MAX_LEN = 128

    BATCH_SIZE = 8 * strategy.num_replicas_in_sync
    EPOCHS = 3
    for k_unstable in [5, 10, 15, 20]:
        data_train = data_train_list[f'{k_unstable}']
        data_test = data_test_list[f'{k_unstable}']

        X_train = data_train[['sentence']].to_numpy().reshape(-1)
        y_train = data_train[['label']].to_numpy().reshape(-1)

        X_test = data_test[['sentence']].to_numpy().reshape(-1)
        y_test = data_test[['label']].to_numpy().reshape(-1)

        tokenizer = RobertaTokenizer.from_pretrained(MODEL_NAME)

        X_train = roberta_encode(X_train, tokenizer, MAX_LEN)
        X_test = roberta_encode(X_test, tokenizer, MAX_LEN)

        y_train = np.asarray(y_train, dtype='int32')
        y_test = np.asarray(y_test, dtype='int32')

        with strategy.scope():
            model = build_model(2, strategy, MAX_LEN, MODEL_NAME)
            model.summary()

        with strategy.scope():
            print('Training...')
            history = model.fit(X_train,
                                y_train,
                                epochs=EPOCHS,
                                batch_size=BATCH_SIZE,
                                verbose=1,
                                validation_data=(X_test, y_test))

        y_score = model.predict(X_test)
        y_pred = [np.argmax(i) for i in y_score]

        accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc = \
            Get_Results.get_results(y_score=y_score, y_pred=y_pred,
                                    model_name=f'{jira_name}_{k_unstable}_RoBERTaV2_{model_name}', y_test=y_test,
                                    path_to_save=path_to_save)

        d = {'project_key': jira_name, 'usability_label': k_unstable,
             'accuracy': accuracy,
             'confusion_matrix': confusion_matrix,
             'classification_report': classification_report,
             'area_under_pre_recall_curve': area_under_pre_recall_curve,
             'avg_precision': average_precision, 'area_under_roc_curve': auc}

        results = pd.concat([results, pd.DataFrame([d.values()], columns=d.keys())], ignore_index=True)

    results.to_csv(
        f'{path_to_save}/Results_RoBERTaV2_{jira_name}_{model_name}.csv', index=False)
