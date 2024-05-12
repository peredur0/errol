# coding: utf-8
"""
Fichier pour tester les développements en cours
"""
import logging


logger = logging.getLogger(__name__)
from src.stages import fouille


def main(conf):
    """
    Processus principal
    :param conf: <Settings>
    :return: None
    """
    logger.info("DEVELOPPEMENT")
    fouille.databases_init(conf)

