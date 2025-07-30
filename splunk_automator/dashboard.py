"""
Enhanced Dashboard Management Module
Provides comprehensive dashboard CRUD operations with validation and backup.
"""

import json
import os
import shutil
from datetime import datetime
from typing import List, Dict, Optional, Set
from .config import Config
from .logging_setup import logger

class DashboardManager:
    """Enhanced dashboard management with validation and backup."""
    
    def __init__(self):
        self.dashboards = []
        self.backup_count = 5  # Keep 5 backup copies
    
    def load_dashboards(self) -> List[Dict]:
        """Load dashboards with backup recovery capability."""
        if os.path.exists(Config.DASHBOARD_FILE):
            try:
                with open(Config.DASHBOARD_FILE, 'r', encoding='utf-8') as f:
                    dashboards = json.load(f)
                
                # Validate dashboard structure
                validated_dashboards = []
                for db in dashboards:
                    if self._validate_dashboard(db):
                        # Ensure all required fields exist
                        db = self._normalize_dashboard(db)
                        validated_dashboards.append(db)
                    else:
                        logger.warning(f"Skipping invalid dashboard: {db.get('name', 'Unknown')}")
                
                logger.info(f"Loaded {len(validated_dashboards)} valid dashboards")
                return validated_dashboards
                
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error in dashboard file: {e}")
                return self._attempt_backup_recovery()
            except Exception as e:
                logger.error(f"Failed to load dashboards: {e}")
                return self._attempt_backup_recovery()
        
        logger.info("No dashboard file found, starting with empty list")
        return []
    
    def save_dashboards(self, dashboards: List[Dict]) -> bool:
        """Save dashboards with automatic backup creation."""
        try:
            # Create backup before saving
            self._create_backup()
            
            # Prepare dashboards for saving (remove transient fields)
            dashboards_to_save = []
            for d in dashboards:
                clean_dashboard = {k: v for k, v in d.items() 
                                 if k not in ['status', 'last_run', 'error_message']}
                dashboards_to_save.append(clean_dashboard)
            
            # Write to temporary file first
            temp_file = Config.DASHBOARD_FILE + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(dashboards_to_save, f, indent=4, ensure_ascii=False)
            
            # Atomic move to final location
            shutil.move(temp_file, Config.DASHBOARD_FILE)
            
            # Set secure permissions
            os.chmod(Config.DASHBOARD_FILE, 0o600)
            
            logger.info(f"Successfully saved {len(dashboards_to_save)} dashboards")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save dashboards: {e}")
            # Clean up temp file if it exists
            temp_file = Config.DASHBOARD_FILE + '.tmp'
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
            return False
    
    def _validate_dashboard(self, dashboard: Dict) -> bool:
        """Validate dashboard structure and required fields."""
        required_fields = ['name', 'url']
        
        if not isinstance(dashboard, dict):
            return False
        
        for field in required_fields:
            if field not in dashboard or not dashboard[field]:
                return False
        
        # Validate URL format
        url = dashboard['url']
        if not (url.startswith('http://') or url.startswith('https://')):
            return False
        
        # Validate name is not empty string
        if not dashboard['name'].strip():
            return False
        
        return True
    
    def _normalize_dashboard(self, dashboard: Dict) -> Dict:
        """Ensure dashboard has all required fields with defaults."""
        defaults = {
            'group': 'Default',
            'description': '',
            'selected': True,
            'status': 'Pending',
            'created_date': datetime.now().isoformat(),
            'last_modified': datetime.now().isoformat(),
            'tags': [],
            'priority': 'normal',  # low, normal, high
            'timeout': 60,  # seconds
            'retry_count': 3
        }
        
        # Apply defaults for missing fields
        for key, default_value in defaults.items():
            if key not in dashboard:
                dashboard[key] = default_value
        
        # Update last_modified timestamp
        dashboard['last_modified'] = datetime.now().isoformat()
        
        return dashboard
    
    def _create_backup(self):
        """Create a backup of the current dashboard file."""
        if not os.path.exists(Config.DASHBOARD_FILE):
            return
        
        try:
            backup_dir = os.path.join(Config.DATA_DIR, 'backups')
            os.makedirs(backup_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = os.path.join(backup_dir, f"dashboards_backup_{timestamp}.json")
            
            shutil.copy2(Config.DASHBOARD_FILE, backup_file)
            logger.debug(f"Created backup: {backup_file}")
            
            # Clean up old backups
            self._cleanup_old_backups(backup_dir)
            
        except Exception as e:
            logger.warning(f"Failed to create backup: {e}")
    
    def _cleanup_old_backups(self, backup_dir: str):
        """Remove old backup files, keeping only the most recent ones."""
        try:
            backup_files = [f for f in os.listdir(backup_dir) 
                           if f.startswith('dashboards_backup_') and f.endswith('.json')]
            backup_files.sort(reverse=True)  # Most recent first
            
            # Remove old backups beyond the limit
            for old_backup in backup_files[self.backup_count:]:
                old_backup_path = os.path.join(backup_dir, old_backup)
                os.remove(old_backup_path)
                logger.debug(f"Removed old backup: {old_backup}")
                
        except Exception as e:
            logger.warning(f"Failed to cleanup old backups: {e}")
    
    def _attempt_backup_recovery(self) -> List[Dict]:
        """Attempt to recover from the most recent backup."""
        backup_dir = os.path.join(Config.DATA_DIR, 'backups')
        
        if not os.path.exists(backup_dir):
            logger.warning("No backup directory found for recovery")
            return []
        
        try:
            backup_files = [f for f in os.listdir(backup_dir) 
                           if f.startswith('dashboards_backup_') and f.endswith('.json')]
            
            if not backup_files:
                logger.warning("No backup files found for recovery")
                return []
            
            # Get the most recent backup
            backup_files.sort(reverse=True)
            latest_backup = os.path.join(backup_dir, backup_files[0])
            
            with open(latest_backup, 'r', encoding='utf-8') as f:
                recovered_dashboards = json.load(f)
            
            logger.info(f"Recovered {len(recovered_dashboards)} dashboards from backup: {backup_files[0]}")
            return recovered_dashboards
            
        except Exception as e:
            logger.error(f"Failed to recover from backup: {e}")
            return []

# Global instance
dashboard_manager = DashboardManager()

def load_dashboards() -> List[Dict]:
    """Load dashboards using the enhanced manager."""
    return dashboard_manager.load_dashboards()

def save_dashboards(dashboards: List[Dict]) -> bool:
    """Save dashboards using the enhanced manager."""
    return dashboard_manager.save_dashboards(dashboards)

def get_groups(dashboards: List[Dict]) -> List[str]:
    """Get sorted list of unique groups including 'All'."""
    groups = {"All"}
    for d in dashboards:
        group = d.get("group", "Default")
        if group:  # Skip empty groups
            groups.add(group)
    return sorted(list(groups))

def get_tags(dashboards: List[Dict]) -> List[str]:
    """Get sorted list of unique tags from all dashboards."""
    tags = set()
    for d in dashboards:
        dashboard_tags = d.get("tags", [])
        if isinstance(dashboard_tags, list):
            tags.update(dashboard_tags)
    return sorted(list(tags))

def select_all(dashboards: List[Dict]) -> int:
    """Select all dashboards and return count of selected."""
    count = 0
    for db in dashboards:
        db['selected'] = True
        count += 1
    return count

def deselect_all(dashboards: List[Dict]) -> int:
    """Deselect all dashboards and return count of deselected."""
    count = 0
    for db in dashboards:
        if db.get('selected', False):
            count += 1
        db['selected'] = False
    return count

def select_by_group(dashboards: List[Dict], group: str) -> int:
    """Select all dashboards in a specific group."""
    count = 0
    for db in dashboards:
        if db.get("group", "Default") == group:
            db['selected'] = True
            count += 1
    return count

def select_by_tag(dashboards: List[Dict], tag: str) -> int:
    """Select all dashboards with a specific tag."""
    count = 0
    for db in dashboards:
        dashboard_tags = db.get("tags", [])
        if isinstance(dashboard_tags, list) and tag in dashboard_tags:
            db['selected'] = True
            count += 1
    return count

def filter_dashboards(dashboards: List[Dict], group_filter: str = "All", 
                     tag_filter: str = None, search_text: str = None) -> List[Dict]:
    """Filter dashboards by group, tag, and search text."""
    filtered = []
    
    for db in dashboards:
        # Group filter
        if group_filter != "All":
            if db.get("group", "Default") != group_filter:
                continue
        
        # Tag filter
        if tag_filter:
            dashboard_tags = db.get("tags", [])
            if not isinstance(dashboard_tags, list) or tag_filter not in dashboard_tags:
                continue
        
        # Search text filter
        if search_text:
            search_text = search_text.lower()
            searchable_text = f"{db.get('name', '')} {db.get('description', '')} {db.get('url', '')}"
            if search_text not in searchable_text.lower():
                continue
        
        filtered.append(db)
    
    return filtered

def refresh_dashboard_list(treeview, dashboards: List[Dict], group_filter_var, 
                          tag_filter_var=None, search_var=None):
    """Enhanced dashboard list refresh with multiple filters."""
    # Store currently selected items
    selected_ids = {iid for iid in treeview.selection()}
    
    # Clear existing items
    treeview.delete(*treeview.get_children())
    
    # Apply filters
    group_filter = group_filter_var.get()
    tag_filter = tag_filter_var.get() if tag_filter_var else None
    search_text = search_var.get() if search_var else None
    
    filtered_dashboards = filter_dashboards(dashboards, group_filter, tag_filter, search_text)
    
    # Populate treeview
    for idx, db in enumerate(filtered_dashboards):
        # Find original index in full dashboard list
        original_idx = dashboards.index(db)
        
        group_name = db.get("group", "Default")
        status = db.get("status", "Pending")
        selected_char = "☑" if db.get("selected") else "☐"
        priority_icon = {"high": "🔴", "normal": "🟡", "low": "🟢"}.get(
            db.get("priority", "normal"), "🟡")
        
        # Format tags for display
        tags = db.get("tags", [])
        tags_display = ", ".join(tags[:3])  # Show first 3 tags
        if len(tags) > 3:
            tags_display += f" (+{len(tags) - 3})"
        
        iid = str(original_idx)
        treeview.insert("", "end", iid=iid, values=(
            selected_char,
            db['name'],
            db.get('url', '')[:50] + ('...' if len(db.get('url', '')) > 50 else ''),
            group_name,
            status,
            priority_icon,
            tags_display
        ))
        
        # Restore selection if it was previously selected
        if iid in selected_ids:
            treeview.selection_add(iid)

def add_dashboard(dashboards: List[Dict], dashboard_data: Dict) -> bool:
    """Add a new dashboard with validation."""
    try:
        # Validate dashboard data
        if not dashboard_manager._validate_dashboard(dashboard_data):
            logger.error("Invalid dashboard data provided")
            return False
        
        # Check for duplicate names
        existing_names = {db['name'].lower() for db in dashboards}
        if dashboard_data['name'].lower() in existing_names:
            logger.error(f"Dashboard with name '{dashboard_data['name']}' already exists")
            return False
        
        # Normalize and add the dashboard
        normalized_dashboard = dashboard_manager._normalize_dashboard(dashboard_data.copy())
        dashboards.append(normalized_dashboard)
        
        logger.info(f"Added new dashboard: {dashboard_data['name']}")
        return True
        
    except Exception as e:
        logger.error(f"Error adding dashboard: {e}")
        return False

def update_dashboard(dashboards: List[Dict], index: int, updates: Dict) -> bool:
    """Update an existing dashboard."""
    try:
        if index < 0 or index >= len(dashboards):
            logger.error(f"Invalid dashboard index: {index}")
            return False
        
        # Update fields
        for key, value in updates.items():
            if key not in ['created_date']:  # Preserve creation date
                dashboards[index][key] = value
        
        # Update last_modified timestamp
        dashboards[index]['last_modified'] = datetime.now().isoformat()
        
        logger.info(f"Updated dashboard at index {index}")
        return True
        
    except Exception as e:
        logger.error(f"Error updating dashboard: {e}")
        return False

def delete_dashboards(dashboards: List[Dict], indices: List[int]) -> int:
    """Delete multiple dashboards by indices. Returns count of deleted dashboards."""
    try:
        # Sort indices in reverse order to maintain correct positions during deletion
        sorted_indices = sorted(indices, reverse=True)
        deleted_count = 0
        
        for index in sorted_indices:
            if 0 <= index < len(dashboards):
                deleted_dashboard = dashboards.pop(index)
                logger.info(f"Deleted dashboard: {deleted_dashboard.get('name', 'Unknown')}")
                deleted_count += 1
            else:
                logger.warning(f"Invalid index for deletion: {index}")
        
        return deleted_count
        
    except Exception as e:
        logger.error(f"Error deleting dashboards: {e}")
        return 0

def get_dashboard_statistics(dashboards: List[Dict]) -> Dict:
    """Get statistics about the dashboard collection."""
    stats = {
        'total': len(dashboards),
        'selected': sum(1 for db in dashboards if db.get('selected', False)),
        'by_group': {},
        'by_status': {},
        'by_priority': {'high': 0, 'normal': 0, 'low': 0}
    }
    
    for db in dashboards:
        # Group statistics
        group = db.get('group', 'Default')
        stats['by_group'][group] = stats['by_group'].get(group, 0) + 1
        
        # Status statistics
        status = db.get('status', 'Pending')
        stats['by_status'][status] = stats['by_status'].get(status, 0) + 1
        
        # Priority statistics
        priority = db.get('priority', 'normal')
        if priority in stats['by_priority']:
            stats['by_priority'][priority] += 1
    
    return stats

def export_dashboards_to_csv(dashboards: List[Dict], file_path: str) -> bool:
    """Export dashboards to CSV format."""
    try:
        import csv
        
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Write header
            writer.writerow([
                'Name', 'URL', 'Group', 'Description', 'Priority', 'Tags',
                'Status', 'Selected', 'Created Date', 'Last Modified'
            ])
            
            # Write dashboard data
            for db in dashboards:
                tags_str = ', '.join(db.get('tags', []))
                writer.writerow([
                    db.get('name', ''),
                    db.get('url', ''),
                    db.get('group', 'Default'),
                    db.get('description', ''),
                    db.get('priority', 'normal'),
                    tags_str,
                    db.get('status', 'Pending'),
                    'Yes' if db.get('selected', False) else 'No',
                    db.get('created_date', ''),
                    db.get('last_modified', '')
                ])
        
        logger.info(f"Exported {len(dashboards)} dashboards to CSV: {file_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error exporting dashboards to CSV: {e}")
        return False
