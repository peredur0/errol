# coding: utf-8
"""
Fichier pour tester les développements en cours
"""

import logging
import pymongo
import pymongo.errors

logger = logging.getLogger(__name__)


def main(conf):
    """
    Processus principal
    :param conf: <Settings>
    :return: None
    """
    logger.info("DEVELOPPEMENT")
    client = connect(conf)

    doc_1 = {
        'hash': 'foo',
        'categorie': 'spam',
        'sujet': 'Je suis un SPAM',
        'expediteur': 'white.rabbit@monty.com',
        'message': 'MWHAHAHAHA',
        'langue': 'en',
        'liens': {
            'URL': 0,
            'MAIL': 1,
            'TEL': 1,
            'NOMBRE': 3,
            'PRIX': 4
        }
    }

    doc_2 = {
        'hash': 'foo',
        'categorie': 'spam',
        'sujet': 'Je suis un SPAM2',
        'expediteur': 'white.rabbit@monty.com',
        'message': 'MWHAHAHAHA2',
        'langue': 'en',
        'liens': {
            'URL': 0,
            'MAIL': 1,
            'TEL': 1,
            'NOMBRE': 3,
            'PRIX': 4
        }
    }

    doc_3 = {
        'hash': 'bar',
        'categorie': 'ham',
        'sujet': 'Je suis un HAM',
        'expediteur': 'white.rabbit@monty.com',
        'message': 'Hello there',
        'langue': 'en',
        'liens': {
            'URL': 1,
            'MAIL': 1,
            'TEL': 1,
            'NOMBRE': 3,
            'PRIX': 4
        }
    }
    db = client[conf.infra['mongo']['db']]
    collection = db[conf.infra['mongo']['collection']]
    documents = [doc_1, doc_2, doc_3]

    insert_documents(documents, collection)

    client.close()


def connect(conf):
    """
    Créé un client pour la connexion avec mongodb
    :param conf: <Settings>
    :return: <pymongoClient>
    """
    c_mongo = conf.infra['mongo']
    uri = (f"mongodb://{c_mongo['user_name']}:{c_mongo['user_pwd']}@{c_mongo['host']}:"
           f"{c_mongo['port']}/{c_mongo['db']}")
    return pymongo.MongoClient(uri)


def insert_documents(documents, collection):
    """
    Ajoute une liste de documents dans une collection mongo
    :param collection: <pymongo_Collection>
    :param documents: <list>
    """
    final_list = []
    doc_ids = set()
    for doc in documents:
        if doc['hash'] in doc_ids:
            logger.info("Document dupliqué - %s", doc['hash'])
            continue
        doc_ids.add(doc['hash'])
        final_list.append(doc)

    hash_list = [doc['hash'] for doc in final_list]

    try:
        with pymongo.timeout(15):
            existing = [doc['hash'] for doc in list(collection.find({'hash': {'$in': hash_list}}))]
    except pymongo.errors.ServerSelectionTimeoutError:
        logger.error("Timeout lors de la recherche de documents")
        return

    final_list = [doc for doc in final_list if doc['hash'] not in existing]

    if not final_list:
        logger.info("Aucun document à ajouter")
        return

    with pymongo.timeout(15):
        try:
            res = collection.insert_many(final_list)
            logger.info("Documents insérés - %s", len(res.inserted_ids))
        except pymongo.errors.BulkWriteError as err:
            logger.error("Erreur d'insertion - %s", err)
