# coding: utf-8
"""
Fichier pour le développement
"""
import logging

logger = logging.getLogger(__name__)

def main(conf):
    """
    Fonction principale
    """
    logger.info("DEVELOPPEMENT")
    logger.info("Developping the new feature - %s", conf)
