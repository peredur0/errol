# coding: utf-8
"""
Code pour la phase de recherche de caractéristiques
"""
import datetime
import re
import logging
import multiprocessing
import tqdm
import pandas as pd

from src.modules import cmd_psql
from src.modules import cmd_mongo
from src.modules import graph
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

    if conf.args['stats']:
        features_stats(conf)
    logger.info("Fin de la recherche des caractéristiques")


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
    tokens = re.findall(r'\w+', texte, re.MULTILINE)
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
    tokens = re.findall(r'\w+', texte, re.MULTILINE)
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
    tokens = re.findall(r'\w+', texte, re.MULTILINE)
    data = zipf.hapax(tokens)
    data['nombre_hapax'] = data.pop('nombres')
    return data


def features_stats(conf):
    """
    Récupère et affiche les données statistiques des caractéristiques
    :param conf: <settings>
    :return: <None>
    """
    client = cmd_psql.create_engine(user=conf.infra['psql']['user'],
                                    passwd=conf.infra['psql']['pass'],
                                    host=conf.infra['psql']['host'],
                                    port=conf.infra['psql']['port'],
                                    dbname=conf.infra['psql']['db'])
    me_cols = ['id_message']
    ca_cols = ['nom']
    ha_cols = ['ratio_mots_uniques', 'ratio_texte', 'nombre_hapax']
    mo_cols = ['char_minuscules', 'char_majuscules', 'mots', 'mots_uniques', 'mots_majuscules',
               'mots_capitalizes']
    po_cols = ['point', 'virgule', 'exclamation', 'interrogation', 'tabulation', 'espace',
               'ligne', 'ligne_vide']
    zi_cols = ['constante', 'coefficient', 'taux_erreur']

    query = f'''
    SELECT 
        {','.join([f'me.{field}' for field in me_cols])}, 
        {','.join([f'ca.{field}' for field in ca_cols])}, 
        {','.join([f'ha.{field}' for field in ha_cols])}, 
        {','.join([f'mo.{field}' for field in mo_cols])}, 
        {','.join([f'po.{field}' for field in po_cols])}, 
        {','.join([f'zi.{field}' for field in zi_cols])} 
    FROM messages me
    JOIN categories ca ON ca.id_categorie = me.id_categorie 
    JOIN features_hapax ha ON ha.id_message = me.id_message 
    JOIN features_mots mo ON mo.id_message = me.id_message 
    JOIN features_ponctuations po ON po.id_message = me.id_message 
    JOIN features_zipf zi ON zi.id_message = me.id_message 
    JOIN controle co ON co.id_message = me.id_message
    WHERE co.features IS NOT NULL
    '''
    full_df = pd.read_sql_query(query, client)
    replace_cols = {name: name.replace('_', '-') for name in list(full_df.columns)}
    full_df = full_df.rename(columns=replace_cols)
    client.dispose()

    print_stats = {
        'char': [col.replace('_', '-') for col in mo_cols[:2]],
        'mots': [col.replace('_', '-') for col in mo_cols[2:4]],
        'format-mots': [col.replace('_', '-') for col in mo_cols[4:]],
        'ponctuation': [col.replace('_', '-') for col in po_cols[:4]],
        'espace': [col.replace('_', '-') for col in po_cols[4:]],
        'zipf': [col.replace('_', '-') for col in zi_cols],
        'hapax': [col.replace('_', '-') for col in ha_cols]
    }

    for categorie, fields in print_stats.items():
        data = full_df.pivot_table(
            index='nom',
            values=fields,
            aggfunc=['mean', graph.q50, graph.q90, 'max']
        ).unstack().unstack()
        latex_data = data.round(2).astype(str)
        latex_data.style.to_latex(
            buf=f'{conf.rapport["features"]}/tab_{categorie}.tex',
            caption=f"Statistiques sur les données {categorie}",
            label=f'tab:f_{categorie}',
            position='H',
            position_float='centering',
            clines='skip-last;data',
            column_format='ll|rr',
            hrules=True
        )
        logger.info("Statistiques %s\n%s", categorie, data)

    if conf.args['graph']:
        excluded = ['nom', 'id-message', 'ligne-vide', 'tabulation', 'interrogation',
                    'exclamation', 'virgule', 'mots-majuscules']
        df_corr = full_df.drop(excluded, axis=1)
        graph.feature_correlation(df_corr, conf)
