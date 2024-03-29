# coding: utf-8
"""
Gestion des configurations du programme
"""

import logging
from configparser import ConfigParser
from src.program import args

logger = logging.getLogger(__name__)


def init():
    """
    Fonction d'initialisation
    :param name: nom du programme à instancier
    :return: <Settings>
    """
    arguments = args.args_handler()
    return Settings(arguments)


def init_log():
    """
    Initialisation du system de logging
    :return: <None>
    """
    log_level = logging.DEBUG
    log_handle = logging.StreamHandler()
    log_format = logging.Formatter('%(asctime)s [%(levelname)s] - (%(name)s) : %(message)s')
    log_handle.setFormatter(log_format)

    mods = ['__main__', 'src.program.settings']
    for module in mods:
        m_logger = logging.getLogger(module)
        m_logger.setLevel(log_level)
        m_logger.addHandler(log_handle)


class Settings:
    """
    Classe regroupant les paramètres globals des programmes
    """
    def __init__(self, arguments):
        init_log()
        self.stage = arguments.stage
        logger.info("Initialisation %s OK", self.stage)
        logger.debug(arguments)

    def __repr__(self):
        return f"<Settings>: {self.stage}"

    def __eq__(self, other):
        if isinstance(other, Settings):
            return self.stage == other.stage
        return NotImplemented
