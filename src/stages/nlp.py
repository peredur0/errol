# coding: utf-8
"""
Traitement NLP via Stanza et mise en base des occurrences
"""
import re
import time
import datetime
import logging
import multiprocessing

import nltk
import stanza
import torch.cuda
import tqdm

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

    multiprocessing.set_start_method('spawn')

    nltk.download("stopwords")
    en_stop = set(stopwords.words('english'))
    pattern = re.compile(r'\w+')

    data_queue = multiprocessing.Queue()
    process = [
        multiprocessing.Process(target=process_pipeline,
                                args=(conf, pattern, en_stop, data_queue)),
        multiprocessing.Process(target=process_database, args=(conf, data_queue))
    ]
    for p in process:
        p.start()
        p.join()

    logger.info("Fin du processus NLP")

def process_logger():
    """
    Défini le logger pour les subprocess
    """
    p_logger = logging.getLogger("nlp.subprocess")
    p_logger.setLevel(logging.INFO)
    log_format = logging.Formatter('%(asctime)s [%(levelname)s] - (%(name)s) : %(message)s')
    log_handle = logging.StreamHandler()
    log_handle.setFormatter(log_format)
    p_logger.addHandler(log_handle)
    return p_logger


def get_all_mails(conf):
    """
    Récupère tous les mails de la base mongo.
    :param conf: <Settings>
    :return: <list> of dict
    """
    client = cmd_mongo.connect(conf)
    collection = client[conf.infra['mongo']['db']][conf.infra['mongo']['collection']]
    documents = cmd_mongo.get_all_documents(collection, ['_id', 'message'])
    client.close()
    return documents


def process_pipeline(conf, pattern, stopw, queue):
    """
    Fonction executé dans un processus séparé
    :param conf: <Settings>
    :param pattern: <re.compile>
    :param stopw: <set>
    :param queue: <Queue>
    """
    p_logger = process_logger()
    p_logger.info("Début du processus traitement nlp")
    stz_pipe = stanza.Pipeline(lang='en', processors='tokenize,mwt,pos,lemma')
    for document in tqdm.tqdm(get_all_mails(conf),
                              desc="Traitement NLP",
                              leave=False,
                              disable=conf.args['progress_bar']):
        result = nlp_pipeline(conf, document, stz_pipe, pattern, stopw)
        if result:
            queue.put(result)
    queue.put("OVER")
    p_logger.info("Fin du traitement nlp")


def process_database(conf, queue):
    """
    Processus de traitement de la queue
    :param conf: <Settings>
    :param queue: <Queue>
    """
    p_logger = process_logger()
    p_logger.info("Début du processus de mise en base")
    counter = 5
    while True:
        if not counter:
            p_logger.info("Process_database interrompu pour inactivité")
            break

        if queue.empty():
            p_logger.info("Data queue vide, 10 secondes d'attente (%s/5)", counter)
            counter -= 1
            time.sleep(10)
            continue

        counter = 5
        data = queue.get()
        if data == 'OVER':
            p_logger.info("Fin de la mise en base")
            break

        insert_pipeline(conf, data)


def insert_pipeline(conf, data):
    """
    Processus de mise en base pour les mots d'un document
    :param conf: <Settings>
    :param data: <dict>
    """
    client = cmd_psql.connect_db(user=conf.infra['psql']['user'],
                                 passwd=conf.infra['psql']['pass'],
                                 host=conf.infra['psql']['host'],
                                 port=conf.infra['psql']['port'],
                                 dbname=conf.infra['psql']['db'])
    for mot, freq in data['bag'].items():
        table = 'nlp_mots_corpus'
        clause = f"mot LIKE '{mot}'"
        id_mot = cmd_psql.get_unique_data(client, table, 'id_mot', clause)

        if not id_mot:
            cmd_psql.insert_data_one(client, table, {'mot': mot})
            id_mot = cmd_psql.get_unique_data(client, table, 'id_mot', clause)

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
        data.update({'bag': {}, 'nlp_status': 'Type error'})

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
