import json
import os
from .config import Config
from .logging_setup import logger

def load_dashboards():
    if os.path.exists(Config.DASHBOARD_FILE):
        try:
            with open(Config.DASHBOARD_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load dashboards: {e}")
    return []

def save_dashboards(dashboards):
    try:
        with open(Config.DASHBOARD_FILE, 'w', encoding='utf-8') as f:
            dashboards_to_save = [{k: v for k, v in d.items() if k != 'status'} for d in dashboards]
            json.dump(dashboards_to_save, f, indent=4)
        os.chmod(Config.DASHBOARD_FILE, 0o600)
    except Exception as exc:
        logger.exception("Error saving dashboards")
        raise

def get_groups(dashboards):
    groups = {"All"}
    for d in dashboards:
        groups.add(d.get("group", "Default"))
    return sorted(list(groups))

def select_all(dashboards):
    for db in dashboards:
        db['selected'] = True

def deselect_all(dashboards):
    for db in dashboards:
        db['selected'] = False

def refresh_dashboard_list(treeview, dashboards, group_filter_var):
    selected_ids = {iid for iid in treeview.selection()}
    treeview.delete(*treeview.get_children())
    selected_filter = group_filter_var.get()
    for idx, db in enumerate(dashboards):
        group_name = db.get("group", "Default")
        if selected_filter == "All" or group_name == selected_filter:
            status = db.get("status", "Pending")
            selected_char = "☑" if db.get("selected") else "☐"
            iid = str(idx)
            treeview.insert("", "end", iid=iid, values=(selected_char, db['name'], db['url'], group_name, status))
            if iid in selected_ids:
                treeview.selection_add(iid)