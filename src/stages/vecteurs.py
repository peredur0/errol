# coding: utf-8
"""
Code pour la phase de recherche de vectorisation
"""
import datetime
import math
import json
import logging
import sys
import multiprocessing
import tqdm

from src.modules import cmd_psql

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

    set_mots = tfidf_search_word(client, conf)
    mot_labels = tfidf_prepare_schema(conf, set_mots, client)
    cmd_psql.apply_databases_updates(conf, conf.infra['psql']['schema']['tfidf'])
    cmd_psql.insert_data_many(client, 'vect_tfidf_mots_labels', mot_labels)

    client.close()


def tfidf_search_word(client, conf):
    """
    Recherche les mots pour la création de la table
    :param client: <psycopg2.Connection>
    :param conf: <Settings>
    :return: <set>
    """
    with open(conf.infra['psql']['vecteurs']['tfidf']['requetes'], 'r', encoding='utf-8') as file:
        sql_reqs = file.read()

    set_mots = set()
    for query in sql_reqs.split(';'):
        if not query:
            continue
        if query.startswith('\n'):
            query = query[1:]
        if conf.args['limit']:
            query = f"{query} LIMIT {conf.args['limit']}"

        for ligne in cmd_psql.exec_query(client, query):
            set_mots.add(ligne[0])

    unwanted = ['spamassassinsightings',
                'deathtospamdeathtospamdeathtospam',
                'spamassassindevel']

    for mot in unwanted:
        set_mots.discard(mot)

    logger.info("Base vectorielle sur %s mots", len(set_mots))
    return set_mots


def tfidf_prepare_schema(conf, set_mots, client):
    """
    Prépare le fichier json pour la mise à jour de la base de données
    :param conf: <Settings>
    :param set_mots: <set>
    :param client: <psycopg2.Connection>
    """
    schema_db = {"name": "errol", "tables": {}}

    tables_update = {"update": [
        {"name": "controle", "action": "ADD_COLUMN",
         "fields": [{"name": "vect_tfidf", "type": ["DATE"]}]},
        {"name": "controle", "action": "ADD_COLUMN",
         "fields": [{"name": "vect_tfidf_status", "type": ["VARCHAR(256)"]}]}
    ]}

    schema_db['tables'].update(tables_update)
    new_tables = []

    n_table = {
        "name": "vect_tfidf_mots_labels",
        "fields": [
            {"name": "id_mot", "type": ['INT', 'UNIQUE', 'NOT NULL']},
            {"name": "label", "type": ['VARCHAR', 'UNIQUE', 'NOT NULL']}
        ],
        "foreign_keys": [
            {
                "name": "fk_tfidf_mots_labels",
                "field": "id_mot",
                "reference": "nlp_mots_corpus(id_mot)",
                "on_delete": "CASCADE"
            }
        ]
    }
    new_tables.append(n_table)

    n_table = {
        "name": "vect_tfidf_messages",
        "fields": [
            {"name": "id_message", "type": ['INT', 'UNIQUE', 'NOT NULL']}
        ],
        "foreign_keys": [
            {
                "name": "fk_tfidf_messages",
                "field": "id_message",
                "reference": "messages(id_message)",
                "on_delete": "CASCADE"
            }
        ]
    }

    mots_labels = []
    for mot in set_mots:
        id_mot = cmd_psql.get_unique_data(client, 'nlp_mots_corpus', 'id_mot', f"mot LIKE '{mot}'")
        label = f"m_{id_mot}"
        mots_labels.append({'id_mot': id_mot, 'label': label})
        n_table['fields'].append({'name': label, 'type': ['DECIMAL', 'DEFAULT 0']})

    new_tables.append(n_table)
    schema_db['tables']['new'] = new_tables
    full_schema = {'databases': [schema_db]}
    with open(conf.infra['psql']['schema']['tfidf'], 'w', encoding='utf-8') as json_file:
        json.dump(full_schema, json_file, indent=2)
        logger.info("Schéma TFIDF sauvegardé %s", conf.infra['psql']['schema']['tfidf'])

    return mots_labels


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
    query = "SELECT COUNT(*) FROM controle WHERE nlp_status LIKE 'OK'"
    total_docs = cmd_psql.exec_query(client, query)[0][0]
    to_process = [entry['id_message'] for entry in
                  cmd_psql.get_data(client, 'controle', ['id_message'], 'vect_tfidf IS NULL')]
    client.close()

    logger.info("Vectorisation TFIDF %s document à traiter", len(to_process))
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


def tfidf_vectorise(pool_args):
    """
    Vectorise un message
    :param pool_args: <tuple>
    :return: <dict>
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
             f"JOIN vect_tfidf_mots_labels vt ON nd.id_mot = vt.id_mot "
             f"JOIN nlp_mots_corpus nc ON nd.id_mot = nc.id_mot "
             f"WHERE nd.id_message = {id_message};")
    result = cmd_psql.exec_query(client, query)

    data = {
        'controle': {
            'id_message': id_message,
            'vect_tfidf': str(datetime.date.today()),
            'vect_tfidf_status': 'OK'
        },
        'vecteur': {
            'id_message': id_message
        }
    }

    if not result:
        logger.warning("Vecteur vide pour le message %s", id_message)
        data['controle']['vect_tfidf_status'] = "VIDE"
        return data

    for label, occurrence, freq_doc in result:
        data['vecteur'][label] = occurrence * math.log(total_docs/freq_doc)

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
        cmd_psql.insert_data_one(client, 'vect_tfidf_messages', entry['vecteur'])
        id_message = entry['controle'].pop('id_message')
        cmd_psql.update(client, 'controle', entry['controle'], f"id_message = {id_message}")

    client.close()
