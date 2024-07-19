# coding: utf-8
"""
Fichier pour tester les développements en cours
"""
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
    logger.info("DEVELOPMENT")
