# coding: utf-8
"""
Programme de vérification d'un message
"""

import logging

logger = logging.getLogger(__name__)


def main(conf):
    """
    Fonction principale
    """
    logger.info("Check d'un message")
    models = {name: f"{conf.infra['storage']}/{name}.pickle" for name in conf.args['models']}




