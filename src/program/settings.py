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
            'src.stages.develop', 'src.stages.fouille', 'src.stages.nlp', 'src.stages.features',
            'src.stages.vecteurs', 'src.stages.train', 'src.stages.check',
            'src.modules.cmd_docker', 'src.modules.cmd_sqlite', 'src.modules.cmd_mongo',
            'src.modules.cmd_psql', 'src.modules.word_count', 'src.modules.importation',
            'src.modules.transformation', 'src.modules.nettoyage', 'src.modules.graph',
            'src.annexes.zipf']
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
            'progress_bar': not arguments.progress_bar,
            'rapport': arguments.rapport
        }

        self.infra = {
            'containers': [conf.get('infra', 'psql_container'),
                           conf.get('infra', 'mongo_container')],
            'psql': {
                'host': conf.get('psql', 'host'),
                'port': conf.get('psql', 'port'),
                'user': conf.get('psql', 'user'),
                'pass': conf.get('psql', 'password'),
                'db': conf.get('psql', 'db'),
                'schema': {
                    'fouille': conf.get('psql', 'schema_fouille'),
                    'features': conf.get('psql', 'schema_features'),
                    'nlp': conf.get('psql', 'schema_nlp'),
                    'tfidf': conf.get('psql', 'schema_tfidf')
                },
                'queries': conf.get('psql', 'queries'),
                'vecteurs': {
                    'tfidf': {
                        "data": conf.get('psql', 'tfidf_data_sql')
                    }
                }
            },
            'mongo': {
                'host': conf.get('mongo', 'host'),
                'port': conf.get('mongo', 'port'),
                'db': conf.get('mongo', 'db'),
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
                self.args['graph'] = arguments.graph

            case 'features':
                self.args['graph'] = arguments.graph
                self.args['langue'] = arguments.langue[0]
                self.args['stats'] = arguments.stats
                self.infra['mongo']['collection'] = arguments.collection
                for cont in self.infra['containers']:
                    if not cmd_docker.container_up(cont):
                        logger.error('Docker conteneur %s non disponible', cont)
                        sys.exit(1)

            case 'nlp':
                self.args['stats'] = arguments.stats
                self.args['langue'] = arguments.langue[0]
                self.infra['mongo']['collection'] = arguments.collection
                for cont in self.infra['containers']:
                    if not cmd_docker.container_up(cont):
                        logger.error('Docker conteneur %s non disponible', cont)
                        sys.exit(1)

            case 'fouille':
                self.args['ham'] = arguments.ham
                self.args['spam'] = arguments.spam
                self.args['graph'] = arguments.graph
                self.args['stats'] = arguments.stats
                self.infra['mongo']['collection'] = arguments.collection[0]

                for cont in self.infra['containers']:
                    if not cmd_docker.container_up(cont):
                        logger.error('Docker conteneur %s non disponible', cont)
                        sys.exit(1)

            case "vecteurs":
                self.args['graph'] = arguments.graph
                self.args['method'] = arguments.method
                self.args['limit'] = arguments.limit
                self.args['init'] = arguments.init
                self.args['langue'] = arguments.langue[0]

                psql_cont = conf.get('infra', 'psql_container')
                if not cmd_docker.container_up(psql_cont):
                    logger.error('Docker conteneur %s non disponible', psql_cont)
                    sys.exit(1)

            case "train":
                psql_cont = conf.get('infra', 'psql_container')
                if not cmd_docker.container_up(psql_cont):
                    logger.error('Docker conteneur %s non disponible', psql_cont)
                    sys.exit(1)
                self.args['models'] = arguments.models
                self.infra['storage'] = conf.get('infra', 'model_store')
                os.makedirs(self.infra['storage'], exist_ok=True)

            case "check":
                psql_cont = conf.get('infra', 'psql_container')
                if not cmd_docker.container_up(psql_cont):
                    logger.error('Docker conteneur %s non disponible', psql_cont)
                    sys.exit(1)
                self.args['models'] = arguments.models
                self.infra['storage'] = conf.get('infra', 'model_store')

            case _:
                logger.error("Etape %s non reconnue", self.stage)
                sys.exit(1)

        self.rapport = {
            'images': conf.get('rapport', 'images'),
            'fouille': conf.get('rapport', 'fouille'),
            'features': conf.get('rapport', 'features')
        }
        logger.info("Initialisation du programme pour la phase %s - OK", self.stage)

    def __repr__(self):
        return f"<Settings: {self.stage}>"

    def __eq__(self, other):
        if isinstance(other, Settings):
            return self.stage == other.stage
        return NotImplemented
