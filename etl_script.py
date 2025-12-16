import requests
from neo4j import GraphDatabase

# --- CONFIGURATION ---
TB_URL = "http://localhost:9090"
TB_USER = "tenant@thingsboard.org"
TB_PASS = "tenant"

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "password"


def get_tb_token():
    url = f"{TB_URL}/api/auth/login"
    try:
        res = requests.post(url, json={"username": TB_USER, "password": TB_PASS})
        res.raise_for_status()
        return res.json()['token']
    except Exception as e:
        print(f"❌ TB Login Failed: {e}")
        return None


def get_tb_entities(token, entity_type):
    """Fetch all Assets or Devices from ThingsBoard"""
    url = f"{TB_URL}/api/tenant/{entity_type}s?pageSize=1000&page=0"
    headers = {"X-Authorization": f"Bearer {token}"}
    res = requests.get(url, headers=headers)
    return res.json()['data']


def get_tb_relations(token, entity_id, entity_type):
    url = f"{TB_URL}/api/relations?fromId={entity_id}&fromType={entity_type}"
    headers = {"X-Authorization": f"Bearer {token}"}
    res = requests.get(url, headers=headers)
    return res.json() if res.status_code == 200 else []

class GraphDB:
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

    def close(self):
        self.driver.close()

    def clear_db(self):
        """Wipe database clean before import"""
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
            print("🧹 Neo4j Database cleared.")

    def create_node(self, entity_id, name, entity_type, label):
        """Create a Node (Asset or Device)"""
        query = (
            f"MERGE (n:{label} {{id: $id}}) "
            "SET n.name = $name, n.type = $type"
        )
        with self.driver.session() as session:
            session.run(query, id=entity_id, name=name, type=entity_type)

    def create_relation(self, from_id, to_id, relation_type):
        """Create an Edge between two nodes"""
        query = (
            "MATCH (a {id: $from_id}), (b {id: $to_id}) "
            f"MERGE (a)-[:{relation_type}]->(b)"
        )
        with self.driver.session() as session:
            session.run(query, from_id=from_id, to_id=to_id)


def run_etl():
    print("🚀 Starting ETL Process...")

    token = get_tb_token()
    if not token: return

    db = GraphDB()
    db.clear_db()

    all_entities = []

    assets = get_tb_entities(token, "asset")
    print(f"📥 Found {len(assets)} Assets. Loading to Neo4j...")
    for a in assets:
        db.create_node(a['id']['id'], a['name'], a['type'], "Asset")
        all_entities.append(a)

    devices = get_tb_entities(token, "device")
    print(f"📥 Found {len(devices)} Devices. Loading to Neo4j...")
    for d in devices:
        db.create_node(d['id']['id'], d['name'], d['type'], "Device")
        all_entities.append(d)

    print("🔗 Syncing Relations (this may take a moment)...")
    count = 0
    for entity in all_entities:
        e_id = entity['id']['id']
        e_type = entity['id']['entityType']

        relations = get_tb_relations(token, e_id, e_type)

        for r in relations:
            to_id = r['to']['id']
            rel_type = r['type']

            db.create_relation(e_id, to_id, rel_type)
            count += 1

    print(f"✅ ETL Complete! Synced {count} relationships.")
    db.close()


if __name__ == "__main__":
    run_etl()