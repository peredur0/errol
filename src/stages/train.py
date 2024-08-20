# coding: utf-8
"""
Fichier pour le développement
"""
import datetime
import json
import logging
import joblib

import pandas as pd
from sklearn import preprocessing
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import precision_recall_fscore_support as score
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn import svm

from src.modules import cmd_psql, cmd_mongo

logger = logging.getLogger(__name__)


def main(conf):
    """
    Fonction principale
    """
    logger.info("Entrainement des modèles")

    logger.info("Récupération des caractéristiques")
    tfidf_vect = get_tfidf_vecteur(conf)
    other_feat = get_other_feat(conf)
    categories = get_categories(conf)

    full_df = tfidf_vect.merge(other_feat, on='id_message')
    full_df = full_df.merge(categories, on='id_message')
    full_df = full_df.sort_index(axis=1)

    logger.info("Nombre de messages: %s - Nombre de caractéristiques: %s",
                full_df.shape[0],
                full_df.shape[1])

    logger.debug("Préparation des données")

    cat_df = full_df['cat']
    vect_feat = full_df.copy()
    vect_feat.drop(['cat', 'categorie', 'id_message'], axis=1, inplace=True)

    vect_only = vect_feat.copy()
    for col in vect_only.columns:
        if not col.startswith('m_'):
            vect_only.drop(col, axis=1, inplace=True)

    datasets = {
        "vect_feat": train_test_split(vect_feat, cat_df, test_size=0.25),
        "vect_only": train_test_split(vect_only, cat_df, test_size=0.25)
    }
    id_ham = get_ham_id(conf)
    logger.info("ID pour les ham - %i", id_ham)

    scaler = None
    results = {}
    for model in conf.args['models']:
        if model == 'rtf':
            logger.info("RandomTree Forest avec les vecteurs tfidf et caractéristiques")
            results['rtf_vect_feat'] = create_random_forest(conf, datasets['vect_feat'], id_ham,
                                                            scaler)
            logger.info("RandomTree Forest avec les vecteurs tfidf seulement")
            results['rtf_vect_only'] = create_random_forest(conf, datasets['vect_only'], id_ham,
                                                            scaler)
            continue

        if model == 'svm':
            logger.info("Support Vector Machine avec les vecteurs tfidf et caractéristiques")
            results['svm_vect_feat'] = create_svm(conf,datasets['vect_feat'], id_ham, scaler)
            logger.info("Support Vector Machine avec les vecteurs tfidf seulement")
            results['svm_vect_only'] = create_svm(conf, datasets['vect_only'], id_ham, scaler)
            continue

    for key, values in results.items():
        logger.info("%s - Precision: %.3f - Recall: %.3f - Accuracy: %.3f - Fscore: %.3f",
                    key, values['precision'], values['recall'], values['accuracy'],
                    values['fscore'])
        save_model(conf, key, values, type(scaler).__name__, id_ham)


def get_tfidf_vecteur(conf):
    """
    Génère le dataframe avec les informations tfidf
    :param conf: <Settings>
    :return: <DataFrame>
    """
    client = cmd_psql.connect_db(user=conf.infra['psql']['user'],
                                 passwd=conf.infra['psql']['pass'],
                                 host=conf.infra['psql']['host'],
                                 port=conf.infra['psql']['port'],
                                 dbname=conf.infra['psql']['db'])
    labels = [entr['label'] for entr in
              cmd_psql.get_data(client, 'vect_mots_labels', ['label'],
                                f"vecteur_algo LIKE 'tfidf' AND langue LIKE '"
                                f"{conf.args['langue']}'")]
    client.close()

    client = cmd_psql.create_engine(user=conf.infra['psql']['user'],
                                    passwd=conf.infra['psql']['pass'],
                                    host=conf.infra['psql']['host'],
                                    port=conf.infra['psql']['port'],
                                    dbname=conf.infra['psql']['db'])

    with open(conf.infra['psql']['queries'], 'r', encoding='utf-8') as q_file:
        queries = json.load(q_file)
    query = queries['train_tfidf_vecteur'].format(langue=conf.args['langue'])
    vecteurs = pd.read_sql(query, client)
    client.dispose()

    vecteurs = vecteurs.pivot_table(values='value', index='id_message', columns='label',
                                    fill_value=0)
    for label in labels:
        if label not in vecteurs.columns:
            vecteurs[label]: 0.0
    vecteurs.reset_index(inplace=True)

    return vecteurs


def get_other_feat(conf):
    """
    Récupère les caractéristiques sélectionnées
    :param conf: <Settings>
    :return: <DataFrame>
    """
    client = cmd_psql.create_engine(user=conf.infra['psql']['user'],
                                    passwd=conf.infra['psql']['pass'],
                                    host=conf.infra['psql']['host'],
                                    port=conf.infra['psql']['port'],
                                    dbname=conf.infra['psql']['db'])

    with open(conf.infra['psql']['queries'], 'r', encoding='utf-8') as q_file:
        queries = json.load(q_file)
    query = queries['train_features'].format(langue=conf.args['langue'])
    vecteurs = pd.read_sql(query, client)
    client.dispose()

    return vecteurs


def get_categories(conf):
    """
    Récupère les caractéristiques sélectionnées
    :param conf: <Settings>
    :return: <DataFrame>
    """
    client = cmd_psql.create_engine(user=conf.infra['psql']['user'],
                                    passwd=conf.infra['psql']['pass'],
                                    host=conf.infra['psql']['host'],
                                    port=conf.infra['psql']['port'],
                                    dbname=conf.infra['psql']['db'])
    with open(conf.infra['psql']['queries'], 'r', encoding='utf-8') as q_file:
        queries = json.load(q_file)
    query = queries['train_categories'].format(langue=conf.args['langue'])
    vecteurs = pd.read_sql(query, client)
    client.dispose()

    return vecteurs


def create_random_forest(conf, datasets, pos_label, normalizer=None):
    """
    Créer un modèle IA via une random tree forest
    :param conf: <Settings>
    :param datasets: <list>
    :param pos_label: <int>
    :param normalizer: <Scaler>
    :return: <dict>
    """
    x_train, x_test, y_train, y_test = datasets
    if normalizer is not None:
        normalize(x_train, normalizer)
        normalize(x_test, normalizer)

    alg_decision_tree = RandomForestClassifier(n_estimators=100, max_depth=100,
                                               n_jobs=conf.infra['cpu_available'])
    model = alg_decision_tree.fit(x_train, y_train)

    predictions = model.predict(x_test)
    precision, recall, fscore, _ = score(y_test, predictions, pos_label=pos_label, average='binary')

    results = {
        'model': model,
        'precision': precision,
        'recall': recall,
        'fscore': fscore,
        'accuracy': (predictions == y_test).sum() / len(predictions),
        'colonnes': x_train.columns
    }
    return results


def create_svm(conf, datasets, pos_label, normalizer=None):
    """
    Créer un modèle IA via une random tree forest
    :param conf: <Settings>
    :param datasets: <list>
    :param pos_label: <int>
    :param normalizer: <Scaler>
    :return: <dict>
    """
    result = {}
    x_train, x_test, y_train, y_test = datasets
    if normalizer is not None:
        normalize(x_train, normalizer)
        normalize(x_test, normalizer)

    alg_svm = svm.SVC()
    svm_params = {'kernel': ['rbf'],
                  'gamma': [0.0001, 0.001, 0.005, 0.01, 1, 10],
                  'C': [0.1, 1, 5, 10, 50, 100]}
    hyper_params_grid = GridSearchCV(alg_svm, svm_params, cv=2, scoring='accuracy',
                                     n_jobs=conf.infra['cpu_available'])
    hyper_params_models = hyper_params_grid.fit(x_train, y_train)
    result['hyper_parms'] = hyper_params_models.best_params_

    best_svm = hyper_params_models.best_estimator_
    result['model'] = best_svm

    predictions = best_svm.predict(x_test)
    precision, recall, fscore, _ = score(y_test, predictions, pos_label=pos_label, average='binary')
    result['precision'] = precision
    result['recall'] = recall
    result['fscore'] = fscore
    result['accuracy'] = (predictions == y_test).sum() / len(predictions)
    result['colonnes'] = x_train.columns

    return result


def normalize(dataframe, normalizer, exclude=None):
    """
    Normalise les données selon une certaine méthode.
    :param dataframe: <Dataframe>
    :param normalizer: <sklean.prepocessing>
    :param exclude: <list>
    """
    if not exclude:
        exclude = []

    for col in dataframe.columns:
        if col in exclude:
            continue
        data = dataframe[[col]].values.astype(float)
        dataframe[col] = normalizer.fit_transform(data)


def get_ham_id(conf):
    """
    Récupère l'id_categorie des ham
    :param conf: <Settings>
    :return: <int>
    """
    client = cmd_psql.connect_db(user=conf.infra['psql']['user'],
                                 passwd=conf.infra['psql']['pass'],
                                 host=conf.infra['psql']['host'],
                                 port=conf.infra['psql']['port'],
                                 dbname=conf.infra['psql']['db'])
    id_ham = cmd_psql.get_unique_data(client, 'categories', 'id_categorie', "nom LIKE 'ham'")
    client.close()
    return id_ham


def save_model(conf, name, values, scaler_name, ham_id):
    """
    Sauvegarde un modèle
    :param conf: <Settings>
    :param name: <str>
    :param values: <dict>
    :param scaler_name: <Scaler>,
    :param ham_id: <int>
    """
    chemin = f"{conf.infra['storage']}/{name}.pkl"
    joblib.dump(values['model'], chemin)
    model = values.pop('model')
    document = {
        'name': name,
        'chemin': chemin,
        'langue': conf.args['langue'],
        'creation': datetime.datetime.now(),
        'colonnes': list(values.pop('colonnes')),
        'evaluation': values,
        'scaler': scaler_name,
        'ham_id': ham_id
    }
    client = cmd_mongo.connect(conf)
    collection = client[conf.infra['mongo']['db']][conf.infra['mongo']['models']]
    collection.delete_many({'name': name})
    collection.insert_one(document)
    client.close()
    joblib.dump(model, chemin)
