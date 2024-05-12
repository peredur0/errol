# coding: utf-8
"""
Code pour la phase de fouille de données
"""
import hashlib
import json
import logging
import multiprocessing
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
    word_count.fouille_wc(files_stack, conf, 'récolte')

    logger.info("Création des documents")
    pool_args = [(file, cat) for cat, f_list in files_stack.items() for file in list(f_list)]
    with multiprocessing.Pool(conf.infra['cpu_available']) as pool:
        result = list(tqdm.tqdm(pool.imap(fouille_doc, pool_args),
                                desc="Création des documents",
                                leave=False,
                                disable=conf.args['progress_bar']))
    result = [doc for doc in result if doc]
    logger.info("Documents créés - %s", len(result))
    word_count.fouille_wc(result, conf, 'création')

    logger.info("Mise en base")
    mise_en_base(result, conf)

    client = cmd_mongo.connect(conf)
    db = client[conf.infra['mongo']['db']]
    collection = db[conf.infra['mongo']['collection']]
    result = cmd_mongo.get_all_documents(collection, ['categorie', 'message'])
    word_count.fouille_wc(result, conf, 'mise_en_base')

    get_stats(conf)

    logger.info('Fin du processus de fouille initial')


def databases_init(conf):
    """
    Initialisation des bases de données
    :param conf: <Settings>
    """
    logger.info("Création de la base SQLITE")
    cli_sqlite = cmd_sqlite.connect(conf.infra['sqlite']['file'])
    cmd_sqlite.create_tables(cli_sqlite, conf.infra['sqlite']['schema_stats'])
    cli_sqlite.close()

    logger.info("Création de la base psql")
    with open(conf.infra['psql']['schema']['fouille'], 'r', encoding='utf-8') as schema_file:
        schema = json.load(schema_file)

    cli_psql = cmd_psql.connect_db(user=conf.infra['psql']['user'],
                                   passwd=conf.infra['psql']['pass'],
                                   host=conf.infra['psql']['host'],
                                   port=conf.infra['psql']['port'],
                                   dbname=conf.infra['psql']['db'])

    for db_schema in schema['databases']:
        if db_schema['name'] == "errol":
            new_tables = db_schema['tables']['new']
            logger.info("Tables à créer - %i", len(new_tables))
            for table in new_tables:
                cmd_psql.create_table(cli_psql, table)
            break

    cli_psql.close()


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
    except langdetect.lang_detect_exception.LangDetectException:
        logger.error("Echec de détection de la langue pour %s", file)
        return None

    if lang != 'en':
        logger.debug('Langue détectée pour %s - %s', file, lang)
        return None

    new_doc = {
        'hash': hashlib.md5(body.encode()).hexdigest(),
        'categorie': cat.lower(),
        'sujet': sujet,
        'expediteur': exp,
        'message': body,
        'langue': lang,
        'liens': liens
    }

    return new_doc


def mise_en_base(result, conf):
    """
    Mise en base de documents
    :param result: <list> [<dict>, ...]
    :param conf: <Settings>
    :return: <None>
    """
    chunk_size = 100
    chunked = [result[i:i + chunk_size] for i in range(0, len(result), chunk_size)]

    client = cmd_mongo.connect(conf)
    db = client[conf.infra['mongo']['db']]
    collection = db[conf.infra['mongo']['collection']]

    for chunk in tqdm.tqdm(chunked,
                           desc="Mise en base des documents",
                           leave=False,
                           disable=conf.args['progress_bar']):
        cmd_mongo.insert_documents(chunk, collection)

    client.close()


def get_stats(conf):
    """
    Récupère les statistiques de la fouille et les affiche
    :param conf: <Settings>
    """
    with open(conf.infra['sqlite']['schema_stats'], 'r', encoding='utf-8') as json_file:
        schema = json.load(json_file)

    data = []
    cats = list(schema.keys())
    client = cmd_sqlite.connect(conf.infra['sqlite']['file'])
    for cat in cats:
        output = cmd_sqlite.get_data(client, cat)
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
    logger.info("Statistiques de la fouille\n%s", pivot)

    zipf_data = zipf_stats(conf)
    link_data = link_stats(conf)

    if conf.args['graph']:
        graph.fouille_dash(stats_df, zipf_data, link_data)


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
    client = cmd_mongo.connect(conf)
    collection = client[conf.infra['mongo']['db']][conf.infra['mongo']['collection']]
    link_data = cmd_mongo.get_all_documents(collection, ['categorie', 'liens'])
    link_data = [{'categorie': entry['categorie'], 'liens': key, 'value': value}
                 for entry in link_data
                 for key, value in entry['liens'].items()]
    link_data = pd.DataFrame(link_data)
    link_data = link_data.pivot_table(
        index='liens',
        values='value',
        columns='categorie',
        aggfunc=['mean', graph.q50, graph.q90, 'max']
    )
    logger.info("Statistiques des liens\n%s", link_data)
    client.close()

    return link_data
