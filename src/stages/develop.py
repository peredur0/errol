# coding: utf-8
"""
Fichier pour tester les développements en cours
"""
import logging
import pandas as pd
import sqlalchemy
from src.modules import graph
from src.modules import cmd_psql
from  src.modules import cmd_mongo


logger = logging.getLogger(__name__)


def get_all_mails(conf):
    """
    Récupère tous les mails de la base mongo.
    :param conf: <Settings>
    :return: <list> of dict
    """
    client = cmd_mongo.connect(conf)
    collection = client[conf.infra['mongo']['db']][conf.infra['mongo']['collection']]
    return cmd_mongo.get_all_documents(collection, ['_id', 'message'])
    return {entry['_id']: entry['message'] for entry in all_docs}


def stats_pipeline(client_psql, entry):
    """
    Pipeline du traitement des données statistiques pour un message
    :param client_psql: <psycopg2.connection>
    :param entry: <dict>
    :return: <None>
    """
    data = {'hash': entry['_id']}
    raw_message = entry['message']

    psql_data = cmd_psql.get_data(client_psql, 'messages', ['id_message'],
                                  f"hash LIKE '{data['hash']}'")
    if not psql_data:
        logger.debug("Message %s absent de la base PSQL", data['hash'])
        return
    data['psql_id'] = psql_data[0]['id_message']
    print(data)

def main(conf):
    """
    Processus principal
    :param conf: <Settings>
    :return: None
    """
    logger.info("DEVELOPMENT")
    all_docs = get_all_mails(conf)
    logger.info("%s documents récupéré dans la base Mongo", len(all_docs))

    cli_psql = cmd_psql.connect_db(user=conf.infra['psql']['user'],
                                   passwd=conf.infra['psql']['pass'],
                                   host=conf.infra['psql']['host'],
                                   port=conf.infra['psql']['port'],
                                   dbname=conf.infra['psql']['db'])

    for entry in all_docs:
        stats_pipeline(cli_psql, entry)
        break
