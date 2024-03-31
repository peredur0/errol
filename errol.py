#! /usr/bin/env python3
# coding: utf-8
"""
Point d'entrée unique du programme
"""
import logging
from src.program import settings

logger = logging.getLogger(__name__)

if __name__ == '__main__':
    global_settings = settings.init()
