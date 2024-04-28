#! /usr/bin/env python3
# coding: utf-8
"""
Point d'entrée unique du programme
"""
import logging
import sys

from src.program import settings
from src.stages import develop, fouille

logger = logging.getLogger(__name__)

if __name__ == '__main__':
    global_settings = settings.init()

    match global_settings.stage:
        case 'develop':
            develop.main(global_settings)

        case 'fouille':
            fouille.main(global_settings)

        case _:
            logger.error("Etape non attendue - %s", global_settings.stage)
            sys.exit(1)
