# coding: utf-8
"""
Fichier pour tester les développements en cours
"""
import re
import logging
import pandas as pd
import sqlalchemy
from src.modules import graph
from src.modules import cmd_psql
from src.modules import cmd_mongo
from src.annexes import zipf
from pprint import pprint


logger = logging.getLogger(__name__)


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


def stats_ponctuation(texte):
    """
    Génère les stats pour la table de ponctuation: points, virgule, espaces, lignes
    :param texte: <str>
    :return: <dict>
    """
    return {
        "point": texte.count('.'),
        "virgule": texte.count(','),
        "exclamation": texte.count('!'),
        "interrogation": texte.count('?'),
        "tabulation": texte.count('\t'),
        "espace": texte.count(' '),
        "ligne": texte.count('\n') + 1,
        "ligne_vide": len(re.findall(r'^\s*$', texte, re.MULTILINE))
    }


def stats_mots(texte):
    """
    Génère les stats pour la table des mots, char non vide
    :param texte: <str>
    :return: <dict>
    """
    tokens = texte.split()
    return {
        'char_minuscules': len(re.findall(r'[a-z]', texte, re.MULTILINE)),
        'char_majuscules': len(re.findall(r'[A-Z]', texte, re.MULTILINE)),
        'mots': len(tokens),
        'mots_uniques': len(set(tokens)),
        'mots_majuscules': sum(mot.isupper() for mot in tokens),
        'mots_capitalizes': sum(bool(re.match(r'[A-Z][a-z]+', mot)) for mot in tokens)
    }


def stats_zipf(texte):
    """
    Génère les informations de la distribution de zipf
    :param texte: <str>
    :return: <dict>
    """
    tokens = texte.split()
    z_data = zipf.zipf_process(tokens)
    return {
        'constante': float(z_data.get('const_moy')),
        'coefficient': float(z_data.get('coef_min')),
        'taux_erreur': float(z_data.get('cout_min'))
    }


def stats_hapax(texte):
    """
    Génère les informations de mots ayant une seule occurrence.
    :param texte: <str> message
    :return: <dict> avec les données
    """
    tokens = texte.split()
    data = zipf.hapax(tokens)
    data['nombre_hapax'] = data.pop('nombres')
    return data


def stats_pipeline(client_psql, entry, fonctions):
    """
    Pipeline du traitement des données statistiques pour un message
    :param client_psql: <psycopg2.connection>
    :param entry: <dict>
    :param fonctions: <list>
    :return: <None>
    """
    data = {'hash': entry['_id']}
    clause = f"hash LIKE '{data['hash']}'"
    psql_data = cmd_psql.get_data(client_psql, 'messages', ['id_message'], clause)
    if not psql_data:
        logger.debug("Message %s absent de la base PSQL", data['hash'])
        return
    data['psql_id'] = psql_data[0]['id_message']

    clause = f"id_message = {data['psql_id']}"
    if stats_status := cmd_psql.get_unique_data(client_psql, 'status', 'stats', clause):
        logger.info("Message %s déjà traité pour la partie stats - %s", data['hash'], stats_status)
        return

    raw_message = entry['message']
    for fonction in fonctions:
        data[fonction.__name__] = fonction(raw_message)

    pprint(data)


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

    fonctions = [stats_ponctuation, stats_mots, stats_zipf, stats_hapax]

    for entry in all_docs:
        stats_pipeline(cli_psql, entry, fonctions)
        break

    cli_psql.close()
