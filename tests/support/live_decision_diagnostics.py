"""Shared test helpers moved out of test modules (TST-01)."""

import json


class Logger:
    def __init__(self):
        self.rows = []
    def info(self, message):
        self.rows.append(json.loads(message))
