import socket


from lib.db import DB, KeyDB


def _raise_dns_error(*args, **kwargs):
    raise socket.gaierror(8, 'nodename nor servname provided, or not known')


def test_redis_host_falls_back_to_localhost_when_docker_name_not_resolvable(monkeypatch):
    monkeypatch.setenv('REDIS_HOST', 'redis')
    monkeypatch.setattr(socket, 'getaddrinfo', _raise_dns_error)

    db = DB()

    assert db.host == 'localhost'


def test_keydb_host_falls_back_to_localhost_when_docker_name_not_resolvable(monkeypatch):
    monkeypatch.setenv('KEYDB_HOST', 'keydb')
    monkeypatch.setattr(socket, 'getaddrinfo', _raise_dns_error)

    keydb = KeyDB()

    assert keydb.host == 'localhost'


def test_custom_host_is_left_untouched_when_not_resolvable(monkeypatch):
    monkeypatch.setenv('REDIS_HOST', 'cache.internal')
    monkeypatch.setattr(socket, 'getaddrinfo', _raise_dns_error)

    db = DB()

    assert db.host == 'cache.internal'


