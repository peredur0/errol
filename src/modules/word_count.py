# coding: utf-8
"""
Code pour la phase de fouille de données
"""
import multiprocessing
import logging
import queue
import tqdm

from src.modules import cmd_sqlite
from src.modules import importation

logger = logging.getLogger(__name__)


def fouille_wc(data_stack, conf, stage):
    """
    Calcule le nombre de mots et mots uniques lors de la phase de fouille
    Stocke directement les informations dans la base SQLite
    :param data_stack: <dict>
    :param conf: <Settings>
    :param stage: <str>
    :return: <None>
    """
    manager = multiprocessing.Manager()
    shared_queue = manager.Queue()

    logger.info("Word Count %s début", stage)
    match stage:
        case 'récolte':
            pool_args = [(file, cat, shared_queue, stage) for cat, f_list in data_stack.items()
                         for file in list(f_list)]

        case 'création' | 'mise_en_base':
            pool_args = [(doc['message'], doc['categorie'], shared_queue, stage) for doc in
                         data_stack]

        case _:
            logger.error("Etape inconnue %s pour le word_count", stage)
            return

    with multiprocessing.Pool(conf.infra['cpu_available']) as pool:
        list(tqdm.tqdm(pool.imap(word_count_args, pool_args),
                       desc=f"Word count progress {stage}...",
                       leave=False,
                       disable=conf.args['progress_bar']))

    words_count = process_queue(shared_queue)
    to_save = prepare_to_save(words_count, pool_args, stage)
    store_word_count(to_save, conf)
    logger.info("Word count %s fin", stage)


def process_queue(shared_queue):
    """
    Fonction qui compte les occurrences de chaque mot.
    :param shared_queue: <Queue>
    """
    words_count = {}
    while not shared_queue.empty():
        q_element = shared_queue.get()
        cat = list(q_element.keys())[0]

        if cat not in words_count:
            words_count[cat] = {}

        for mot, iteration in q_element[cat].items():
            if mot not in words_count[cat]:
                words_count[cat][mot] = iteration
            else:
                words_count[cat][mot] += iteration

    return words_count


def prepare_to_save(words_count, pool_args, stage):
    """
    Préparation des données à sauvegarder
    :param words_count: <dict>
    :param pool_args: <int>
    :param stage: <str>
    :return: <dict>
    """
    to_save = {}
    for cat, words in words_count.items():
        to_save[cat] = {
            'etape': stage,
            'mails': len([arg for arg in pool_args if arg[1] == cat]),
            'mots': sum(iteration for iteration in words.values()),
            'mots_uniques': len(words.keys())
        }

    to_save['globales'] = {'etape': stage, 'mails': 0, 'mots': 0, 'mots_uniques': 0}

    for cat in [cat_key for cat_key in to_save if cat_key != 'globales']:
        for key in ['mails', 'mots', 'mots_uniques']:
            to_save['globales'][key] += to_save[cat][key]

    return to_save


def word_count_args(pool_arg):
    """
    Compte les mots d'un mail d'une catégorie et ajoute le comptage
    word_count format : {'ham' : {'foo' : 1, 'bar' : 2}}
    :param pool_arg: <list> [<str>, <str>, <dict>]
    :return: <None>
    """
    source = pool_arg[0]
    cat = pool_arg[1]
    words_queue = pool_arg[2]
    stage = pool_arg[3]
    word_count = {cat: {}}

    match stage:
        case 'récolte':
            mots = importation.get_text_file(source).split()
        case 'création' | 'mise_en_base':
            mots = source.split()
        case _:
            logger.error('Etape inconnue pour word_count - %s', stage)
            return

    if not mots:
        return

    for mot in mots:
        if mot not in word_count[cat]:
            word_count[cat][mot] = 1
        else:
            word_count[cat][mot] += 1

    try:
        words_queue.put(word_count, timeout=2)
    except queue.Full as err:
        logger.error("Queue WordCounts pleine. Essayez avec moins de données - %s", err)
        return


def store_word_count(data, conf):
    """
    Store word count information into database:
    :param data: <dict>
    :param conf: <Settings>
    :return: <None>
    """
    cli_sqlite = cmd_sqlite.connect(conf.infra['sqlite']['file'])
    for key, value in data.items():
        cmd_sqlite.insert_dict(cli_sqlite, key, value)
    cli_sqlite.close()
    logger.debug(data)
