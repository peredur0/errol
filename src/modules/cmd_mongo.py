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
    :return: <list>
    """
    final_list = []
    doc_ids = set()
    for doc in documents:
        if doc['_id'] in doc_ids:
            logger.info("Document dupliqué dans %s - %s", collection.name, doc['_id'])
            continue
        doc_ids.add(doc['_id'])
        final_list.append(doc)

    hash_list = [doc['_id'] for doc in final_list]
    try:
        with pymongo.timeout(15):
            existing = [doc['_id'] for doc in list(collection.find({'_id': {'$in': hash_list}}))]
    except pymongo.errors.ServerSelectionTimeoutError:
        logger.error("Timeout lors de la recherche de documents")
        return []

    final_list = [doc for doc in final_list if doc['_id'] not in existing]

    if not final_list:
        logger.info("Aucun document à ajouter")
        return []

    with pymongo.timeout(15):
        try:
            res = collection.insert_many(final_list)
            res = res.inserted_ids
        except (pymongo.errors.BulkWriteError, bson.errors.InvalidDocument) as err:
            logger.error("Erreur d'insertion par groupe - %s", err)
            res = []
            for document in final_list:
                ret = insert_document(document, collection)
                if ret:
                    res.append(ret)

        logger.info("Documents insérés dans %s - %s", collection.name, len(res))
        return res


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
            logger.debug("Document déjà présent dans %s - %s", collection.name, document['_id'])
            return None
        except pymongo.errors.WriteError as err:
            logger.error(err)
            return None

        logger.debug("Document inséré unitairement dans %s - %s", collection.name, res.inserted_id)
        return res.inserted_id


def get_all_documents(collection, d_filter=None, include=None, limit=None):
    """
    Récupère tous les documents d'une collection
    :param collection: <pymongo_Collection>
    :param d_filter: <dict>
    :param include: <str|list>
    :param limit: <int>
    :return: <Cursor|list>
    """
    if d_filter is None:
        d_filter = {}
    if include is None:
        include = {}
    if isinstance(include, list):
        include = {field: 1 for field in include}
    else:
        include = {}

    try:
        with pymongo.timeout(15):
            if limit:
                return list(collection.find(d_filter, include).limit(limit))
            return list(collection.find(d_filter, include))
    except pymongo.errors.ServerSelectionTimeoutError as err:
        logger.error(err)
        return []
