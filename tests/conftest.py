import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import make_app, make_factory  # noqa: E402


@pytest.fixture()
def app(tmp_path):
    return make_app(tmp_path)


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def make(client, app):
    return make_factory(client, app)
