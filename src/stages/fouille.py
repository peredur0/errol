# coding: utf-8
"""
Code pour la phase de fouille de données
"""
import datetime
import hashlib
import json
import logging
import multiprocessing
import sys

import langdetect
import tqdm
import pandas as pd
from src.modules import cmd_sqlite
from src.modules import cmd_mongo
from src.modules import cmd_psql
from src.modules import importation
from src.modules import word_count
from src.modules import nettoyage
from src.modules import graph
from src.annexes import zipf

logger = logging.getLogger(__name__)


def main(conf):
    """
    Fonction principale pour la fouille
    :param conf: <Settings>
    :return: <None>
    """
    logger.info("Collecte des mails et mise en base")
    databases_init(conf)

    logger.info("Récolte")
    files_stack = {'ham': [], 'spam': []}

    for cat in ['ham', 'spam']:
        try:
            for folder in conf.args[cat]:
                files_stack[cat] += importation.get_files(folder)
        except TypeError:
            logger.warning("%s - aucun dossier donné en argument", cat)
            continue
    if conf.args['stats']:
        word_count.fouille_wc(files_stack, conf, 'récolte')

    logger.info("Création des documents")
    pool_args = [(file, cat) for cat, f_list in files_stack.items() for file in list(f_list)]
    with multiprocessing.Pool(conf.infra['cpu_available']) as pool:
        result = list(tqdm.tqdm(pool.imap(fouille_doc, pool_args),
                                desc="Création des documents",
                                leave=False,
                                total=len(pool_args),
                                disable=conf.args['progress_bar']))
    result = [doc for doc in result if doc]
    logger.info("Documents créés - %s", len(result))

    if conf.args['stats']:
        word_count.fouille_wc(result, conf, 'création')

    logger.info("Mise en base")
    mise_en_base(result, conf)

    client = cmd_mongo.connect(conf)
    db = client[conf.infra['mongo']['db']]
    collection = db[conf.infra['mongo']['collection']]
    result = cmd_mongo.get_all_documents(collection, ['categorie', 'message'])
    if conf.args['stats']:
        word_count.fouille_wc(result, conf, 'mise_en_base')
        get_stats(conf)

    logger.info('Fin du processus de fouille initial')


def databases_init(conf):
    """
    Initialisation des bases de données
    :param conf: <Settings>
    """
    if conf.args['stats']:
        logger.info("Création de la base SQLITE")
        cli_sqlite = cmd_sqlite.connect(conf.infra['sqlite']['file'])
        cmd_sqlite.create_tables(cli_sqlite, conf.infra['sqlite']['schema_stats'])
        cli_sqlite.close()

    logger.info("Création de la base psql")
    cmd_psql.apply_databases_updates(conf, conf.infra['psql']['schema']['fouille'])


def fouille_doc(pool_args):
    """
    Processus de création des documents
    :param pool_args: <tuple>
    :return: <dict>
    """
    cat = pool_args[1]
    file = pool_args[0]

    mail = importation.load_mail(file)
    sujet, exp = importation.extract_mail_meta(mail)
    body = importation.extract_mail_body(mail)
    body, liens = nettoyage.clear_texte_init(body)

    if not body:
        logger.warning("Echec de récupération du corps de %s", file)
        return None

    try:
        lang = langdetect.detect(body)
    except langdetect.lang_detect_exception.LangDetectException as err:
        logger.error("Echec de détection de la langue pour %s %s", file, err)
        return None

    new_doc = {
        'hash': hashlib.md5(body.encode()).hexdigest(),
        'categorie': cat.lower(),
        'sujet': sujet if sujet else 'null',
        'expediteur': exp,
        'message': body,
        'langue': lang,
        'liens': liens
    }

    return new_doc


mongo_fields = ['categorie', 'sujet', 'expediteur', 'message', 'langue']
psql_fields = ['hash', 'categorie', 'langue']


def mise_en_base(result, conf):
    """
    Mise en base de documents
    :param result: <list> [<dict>, ...]
    :param conf: <Settings>
    :return: <None>
    """
    chunk_size = 50
    chunked = [result[i:i + chunk_size] for i in range(0, len(result), chunk_size)]

    cli_mongo = cmd_mongo.connect(conf)
    db = cli_mongo[conf.infra['mongo']['db']]
    collection = db[conf.infra['mongo']['collection']]

    cli_psql = cmd_psql.connect_db(user=conf.infra['psql']['user'],
                                   passwd=conf.infra['psql']['pass'],
                                   host=conf.infra['psql']['host'],
                                   port=conf.infra['psql']['port'],
                                   dbname=conf.infra['psql']['db'])

    for chunk in tqdm.tqdm(chunked,
                           desc="Mise en base des documents",
                           leave=False,
                           disable=conf.args['progress_bar']):
        mongo_chunk = []
        psql_chunk = []
        for doc in chunk:
            m_entry = {k: v for k, v in doc.items() if k in mongo_fields}
            m_entry['_id'] = doc['hash']
            mongo_chunk.append(m_entry)

            p_entry = {k: v for k, v in doc.items() if k in psql_fields}
            p_entry.update(doc['liens'])
            psql_chunk.append(p_entry)

        inserted = cmd_mongo.insert_documents(mongo_chunk, collection)

        psql_chunk = {doc['hash']: doc for doc in psql_chunk if doc['hash'] in inserted}
        psql_insert(psql_chunk, cli_psql)

    cli_mongo.close()
    cli_psql.close()


def get_stats(conf):
    """
    Récupère les statistiques de la fouille et les affiche
    :param conf: <Settings>
    """
    with open(conf.infra['sqlite']['schema_stats'], 'r', encoding='utf-8') as json_file:
        schema = json.load(json_file)

    data = []
    for cat in list(schema.keys()):
        output = cmd_sqlite.get_data(cmd_sqlite.connect(conf.infra['sqlite']['file']), cat)
        for row in output:
            keys = list(schema[cat].keys())
            row_info = dict(zip(keys, row))
            row_info['categorie'] = cat
            data.append(row_info)

    stats_df = pd.DataFrame(data)
    pivot = stats_df.pivot_table(values=['mails', 'mots', 'mots_uniques'],
                                 columns=['categorie'],
                                 index=['etape'],
                                 sort=False)
    pivot = pivot.astype(int)
    logger.info("Statistiques de la fouille\n%s", pivot)

    if conf.args['rapport']:
        latex_table = pivot.to_latex(
            caption='Données statistiques de la fouille',
            label='tab:fouillestats',
            index=True,
            column_format='l|rrr|rrr|rrr',
            longtable=False,
            escape=True,
            multicolumn=True,
            multicolumn_format='c',
            float_format="%.1f"
        )
        with open(f'{conf.rapport["fouille"]}/stats.tex', 'w', encoding='utf-8') as file:
            file.write(latex_table)

    zipf_data = zipf_stats(conf)
    link_data = link_stats(conf)

    if conf.args['graph']:
        graph.fouille_dash(conf, stats_df, zipf_data, link_data)


def zipf_stats(conf):
    """
    Génère les statistiques en relation avec la distribution de zipf.
    :param conf: <Settings>
    :return: <dict>
    """
    client = cmd_mongo.connect(conf)
    collection = client[conf.infra['mongo']['db']][conf.infra['mongo']['collection']]
    bag = cmd_mongo.get_all_documents(collection, include='message')
    bag = [doc['message'].split() for doc in bag]
    bag = [mot for doc in bag for mot in doc]

    zipf_data = zipf.zipf_process(bag)
    logger.info("Distribution de zipf\n\tconstante: %.2f\n\tcoefficient k: %.2f",
                zipf_data['const_moy'], zipf_data['coef_min'])
    client.close()
    return zipf_data


def link_stats(conf):
    """
    Génère les statistiques des liens.
    :param conf: <Settings>
    :return: <Dataframe>
    """
    client = cmd_psql.create_engine(user=conf.infra['psql']['user'],
                                    passwd=conf.infra['psql']['pass'],
                                    host=conf.infra['psql']['host'],
                                    port=conf.infra['psql']['port'],
                                    dbname=conf.infra['psql']['db'])

    query = '''SELECT
        c.nom, l.url, l.mail, l.tel, l.nombre, l.prix
        FROM liens l 
        JOIN messages m ON l.id_message = m.id_message
        JOIN categories c ON m.id_categorie = c.id_categorie;
        '''

    link_data = pd.read_sql_query(query, client)
    client.dispose()

    link_data.columns = ['categorie', 'url', 'mail', 'tel', 'nombre', 'prix']
    aggfunc = ['mean', graph.q50, graph.q90, 'max']
    link_data = link_data.groupby('categorie')[link_data.columns[1:]].agg(
        aggfunc).unstack().unstack()

    logger.info("Statistiques des liens\n%s", link_data)

    if conf.args['rapport']:
        latex_data = link_data.round(2).astype(str)
        latex_data.style.to_latex(
            buf=f'{conf.rapport["fouille"]}/liens.tex',
            caption="Statistiques sur les liens et informations numériques",
            label='tab:p1liens',
            position='H',
            position_float='centering',
            clines='skip-last;data',
            column_format='ll|rrr',
            hrules=True
        )
    return link_data


liens_fields = ['url', 'mail', 'tel', 'nombre', 'prix']


def psql_insert(psql_chunk, client):
    """
    Insertion des documents de la fouille dans les tables PSQL
    :param psql_chunk: <dict>
    :param client: <psycopg2.connection>
    :return: <None>
    """
    if not psql_chunk:
        logger.debug("Aucunes données disponibles suite à l'insertion dans Mongo")
        return

    table = 'categories'
    exists_cat = {line['nom']: line['id_categorie']
                  for line in cmd_psql.get_data(client, table, ['nom', 'id_categorie'])}
    doc_cat = set(doc['categorie'] for doc in psql_chunk.values())
    to_insert = [cat for cat in doc_cat if cat not in exists_cat]

    if to_insert:
        cmd_psql.insert_data_many(client, table, [{'nom': cat} for cat in to_insert])
        exists_cat = {line['nom']: line['id_categorie']
                      for line in cmd_psql.get_data(client, table, ['nom', 'id_categorie'])}
        logger.info('Catégories insérées dans la table %s - %s', table, to_insert)

    hashes = [f"'{key}'" for key in psql_chunk.keys()]
    clause = f"hash in ({','.join(hashes)})"

    table = "messages"
    exists = [line['hash'] for line in cmd_psql.get_data(client, table, ['hash'], clause)]
    to_insert = [{'hash': hash_mess,
                  'id_categorie': exists_cat.get(doc['categorie']),
                  'langue': doc['langue']}
                 for hash_mess, doc in psql_chunk.items() if hash_mess not in exists]
    if to_insert:
        logger.info("Documents a insérés dans la table %s - %s", table, len(to_insert))
        cmd_psql.insert_data_many(client, table, to_insert)

    exists_mess = {line['hash']: line['id_message']
                   for line in cmd_psql.get_data(client, table, ['hash', 'id_message'], clause)}

    table = "liens"
    exists = set(line['id_message'] for
                 line in cmd_psql.get_data(client, table, ['id_message']))
    to_insert = []
    for hash_mess, document in psql_chunk.items():
        if exists_mess[hash_mess] in exists:
            continue
        tmp_doc = {key.lower(): value for key, value in document.items()
                   if key.lower() in liens_fields}
        tmp_doc['id_message'] = exists_mess[hash_mess]
        to_insert.append(tmp_doc)

    if to_insert:
        logger.info("Documents a insérés dans la table %s - %s", table, len(to_insert))
        cmd_psql.insert_data_many(client, table, to_insert)

    table = "controle"
    exists = set(line['id_message'] for
                 line in cmd_psql.get_data(client, table, ['id_message']))
    to_insert = []
    for hash_mess, document in psql_chunk.items():
        if exists_mess[hash_mess] in exists:
            continue
        to_insert.append({'id_message': exists_mess[hash_mess],
                          'initial': str(datetime.date.today())})

    if to_insert:
        logger.info("Documents a insérés dans la table %s - %s", table, len(to_insert))
        cmd_psql.insert_data_many(client, table, to_insert)
