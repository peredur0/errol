# coding: utf-8
"""
Fichier pour le développement
"""

import logging
import pickle

import pandas as pd
from sklearn import preprocessing
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import precision_recall_fscore_support as score
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn import svm

from src.modules import cmd_psql

logger = logging.getLogger(__name__)


def get_tfidf_vecteur(conf):
    """
    Génère le dataframe avec les informations tfidf;
    :param conf: <Settings>
    :return: <DataFrame>
    """
    client = cmd_psql.connect_db(user=conf.infra['psql']['user'],
                                 passwd=conf.infra['psql']['pass'],
                                 host=conf.infra['psql']['host'],
                                 port=conf.infra['psql']['port'],
                                 dbname=conf.infra['psql']['db'])
    labels = [entr['label'] for entr in
              cmd_psql.get_data(client, 'vect_mots_labels', ['label'], "vecteur_algo LIKE 'tfidf'")]
    client.close()

    client = cmd_psql.create_engine(user=conf.infra['psql']['user'],
                                    passwd=conf.infra['psql']['pass'],
                                    host=conf.infra['psql']['host'],
                                    port=conf.infra['psql']['port'],
                                    dbname=conf.infra['psql']['db'])
    query = """
        SELECT vm.id_message, vm.label, vm.value
        FROM vect_messages vm
        JOIN controle co ON vm.id_message = co.id_message
        WHERE vm.vecteur_algo LIKE 'tfidf'
        AND co.vect_tfidf_status LIKE 'OK';
        """
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
    query = """
           SELECT co.id_message, li.nombre, li.url,  
           fh.nombre_hapax hapax, fh.ratio_mots_uniques hapax_uniques, 
           fm.char_majuscules majuscules, fp.espace 
           FROM controle co 
           JOIN liens li ON co.id_message = li.id_message
           JOIN features_hapax fh ON co.id_message = fh.id_message
           JOIN features_mots fm ON co.id_message = fm.id_message
           JOIN features_ponctuations fp ON co.id_message = fp.id_message
           WHERE co.vect_tfidf_status LIKE 'OK';
           """
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
    query = """
               SELECT co.id_message, me.id_categorie cat, ca.nom categorie
               FROM controle co 
               JOIN messages me ON me.id_message = co.id_message
               JOIN categories ca ON me.id_categorie = ca.id_categorie
               WHERE co.vect_tfidf_status LIKE 'OK';
               """
    vecteurs = pd.read_sql(query, client)
    client.dispose()

    return vecteurs


def create_random_forest(datasets, pos_label):
    """
    Créer un modèle IA via une random tree forest
    :param datasets: <list>
    :param pos_label: <int>
    :return: <dict>
    """
    x_train, x_test, y_train, y_test = datasets
    alg_decision_tree = RandomForestClassifier(n_estimators=100, max_depth=100, n_jobs=-1)
    model = alg_decision_tree.fit(x_train, y_train)

    predictions = model.predict(x_test)
    precision, recall, fscore, _ = score(y_test, predictions, pos_label=pos_label, average='binary')

    results = {
        'model': model,
        'precision': precision,
        'recall': recall,
        'fscore': fscore,
        'accuracy': (predictions == y_test).sum() / len(predictions)
    }
    return results


def create_svm(datasets, pos_label):
    """
    Créer un modèle IA via une random tree forest
    :param datasets: <list>
    :param pos_label: <int>
    :return: <dict>
    """
    result = {}
    x_train, x_test, y_train, y_test = datasets
    alg_svm = svm.SVC()
    svm_params = {'kernel': ['rbf'],
                  'gamma': [0.0001, 0.001, 0.005, 0.01, 1, 10],
                  'C': [0.1, 1, 5, 10, 50, 100]}
    hyper_params_grid = GridSearchCV(alg_svm, svm_params, cv=2, scoring='accuracy', n_jobs=-1)
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
    normalize(full_df, preprocessing.StandardScaler(), exclude=['id_message', 'cat', 'categorie'])

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

    results = {}
    for model in conf.args['models']:
        if model == 'rtf':
            logger.info("RandomTree Forest avec les vecteurs tfidf et caractéristiques")
            results['rtf_vect_feat'] = create_random_forest(datasets['vect_feat'], id_ham)
            logger.info("RandomTree Forest avec les vecteurs tfidf seulement")
            results['rtf_vect_only'] = create_random_forest(datasets['vect_only'], id_ham)
            continue

        if model == 'svm':
            logger.info("Support Vector Machine avec les vecteurs tfidf et caractéristiques")
            results['svm_vect_feat'] = create_svm(datasets['vect_feat'], id_ham)
            logger.info("Support Vector Machine avec les vecteurs tfidf seulement")
            results['svm_vect_only'] = create_svm(datasets['vect_only'], id_ham)
            continue

    for key, values in results.items():
        logger.info("%s - Precision: %.3f - Recall: %.3f - Accuracy: %.3f - Fscore: %.3f",
                    key, values['precision'], values['recall'], values['accuracy'],
                    values['fscore'])
        with open(f"{conf.infra['storage']}/{key}.pickle", 'wb') as pkl_file:
            pickle.dump(values['model'], pkl_file)
