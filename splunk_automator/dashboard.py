import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Set, Tuple, Any
from .config import Config
from .logging_setup import logger, timing_context
from .utils import create_backup, validate_json_file, safe_file_operation

class DashboardManager:
    """Enhanced dashboard management with validation, backup, and advanced features."""
    
    def __init__(self):
        self.dashboard_file = Config.DASHBOARD_FILE
        self.cache = None
        self.cache_timestamp = None
        self.cache_ttl = 300  # 5 minutes cache TTL
    
    def load_dashboards(self, use_cache: bool = True) -> List[Dict]:
        """Load dashboards with caching and validation."""
        with timing_context("load_dashboards"):
            try:
                # Check cache validity
                if use_cache and self._is_cache_valid():
                    return self.cache.copy()
                
                if not os.path.exists(self.dashboard_file):
                    logger.info("Dashboard file does not exist, returning empty list")
                    self.cache = []
                    self.cache_timestamp = datetime.now()
                    return []
                
                # Validate JSON file
                is_valid, error_msg = validate_json_file(self.dashboard_file)
                if not is_valid:
                    logger.error(f"Invalid dashboard file: {error_msg}")
                    return self._handle_corrupted_file()
                
                # Load dashboards
                with open(self.dashboard_file, 'r', encoding='utf-8') as f:
                    dashboards = json.load(f)
                
                if not isinstance(dashboards, list):
                    logger.error("Dashboard file does not contain a list")
                    return []
                
                # Validate and clean dashboards
                cleaned_dashboards = []
                for i, dashboard in enumerate(dashboards):
                    try:
                        validated_dashboard = self._validate_dashboard(dashboard, i)
                        if validated_dashboard:
                            cleaned_dashboards.append(validated_dashboard)
                    except Exception as e:
                        logger.warning(f"Skipping invalid dashboard at index {i}: {e}")
                        continue
                
                # Update cache
                self.cache = cleaned_dashboards
                self.cache_timestamp = datetime.now()
                
                logger.info(f"Loaded {len(cleaned_dashboards)} dashboards")
                return cleaned_dashboards.copy()
                
            except Exception as e:
                logger.error(f"Failed to load dashboards: {e}")
                return []
    
    def save_dashboards(self, dashboards: List[Dict], create_backup: bool = True) -> bool:
        """Save dashboards with backup and validation."""
        with timing_context("save_dashboards"):
            try:
                # Validate input
                if not isinstance(dashboards, list):
                    raise ValueError("Dashboards must be a list")
                
                # Validate each dashboard
                validated_dashboards = []
                for i, dashboard in enumerate(dashboards):
                    validated = self._validate_dashboard(dashboard, i, strict=True)
                    if validated:
                        validated_dashboards.append(validated)
                
                # Create backup if requested
                backup_path = None
                if create_backup and os.path.exists(self.dashboard_file):
                    backup_path = create_backup(self.dashboard_file)
                
                # Prepare data for saving (remove transient fields)
                save_data = []
                for dashboard in validated_dashboards:
                    save_dashboard = {k: v for k, v in dashboard.items() 
                                    if k not in ['status', 'selected', 'last_run', 'error_count']}
                    save_data.append(save_dashboard)
                
                # Save with error handling
                def save_operation():
                    with open(self.dashboard_file, 'w', encoding='utf-8') as f:
                        json.dump(save_data, f, indent=4, ensure_ascii=False)
                    os.chmod(self.dashboard_file, Config.SECURE_FILE_PERMISSIONS)
                
                safe_file_operation(save_operation)
                
                # Update cache
                self.cache = validated_dashboards
                self.cache_timestamp = datetime.now()
                
                logger.info(f"Saved {len(validated_dashboards)} dashboards")
                return True
                
            except Exception as e:
                logger.error(f"Failed to save dashboards: {e}")
                # Restore from backup if save failed
                if backup_path and os.path.exists(backup_path):
                    try:
                        from .utils import restore_from_backup
                        restore_from_backup(self.dashboard_file, backup_path)
                        logger.info("Restored dashboard file from backup")
                    except Exception as restore_error:
                        logger.error(f"Failed to restore from backup: {restore_error}")
                return False
    
    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if not self.cache or not self.cache_timestamp:
            return False
        
        cache_age = (datetime.now() - self.cache_timestamp).total_seconds()
        return cache_age < self.cache_ttl
    
    def _validate_dashboard(self, dashboard: Dict, index: int, strict: bool = False) -> Optional[Dict]:
        """Validate and clean a dashboard entry."""
        try:
            if not isinstance(dashboard, dict):
                raise ValueError("Dashboard must be a dictionary")
            
            # Required fields
            required_fields = ['name', 'url']
            for field in required_fields:
                if field not in dashboard:
                    raise ValueError(f"Missing required field: {field}")
                if not dashboard[field] or not str(dashboard[field]).strip():
                    raise ValueError(f"Field {field} cannot be empty")
            
            # Clean and validate fields
            cleaned = {
                'name': str(dashboard['name']).strip(),
                'url': str(dashboard['url']).strip(),
                'group': str(dashboard.get('group', 'Default')).strip(),
                'description': str(dashboard.get('description', '')).strip(),
                'created_at': dashboard.get('created_at', datetime.now().isoformat()),
                'updated_at': datetime.now().isoformat(),
                'enabled': bool(dashboard.get('enabled', True)),
                'tags': self._validate_tags(dashboard.get('tags', [])),
                'metadata': dashboard.get('metadata', {})
            }
            
            # Add runtime fields
            cleaned.update({
                'selected': bool(dashboard.get('selected', True)),
                'status': dashboard.get('status', 'Pending'),
                'last_run': dashboard.get('last_run'),
                'error_count': int(dashboard.get('error_count', 0))
            })
            
            # URL validation
            if not self._is_valid_url(cleaned['url']):
                if strict:
                    raise ValueError(f"Invalid URL format: {cleaned['url']}")
                else:
                    logger.warning(f"Dashboard {index} has potentially invalid URL: {cleaned['url']}")
            
            # Name validation
            if len(cleaned['name']) > 255:
                cleaned['name'] = cleaned['name'][:255]
                logger.warning(f"Dashboard {index} name truncated to 255 characters")
            
            return cleaned
            
        except Exception as e:
            if strict:
                raise
            logger.warning(f"Dashboard validation failed for index {index}: {e}")
            return None
    
    def _validate_tags(self, tags: Any) -> List[str]:
        """Validate and clean tags list."""
        if not tags:
            return []
        
        if isinstance(tags, str):
            tags = [tag.strip() for tag in tags.split(',')]
        
        if not isinstance(tags, list):
            return []
        
        cleaned_tags = []
        for tag in tags:
            if isinstance(tag, str) and tag.strip():
                clean_tag = tag.strip().lower()
                if clean_tag not in cleaned_tags and len(clean_tag) <= 50:
                    cleaned_tags.append(clean_tag)
        
        return cleaned_tags[:10]  # Limit to 10 tags
    
    def _is_valid_url(self, url: str) -> bool:
        """Basic URL validation."""
        try:
            from urllib.parse import urlparse
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False
    
    def _handle_corrupted_file(self) -> List[Dict]:
        """Handle corrupted dashboard file."""
        try:
            # Try to create backup of corrupted file
            corrupted_backup = f"{self.dashboard_file}.corrupted.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            if os.path.exists(self.dashboard_file):
                import shutil
                shutil.copy2(self.dashboard_file, corrupted_backup)
                logger.info(f"Corrupted file backed up to: {corrupted_backup}")
            
            # Return empty list
            return []
            
        except Exception as e:
            logger.error(f"Error handling corrupted file: {e}")
            return []
    
    def get_groups(self, dashboards: List[Dict] = None) -> List[str]:
        """Get all unique groups from dashboards."""
        if dashboards is None:
            dashboards = self.load_dashboards()
        
        groups = {"All"}
        for dashboard in dashboards:
            group = dashboard.get("group", "Default")
            if group and group.strip():
                groups.add(group.strip())
        
        return sorted(list(groups))
    
    def get_tags(self, dashboards: List[Dict] = None) -> List[str]:
        """Get all unique tags from dashboards."""
        if dashboards is None:
            dashboards = self.load_dashboards()
        
        all_tags = set()
        for dashboard in dashboards:
            tags = dashboard.get("tags", [])
            if isinstance(tags, list):
                all_tags.update(tags)
        
        return sorted(list(all_tags))
    
    def filter_dashboards(self, dashboards: List[Dict], filters: Dict[str, Any]) -> List[Dict]:
        """Filter dashboards based on criteria."""
        filtered = dashboards.copy()
        
        # Group filter
        group_filter = filters.get('group')
        if group_filter and group_filter != "All":
            filtered = [d for d in filtered if d.get('group', 'Default') == group_filter]
        
        # Tag filter
        tag_filter = filters.get('tags')
        if tag_filter:
            if isinstance(tag_filter, str):
                tag_filter = [tag_filter]
            filtered = [d for d in filtered 
                       if any(tag in d.get('tags', []) for tag in tag_filter)]
        
        # Status filter
        status_filter = filters.get('status')
        if status_filter:
            filtered = [d for d in filtered if d.get('status') == status_filter]
        
        # Enabled filter
        enabled_filter = filters.get('enabled')
        if enabled_filter is not None:
            filtered = [d for d in filtered if d.get('enabled', True) == enabled_filter]
        
        # Search filter
        search_term = filters.get('search')
        if search_term:
            search_lower = search_term.lower()
            filtered = [d for d in filtered 
                       if search_lower in d.get('name', '').lower() or 
                          search_lower in d.get('description', '').lower() or
                          search_lower in d.get('url', '').lower()]
        
        return filtered
    
    def select_all(self, dashboards: List[Dict]) -> None:
        """Mark all dashboards as selected."""
        for dashboard in dashboards:
            dashboard['selected'] = True
    
    def deselect_all(self, dashboards: List[Dict]) -> None:
        """Deselect all dashboards."""
        for dashboard in dashboards:
            dashboard['selected'] = False
    
    def select_by_group(self, dashboards: List[Dict], group: str) -> None:
        """Select all dashboards in a specific group."""
        for dashboard in dashboards:
            if dashboard.get('group', 'Default') == group:
                dashboard['selected'] = True
    
    def select_by_tags(self, dashboards: List[Dict], tags: List[str]) -> None:
        """Select dashboards with specific tags."""
        for dashboard in dashboards:
            dashboard_tags = dashboard.get('tags', [])
            if any(tag in dashboard_tags for tag in tags):
                dashboard['selected'] = True
    
    def add_dashboard(self, name: str, url: str, group: str = "Default", 
                     description: str = "", tags: List[str] = None, 
                     metadata: Dict[str, Any] = None) -> bool:
        """Add a new dashboard."""
        try:
            dashboards = self.load_dashboards()
            
            # Check for duplicates
            existing_names = {d['name'].lower() for d in dashboards}
            if name.lower() in existing_names:
                raise ValueError(f"Dashboard with name '{name}' already exists")
            
            new_dashboard = {
                'name': name,
                'url': url,
                'group': group,
                'description': description,
                'tags': tags or [],
                'metadata': metadata or {},
                'created_at': datetime.now().isoformat(),
                'enabled': True,
                'selected': True,
                'status': 'Pending'
            }
            
            # Validate new dashboard
            validated = self._validate_dashboard(new_dashboard, len(dashboards), strict=True)
            if not validated:
                raise ValueError("Dashboard validation failed")
            
            dashboards.append(validated)
            return self.save_dashboards(dashboards)
            
        except Exception as e:
            logger.error(f"Failed to add dashboard: {e}")
            return False
    
    def update_dashboard(self, dashboard_name: str, updates: Dict[str, Any]) -> bool:
        """Update an existing dashboard."""
        try:
            dashboards = self.load_dashboards()
            
            # Find dashboard to update
            dashboard_index = None
            for i, dashboard in enumerate(dashboards):
                if dashboard['name'] == dashboard_name:
                    dashboard_index = i
                    break
            
            if dashboard_index is None:
                raise ValueError(f"Dashboard '{dashboard_name}' not found")
            
            # Apply updates
            dashboard = dashboards[dashboard_index]
            dashboard.update(updates)
            dashboard['updated_at'] = datetime.now().isoformat()
            
            # Validate updated dashboard
            validated = self._validate_dashboard(dashboard, dashboard_index, strict=True)
            if not validated:
                raise ValueError("Updated dashboard validation failed")
            
            dashboards[dashboard_index] = validated
            return self.save_dashboards(dashboards)
            
        except Exception as e:
            logger.error(f"Failed to update dashboard: {e}")
            return False
    
    def delete_dashboards(self, dashboard_names: List[str]) -> bool:
        """Delete multiple dashboards."""
        try:
            dashboards = self.load_dashboards()
            names_to_delete = set(dashboard_names)
            
            # Filter out dashboards to delete
            remaining_dashboards = [
                d for d in dashboards if d['name'] not in names_to_delete
            ]
            
            deleted_count = len(dashboards) - len(remaining_dashboards)
            logger.info(f"Deleting {deleted_count} dashboards")
            
            return self.save_dashboards(remaining_dashboards)
            
        except Exception as e:
            logger.error(f"Failed to delete dashboards: {e}")
            return False
    
    def export_dashboards(self, file_path: str, dashboards: List[Dict] = None, 
                         include_runtime_data: bool = False) -> bool:
        """Export dashboards to a file."""
        try:
            if dashboards is None:
                dashboards = self.load_dashboards()
            
            # Prepare export data
            export_data = []
            excluded_fields = [] if include_runtime_data else ['status', 'selected', 'last_run', 'error_count']
            
            for dashboard in dashboards:
                export_dashboard = {k: v for k, v in dashboard.items() 
                                  if k not in excluded_fields}
                export_data.append(export_dashboard)
            
            # Add export metadata
            export_wrapper = {
                'version': '2.0',
                'exported_at': datetime.now().isoformat(),
                'exported_by': 'Splunk Dashboard Automator',
                'dashboard_count': len(export_data),
                'dashboards': export_data
            }
            
            # Save export file
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_wrapper, f, indent=4, ensure_ascii=False)
            
            logger.info(f"Exported {len(export_data)} dashboards to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export dashboards: {e}")
            return False
    
    def import_dashboards(self, file_path: str, merge_mode: str = 'skip_duplicates') -> Tuple[bool, int, List[str]]:
        """
        Import dashboards from a file.
        
        Args:
            file_path: Path to import file
            merge_mode: 'skip_duplicates', 'update_duplicates', or 'rename_duplicates'
        
        Returns:
            Tuple of (success, imported_count, error_messages)
        """
        try:
            # Validate import file
            is_valid, error_msg = validate_json_file(file_path)
            if not is_valid:
                return False, 0, [f"Invalid import file: {error_msg}"]
            
            # Load import data
            with open(file_path, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
            
            # Handle different import formats
            if isinstance(import_data, dict) and 'dashboards' in import_data:
                # New format with metadata
                dashboards_to_import = import_data['dashboards']
            elif isinstance(import_data, list):
                # Legacy format - direct list
                dashboards_to_import = import_data
            else:
                return False, 0, ["Invalid import file format"]
            
            # Load existing dashboards
            existing_dashboards = self.load_dashboards()
            existing_names = {d['name'].lower(): d for d in existing_dashboards}
            
            imported_count = 0
            error_messages = []
            
            for i, dashboard_data in enumerate(dashboards_to_import):
                try:
                    # Validate imported dashboard
                    validated = self._validate_dashboard(dashboard_data, i)
                    if not validated:
                        error_messages.append(f"Dashboard {i}: Validation failed")
                        continue
                    
                    dashboard_name_lower = validated['name'].lower()
                    
                    # Handle duplicates based on merge mode
                    if dashboard_name_lower in existing_names:
                        if merge_mode == 'skip_duplicates':
                            continue
                        elif merge_mode == 'update_duplicates':
                            # Update existing dashboard
                            for j, existing in enumerate(existing_dashboards):
                                if existing['name'].lower() == dashboard_name_lower:
                                    existing_dashboards[j] = validated
                                    break
                        elif merge_mode == 'rename_duplicates':
                            # Rename to avoid conflict
                            base_name = validated['name']
                            counter = 1
                            while f"{base_name}_{counter}".lower() in existing_names:
                                counter += 1
                            validated['name'] = f"{base_name}_{counter}"
                            existing_dashboards.append(validated)
                            existing_names[validated['name'].lower()] = validated
                    else:
                        # Add new dashboard
                        existing_dashboards.append(validated)
                        existing_names[dashboard_name_lower] = validated
                    
                    imported_count += 1
                    
                except Exception as e:
                    error_messages.append(f"Dashboard {i}: {str(e)}")
                    continue
            
            # Save updated dashboards
            if imported_count > 0:
                success = self.save_dashboards(existing_dashboards)
                if not success:
                    return False, 0, ["Failed to save imported dashboards"]
            
            return True, imported_count, error_messages
            
        except Exception as e:
            logger.error(f"Failed to import dashboards: {e}")
            return False, 0, [str(e)]
    
    def get_dashboard_statistics(self, dashboards: List[Dict] = None) -> Dict[str, Any]:
        """Get statistics about dashboards."""
        if dashboards is None:
            dashboards = self.load_dashboards()
        
        stats = {
            'total_count': len(dashboards),
            'enabled_count': sum(1 for d in dashboards if d.get('enabled', True)),
            'disabled_count': sum(1 for d in dashboards if not d.get('enabled', True)),
            'selected_count': sum(1 for d in dashboards if d.get('selected', False)),
            'groups': {},
            'status_counts': {},
            'tags': {},
            'recent_additions': 0,
            'recent_updates': 0
        }
        
        # Count by groups
        for dashboard in dashboards:
            group = dashboard.get('group', 'Default')
            stats['groups'][group] = stats['groups'].get(group, 0) + 1
        
        # Count by status
        for dashboard in dashboards:
            status = dashboard.get('status', 'Pending')
            stats['status_counts'][status] = stats['status_counts'].get(status, 0) + 1
        
        # Count by tags
        for dashboard in dashboards:
            tags = dashboard.get('tags', [])
            for tag in tags:
                stats['tags'][tag] = stats['tags'].get(tag, 0) + 1
        
        # Count recent additions/updates (last 7 days)
        from datetime import timedelta
        cutoff_date = datetime.now() - timedelta(days=7)
        
        for dashboard in dashboards:
            created_str = dashboard.get('created_at')
            updated_str = dashboard.get('updated_at')
            
            try:
                if created_str:
                    created_date = datetime.fromisoformat(created_str.replace('Z', '+00:00'))
                    if created_date > cutoff_date:
                        stats['recent_additions'] += 1
                
                if updated_str:
                    updated_date = datetime.fromisoformat(updated_str.replace('Z', '+00:00'))
                    if updated_date > cutoff_date:
                        stats['recent_updates'] += 1
            except ValueError:
                continue
        
        return stats
    
    def validate_dashboard_urls(self, dashboards: List[Dict] = None) -> Dict[str, List[str]]:
        """Validate URLs in dashboards and return results."""
        if dashboards is None:
            dashboards = self.load_dashboards()
        
        results = {
            'valid': [],
            'invalid': [],
            'suspicious': []
        }
        
        for dashboard in dashboards:
            url = dashboard.get('url', '')
            name = dashboard.get('name', 'Unknown')
            
            if not url:
                results['invalid'].append(f"{name}: Empty URL")
                continue
            
            # Basic URL validation
            if not self._is_valid_url(url):
                results['invalid'].append(f"{name}: Invalid URL format")
                continue
            
            # Check for suspicious patterns
            suspicious_patterns = [
                'localhost',
                '127.0.0.1',
                '192.168.',
                '10.',
                '172.16.',
                'test',
                'dev',
                'staging'
            ]
            
            url_lower = url.lower()
            if any(pattern in url_lower for pattern in suspicious_patterns):
                results['suspicious'].append(f"{name}: Potentially non-production URL")
            else:
                results['valid'].append(f"{name}: URL appears valid")
        
        return results
    
    def cleanup_dashboards(self, dashboards: List[Dict] = None) -> Tuple[List[Dict], int]:
        """Clean up dashboards by removing duplicates and fixing issues."""
        if dashboards is None:
            dashboards = self.load_dashboards()
        
        cleaned_dashboards = []
        seen_names = set()
        cleaned_count = 0
        
        for dashboard in dashboards:
            original_dashboard = dashboard.copy()
            
            # Fix name duplicates
            name = dashboard.get('name', '').strip()
            original_name = name
            counter = 1
            
            while name.lower() in seen_names:
                name = f"{original_name}_{counter}"
                counter += 1
            
            dashboard['name'] = name
            seen_names.add(name.lower())
            
            # Clean up fields
            dashboard['group'] = dashboard.get('group', 'Default').strip() or 'Default'
            dashboard['description'] = dashboard.get('description', '').strip()
            
            # Ensure required fields
            if 'created_at' not in dashboard:
                dashboard['created_at'] = datetime.now().isoformat()
            
            dashboard['updated_at'] = datetime.now().isoformat()
            
            # Fix tags
            dashboard['tags'] = self._validate_tags(dashboard.get('tags', []))
            
            # Track if dashboard was modified
            if dashboard != original_dashboard:
                cleaned_count += 1
            
            cleaned_dashboards.append(dashboard)
        
        return cleaned_dashboards, cleaned_count

# UI helper functions for treeview management
def refresh_dashboard_list(treeview, dashboards: List[Dict], group_filter_var, 
                          search_filter: str = None, status_filter: str = None):
    """Enhanced refresh function with multiple filters."""
    try:
        # Store current selection
        selected_ids = {iid for iid in treeview.selection()}
        
        # Clear existing items
        treeview.delete(*treeview.get_children())
        
        # Apply filters
        filtered_dashboards = dashboards.copy()
        
        # Group filter
        selected_group = group_filter_var.get()
        if selected_group != "All":
            filtered_dashboards = [
                d for d in filtered_dashboards 
                if d.get("group", "Default") == selected_group
            ]
        
        # Search filter
        if search_filter:
            search_lower = search_filter.lower()
            filtered_dashboards = [
                d for d in filtered_dashboards
                if search_lower in d.get('name', '').lower() or
                   search_lower in d.get('description', '').lower() or
                   search_lower in d.get('url', '').lower()
            ]
        
        # Status filter
        if status_filter and status_filter != "All":
            filtered_dashboards = [
                d for d in filtered_dashboards
                if d.get('status', 'Pending') == status_filter
            ]
        
        # Populate treeview
        for idx, dashboard in enumerate(filtered_dashboards):
            try:
                # Find original index in full dashboard list
                original_idx = None
                for i, orig_dash in enumerate(dashboards):
                    if orig_dash.get('name') == dashboard.get('name'):
                        original_idx = i
                        break
                
                if original_idx is None:
                    continue
                
                group_name = dashboard.get("group", "Default")
                status = dashboard.get("status", "Pending")
                selected_char = "☑" if dashboard.get("selected") else "☐"
                enabled_char = "✓" if dashboard.get("enabled", True) else "✗"
                
                # Add tags if present
                tags = dashboard.get("tags", [])
                tags_str = ", ".join(tags[:3])  # Show first 3 tags
                if len(tags) > 3:
                    tags_str += "..."
                
                iid = str(original_idx)
                values = (
                    selected_char,
                    dashboard['name'],
                    dashboard['url'],
                    group_name,
                    status,
                    enabled_char,
                    tags_str
                )
                
                # Insert item
                item = treeview.insert("", "end", iid=iid, values=values)
                
                # Apply styling based on status
                if status == "Failed":
                    treeview.set(item, 4, f"❌ {status}")
                elif status == "Complete":
                    treeview.set(item, 4, f"✅ {status}")
                elif status == "Processing":
                    treeview.set(item, 4, f"⏳ {status}")
                
                # Restore selection
                if iid in selected_ids:
                    treeview.selection_add(iid)
                    
            except Exception as e:
                logger.warning(f"Error adding dashboard to treeview: {e}")
                continue
                
    except Exception as e:
        logger.error(f"Error refreshing dashboard list: {e}")

def setup_enhanced_treeview(treeview):
    """Set up enhanced treeview with better columns and styling."""
    # Configure columns
    columns = {
        "Selected": {"width": 40, "minwidth": 40, "anchor": "center"},
        "Name": {"width": 200, "minwidth": 150, "anchor": "w"},
        "URL": {"width": 300, "minwidth": 200, "anchor": "w"},
        "Group": {"width": 100, "minwidth": 80, "anchor": "center"},
        "Status": {"width": 100, "minwidth": 80, "anchor": "center"},
        "Enabled": {"width": 60, "minwidth": 50, "anchor": "center"},
        "Tags": {"width": 150, "minwidth": 100, "anchor": "w"}
    }
    
    # Set up columns
    treeview["columns"] = list(columns.keys())
    treeview["show"] = "headings"
    
    for col, config in columns.items():
        treeview.heading(col, text=col, anchor="center")
        treeview.column(col, **config)
    
    # Configure alternating row colors (if supported)
    try:
        treeview.tag_configure('oddrow', background='#f0f0f0')
        treeview.tag_configure('evenrow', background='white')
    except:
        pass

# Backward compatibility functions
def load_dashboards():
    """Backward compatible function."""
    manager = DashboardManager()
    return manager.load_dashboards()

def save_dashboards(dashboards):
    """Backward compatible function."""
    manager = DashboardManager()
    return manager.save_dashboards(dashboards)

def get_groups(dashboards):
    """Backward compatible function."""
    manager = DashboardManager()
    return manager.get_groups(dashboards)

def select_all(dashboards):
    """Backward compatible function."""
    manager = DashboardManager()
    manager.select_all(dashboards)

def deselect_all(dashboards):
    """Backward compatible function."""
    manager = DashboardManager()
    manager.deselect_all(dashboards)
