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


def fouille_wc_files(file_stack, conf):
    """
    Calcule le nombre de mots et mots uniques pour les fichiers donnés lors de la phase de récoler
    Stocke directement les informations dans la base SQLite
    :param file_stack: <dict>
    :param conf: <Settings>
    :return: <None>
    """
    manager = multiprocessing.Manager()
    shared_queue = manager.Queue()

    logger.info("Word Count récolte début")
    pool_args = [(file, cat, shared_queue) for cat, f_list in file_stack.items() for file in list(
        f_list)]

    with multiprocessing.Pool(conf.infra['cpu_available']) as pool:
        list(tqdm.tqdm(pool.imap(word_count_file, pool_args),
                       desc="Word count progress",
                       leave=False,
                       disable=conf.args['progress_bar']))

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

    to_save = {}
    for cat, words in words_count.items():
        to_save[cat] = {
            'etape': 'récolte',
            'mails': len([arg for arg in pool_args if arg[1] == cat]),
            'mots': sum(iteration for iteration in words.values()),
            'mots_uniques': len(words.keys())
        }

    to_save['globales'] = {'etape': 'récolte', 'mails': 0, 'mots': 0, 'mots_uniques': 0}

    for cat in [cat_key for cat_key in to_save if cat_key != 'globales']:
        for key in ['mails', 'mots', 'mots_uniques']:
            to_save['globales'][key] += to_save[cat][key]

    store_word_count(to_save, conf)
    logger.info("Word count récolte fin")


def word_count_file(pool_arg):
    """
    Compte les mots d'un mail d'une catégorie et ajoute le comptage
    :param pool_arg: <list> [<str>, <str>, <dict>]
    :return: <None>
    """
    file = pool_arg[0]
    cat = pool_arg[1]
    words_queue = pool_arg[2]
    word_count = {cat: {}}

    mots = importation.get_text_file(file).split()
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
