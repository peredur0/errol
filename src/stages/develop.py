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



def create_user(conf):
    """
    Ajoute le nouvel utilisateur
    :param conf: <Settings>
    """
    db = conf.infra['mongo']['db']
    new_user = conf.infra['mongo']['user_name']
    new_pwd = conf.infra['mongo']['user_pwd']

    client = pymongo.MongoClient()
    try:
        with pymongo.timeout(3):
            client[db].command('createUser', new_user, pwd=new_pwd,
                               roles=[{'role': 'readWrite', 'db': db}])
    except pymongo.errors.ServerSelectionTimeoutError:
        logger.error("Timeout lors de la création de l'utilisateur")
    except pymongo.errors.OperationFailure as err:
        logger.error(err)
    finally:
        client.close()
