import streamlit as st
import requests
from neo4j import GraphDatabase
import uuid
TB_URL = "http://localhost:9090"
TB_USER = "tenant@thingsboard.org"
TB_PASS = "tenant"

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "password"


class IoTManager:
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

    def close(self):
        self.driver.close()

    def get_token(self):
        try:
            res = requests.post(f"{TB_URL}/api/auth/login", json={"username": TB_USER, "password": TB_PASS})
            return res.json().get('token')
        except:
            return None

    def get_assets(self):
        with self.driver.session() as session:
            query = """
            MATCH (n:Asset) 
            RETURN n.name AS Name, n.type AS Type, n.status AS Status, n.id AS ID
            ORDER BY n.status DESC, n.name ASC
            """
            return [record.data() for record in session.run(query)]

    def create_draft_asset(self, name, asset_type):
        temp_id = str(uuid.uuid4())
        with self.driver.session() as session:
            session.run(
                "CREATE (a:Asset {id: $id, name: $name, type: $type, status: 'draft'})",
                id=temp_id, name=name, type=asset_type
            )

    def sync_to_thingsboard(self):
            token = self.get_token()
            if not token:
                return "❌ Auth Failure: Could not get Token from ThingsBoard."

            headers = {"X-Authorization": f"Bearer {token}"}

            with self.driver.session() as session:
                drafts = list(
                    session.run("MATCH (n:Asset {status: 'draft'}) RETURN n.id AS id, n.name AS name, n.type AS type"))

            if not drafts: return "⚠️ No drafts found to sync."

            success_count = 0
            errors = []

            for node in drafts:
                payload = {
                    "name": node['name'],
                    "type": node['type']
                }

                try:
                    url = f"{TB_URL}/api/asset"
                    res = requests.post(url, json=payload, headers=headers)

                    if res.status_code == 200:
                        real_id = res.json()['id']['id']

                        with self.driver.session() as session:
                            session.run(
                                "MATCH (n:Asset {id: $old_id}) SET n.id = $new_id, n.status = 'synced'",
                                old_id=node['id'],
                                new_id=real_id
                            )
                        success_count += 1
                    else:
                        errors.append(f"Failed '{node['name']}': HTTP {res.status_code} - {res.text}")

                except Exception as e:
                    errors.append(f"Exception for '{node['name']}': {str(e)}")

            if success_count > 0 and not errors:
                return f"✅ Successfully synced {success_count} assets."
            elif errors:
                return f"⚠️ Synced {success_count}, but with errors: " + " | ".join(errors)
            else:
                return "❌ Sync failed completely."

    def import_from_cloud(self):
        token = self.get_token()
        if not token: return "❌ Auth Failed"
        headers = {"X-Authorization": f"Bearer {token}"}

        try:
            res = requests.get(f"{TB_URL}/api/tenant/assets?pageSize=1000&page=0", headers=headers)
            assets = res.json()['data']
        except Exception as e:
            return f"❌ Connection Error: {e}"

        count = 0
        with self.driver.session() as session:
            for item in assets:
                query = """
                MERGE (n:Asset {id: $id})
                SET n.name = $name, n.type = $type, n.status = 'synced'
                """
                session.run(query, id=item['id']['id'], name=item['name'], type=item['type'])
                count += 1

        return f"✅ Imported & Aligned {count} assets from ThingsBoard."

    def delete_asset(self, asset_id, policy):
        msg = ""
        if policy == "strict":
            token = self.get_token()
            if token:
                headers = {"X-Authorization": f"Bearer {token}"}
                res = requests.delete(f"{TB_URL}/api/asset/{asset_id}", headers=headers)
                if res.status_code == 200:
                    msg += "☁️ Deleted from Cloud. "
                else:
                    msg += f"⚠️ Cloud delete failed ({res.status_code}). "

        with self.driver.session() as session:
            check = session.run("MATCH (n) WHERE n.id = $id RETURN n", id=asset_id).single()

            if check:
                session.run("MATCH (n) WHERE n.id = $id DETACH DELETE n", id=asset_id)
                msg += "🗑️ Graph Node Deleted."
            else:
                msg += "⚠️ Node not found in Graph (ID mismatch?)."

        return msg


st.set_page_config(page_title="IoT Manager", layout="wide")
st.title("IoT#ETL with Thingsboard")

manager = IoTManager()

# SIDEBAR
st.sidebar.header("Configuration")

st.sidebar.subheader("1. ETL")
if st.sidebar.button("⬇️ Import from Cloud", help="Restores assets from ThingsBoard if they are missing locally"):
    with st.spinner("Pulling data from ThingsBoard..."):
        msg = manager.import_from_cloud()
        if "✅" in msg:
            st.toast(msg, icon="✅")
            st.rerun()
        else:
            st.error(msg)

st.sidebar.markdown("---")

st.sidebar.subheader("2. Synchronization")
if st.sidebar.button("⬆️ Sync Drafts to Cloud", help="Pushes new local rooms to ThingsBoard"):
    with st.spinner("Pushing data..."):
        msg = manager.sync_to_thingsboard()
        if "✅" in msg:
            st.toast(msg, icon="✅")
            st.rerun()
        elif "⚠️" in msg:
             st.toast(msg, icon="⚠️")
             st.rerun()
        else:
            st.error(msg)

st.sidebar.markdown("---")

st.sidebar.subheader("3. Settings")
sync_policy = st.sidebar.radio(
    "Deletion Policy",
    ("Safe Mode (Graph Only)", "Strict Mode (Graph + Cloud)"),
    index=0
)
policy_code = "safe" if "Safe" in sync_policy else "strict"

tab1, tab2 = st.tabs(["Infrastructure", "➕ Create Asset"])

with tab1:
    st.subheader("Current Infrastructure")
    assets = manager.get_assets()

    if assets:
        for asset in assets:
            col1, col2, col3, col4, col5 = st.columns([3, 2, 2, 3, 1])
            col1.write(f"**{asset['Name']}**")
            col2.write(asset['Type'])
            col3.write(asset['Status'] if asset.get('Status') else "synced")
            col4.write(f"`{asset['ID']}`")

            if col5.button("❌", key=asset['ID'], help="Delete Asset"):
                result = manager.delete_asset(asset['ID'], policy_code)
                st.toast(result)
                st.rerun()
    else:
        st.info("No assets found.")

with tab2:
    st.subheader("Create New Asset")
    col1, col2 = st.columns(2)
    new_name = col1.text_input("Name")
    new_type = col2.selectbox("Type", ["Building", "Floor", "Room", "Warehouse"])

    if st.button("Create Draft"):
        if new_name:
            manager.create_draft_asset(new_name, new_type)
            st.success("Draft created! Go to sidebar to Sync.")
            st.rerun()

manager.close()