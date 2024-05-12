# coding: utf-8
"""
Fichier pour tester les développements en cours
"""
import logging
from src.stages import fouille


logger = logging.getLogger(__name__)


def main(conf):
    """
    Processus principal
    :param conf: <Settings>
    :return: None
    """
    logger.info("DEVELOPPEMENT")
    fouille.databases_init(conf)
