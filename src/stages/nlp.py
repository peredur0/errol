# coding: utf-8
"""
Traitement NLP via Stanza et mise en base des occurrences
"""
import json
import re
import datetime
import logging

import nltk
import stanza
import torch.cuda
import tqdm
import pandas as pd

from nltk.corpus import stopwords
from src.modules import cmd_mongo
from src.modules import cmd_psql
from src.annexes import zipf

logger = logging.getLogger(__name__)


def main(conf):
    """
    Processus principal
    :param conf: <Settings>
    :return: None
    """
    logger.info("Traitement NLP")
    logger.info("Mise à jour de la base psql")
    cmd_psql.apply_databases_updates(conf, conf.infra['psql']['schema']['nlp'])

    nltk.download("stopwords")
    match conf.args['langue']:
        case 'en':
            stopw = set(stopwords.words('english'))
        case 'fr':
            stopw = set(stopwords.words('french'))
        case _:
            stopw = set()

    pattern = re.compile(r'\w+')
    stz_pipe = stanza.Pipeline(lang=conf.args['langue'], processors='tokenize,mwt,pos,lemma')

    documents = process_pipeline(conf, stz_pipe, pattern, stopw)
    insert_pipeline(conf, documents)

    if conf.args['stats']:
        nlp_stats(conf)
    logger.info("Fin du processus NLP")


def get_all_mails(conf):
    """
    Récupère tous les mails de la base mongo.
    :param conf: <Settings>
    :return: <list> of dict
    """
    documents = []
    for arg_collection in conf.infra['mongo']['collection']:
        logger.info("Récupération des documents dans %s", arg_collection)
        client = cmd_mongo.connect(conf)
        collection = client[conf.infra['mongo']['db']][arg_collection]
        documents += cmd_mongo.get_all_documents(collection,
                                                 d_filter={'langue': conf.args['langue']},
                                                 include=['_id', 'message'])
        client.close()

    return documents


def process_pipeline(conf, stz_pipe, pattern, stopw):
    """
    Fonction executé dans un processus séparé
    :param conf: <Settings>
    :param stz_pipe: <stanza.Pipeline>
    :param pattern: <re.compile>
    :param stopw: <set>
    """
    results = []
    logger.info("Début du processus traitement nlp")
    for document in tqdm.tqdm(get_all_mails(conf),
                              desc="Traitement NLP",
                              leave=False,
                              disable=conf.args['progress_bar']):
        data = nlp_pipeline(conf, document, stz_pipe, pattern, stopw)
        if data:
            results.append(data)

    logger.info("Fin du traitement nlp")
    return results


def insert_pipeline(conf, documents):
    """
    Processus de mise en base pour les mots des documents
    :param conf: <Settings>
    :param documents: <list>
    """
    logger.info("Début de la mise en base")
    client = cmd_psql.connect_db(user=conf.infra['psql']['user'],
                                 passwd=conf.infra['psql']['pass'],
                                 host=conf.infra['psql']['host'],
                                 port=conf.infra['psql']['port'],
                                 dbname=conf.infra['psql']['db'])
    lang = conf.args['langue']
    for data in tqdm.tqdm(documents,
                          desc="Mise en base",
                          leave=False,
                          disable=conf.args['progress_bar']):

        for mot, freq in data['bag'].items():
            mot = mot.replace("'", "")
            table = 'nlp_mots_corpus'
            clause = f"mot LIKE '{mot}' and langue LIKE '{lang}'"
            id_mot = cmd_psql.get_unique_data(client, table, 'id_mot', clause)

            if not id_mot:
                cmd_psql.insert_data_one(client, table, {'mot': mot, 'langue': lang})
                id_mot = cmd_psql.get_unique_data(client, table, 'id_mot', clause)

            if not id_mot:
                logger.error("Echec d'insertion du mot '%s' du message %s", mot,
                             data['id_message'])
                continue

            clause = f"id_mot = {id_mot}"
            fields = ['freq_corpus', 'freq_documents', f'freq_{data["categorie"]}']
            freq_mot = cmd_psql.get_data(client, table, fields, clause)[0]

            freq_mot['freq_corpus'] += freq
            freq_mot['freq_documents'] += 1
            freq_mot[f'freq_{data["categorie"]}'] += 1
            cmd_psql.update(client, table, freq_mot, clause)

            table = 'nlp_mots_documents'
            cmd_psql.insert_data_one(client, table, {'id_mot': id_mot,
                                                     'id_message': data['id_message'],
                                                     'occurrence': freq})

        table = 'controle'
        clause = f"id_message = {data['id_message']}"
        cmd_psql.update(client, table, {key: value for key, value
                                        in data.items() if key in ['nlp', 'nlp_status']}, clause)

    client.close()
    logger.info("Fin de la mise en base")


def nlp_pipeline(conf, document, stz_pipe, pattern, stopw):
    """
    Pipeline du traitement pour un message
    :param conf: <Settings>
    :param document: <dict>
    :param stz_pipe: <stanza.pipeline>
    :param pattern: <re.compile>
    :param stopw: <set>
    :return: <dict>
    """
    client_psql = cmd_psql.connect_db(user=conf.infra['psql']['user'],
                                      passwd=conf.infra['psql']['pass'],
                                      host=conf.infra['psql']['host'],
                                      port=conf.infra['psql']['port'],
                                      dbname=conf.infra['psql']['db'])
    clause = f"hash LIKE '{document['_id']}'"
    psql_data = cmd_psql.get_data(client_psql, 'messages', ['id_message'], clause)
    if not psql_data:
        logger.warning("Message %s absent de la base PSQL", document['_id'])
        return None
    data = {'id_message': psql_data[0]['id_message']}

    clause = f"id_message = {data['id_message']}"
    if nlp_ctrl := cmd_psql.get_unique_data(client_psql, 'controle', 'nlp', clause):
        logger.debug("Message %s déjà traité pour la partie nlp - %s", document['_id'],
                     nlp_ctrl)
        return None

    query = (f"SELECT c.nom as categorie FROM messages m "
             f"JOIN categories c ON m.id_categorie = c.id_categorie "
             f"WHERE m.id_message = {data['id_message']};")
    data['categorie'] = cmd_psql.exec_query(client_psql, query)[0][0]
    client_psql.close()

    data.update({'nlp': str(datetime.date.today()), 'nlp_status': 'OK'})
    try:
        data.update({
            'bag': zipf.freq_mot(lemmatise(document['message'], stopw, stz_pipe, pattern))
        })
    except TypeError as err:
        logger.warning("Erreur de traitement %s - %s", document['_id'], err)
        data.update({'bag': {}, 'nlp_status': 'Type error'})
    except torch.cuda.OutOfMemoryError as err:
        logger.warning("Erreur de traitement %s - %s", document['_id'], err)
        data.update({'bag': {}, 'nlp_status': 'Memory error'})

    return data


def lemmatise(message, stopwds, pipeline, pattern):
    """
    Réduit un texte avec les principes de lemmatisation.
    Retire les ponctuations et les stopwords
    :param message: <str> message à traiter
    :param stopwds: <list> liste des stopwords
    :param pipeline: <stanza.Pipeline> Pipeline nlp
    :param pattern: <re.compile>
    :return: <list> message lemmatisé sous forme de liste de mot
    """
    doc = pipeline(message)
    lemma = [mot.lemma for phrase in doc.sentences for mot in phrase.words]
    return [lem.lower() for lem in lemma if re.match(pattern, lem) and lem.lower() not in stopwds]


def nlp_stats(conf):
    """
    Récupère et affiche les statistiques sur les mots:
    :param conf: <Settings>
    """
    client = cmd_psql.create_engine(user=conf.infra['psql']['user'],
                                    passwd=conf.infra['psql']['pass'],
                                    host=conf.infra['psql']['host'],
                                    port=conf.infra['psql']['port'],
                                    dbname=conf.infra['psql']['db'])

    with open(conf.infra['psql']['queries'], 'r', encoding='utf-8') as file:
        sql_queries = json.load(file)

    stats_df = []
    for query in sql_queries['sql_nlp']:
        new_df = pd.read_sql_query(query.format(langue=conf.args['langue']), client)
        stats_df.append(new_df.to_string(index=False))

    logger.info("Données en base - \n%s", '\n'.join(stats_df))

    client.dispose()
