# coding: utf-8
"""
Fichier pour le développement
"""

import logging

import pandas as pd
from sklearn import preprocessing

from src.modules import graph
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


def create_random_forest(conf, train_dfs):
    """
    Créer un modèle IA via une random tree forest:
    :param conf: <Settings>
    :param full_df: <DataFrame>
    """

def main(conf):
    """
    Fonction principale
    """
    logger.info("DEVELOPPEMENT")

    logger.info("Récupération des caractéristiques")
    tfidf_vect = get_tfidf_vecteur(conf)
    other_feat = get_other_feat(conf)
    categories = get_categories(conf)

    full_df = tfidf_vect.merge(other_feat, on='id_message')
    full_df = full_df.merge(categories, on='id_message')

    logger.info("Nombre de messages: %s - Nombre de caractéristiques: %s",
                full_df.shape[0],
                full_df.shape[1])
