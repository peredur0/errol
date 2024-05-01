# coding: utf-8
"""
Wrapper pour les commandes mongo
"""
import logging
import bson.errors
import pymongo
import pymongo.errors

logger = logging.getLogger(__name__)


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
        except (pymongo.errors.BulkWriteError, bson.errors.InvalidDocument) as err:
            logger.error("Erreur d'insertion par groupe - %s", err)
            for document in final_list:
                insert_document(document, collection)
            return

        logger.info("Documents insérés - %s", len(res.inserted_ids))


def insert_document(document, collection):
    """
    Ajoute un document dans une collection mongo
    :param collection: <pymongo_Collection>
    :param document: <dict>
    """
    with pymongo.timeout(15):
        try:
            res = collection.insert_one(document)
        except pymongo.errors.DuplicateKeyError:
            logger.debug("Document %s déjà présent", document['hash'])
            return
        except pymongo.errors.WriteError as err:
            logger.error(err)
            return

        logger.debug("Document %s inséré unitairement", res.inserted_id)


def get_all_documents(collection, include=None):
    """
    Récupère tous les documents d'une collection
    :param collection: <pymongo_Collection>
    :param include: <str|list>
    """
    if include is None:
        include = {}
    if isinstance(include, list):
        include = {field: 1 for field in include}
    else:
        include = {include: 1}

    with pymongo.timeout(15):
        return collection.find({}, include)
