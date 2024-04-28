# coding: utf-8
"""
Gestion des configurations du programme
"""

import logging
import multiprocessing
import os.path
import sys
from configparser import ConfigParser
from src.program import args
from src.modules import cmd_docker

logger = logging.getLogger(__name__)


def init():
    """
    Fonction d'initialisation
    :return: <Settings>
    """
    arguments = args.args_handler()
    ini_file = './config/errol.ini'
    if not os.path.isfile(ini_file):
        print(f"FATAL ERROR: fichier manquant {ini_file}", file=sys.stderr)
        sys.exit(1)

    conf = ConfigParser()
    conf.read(ini_file, encoding='utf-8')
    return Settings(conf, arguments)


def init_log(debug):
    """
    Initialisation du system de logging
    :param debug: <bool>
    :return: <None>
    """
    log_level = logging.DEBUG if debug else logging.INFO
    log_handle = logging.StreamHandler()
    log_format = logging.Formatter('%(asctime)s [%(levelname)s] - (%(name)s) : %(message)s')
    log_handle.setFormatter(log_format)

    mods = ['__main__',
            'src.program.settings',
            'src.stages.develop', 'src.stages.fouille', 'src.stages.lang',
            'src.modules.cmd_docker', 'src.modules.cmd_sqlite', 'src.modules.cmd_mongo',
            'src.modules.word_count', 'src.modules.importation', 'src.modules.transformation',
            'src.modules.nettoyage']
    for module in mods:
        m_logger = logging.getLogger(module)
        m_logger.setLevel(log_level)
        m_logger.addHandler(log_handle)


class Settings:
    """
    Classe regroupant les paramètres globals des programmes
    """
    def __init__(self, conf, arguments):
        try:
            init_log(arguments.debug)
        except AttributeError:
            init_log(False)

        self.stage = arguments.stage
        self.args = {
            'progress_bar': not arguments.progress_bar
        }

        self.infra = {
            'containers': [conf.get('infra', 'psql_container'),
                           conf.get('infra', 'mongo_container')],
            'psql': {
                'host': conf.get('psql', 'host'),
                'port': conf.get('psql', 'port')
            },
            'mongo': {
                'host': conf.get('mongo', 'host'),
                'port': conf.get('mongo', 'port'),
                'db': conf.get('mongo', 'db'),
                'collection': conf.get('mongo', 'collection'),
                'user_name': conf.get('mongo', 'user'),
                'user_pwd': conf.get('mongo', 'password')
            },
            'sqlite': {
                'file': conf.get('sqlite', 'file'),
                'schema_stats': conf.get('sqlite', 'schema_stats')
            },
            'cpu_available': (multiprocessing.cpu_count()//2)+1
        }

        match self.stage:
            case 'develop':
                pass

            case 'fouille':
                self.args['ham'] = arguments.ham
                self.args['spam'] = arguments.spam
                self.args['csv'] = arguments.fichier_csv

                for cont in self.infra['containers']:
                    if not cmd_docker.container_up(cont):
                        logger.error('Docker conteneur %s non disponible', cont)
                        sys.exit(1)

            case _:
                logger.error("Etape %s non reconnue", self.stage)
                sys.exit(1)

        logger.info("Initialisation %s OK", self.stage)

    def __repr__(self):
        return f"<Settings: {self.stage}>"

    def __eq__(self, other):
        if isinstance(other, Settings):
            return self.stage == other.stage
        return NotImplemented
