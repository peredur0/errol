#! /usr/bin/env python3
# coding: utf-8

"""
Module d'outil pour docker
"""
import logging
import docker
import docker.errors

logger = logging.getLogger(__name__)


def container_up(name):
    """
    Vérifie l'état du conteneur.
    :param name: <str> nom du conteneur
    :return: <bool>
    """
    docker_cli = docker.DockerClient()

    try:
        conteneur = docker_cli.containers.get(name)
    except docker.errors.NotFound as err:
        logger.warning(err)
        return False

    conteneur_state = conteneur.attrs['State']
    return conteneur_state['Status'] == "running"
