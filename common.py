import sqlite3
import os

data_file = os.path.expanduser('db.sqlite')
db = sqlite3.connect(data_file)
