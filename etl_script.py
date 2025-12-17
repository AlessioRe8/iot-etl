import requests
from neo4j import GraphDatabase

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
    """Fetch all Assets or Devices"""
    url = f"{TB_URL}/api/tenant/{entity_type}s?pageSize=1000&page=0"
    headers = {"X-Authorization": f"Bearer {token}"}
    res = requests.get(url, headers=headers)
    return res.json()['data']


def get_tb_attributes(token, entity_id, entity_type):
    """
    Fetch dynamic attributes for an entity.
    """
    url = f"{TB_URL}/api/plugins/telemetry/{entity_type.upper()}/{entity_id}/values/attributes/SERVER_SCOPE"
    headers = {"X-Authorization": f"Bearer {token}"}
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            return {item['key']: item['value'] for item in res.json()}
    except:
        pass
    return {}


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

    def get_all_node_ids(self, label):
        """Get all IDs currently in the graph to check for deletions"""
        with self.driver.session() as session:
            result = session.run(f"MATCH (n:{label}) RETURN n.id as id")
            return {record["id"] for record in result}

    def delete_node(self, entity_id):
        """Remove a node that no longer exists in ThingsBoard"""
        with self.driver.session() as session:
            session.run("MATCH (n {id: $id}) DETACH DELETE n", id=entity_id)
            print(f"🗑️ Deleted Node {entity_id} (Sync alignment)")

    def upsert_node(self, entity_data, attributes, label):
        e_id = entity_data['id']['id']
        name = entity_data.get('name', 'Unknown')
        e_type = entity_data.get('type', 'Unknown')

        properties = {
            "id": e_id,
            "name": name,
            "type": e_type,
            "tb_label": entity_data.get('label', '')
        }
        properties.update(attributes)

        query = (
            f"MERGE (n:{label} {{id: $id}}) "
            "SET n += $props "
        )
        with self.driver.session() as session:
            session.run(query, id=e_id, props=properties)

    def create_relation(self, from_id, to_id, relation_type):
        query = (
            "MATCH (a {id: $from_id}), (b {id: $to_id}) "
            f"MERGE (a)-[:{relation_type}]->(b)"
        )
        with self.driver.session() as session:
            session.run(query, from_id=from_id, to_id=to_id)

def run_etl():
    print("🚀 Starting Smart ETL (Alignment Mode)...")
    token = get_tb_token()
    if not token: return

    db = GraphDB()

    entity_groups = [("asset", "Asset"), ("device", "Device")]

    all_current_tb_ids = set()
    all_entities_data = []

    for tb_type, graph_label in entity_groups:
        print(f"📥 Processing {graph_label}s...")

        tb_items = get_tb_entities(token, tb_type)

        for item in tb_items:
            e_id = item['id']['id']
            all_current_tb_ids.add(e_id)

            attrs = get_tb_attributes(token, e_id, tb_type)

            db.upsert_node(item, attrs, graph_label)
            all_entities_data.append(item)

        graph_ids = db.get_all_node_ids(graph_label)

        current_tb_type_ids = {i['id']['id'] for i in tb_items}
        ids_to_delete = graph_ids - current_tb_type_ids

        for del_id in ids_to_delete:
            db.delete_node(del_id)

    print("🔗 Syncing Relations...")
    for entity in all_entities_data:
        e_id = entity['id']['id']
        e_type = entity['id']['entityType']

        relations = get_tb_relations(token, e_id, e_type)
        for r in relations:
            to_id = r['to']['id']
            rel_type = r['type']
            db.create_relation(e_id, to_id, rel_type)

    print("✅ Smart Sync Complete!")
    db.close()


if __name__ == "__main__":
    run_etl()