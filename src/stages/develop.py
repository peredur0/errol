# coding: utf-8
"""
Fichier pour tester les développements en cours
"""
import logging
import pandas as pd
import sqlalchemy
from src.modules import graph
from src.modules import cmd_psql


logger = logging.getLogger(__name__)


def main(conf):
    """
    Processus principal
    :param conf: <Settings>
    :return: None
    """
    logger.info("DEVELOPPEMENT")
