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
from src.modules import importation
from src.modules import word_count
from src.modules import nettoyage
from src.modules import cmd_mongo

logger = logging.getLogger(__name__)


def main(conf):
    """
    Fonction principale pour la fouille
    :param conf: <Settings>
    :return: <None>
    """
    logger.info("Collecte des mails et mise en base")
    logger.info("Création de la base SQLITE")
    cli_sqlite = cmd_sqlite.connect(conf.infra['sqlite']['file'])
    cmd_sqlite.create_tables(cli_sqlite, conf.infra['sqlite']['schema_stats'])
    cli_sqlite.close()

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

    logger.info('Statistiques de la fouille')
    get_stats(conf)


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

    if conf.args['graph']:
        pass
