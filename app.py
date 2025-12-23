import streamlit as st
import requests
from neo4j import GraphDatabase
import uuid
from streamlit_agraph import agraph, Node, Edge, Config

import os
from dotenv import load_dotenv


load_dotenv()
TB_URL = os.getenv("TB_URL")
TB_USER = os.getenv("TB_USER")
TB_PASS = os.getenv("TB_PASSWORD")
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD")

@st.cache_resource
def get_driver():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    return driver

class IoTManager:
    def __init__(self):
        self.driver = get_driver()


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

    def get_devices(self):
        with self.driver.session() as session:
            query = """
            MATCH (n:Device) 
            RETURN n.name AS Name, n.type AS Type, n.label as Label, n.status AS Status, n.id AS ID
            ORDER BY n.status DESC, n.name ASC
            """
            return [record.data() for record in session.run(query)]

    def get_all_nodes(self):
        """Helper to get list of ALL node names for dropdowns"""
        with self.driver.session() as session:
            query = "MATCH (n) WHERE n:Asset OR n:Device RETURN n.name AS Name ORDER BY n.name"
            return [r['Name'] for r in session.run(query)]

    def get_relations(self):
        with self.driver.session() as session:
            query = """
            MATCH (a)-[r]->(b)
            WHERE (a:Asset OR a:Device) AND (b:Asset OR b:Device)
            RETURN a.name AS From, type(r) AS Relation, b.name AS To, r.status AS Status
            """
            return [record.data() for record in session.run(query)]

    def get_agraph_elements(self):
        nodes = []
        edges = []
        with self.driver.session() as session:
            result_nodes = session.run("MATCH (n) WHERE n:Asset OR n:Device RETURN n.id AS id, n.name AS name, labels(n) AS labels, n.status AS status")
            for r in result_nodes:
                lbl = "Device" if "Device" in r['labels'] else "Asset"

                if r['status'] == 'draft':
                    node_color = "#808080"
                elif lbl == "Asset":
                    node_color = "#00C853"
                else:
                    node_color = "#2962FF"

                nodes.append(Node(
                    id=r['name'],
                    label=r['name'],
                    size=25,
                    shape="box",
                    color=node_color,
                    font={'color': 'white'}
                ))

            result_edges = session.run("MATCH (a)-[r]->(b) WHERE (a:Asset OR a:Device) AND (b:Asset OR b:Device) RETURN a.name AS src, b.name AS tgt, type(r) AS type, r.status AS status")
            for r in result_edges:
                edge_color = "#FFFFFF" if r['status'] == 'synced' else "#FF5252"

                edges.append(Edge(
                    source=r['src'],
                    target=r['tgt'],
                    label=r['type'],
                    color=edge_color,
                    font={'color': 'white', 'strokeWidth': 0}
                ))

        return nodes, edges

    def create_draft_asset(self, name, asset_type):
        temp_id = str(uuid.uuid4())
        with self.driver.session() as session:
            session.run(
                "CREATE (a:Asset {id: $id, name: $name, type: $type, status: 'draft'})",
                id=temp_id, name=name, type=asset_type
            )

    def create_draft_device(self, name, device_type, label=None):
        temp_id = str(uuid.uuid4())
        with self.driver.session() as session:
            session.run(
                "CREATE (d:Device {id: $id, name: $name, type: $type, label: $label, status: 'draft'})",
                id=temp_id, name=name, type=device_type, label=label or "Device"
            )

    def create_relation(self, from_name, to_name, rel_type):
        with self.driver.session() as session:
            query = f"""
            MATCH (a), (b) 
            WHERE a.name = $from_name AND b.name = $to_name
            MERGE (a)-[:{rel_type}]->(b)
            """
            session.run(query, from_name=from_name, to_name=to_name)

    def sync_assets_to_cloud(self):
            token = self.get_token()
            if not token:
                return "❌ Auth Failure: Could not get Token."

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

    def sync_devices_to_cloud(self):
        token = self.get_token()
        if not token: return "❌ Auth Failure"

        headers = {"X-Authorization": f"Bearer {token}"}

        with self.driver.session() as session:
            drafts = list(session.run("MATCH (n:Device {status: 'draft'}) RETURN n.id AS id, n.name AS name, n.type AS type, n.label AS label"))

        if not drafts: return "⚠️ No device drafts found."

        success_count = 0
        errors = []

        for node in drafts:
            payload = {
                "name": node['name'],
                "type": node['type'],
                "label": node['label'] if node['label'] else "Device"
            }

            try:
                url = f"{TB_URL}/api/device"
                res = requests.post(url, json=payload, headers=headers)

                if res.status_code == 200:
                    real_id = res.json()['id']['id']

                    with self.driver.session() as session:
                        session.run(
                            "MATCH (n:Device {id: $old_id}) SET n.id = $new_id, n.status = 'synced'",
                            old_id=node['id'],
                            new_id=real_id
                        )
                    success_count += 1
                else:
                    errors.append(f"Failed '{node['name']}': {res.status_code}")

            except Exception as e:
                errors.append(f"Error '{node['name']}': {str(e)}")

        if success_count > 0:
            return f"✅ Synced {success_count} Devices."
        else:
            return "❌ Sync failed. " + " ".join(errors)

    def sync_relationship_to_cloud(self, from_name, to_name, rel_type):
        token = self.get_token()
        if not token: return "❌ Auth Failed"
        headers = {"X-Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        with self.driver.session() as session:
            result = session.run("""
                MATCH (a {name: $source})-[:%s]->(b {name: $target})
                RETURN a.id as from_id, labels(a) as from_labels, a.status as from_status, 
                       b.id as to_id, labels(b) as to_labels, b.status as to_status
            """ % rel_type, source=from_name, target=to_name).single()

        if not result: return "❌ Relation not found."

        if result['from_status'] == 'draft' or result['to_status'] == 'draft':
            return "⚠️ Cannot sync relationship: One or both entities are still Drafts. Sync nodes first!"

        from_type = "DEVICE" if "Device" in result['from_labels'] else "ASSET"
        to_type = "DEVICE" if "Device" in result['to_labels'] else "ASSET"

        payload = {
            "from": {"id": result['from_id'], "entityType": from_type},
            "to": {"id": result['to_id'], "entityType": to_type},
            "type": rel_type, "typeGroup": "COMMON"
        }

        try:
            res = requests.post(f"{TB_URL}/api/relation", json=payload, headers=headers)
            if res.status_code == 200:
                with self.driver.session() as session:
                    session.run(f"MATCH (a {{name: $f}})-[r:{rel_type}]->(b {{name: $t}}) SET r.status = 'synced'",
                                f=from_name, t=to_name)
                return f"✅ Linked: {from_name} -> {to_name}"
            else:
                return f"⚠️ Error {res.status_code}"
        except Exception as e:
            return f"❌ Exception: {e}"

    def import_from_cloud(self):
        token = self.get_token()
        if not token: return "❌ Auth Failed"
        headers = {"X-Authorization": f"Bearer {token}"}

        asset_ids = []
        device_ids = []
        messages = []

        try:
            res = requests.get(f"{TB_URL}/api/tenant/assets?pageSize=1000&page=0", headers=headers)
            if res.status_code == 200:
                assets = res.json()['data']
                with self.driver.session() as session:
                    for item in assets:
                        query = "MERGE (n:Asset {id: $id}) SET n.name = $name, n.type = $type, n.status = 'synced'"
                        session.run(query, id=item['id']['id'], name=item['name'], type=item['type'])
                        asset_ids.append(item['id']['id'])
                messages.append(f"✅ {len(assets)} Assets")
        except Exception as e:
            messages.append(f"❌ Assets: {str(e)}")

        try:
            res = requests.get(f"{TB_URL}/api/tenant/devices?pageSize=1000&page=0", headers=headers)
            if res.status_code == 200:
                devices = res.json()['data']
                with self.driver.session() as session:
                    for item in devices:
                        lbl = item.get('label', 'Device')
                        query = "MERGE (n:Device {id: $id}) SET n.name = $name, n.type = $type, n.label = $lbl, n.status = 'synced'"
                        session.run(query, id=item['id']['id'], name=item['name'], type=item['type'], lbl=lbl)
                        device_ids.append(item['id']['id'])
                messages.append(f"✅ {len(devices)} Devices")
        except Exception as e:
            messages.append(f"❌ Devices: {str(e)}")

        rel_count = 0
        all_ids = [(uid, 'ASSET') for uid in asset_ids] + [(uid, 'DEVICE') for uid in device_ids]

        with self.driver.session() as session:
            for entity_id, entity_type in all_ids:
                try:
                    r_res = requests.get(f"{TB_URL}/api/relations/info?fromId={entity_id}&fromType={entity_type}",
                                         headers=headers)
                    if r_res.status_code == 200:
                        relations = r_res.json()
                        for rel in relations:
                            target_id = rel['to']['id']
                            rel_type = rel['type']

                            query = f"""
                            MATCH (a {{id: $src}}), (b {{id: $tgt}})
                            MERGE (a)-[r:{rel_type}]->(b)
                            SET r.status = 'synced'
                            """
                            session.run(query, src=entity_id, tgt=target_id)
                            rel_count += 1
                except:
                    pass

        messages.append(f"✅ {rel_count} Relations")
        return " | ".join(messages)

    def delete_node(self, node_id, node_label, policy):
        msg = ""
        if policy == "strict":
            token = self.get_token()
            if token:
                headers = {"X-Authorization": f"Bearer {token}"}
                endpoint = "device" if node_label == "Device" else "asset"
                res = requests.delete(f"{TB_URL}/api/{endpoint}/{node_id}", headers=headers)
                if res.status_code == 200:
                    msg += "⚠️ Cloud Deleted. "
                else:
                    msg += f"⚠️ Cloud Fail ({res.status_code}). "

        with self.driver.session() as session:
            session.run("MATCH (n) WHERE n.id = $id DETACH DELETE n", id=node_id)
            msg += "Graph Node Deleted."
        return msg


    def delete_relation(self, from_name, to_name, rel_type, policy="safe"):
        msg = ""

        if policy == "strict":
            token = self.get_token()
            if token:
                with self.driver.session() as session:
                    res = session.run("""
                        MATCH (a {name: $f})-[r]->(b {name: $t})
                        RETURN a.id, labels(a), b.id, labels(b)
                    """, f=from_name, t=to_name).single()

                if res:
                    f_type = "DEVICE" if "Device" in res['labels(a)'] else "ASSET"
                    t_type = "DEVICE" if "Device" in res['labels(b)'] else "ASSET"

                    params = {
                        "fromId": res['a.id'], "fromType": f_type,
                        "relationType": rel_type,
                        "toId": res['b.id'], "toType": t_type
                    }
                    headers = {"X-Authorization": f"Bearer {token}"}
                    api_res = requests.delete(f"{TB_URL}/api/relation", params=params, headers=headers)
                    if api_res.status_code == 200:
                        msg += "⚠️ Cloud Link Removed. "
                    else:
                        msg += "⚠️ Cloud Fail. "

        with self.driver.session() as session:
            query = f"MATCH (a {{name: $f}})-[r:{rel_type}]->(b {{name: $t}}) DELETE r"
            session.run(query, f=from_name, t=to_name)
            msg += "🗑️ Graph Link Deleted."

        return msg


st.set_page_config(page_title="IoT Manager", layout="wide")
st.title("IoT#ETL with ThingsBoard")

if 'msg_queue' not in st.session_state:
    st.session_state.msg_queue = []

if st.session_state.msg_queue:
    for msg in st.session_state.msg_queue:
        if "✅" in msg: st.success(msg)
        elif "⚠️" in msg: st.warning(msg)
        elif "❌" in msg: st.error(msg)
        else: st.info(msg)
    st.session_state.msg_queue = []

def notify_and_rerun(message):
    st.session_state.msg_queue.append(message)
    st.rerun()

manager = IoTManager()


@st.dialog("Confirm Deletion")
def confirm_delete_dialog(item_type, item_id_or_name, extra_info=None, policy="safe"):
    st.write(f"Are you sure you want to delete this **{item_type}**?")

    if extra_info:
        st.caption(f"Details: {extra_info}")

    if policy == "strict":
        st.error("⚠️ STRICT MODE ON: This will delete the entity from the Cloud!")
    else:
        st.info("Safe Mode: Deletes from local Graph only.")

    col1, col2 = st.columns(2)
    if col1.button("Yes, Delete", type="primary", use_container_width=True):
        if item_type == "Asset":
            msg = manager.delete_node(item_id_or_name, "Asset", policy)
        elif item_type == "Device":
            msg = manager.delete_node(item_id_or_name, "Device", policy)
        elif item_type == "Relationship":
            f, t, r = extra_info
            msg = manager.delete_relation(f, t, r, policy)

        st.session_state.msg_queue.append(msg)
        st.rerun()

    if col2.button("Cancel", use_container_width=True):
        st.rerun()

# SIDEBAR
st.sidebar.header("Configuration")
st.sidebar.subheader("1. ETL")
if st.sidebar.button("⬇️ Import Cloud Data", help="Import Assets & Devices from ThingsBoard"):
    with st.spinner("Importing..."):
        msg = manager.import_from_cloud()
        notify_and_rerun(msg)
st.sidebar.markdown("---")
st.sidebar.subheader("2. Synchronization")
c1, c2 = st.sidebar.columns(2)
with c1:
    if st.button("⬆️ Assets"):
        msg = manager.sync_assets_to_cloud()
        notify_and_rerun(msg)
with c2:
    if st.button("⬆️ Devices"):
        msg = manager.sync_devices_to_cloud()
        notify_and_rerun(msg)

st.sidebar.markdown("---")
st.sidebar.subheader("3. Settings")
sync_policy = st.sidebar.radio("Deletion Policy", ("Safe Mode (Graph Only)", "Strict Mode (Graph + Cloud)"), index=0)
policy_code = "safe" if "Safe" in sync_policy else "strict"

view = st.radio("Navigation", ["Infrastructure", "Create Entities", "Relationships", "Graph"], horizontal=True, label_visibility="collapsed")

if view == "Infrastructure":
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Assets")
        for a in manager.get_assets():
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.write(f"**{a['Name']}** ({a['Type']})")
            c2.caption(a['Status'] or 'synced')
            if c3.button("❌", key=f"del_a_{a['ID']}"):
                confirm_delete_dialog("Asset", a['ID'], policy=policy_code)

    with col_b:
        st.subheader("Devices")
        for d in manager.get_devices():
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.write(f"**{d['Name']}** ({d['Type']})")
            c2.caption(d['Status'] or 'synced')
            if c3.button("❌", key=f"del_d_{d['ID']}"):
                confirm_delete_dialog("Device", d['ID'], policy=policy_code)

elif view == "Create Entities":
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### New Asset")
        with st.form("asset_form"):
            aname = st.text_input("Name")
            atype = st.selectbox("Type", ["Building", "Room", "Floor", "Area"])
            if st.form_submit_button("Create Asset"):
                if aname:
                    manager.create_draft_asset(aname, atype)
                    notify_and_rerun(f"✅ Created Draft Asset: {aname}")
    with c2:
        st.markdown("### New Device")
        with st.form("device_form"):
            dname = st.text_input("Name")
            dtype = st.selectbox("Type", ["default", "Sensor", "Thermostat", "Switch"])
            dlabel = st.text_input("Label", "Device")
            if st.form_submit_button("Create Device"):
                if dname:
                    manager.create_draft_device(dname, dtype, dlabel)
                    notify_and_rerun(f"✅ Created Draft Device: {dname}")

elif view == "Relationships":
    st.subheader("Link Entities")
    nodes = manager.get_all_nodes()
    if nodes:
        c1, c2, c3, c4 = st.columns([3, 2, 3, 2])
        with c1:
            src = st.selectbox("Source", nodes)
        with c2:
            rel = st.selectbox("Relation", ["Contains", "Manages", "Feeds"])
        with c3:
            tgt = st.selectbox("Target", nodes)
        with c4:
            st.write("")
            st.write("")
            if st.button("Link"):
                if src != tgt:
                    manager.create_relation(src, tgt, rel)
                    notify_and_rerun(f"✅ Linked: {src} -> {tgt}")
                else:
                    st.error("Loop detected.")

    st.markdown("---")
    st.subheader("Existing Relationships")
    relations = manager.get_relations()
    if relations:
        for i, r in enumerate(relations):
            c1, c2, c3, c4, c5 = st.columns([3, 2, 3, 2, 1])
            c1.write(f"**{r['From']}**")
            c2.write(f"→ {r['Relation']} →")
            c3.write(f"**{r['To']}**")

            status = r.get('Status')
            if status == 'synced':
                c4.caption("synced")
            else:
                if c4.button("⬆️ Push", key=f"sync_rel_{i}"):
                    msg = manager.sync_relationship_to_cloud(r['From'], r['To'], r['Relation'])
                    notify_and_rerun(msg)

            if c5.button("❌", key=f"del_rel_{i}"):
                confirm_delete_dialog("Relationship", None, extra_info=(r['From'], r['To'], r['Relation']), policy=policy_code)
    else:
        st.info("No relationships defined.")

elif view == "Graph":
    st.subheader("Interactive Graph Visualization")

    with st.expander("Legend & Info", expanded=True):
        st.markdown("""
        **Nodes:**
        - 🟢 Synced Asset
        - 🔵 Synced Device
        - 🔘 Draft Element

        **Edges:**
        - ⚪ Synced Relationship
        - 🔴 Draft Relationship
        """)

    nodes, edges = manager.get_agraph_elements()
    config = Config(width=1000, height=600, directed=True, physics=True, hierarchical=False, nodeHighlightBehavior=True,
                    highlightColor="#F7A7A6", collapsible=False)
    if nodes:
        agraph(nodes=nodes, edges=edges, config=config)
    else:
        st.info("Graph is empty.")