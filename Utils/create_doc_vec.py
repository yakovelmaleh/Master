import pandas as pd
from gensim.models.doc2vec import Doc2Vec, TaggedDocument
from nltk import bigrams, ngrams
from numpy import random
random.seed(1)


def tag_docs(docs, col):
    tagged = docs.apply(
        lambda r: TaggedDocument(words=(r['clean_text_new']),  tags=[(r['issue_key'])]), axis=1)

    return tagged


def train_doc2vec_model(tagged_docs, window, size):
    sents = tagged_docs.values
    doc2vec_model = Doc2Vec(sents, size=size, window=window, iter=20, dm=1)
    return doc2vec_model


def vec_for_learning(doc2vec_model, tagged_docs):
    sents = tagged_docs.values
    doc_vectors = [(doc2vec_model.infer_vector(doc.words, steps=20)) for doc in sents]
    return doc_vectors


"""
this function creates the document vector.
input: project data
ouptup: train and test document vector feature
"""
def create_doc_to_vec(train_data, test_data, is_first, size, project_key):

    train_index = train_data.index.values
    test_index = test_data.index.values

    train_data1 = train_data.copy()
    test_data1 = test_data.copy()
    train_tagged = tag_docs(train_data1, 'clean_text_new')
    test_tagged = tag_docs(test_data1, 'clean_text_new')

    if is_first:
        # if the first running we creation the model
        # Init the Doc2Vec model
        model = Doc2Vec(size=size, min_count=2, alpha=0.025, seed=5, epochs=50, dm=1)
        # Build the Volabulary
        model.build_vocab(train_tagged)
        # Train the Doc2Vec model
        model.train(train_tagged, total_examples=model.corpus_count, epochs=model.epochs)
        # saving the created model
        model.save('doc2vec_{}_{}.model'.format(size, project_key))
        # model = Doc2Vec.load('doc2vec_10_{}.model'.format(project_key))

        x_train = model.docvecs.vectors_docs
        x_train = pd.DataFrame(x_train)
        x_test = vec_for_learning(model, test_tagged)
        x_test = pd.DataFrame(x_test)

    else:
        # else we only loading the model
        # loading the model
        d2v_model = Doc2Vec.load('..Models/word_vector/doc2vec_10_{}.model'.format(project_key))

        x_train = d2v_model.docvecs.vectors_docs
        x_train = pd.DataFrame(x_train)
        x_test = vec_for_learning(d2v_model, test_tagged)
        x_test = pd.DataFrame(x_test)
        print("word vector")

    return x_train, x_test

