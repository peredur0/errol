# coding: utf-8
"""
Code pour la phase de recherche de caractéristiques
"""
import datetime
import re
import logging
import multiprocessing
import tqdm

from src.modules import cmd_psql
from src.modules import cmd_mongo
from src.annexes import zipf


logger = logging.getLogger(__name__)


def main(conf):
    """
    Processus principal
    :param conf: <Settings>
    :return: None
    """
    logger.info("Récupération des caractéristiques")

    logger.info("Miser à jour de la base psql")
    cmd_psql.apply_databases_updates(conf, conf.infra['psql']['schema']['features'])

    all_docs = get_all_mails(conf)
    logger.info("Traitement statistique sur %s documents", len(all_docs))

    fonctions = [features_ponctuations, features_mots, features_zipf, features_hapax]
    pool_args = [(conf, entry, fonctions) for entry in all_docs]
    with multiprocessing.Pool(conf.infra['cpu_available']) as pool:
        result = list(tqdm.tqdm(pool.imap(features_pipeline, pool_args),
                                desc="Traitement statistique",
                                leave=False,
                                total=len(pool_args),
                                disable=conf.args['progress_bar']))
    result = [entry for entry in result if entry]

    if result:
        mise_en_base(result, conf)
    else:
        logger.info("Aucun fichier à traiter")
    logger.info("Fin de la recherche des caractéristiques")


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


def features_pipeline(pool_args):
    """
    Pipeline du traitement des données statistiques pour un message
    :param pool_args: <tuple>
    :return: <None>
    """
    conf = pool_args[0]
    entry = pool_args[1]
    fonctions = pool_args[2]
    client_psql = cmd_psql.connect_db(user=conf.infra['psql']['user'],
                                      passwd=conf.infra['psql']['pass'],
                                      host=conf.infra['psql']['host'],
                                      port=conf.infra['psql']['port'],
                                      dbname=conf.infra['psql']['db'])
    data = {'hash': entry['_id']}
    clause = f"hash LIKE '{data['hash']}'"
    psql_data = cmd_psql.get_data(client_psql, 'messages', ['id_message'], clause)
    if not psql_data:
        logger.warning("Message %s absent de la base PSQL", data['hash'])
        return None
    data['id_message'] = psql_data[0]['id_message']

    clause = f"id_message = {data['id_message']}"
    if features_ctrl := cmd_psql.get_unique_data(client_psql, 'controle', 'features', clause):
        logger.debug("Message %s déjà traité pour la partie features - %s", data['hash'],
                     features_ctrl)
        return None

    raw_message = entry['message']
    for fonction in fonctions:
        data[fonction.__name__] = fonction(raw_message)

    client_psql.close()
    return data


def mise_en_base(result, conf):
    """
    Mise en base des nouvelles informations
    """
    logger.info("Mise en base des données statistiques")
    batch_size = 50
    batches = [result[i:i + batch_size] for i in range(0, len(result), batch_size)]

    cli_psql = cmd_psql.connect_db(user=conf.infra['psql']['user'],
                                   passwd=conf.infra['psql']['pass'],
                                   host=conf.infra['psql']['host'],
                                   port=conf.infra['psql']['port'],
                                   dbname=conf.infra['psql']['db'])

    for batch in tqdm.tqdm(batches,
                           desc="Mise en base des features",
                           leave=False,
                           disable=conf.args['progress_bar']):

        for entry in batch:
            psql_id = entry['id_message']
            for table in entry:
                if table in ["hash", "id_message"]:
                    continue
                to_insert = {"id_message": psql_id}
                to_insert.update(entry[table])
                cmd_psql.insert_data_one(cli_psql, table, to_insert)
                logger.debug("Data %s insérée dans %s", psql_id, table)

            to_update = {"features": str(datetime.date.today())}
            cmd_psql.update(cli_psql, 'controle', to_update, clause=f'id_message = {psql_id}')

        logger.info("%s documents traités", len(batch))

    cli_psql.close()


def features_ponctuations(texte):
    """
    Génère les features pour la table de ponctuation: points, virgule, espaces, lignes
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


def features_mots(texte):
    """
    Génère les features pour la table des mots, char non vide
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


def features_zipf(texte):
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


def features_hapax(texte):
    """
    Génère les informations de mots ayant une seule occurrence.
    :param texte: <str> message
    :return: <dict> avec les données
    """
    tokens = texte.split()
    data = zipf.hapax(tokens)
    data['nombre_hapax'] = data.pop('nombres')
    return data
