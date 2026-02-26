from cassandra.cluster import Cluster
from datetime import datetime, timezone
import threading


class CassandraLogger:

    def __init__(self):
        self.session = None
        self.lock = threading.Lock()

        try:
            cluster = Cluster(["127.0.0.1"])
            self.session = cluster.connect()
            print("Cassandra connected successfully")

            # create keyspace
            self.session.execute("""
            CREATE KEYSPACE IF NOT EXISTS crawler_logs
            WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};
            """)

            self.session.set_keyspace("crawler_logs")

            # create table
            self.session.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id UUID PRIMARY KEY,
                timestamp TIMESTAMP,
                level TEXT,
                message TEXT,
                url TEXT
            );
            """)

        except Exception as e:
            print("Cassandra connection failed:", e)
            self.session = None

    def log(self, level, message, url=None):
        if not self.session:
            return

        try:
            with self.lock:
                self.session.execute(
                    """
                    INSERT INTO logs (id, timestamp, level, message, url)
                    VALUES (uuid(), %s, %s, %s, %s)
                    """,
                    (datetime.now(timezone.utc), level, message, url)
                )
        except Exception as e:
            print("Cassandra log failed:", e)

            