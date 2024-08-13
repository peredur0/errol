# coding: utf-8
"""
Code pour la phase de recherche de vectorisation
"""
import datetime
import json
import math
import logging
import sys
import multiprocessing
import tqdm

import pandas as pd
from src.modules import cmd_psql
from src.modules import graph

logger = logging.getLogger(__name__)


def main(conf):
    """
    Processus principal de la vectorisation
    """
    for method in conf.args['method']:
        match method:
            case 'tfidf':
                if conf.args['init']:
                    tfidf_init_base(conf)
                tfidf_vect_full(conf)

            case _:
                logger.error("Methode inconnue %s", method)
                sys.exit(1)

    logger.info("Fin des vectorisations")


def tfidf_init_base(conf):
    """
    Initialise la base vectorielle
    :param conf: <Settings>
    :return: <None>
    """
    logger.info('Initialisation de la base vectorielle pour TF-IDF')
    client = cmd_psql.connect_db(user=conf.infra['psql']['user'],
                                 passwd=conf.infra['psql']['pass'],
                                 host=conf.infra['psql']['host'],
                                 port=conf.infra['psql']['port'],
                                 dbname=conf.infra['psql']['db'])

    cmd_psql.apply_databases_updates(conf, conf.infra['psql']['schema']['tfidf'])
    set_mots = tfidf_search_word(client, conf)
    langue = conf.args['langue']
    mots_labels = []
    for mot in set_mots:
        id_mot = cmd_psql.get_unique_data(client,
                                          'nlp_mots_corpus',
                                          'id_mot',
                                          f"mot LIKE '{mot}' AND langue LIKE '{langue}'")
        label = f"m_{id_mot}"
        mots_labels.append({'id_mot': id_mot, 'vecteur_algo': 'tfidf', 'label': label,
                            'langue': langue})

    cmd_psql.insert_data_many(client, 'vect_mots_labels', mots_labels)

    client.close()


def tfidf_search_word(client, conf):
    """
    Recherche les mots pour la création de la table
    :param client: <psycopg2.Connection>
    :param conf: <Settings>
    :return: <set>
    """
    with open(conf.infra['psql']['queries'], 'r', encoding='utf-8') as file:
        sql_reqs = json.load(file)

    set_mots = set()
    for query in sql_reqs['tfidf']:
        if conf.args['limit']:
            query = f"{query} LIMIT {conf.args['limit']}"

        query = query.format(langue=conf.args['langue'])
        for ligne in cmd_psql.exec_query(client, query):
            set_mots.add(ligne[0])

    unwanted = ['spamassassinsightings',
                'deathtospamdeathtospamdeathtospam',
                'spamassassindevel']

    for mot in unwanted:
        set_mots.discard(mot)

    logger.info("Base vectorielle sur %s mots", len(set_mots))
    return set_mots


def tfidf_vect_full(conf):
    """
    Prépare les données pour la vectorisation tfidf
    :param conf: <Settings>
    """
    client = cmd_psql.connect_db(user=conf.infra['psql']['user'],
                                 passwd=conf.infra['psql']['pass'],
                                 host=conf.infra['psql']['host'],
                                 port=conf.infra['psql']['port'],
                                 dbname=conf.infra['psql']['db'])
    query = (f"SELECT COUNT(*) FROM controle co "
             f"JOIN messages me ON co.id_message = me.id_message "
             f"WHERE co.nlp_status LIKE 'OK' "
             f"AND me.langue LIKE '{conf.args['langue']}'")
    total_docs = cmd_psql.exec_query(client, query)[0][0]

    query = (f"SELECT co.id_message FROM controle co "
             f"JOIN messages me ON co.id_message = me.id_message "
             f"WHERE co.vect_tfidf IS NULL "
             f"AND me.langue LIKE '{conf.args['langue']}'")
    ctrl_docs = cmd_psql.exec_query(client, query)
    if ctrl_docs == -1:
        logger.error("Echec de recherche des documents à traité")
        return

    to_process = [entry[0] for entry in ctrl_docs]
    client.close()

    logger.info("Vectorisation TFIDF %s documents à traiter", len(to_process))
    pool_args = [(conf, total_docs, id_message) for id_message in to_process]
    with multiprocessing.Pool(conf.infra['cpu_available']) as pool:
        result = list(tqdm.tqdm(pool.imap(tfidf_vectorise, pool_args),
                                desc="Vectorisation TFIDF",
                                leave=False,
                                total=len(pool_args),
                                disable=conf.args['progress_bar']))
    result = [doc for doc in result if doc]
    logger.info('%s documents vectorisés', len(result))

    tfidf_store_vecteurs(conf, result)

    if conf.args['graph']:
        tfidf_graph(conf)


def tfidf_vectorise(pool_args):
    """
    Vectorise un message
    :param pool_args: <tuple>
    :return: <list>
    """
    conf = pool_args[0]
    total_docs = pool_args[1]
    id_message = pool_args[2]

    client = cmd_psql.connect_db(user=conf.infra['psql']['user'],
                                 passwd=conf.infra['psql']['pass'],
                                 host=conf.infra['psql']['host'],
                                 port=conf.infra['psql']['port'],
                                 dbname=conf.infra['psql']['db'])

    query = (f"SELECT vt.label, nd.occurrence, nc.freq_documents "
             f"FROM nlp_mots_documents nd "
             f"JOIN vect_mots_labels vt ON nd.id_mot = vt.id_mot "
             f"JOIN nlp_mots_corpus nc ON nd.id_mot = nc.id_mot "
             f"WHERE nd.id_message = {id_message} "
             f"AND vt.vecteur_algo LIKE 'tfidf';")
    result = cmd_psql.exec_query(client, query)

    data = {
        'id_message': id_message,
        'controle': {
            'vect_tfidf': str(datetime.date.today()),
            'vect_tfidf_status': 'OK'
        },
        'vecteur': []
    }

    if not result:
        logger.warning("Vecteur vide pour le message %s", id_message)
        data['controle']['vect_tfidf_status'] = "VIDE"
        return data

    for label, occ, freq_doc in result:
        data['vecteur'].append(
            {
                "label": label,
                "value": occ * math.log(total_docs/freq_doc),
                "vecteur_algo": 'tfidf'
            }
        )

    client.close()
    return data


def tfidf_store_vecteurs(conf, result):
    """
    Stocke les vecteurs dans leur base.
    :param conf: <Settings>
    :param result: <list>
    """
    logger.info("Mise en base")
    client = cmd_psql.connect_db(user=conf.infra['psql']['user'],
                                 passwd=conf.infra['psql']['pass'],
                                 host=conf.infra['psql']['host'],
                                 port=conf.infra['psql']['port'],
                                 dbname=conf.infra['psql']['db'])
    for entry in tqdm.tqdm(result,
                           desc="Mise en base",
                           leave=False,
                           disable=conf.args['progress_bar']):
        id_message = entry['id_message']
        for case in entry['vecteur']:
            case.update({'id_message': id_message})

        if entry['vecteur']:
            res = cmd_psql.insert_data_many(client, 'vect_messages', entry['vecteur'])
            if res == -1:
                logger.error("Echec d'insertion du message %s - arrêt du stockage", id_message)
                break
        cmd_psql.update(client, 'controle', entry['controle'], f"id_message = {id_message}")

    client.close()


def tfidf_graph(conf):
    """
    Affiche les données de la vectorisation
    :param conf: <Settings>
    """
    client = cmd_psql.create_engine(user=conf.infra['psql']['user'],
                                    passwd=conf.infra['psql']['pass'],
                                    host=conf.infra['psql']['host'],
                                    port=conf.infra['psql']['port'],
                                    dbname=conf.infra['psql']['db'])

    with open(conf.infra['psql']['vecteurs']['tfidf']['data'], 'r', encoding='utf-8') as file:
        sql_reqs = file.read()

    queries = sql_reqs.split(';')
    df_1 = pd.read_sql_query(queries[0], client)
    df_1 = df_1.drop(['document'], axis=1)

    df_2 = pd.read_sql_query(queries[1], client)
    df_2 = df_2.drop(['label'], axis=1)
    graph.vecteurs_dash(df_1, df_2, conf)

    client.dispose()