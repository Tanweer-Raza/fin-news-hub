import logging
from cassandra_logger import CassandraLogger

cassandra_logger = CassandraLogger()


class CassandraHandler(logging.Handler):

    def emit(self, record):
        try:
            msg = self.format(record)
            level = record.levelname

            url = None
            if hasattr(record, "url"):
                url = record.url

            cassandra_logger.log(level, msg, url)
        except Exception as e:
            print("Cassandra logging failed:", e)