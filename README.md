<p align="center">
  <a href="https://www.unicam.it/">
    <img alt="Unicam Logo" src="./util/logo-unicam.svg">
  </a>
</p>

# IoT Digital Twin Manager

## Project Overview
This project implements a bidirectional synchronization system between an IoT Platform (**ThingsBoard**) and a Graph Database (**Neo4j**). It allows for advanced topology management of IoT assets using a custom Python dashboard.

## Features
* **Smart ETL:** Extracts Assets and Devices from ThingsBoard and maps them into a Graph structure.
* **Graph Management UI:** A **Streamlit** dashboard to visualize the infrastructure, add/remove assets, and link them (e.g., `Room` -> `CONTAINS` -> `Sensor`).
* **Reverse Sync:** "Draft" assets created in the UI can be pushed to ThingsBoard with a single click.
* **Configurable Safety:** Implemented as a choose-able deletion policy.
    * **Safe Mode:** Deletes nodes locally (simulation).
    * **Strict Mode:** Deletes the actual asset in the Cloud.

## Architecture
* **Source:** ThingsBoard Community Edition
* **Persistence:** Neo4j Graph Database
* **Middleware:** Python 3.x (Streamlit, Requests, Neo4j Driver)

## Setup & Installation

### 1. Prerequisites
* Docker Desktop installed.
* Python 3.10+ installed.

### 2. Launch Infrastructure
Start the containers for ThingsBoard and Neo4j:
```bash
docker-compose up -d
```

### 3. Configuration

Create a `.env` file in the root directory to store your credentials. You can use the provided `.env.example` as a template.

### 4. Install Dependencies

Create and activate virtual environment (Linux/Mac)
```bash
python3 -m venv venv
source venv/bin/activate
```

Create and activate virtual environment (Windows)
```bash
python -m venv venv
.\venv\Scripts\activate
```

Install requirements
```bash
pip install -r requirements.txt
```

### 5. Run the Application
Launch the Streamlit dashboard with:
```bash
streamlit run app.py
```
or (if streamlit is not installed in PATH)
```bash
python -m streamlit run app.py
```

## Usage Guide

### 1. Sidebar Configuration
* **Import Cloud Data:** Click this button to pull your existing infrastructure from ThingsBoard. It fetches **Assets**, **Devices**, and **Relationships** to populate the local Neo4j graph.
* **Batch Sync:** Use the buttons to batch-upload all locally created draft entities to the cloud.
* **Deletion Policy:**
    * **Safe Mode:** Deletes nodes/relationships only from the local graph.
    * **Strict Mode:** Deletes the actual entity from ThingsBoard Cloud.

### 2. Main Interface
The application is organized into four main views:

#### Infrastructure
* **Monitor:** View separate lists for Assets and Devices.
* **Manage:** Click `❌` to remove an entity. A **confirmation popup** will appear to prevent accidental deletions.

#### Create Entities
* **Drafting:** Create new **Assets** or **Devices**.
* **Status:** Newly created items are marked as `draft` until they are synced.

#### Relationships
* **Link Nodes:** Select any two nodes to create a connection.
* **Push to Cloud:** Draft relationships appear with a **"Push"** button. Click it to sync that specific link to ThingsBoard.
* **Validation:** The system prevents syncing links if the connected nodes are still drafts.

#### Graph
* **Interactive Topology:** A physics-enabled visualization of your entire IoT network.