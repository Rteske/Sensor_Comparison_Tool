"""
Lookup Table GUI Tool
Loads sensor comparison data files and creates lookup tables for Python-side correction.
"""

import os
import csv
import json
import datetime
import tkinter as tk
import openpyxl
from tkinter import ttk, filedialog, messagebox
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk


class LookupTable:
    """Lookup table class for distance correction"""
    
    def __init__(self, name="Untitled"):
        self.name = name
        self.positions = []  # Reference positions (e.g., string pot readings)
        self.distances = []  # Corresponding sensor distances
        self.created_date = datetime.datetime.now().isoformat()
        self.source_files = []
        self.metadata = {}
    
    def add_data(self, positions, distances):
        """Add data points to the lookup table"""
        self.positions.extend(positions)
        self.distances.extend(distances)
    
    def compile(self, bin_size=1.0, method='average'):
        """
        Compile the lookup table by binning and averaging data points.
        
        Args:
            bin_size: Size of position bins in mm
            method: 'average', 'median', or 'linear_fit'
        """
        if not self.positions or not self.distances:
            return False
        
        # Create pairs and sort by position
        data_pairs = list(zip(self.positions, self.distances))
        data_pairs.sort(key=lambda x: x[0])
        
        # Bin the data
        binned_data = {}
        for pos, dist in data_pairs:
            bin_key = round(pos / bin_size) * bin_size
            if bin_key not in binned_data:
                binned_data[bin_key] = []
            binned_data[bin_key].append(dist)
        
        # Calculate representative value for each bin
        self.compiled_positions = []
        self.compiled_distances = []
        self.compiled_std = []
        self.compiled_count = []
        
        for pos in sorted(binned_data.keys()):
            values = binned_data[pos]
            self.compiled_positions.append(pos)
            self.compiled_count.append(len(values))
            self.compiled_std.append(np.std(values) if len(values) > 1 else 0)
            
            if method == 'average':
                self.compiled_distances.append(np.mean(values))
            elif method == 'median':
                self.compiled_distances.append(np.median(values))
            else:
                self.compiled_distances.append(np.mean(values))
        
        self.metadata['bin_size'] = bin_size
        self.metadata['method'] = method
        self.metadata['compiled_date'] = datetime.datetime.now().isoformat()
        
        return True
    
    def lookup(self, position):
        """
        Look up the corrected distance for a given position using linear interpolation.
        """
        if not hasattr(self, 'compiled_positions') or not self.compiled_positions:
            return None
        
        positions = self.compiled_positions
        distances = self.compiled_distances
        
        # Handle edge cases
        if position <= positions[0]:
            return distances[0]
        if position >= positions[-1]:
            return distances[-1]
        
        # Find interpolation points
        for i in range(len(positions) - 1):
            if positions[i] <= position <= positions[i + 1]:
                x1, y1 = positions[i], distances[i]
                x2, y2 = positions[i + 1], distances[i + 1]
                
                # Linear interpolation
                return y1 + (y2 - y1) * (position - x1) / (x2 - x1)
        
        return None
    
    def reverse_lookup(self, distance):
        """
        Reverse lookup: get position for a given distance.
        """
        if not hasattr(self, 'compiled_positions') or not self.compiled_positions:
            return None
        
        positions = self.compiled_positions
        distances = self.compiled_distances
        
        # Handle edge cases
        if distance <= min(distances):
            idx = distances.index(min(distances))
            return positions[idx]
        if distance >= max(distances):
            idx = distances.index(max(distances))
            return positions[idx]
        
        # Find interpolation points (assuming monotonic relationship)
        for i in range(len(distances) - 1):
            d1, d2 = distances[i], distances[i + 1]
            if (d1 <= distance <= d2) or (d2 <= distance <= d1):
                p1, p2 = positions[i], positions[i + 1]
                
                # Linear interpolation
                if d2 != d1:
                    return p1 + (p2 - p1) * (distance - d1) / (d2 - d1)
        
        return None
    
    def get_correction(self, sensor_distance):
        """
        Get the correction offset for a given sensor distance.
        Returns the difference between the true position and the sensor reading.
        """
        true_position = self.reverse_lookup(sensor_distance)
        if true_position is not None:
            return true_position - sensor_distance
        return 0
    
    def to_dict(self):
        """Convert lookup table to dictionary for saving"""
        data = {
            'name': self.name,
            'created_date': self.created_date,
            'source_files': self.source_files,
            'metadata': self.metadata,
            'raw_positions': self.positions,
            'raw_distances': self.distances,
        }
        
        if hasattr(self, 'compiled_positions'):
            data['compiled_positions'] = self.compiled_positions
            data['compiled_distances'] = self.compiled_distances
            data['compiled_std'] = self.compiled_std
            data['compiled_count'] = self.compiled_count
        
        return data
    
    @classmethod
    def from_dict(cls, data):
        """Create lookup table from dictionary"""
        lut = cls(data.get('name', 'Untitled'))
        lut.created_date = data.get('created_date', datetime.datetime.now().isoformat())
        lut.source_files = data.get('source_files', [])
        lut.metadata = data.get('metadata', {})
        lut.positions = data.get('raw_positions', [])
        lut.distances = data.get('raw_distances', [])
        
        if 'compiled_positions' in data:
            lut.compiled_positions = data['compiled_positions']
            lut.compiled_distances = data['compiled_distances']
            lut.compiled_std = data.get('compiled_std', [])
            lut.compiled_count = data.get('compiled_count', [])
        
        return lut
    
    def save(self, filepath):
        """Save lookup table to JSON file"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def load(cls, filepath):
        """Load lookup table from JSON file"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)


class LookupTableGUI:
    """Main GUI application for lookup table management"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Sensor Lookup Table Tool")
        self.root.geometry("1200x800")
        
        # Data storage
        self.lookup_tables = {}  # name -> LookupTable
        self.current_lut = None
        self.loaded_files = []
        self.pending_data = {'positions': [], 'distances': [], 'files': []}
        
        # Default data directory
        self.data_dir = os.path.join(os.path.dirname(__file__), "data")
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the main UI"""
        # Create main paned window
        self.main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Left panel - File browser and LUT list
        self.left_frame = ttk.Frame(self.main_paned, width=300)
        self.main_paned.add(self.left_frame, weight=1)
        
        # Right panel - Data view and plots
        self.right_frame = ttk.Frame(self.main_paned)
        self.main_paned.add(self.right_frame, weight=3)
        
        self.setup_left_panel()
        self.setup_right_panel()
        self.setup_menu()
    
    def setup_menu(self):
        """Setup menu bar"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open Data Directory...", command=self.open_data_directory)
        file_menu.add_separator()
        file_menu.add_command(label="Load Lookup Table...", command=self.load_lut_file)
        file_menu.add_command(label="Save Lookup Table...", command=self.save_lut_file)
        file_menu.add_separator()
        file_menu.add_command(label="Export to C Header...", command=self.export_to_header)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        
        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Test Lookup Value...", command=self.test_lookup_dialog)
        tools_menu.add_command(label="Batch Correction...", command=self.batch_correction_dialog)
    
    def setup_left_panel(self):
        """Setup left panel with file browser and LUT list"""
        # Notebook for tabs
        notebook = ttk.Notebook(self.left_frame)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # Tab 1: Data Directory
        files_frame = ttk.Frame(notebook)
        notebook.add(files_frame, text="Data Directory")
        
        # Directory selection
        dir_frame = ttk.LabelFrame(files_frame, text="Data Directory")
        dir_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.dir_path_var = tk.StringVar(value=self.data_dir)
        dir_entry = ttk.Entry(dir_frame, textvariable=self.dir_path_var, state='readonly')
        dir_entry.pack(fill=tk.X, padx=5, pady=2)
        
        dir_btn_frame = ttk.Frame(dir_frame)
        dir_btn_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(dir_btn_frame, text="Browse...", command=self.open_data_directory).pack(side=tk.LEFT)
        ttk.Button(dir_btn_frame, text="Refresh", command=self.refresh_file_list).pack(side=tk.LEFT, padx=5)
        
        # Load all button
        load_frame = ttk.LabelFrame(files_frame, text="Load Data")
        load_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(load_frame, text="Load All Files in Directory", 
                   command=self.load_all_from_directory).pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(load_frame, text="Clear Pending Data", 
                   command=self.clear_pending_data).pack(fill=tk.X, padx=5, pady=2)
        
        # File tree (shows what's available)
        tree_frame = ttk.LabelFrame(files_frame, text="Available Files")
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.file_tree = ttk.Treeview(tree_frame, selectmode='extended')
        self.file_tree.heading('#0', text='Excel Files')
        self.file_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.file_tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_tree.configure(yscrollcommand=scrollbar.set)
        
        # Tab 2: Lookup Tables
        lut_frame = ttk.Frame(notebook)
        notebook.add(lut_frame, text="Lookup Tables")
        
        # LUT list
        lut_list_frame = ttk.Frame(lut_frame)
        lut_list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.lut_listbox = tk.Listbox(lut_list_frame, selectmode=tk.SINGLE)
        self.lut_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.lut_listbox.bind('<<ListboxSelect>>', self.on_lut_select)
        
        lut_scroll = ttk.Scrollbar(lut_list_frame, orient=tk.VERTICAL, command=self.lut_listbox.yview)
        lut_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.lut_listbox.configure(yscrollcommand=lut_scroll.set)
        
        # LUT action buttons
        lut_btn_frame = ttk.Frame(lut_frame)
        lut_btn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(lut_btn_frame, text="New LUT", command=self.create_new_lut).pack(side=tk.LEFT)
        ttk.Button(lut_btn_frame, text="Delete", command=self.delete_lut).pack(side=tk.LEFT, padx=5)
        
        # Initialize file list
        self.refresh_file_list()
    
    def setup_right_panel(self):
        """Setup right panel with data view and plots"""
        # Notebook for different views
        self.right_notebook = ttk.Notebook(self.right_frame)
        self.right_notebook.pack(fill=tk.BOTH, expand=True)
        
        # Tab 1: Pending Data
        self.pending_frame = ttk.Frame(self.right_notebook)
        self.right_notebook.add(self.pending_frame, text="Pending Data")
        self.setup_pending_tab()
        
        # Tab 2: Compiled LUT
        self.compiled_frame = ttk.Frame(self.right_notebook)
        self.right_notebook.add(self.compiled_frame, text="Compiled LUT")
        self.setup_compiled_tab()
        
        # Tab 3: Test/Apply
        self.test_frame = ttk.Frame(self.right_notebook)
        self.right_notebook.add(self.test_frame, text="Test & Apply")
        self.setup_test_tab()
    
    def setup_pending_tab(self):
        """Setup the pending data tab"""
        # Info frame
        info_frame = ttk.LabelFrame(self.pending_frame, text="Pending Data Info")
        info_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.pending_info_label = ttk.Label(info_frame, text="No data loaded")
        self.pending_info_label.pack(padx=5, pady=5)
        
        # Loaded files list
        files_frame = ttk.LabelFrame(self.pending_frame, text="Loaded Files")
        files_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.loaded_files_text = tk.Text(files_frame, height=4, state=tk.DISABLED)
        self.loaded_files_text.pack(fill=tk.X, padx=5, pady=5)
        
        # Compile options
        options_frame = ttk.LabelFrame(self.pending_frame, text="Compile Options")
        options_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Bin size
        bin_frame = ttk.Frame(options_frame)
        bin_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(bin_frame, text="Bin Size (mm):").pack(side=tk.LEFT)
        self.bin_size_var = tk.StringVar(value="1.0")
        ttk.Entry(bin_frame, textvariable=self.bin_size_var, width=10).pack(side=tk.LEFT, padx=5)
        
        # Method
        method_frame = ttk.Frame(options_frame)
        method_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(method_frame, text="Method:").pack(side=tk.LEFT)
        self.method_var = tk.StringVar(value="average")
        ttk.Combobox(method_frame, textvariable=self.method_var, 
                     values=["average", "median"], state="readonly", width=15).pack(side=tk.LEFT, padx=5)
        
        # LUT name
        name_frame = ttk.Frame(options_frame)
        name_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(name_frame, text="LUT Name:").pack(side=tk.LEFT)
        self.lut_name_var = tk.StringVar(value="New_LUT")
        ttk.Entry(name_frame, textvariable=self.lut_name_var, width=20).pack(side=tk.LEFT, padx=5)
        
        # Compile button
        ttk.Button(options_frame, text="Compile Lookup Table", 
                   command=self.compile_pending_data).pack(pady=10)
        
        # Plot frame
        plot_frame = ttk.LabelFrame(self.pending_frame, text="Raw Data Preview")
        plot_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.pending_fig, self.pending_ax = plt.subplots(figsize=(8, 4))
        self.pending_canvas = FigureCanvasTkAgg(self.pending_fig, plot_frame)
        self.pending_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        toolbar_frame = ttk.Frame(plot_frame)
        toolbar_frame.pack(fill=tk.X)
        NavigationToolbar2Tk(self.pending_canvas, toolbar_frame)
    
    def setup_compiled_tab(self):
        """Setup the compiled LUT tab"""
        # Info frame
        info_frame = ttk.LabelFrame(self.compiled_frame, text="Lookup Table Info")
        info_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.compiled_info_label = ttk.Label(info_frame, text="No lookup table selected")
        self.compiled_info_label.pack(padx=5, pady=5)
        
        # Data table
        table_frame = ttk.LabelFrame(self.compiled_frame, text="LUT Data")
        table_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Treeview for data
        columns = ('position', 'distance', 'std', 'count')
        self.lut_tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=10)
        
        self.lut_tree.heading('position', text='Position (mm)')
        self.lut_tree.heading('distance', text='Distance (mm)')
        self.lut_tree.heading('std', text='Std Dev')
        self.lut_tree.heading('count', text='Samples')
        
        self.lut_tree.column('position', width=100)
        self.lut_tree.column('distance', width=100)
        self.lut_tree.column('std', width=80)
        self.lut_tree.column('count', width=80)
        
        self.lut_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        tree_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.lut_tree.yview)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.lut_tree.configure(yscrollcommand=tree_scroll.set)
        
        # Plot frame
        plot_frame = ttk.LabelFrame(self.compiled_frame, text="LUT Visualization")
        plot_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.compiled_fig, self.compiled_axes = plt.subplots(1, 2, figsize=(10, 4))
        self.compiled_canvas = FigureCanvasTkAgg(self.compiled_fig, plot_frame)
        self.compiled_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        toolbar_frame = ttk.Frame(plot_frame)
        toolbar_frame.pack(fill=tk.X)
        NavigationToolbar2Tk(self.compiled_canvas, toolbar_frame)
    
    def setup_test_tab(self):
        """Setup the test & apply tab"""
        # Single value test
        test_frame = ttk.LabelFrame(self.test_frame, text="Test Lookup (Sensor Distance → True Position)")
        test_frame.pack(fill=tk.X, padx=5, pady=5)
        
        input_frame = ttk.Frame(test_frame)
        input_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(input_frame, text="Sensor Distance (mm):").pack(side=tk.LEFT)
        self.test_input_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.test_input_var, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(input_frame, text="Get True Position", command=self.test_single_lookup).pack(side=tk.LEFT)
        
        self.test_result_label = ttk.Label(test_frame, text="Result: -")
        self.test_result_label.pack(padx=5, pady=5)
        
        # Batch correction
        batch_frame = ttk.LabelFrame(self.test_frame, text="Batch Correction")
        batch_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        btn_frame = ttk.Frame(batch_frame)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(btn_frame, text="Load CSV Data...", command=self.load_batch_data).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Apply Correction", command=self.apply_batch_correction).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Save Corrected Data...", command=self.save_corrected_data).pack(side=tk.LEFT)
        
        # Batch data preview
        self.batch_text = tk.Text(batch_frame, height=10)
        self.batch_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.batch_data = None
        self.corrected_data = None
    
    def open_data_directory(self):
        """Open a data directory"""
        directory = filedialog.askdirectory(initialdir=self.data_dir, title="Select Data Directory")
        if directory:
            self.data_dir = directory
            self.dir_path_var.set(directory)
            self.refresh_file_list()
    
    def refresh_file_list(self):
        """Refresh the file tree with available data files"""
        # Clear existing items
        for item in self.file_tree.get_children():
            self.file_tree.delete(item)
        
        if not os.path.exists(self.data_dir):
            return
        
        # Walk through data directory
        for root, dirs, files in os.walk(self.data_dir):
            rel_path = os.path.relpath(root, self.data_dir)
            
            if rel_path == '.':
                parent = ''
            else:
                parent = self.file_tree.insert('', 'end', rel_path, text=rel_path, open=True)
            
            for f in sorted(files):
                if f.endswith('.xlsx') and f.startswith('TDS_'):
                    file_path = os.path.join(root, f)
                    item_id = file_path
                    if parent:
                        self.file_tree.insert(parent, 'end', item_id, text=f)
                    else:
                        self.file_tree.insert('', 'end', item_id, text=f)
    
    def load_all_from_directory(self):
        """Load all Excel files from the data directory"""
        if not os.path.exists(self.data_dir):
            messagebox.showwarning("Warning", "Data directory does not exist")
            return
        
        # Clear existing pending data
        self.clear_pending_data()
        
        file_count = 0
        # Walk through data directory and load all TDS_*.xlsx files
        for root, dirs, files in os.walk(self.data_dir):
            for f in sorted(files):
                if f.endswith('.xlsx') and f.startswith('TDS_'):
                    filepath = os.path.join(root, f)
                    self.load_xlsx_file(filepath)
                    file_count += 1
        
        if file_count == 0:
            messagebox.showinfo("Info", "No TDS_*.xlsx files found in directory")
        else:
            messagebox.showinfo("Success", f"Loaded {file_count} files with {len(self.pending_data['positions'])} data points")
        
        self.update_pending_display()
    
    def load_xlsx_file(self, filepath):
        """Load an Excel file and add to pending data"""
        try:
            wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
            
            # Try to find RAW_DATA sheet first, otherwise use active sheet
            if 'RAW_DATA' in wb.sheetnames:
                ws = wb['RAW_DATA']
            else:
                ws = wb.active
            
            row_count = 0
            for row in ws.iter_rows(min_row=1, values_only=True):
                if row and len(row) >= 4:
                    try:
                        # Excel format: distance, temp, position, delta, ...
                        distance = float(row[0]) if row[0] is not None else None
                        position = float(row[2]) if row[2] is not None else None
                        
                        if distance is not None and position is not None:
                            self.pending_data['positions'].append(position)
                            self.pending_data['distances'].append(distance)
                            row_count += 1
                    except (ValueError, TypeError):
                        continue
            
            wb.close()
            
            if filepath not in self.pending_data['files']:
                self.pending_data['files'].append(filepath)
            
            print(f"Loaded: {filepath} ({row_count} data points)")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load {filepath}: {str(e)}")
    
    def clear_pending_data(self):
        """Clear all pending data"""
        self.pending_data = {'positions': [], 'distances': [], 'files': []}
        self.update_pending_display()
    
    def update_pending_display(self):
        """Update the pending data display"""
        count = len(self.pending_data['positions'])
        file_count = len(self.pending_data['files'])
        
        self.pending_info_label.config(
            text=f"Data Points: {count} | Files Loaded: {file_count}"
        )
        
        # Update loaded files text
        self.loaded_files_text.config(state=tk.NORMAL)
        self.loaded_files_text.delete(1.0, tk.END)
        for f in self.pending_data['files']:
            self.loaded_files_text.insert(tk.END, os.path.basename(f) + "\n")
        self.loaded_files_text.config(state=tk.DISABLED)
        
        # Update plot
        self.pending_ax.clear()
        if count > 0:
            self.pending_ax.scatter(self.pending_data['positions'], 
                                    self.pending_data['distances'],
                                    alpha=0.5, s=10)
            self.pending_ax.set_xlabel('Position (mm)')
            self.pending_ax.set_ylabel('Sensor Distance (mm)')
            self.pending_ax.set_title('Raw Data (Position vs Distance)')
            self.pending_ax.grid(True, alpha=0.3)
            
            # Add ideal line
            min_val = min(min(self.pending_data['positions']), min(self.pending_data['distances']))
            max_val = max(max(self.pending_data['positions']), max(self.pending_data['distances']))
            self.pending_ax.plot([min_val, max_val], [min_val, max_val], 'r--', label='Ideal (y=x)')
            self.pending_ax.legend()
        
        self.pending_fig.tight_layout()
        self.pending_canvas.draw()
    
    def compile_pending_data(self):
        """Compile pending data into a lookup table"""
        if not self.pending_data['positions']:
            messagebox.showwarning("Warning", "No data to compile")
            return
        
        try:
            bin_size = float(self.bin_size_var.get())
        except ValueError:
            messagebox.showerror("Error", "Invalid bin size")
            return
        
        name = self.lut_name_var.get().strip()
        if not name:
            name = f"LUT_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Create new lookup table
        lut = LookupTable(name)
        lut.add_data(self.pending_data['positions'], self.pending_data['distances'])
        lut.source_files = self.pending_data['files'].copy()
        
        # Compile
        method = self.method_var.get()
        if lut.compile(bin_size=bin_size, method=method):
            self.lookup_tables[name] = lut
            self.current_lut = lut
            self.update_lut_list()
            self.update_compiled_display()
            
            # Auto-save lookup table to data directory
            try:
                lut_dir = os.path.join(self.data_dir, "lookup_tables")
                os.makedirs(lut_dir, exist_ok=True)
                
                # Save JSON
                json_path = os.path.join(lut_dir, f"{name}.json")
                lut.save(json_path)
                
                # Save Python module for easy import
                py_path = os.path.join(lut_dir, f"{name}.py")
                self.write_python_module(py_path, lut)
                
                # Save C header
                h_path = os.path.join(lut_dir, f"{name}.h")
                self.write_c_header(h_path)
                
                messagebox.showinfo("Success", 
                    f"Lookup table '{name}' created with {len(lut.compiled_positions)} entries\n\n"
                    f"Saved to: {lut_dir}\n"
                    f"- {name}.json (data file)\n"
                    f"- {name}.py (Python module)\n"
                    f"- {name}.h (C header)")
            except Exception as e:
                messagebox.showwarning("Warning", 
                    f"Lookup table created but failed to auto-save: {str(e)}")
            
            # Switch to compiled tab
            self.right_notebook.select(1)
        else:
            messagebox.showerror("Error", "Failed to compile lookup table")
    
    def update_lut_list(self):
        """Update the lookup table listbox"""
        self.lut_listbox.delete(0, tk.END)
        for name in sorted(self.lookup_tables.keys()):
            self.lut_listbox.insert(tk.END, name)
    
    def on_lut_select(self, event):
        """Handle LUT selection"""
        selection = self.lut_listbox.curselection()
        if selection:
            name = self.lut_listbox.get(selection[0])
            self.current_lut = self.lookup_tables.get(name)
            self.update_compiled_display()
    
    def update_compiled_display(self):
        """Update the compiled LUT display"""
        # Clear tree
        for item in self.lut_tree.get_children():
            self.lut_tree.delete(item)
        
        if not self.current_lut or not hasattr(self.current_lut, 'compiled_positions'):
            self.compiled_info_label.config(text="No lookup table selected")
            return
        
        lut = self.current_lut
        
        # Update info
        info_text = (f"Name: {lut.name} | "
                    f"Entries: {len(lut.compiled_positions)} | "
                    f"Bin Size: {lut.metadata.get('bin_size', 'N/A')} mm | "
                    f"Method: {lut.metadata.get('method', 'N/A')}")
        self.compiled_info_label.config(text=info_text)
        
        # Populate tree
        for i in range(len(lut.compiled_positions)):
            self.lut_tree.insert('', 'end', values=(
                f"{lut.compiled_positions[i]:.2f}",
                f"{lut.compiled_distances[i]:.2f}",
                f"{lut.compiled_std[i]:.3f}" if lut.compiled_std else "N/A",
                lut.compiled_count[i] if lut.compiled_count else "N/A"
            ))
        
        # Update plots
        for ax in self.compiled_axes:
            ax.clear()
        
        # Plot 1: Position vs Distance with error bars
        ax1 = self.compiled_axes[0]
        if lut.compiled_std and any(s > 0 for s in lut.compiled_std):
            ax1.errorbar(lut.compiled_positions, lut.compiled_distances, 
                        yerr=lut.compiled_std, fmt='o-', capsize=3, markersize=4)
        else:
            ax1.plot(lut.compiled_positions, lut.compiled_distances, 'o-', markersize=4)
        
        # Add ideal line
        min_val = min(min(lut.compiled_positions), min(lut.compiled_distances))
        max_val = max(max(lut.compiled_positions), max(lut.compiled_distances))
        ax1.plot([min_val, max_val], [min_val, max_val], 'r--', alpha=0.7, label='Ideal (y=x)')
        
        ax1.set_xlabel('Position (mm)')
        ax1.set_ylabel('Sensor Distance (mm)')
        ax1.set_title('Lookup Table')
        ax1.grid(True, alpha=0.3)
        ax1.legend()
        
        # Plot 2: Error/Delta
        ax2 = self.compiled_axes[1]
        deltas = [lut.compiled_distances[i] - lut.compiled_positions[i] 
                  for i in range(len(lut.compiled_positions))]
        ax2.plot(lut.compiled_positions, deltas, 'o-', color='orange', markersize=4)
        ax2.axhline(y=0, color='r', linestyle='--', alpha=0.7)
        ax2.set_xlabel('Position (mm)')
        ax2.set_ylabel('Error (mm)')
        ax2.set_title('Sensor Error vs Position')
        ax2.grid(True, alpha=0.3)
        
        self.compiled_fig.tight_layout()
        self.compiled_canvas.draw()
    
    def create_new_lut(self):
        """Create a new empty lookup table"""
        name = f"LUT_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.lut_name_var.set(name)
        self.right_notebook.select(0)  # Switch to pending data tab
    
    def delete_lut(self):
        """Delete selected lookup table"""
        selection = self.lut_listbox.curselection()
        if selection:
            name = self.lut_listbox.get(selection[0])
            if messagebox.askyesno("Confirm", f"Delete lookup table '{name}'?"):
                del self.lookup_tables[name]
                if self.current_lut and self.current_lut.name == name:
                    self.current_lut = None
                self.update_lut_list()
                self.update_compiled_display()
    
    def load_lut_file(self):
        """Load a lookup table from file"""
        filepath = filedialog.askopenfilename(
            title="Load Lookup Table",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filepath:
            try:
                lut = LookupTable.load(filepath)
                self.lookup_tables[lut.name] = lut
                self.current_lut = lut
                self.update_lut_list()
                self.update_compiled_display()
                messagebox.showinfo("Success", f"Loaded lookup table: {lut.name}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load: {str(e)}")
    
    def save_lut_file(self):
        """Save current lookup table to file"""
        if not self.current_lut:
            messagebox.showwarning("Warning", "No lookup table selected")
            return
        
        filepath = filedialog.asksaveasfilename(
            title="Save Lookup Table",
            defaultextension=".json",
            initialfile=f"{self.current_lut.name}.json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filepath:
            try:
                self.current_lut.save(filepath)
                messagebox.showinfo("Success", f"Saved: {filepath}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save: {str(e)}")
    
    def export_to_header(self):
        """Export current lookup table to C header file"""
        if not self.current_lut or not hasattr(self.current_lut, 'compiled_positions'):
            messagebox.showwarning("Warning", "No compiled lookup table selected")
            return
        
        filepath = filedialog.asksaveasfilename(
            title="Export to C Header",
            defaultextension=".h",
            initialfile=f"{self.current_lut.name}.h",
            filetypes=[("C Header files", "*.h"), ("All files", "*.*")]
        )
        if filepath:
            try:
                self.write_c_header(filepath)
                messagebox.showinfo("Success", f"Exported: {filepath}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export: {str(e)}")
    
    def write_python_module(self, filepath, lut=None):
        """Write lookup table as importable Python module"""
        if lut is None:
            lut = self.current_lut
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('"""\n')
            f.write(f"Sensor Distance Lookup Table: {lut.name}\n")
            f.write(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Bin Size: {lut.metadata.get('bin_size', 'N/A')} mm\n")
            f.write(f"Method: {lut.metadata.get('method', 'N/A')}\n")
            f.write('\n')
            f.write('Usage:\n')
            f.write('    from {} import get_true_position\n'.format(os.path.splitext(os.path.basename(filepath))[0]))
            f.write('    \n')
            f.write('    sensor_distance = 150.5  # mm from sensor\n')
            f.write('    true_position = get_true_position(sensor_distance)\n')
            f.write('    print(f"True position: {true_position:.2f}mm")\n')
            f.write('"""\n\n')
            
            f.write('# Lookup table data\n')
            f.write(f"LUT_POSITIONS = {lut.compiled_positions}\n\n")
            f.write(f"LUT_DISTANCES = {lut.compiled_distances}\n\n")
            
            f.write('def get_true_position(sensor_distance):\n')
            f.write('    """\n')
            f.write('    Get the true position for a given sensor distance reading.\n')
            f.write('    \n')
            f.write('    Args:\n')
            f.write('        sensor_distance: Distance measured by the sensor (mm)\n')
            f.write('    \n')
            f.write('    Returns:\n')
            f.write('        True position (mm) or None if out of range\n')
            f.write('    """\n')
            f.write('    positions = LUT_POSITIONS\n')
            f.write('    distances = LUT_DISTANCES\n')
            f.write('    \n')
            f.write('    # Handle edge cases\n')
            f.write('    if sensor_distance <= min(distances):\n')
            f.write('        idx = distances.index(min(distances))\n')
            f.write('        return positions[idx]\n')
            f.write('    if sensor_distance >= max(distances):\n')
            f.write('        idx = distances.index(max(distances))\n')
            f.write('        return positions[idx]\n')
            f.write('    \n')
            f.write('    # Linear interpolation\n')
            f.write('    for i in range(len(distances) - 1):\n')
            f.write('        d1, d2 = distances[i], distances[i + 1]\n')
            f.write('        if (d1 <= sensor_distance <= d2) or (d2 <= sensor_distance <= d1):\n')
            f.write('            p1, p2 = positions[i], positions[i + 1]\n')
            f.write('            if d2 != d1:\n')
            f.write('                return p1 + (p2 - p1) * (sensor_distance - d1) / (d2 - d1)\n')
            f.write('    \n')
            f.write('    return None\n\n')
            
            f.write('def get_sensor_error(sensor_distance):\n')
            f.write('    """\n')
            f.write('    Get the error (distance - true_position) for a sensor reading.\n')
            f.write('    \n')
            f.write('    Args:\n')
            f.write('        sensor_distance: Distance measured by the sensor (mm)\n')
            f.write('    \n')
            f.write('    Returns:\n')
            f.write('        Error in mm (positive = sensor reads too high)\n')
            f.write('    """\n')
            f.write('    true_pos = get_true_position(sensor_distance)\n')
            f.write('    if true_pos is not None:\n')
            f.write('        return sensor_distance - true_pos\n')
            f.write('    return 0\n\n')
            
            f.write('if __name__ == "__main__":\n')
            f.write('    # Test the lookup table\n')
            f.write('    print("Sensor Distance Lookup Table Test")\n')
            f.write('    print("=" * 50)\n')
            f.write('    print(f"Table has {len(LUT_POSITIONS)} entries")\n')
            f.write('    print(f"Range: {min(LUT_DISTANCES):.2f}mm to {max(LUT_DISTANCES):.2f}mm\\n")\n')
            f.write('    \n')
            f.write('    # Test some values\n')
            f.write('    test_distances = [50, 100, 150, 200, 250]\n')
            f.write('    for dist in test_distances:\n')
            f.write('        true_pos = get_true_position(dist)\n')
            f.write('        if true_pos:\n')
            f.write('            error = get_sensor_error(dist)\n')
            f.write('            print(f"Sensor: {dist:6.2f}mm → True: {true_pos:6.2f}mm | Error: {error:+6.2f}mm")\n')
    
    def write_c_header(self, filepath, lut=None):
        """Write lookup table to C header file"""
        if lut is None:
            lut = self.current_lut
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"// Sensor Distance Lookup Table: {lut.name}\n")
            f.write(f"// Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"// Bin Size: {lut.metadata.get('bin_size', 'N/A')} mm\n")
            f.write(f"// Method: {lut.metadata.get('method', 'N/A')}\n\n")
            
            guard = lut.name.upper().replace(' ', '_') + "_H"
            f.write(f"#ifndef {guard}\n")
            f.write(f"#define {guard}\n\n")
            
            f.write(f"#define LUT_SIZE {len(lut.compiled_positions)}\n\n")
            
            f.write("static const float lut_positions[LUT_SIZE] = {\n")
            for i, pos in enumerate(lut.compiled_positions):
                comma = "," if i < len(lut.compiled_positions) - 1 else ""
                f.write(f"    {pos:.2f}f{comma}\n")
            f.write("};\n\n")
            
            f.write("static const float lut_distances[LUT_SIZE] = {\n")
            for i, dist in enumerate(lut.compiled_distances):
                comma = "," if i < len(lut.compiled_distances) - 1 else ""
                f.write(f"    {dist:.2f}f{comma}\n")
            f.write("};\n\n")
            
            f.write(f"#endif // {guard}\n")
    
    def test_lookup_dialog(self):
        """Open test lookup dialog"""
        self.right_notebook.select(2)  # Switch to test tab
    
    def test_single_lookup(self):
        """Test a single lookup value: sensor distance -> true position"""
        if not self.current_lut:
            messagebox.showwarning("Warning", "No lookup table selected")
            return
        
        try:
            sensor_distance = float(self.test_input_var.get())
        except ValueError:
            messagebox.showerror("Error", "Invalid sensor distance value")
            return
        
        true_position = self.current_lut.reverse_lookup(sensor_distance)
        if true_position is not None:
            error = sensor_distance - true_position
            self.test_result_label.config(
                text=f"Result: Sensor {sensor_distance:.2f}mm → True Position {true_position:.2f}mm | Error: {error:.2f}mm"
            )
        else:
            self.test_result_label.config(text="Result: Distance out of range")
    
    def batch_correction_dialog(self):
        """Open batch correction dialog"""
        self.right_notebook.select(2)  # Switch to test tab
    
    def load_batch_data(self):
        """Load CSV data for batch correction"""
        filepath = filedialog.askopenfilename(
            title="Load CSV Data",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if filepath:
            try:
                self.batch_data = []
                with open(filepath, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    for row in reader:
                        self.batch_data.append(row)
                
                # Display preview
                self.batch_text.delete(1.0, tk.END)
                self.batch_text.insert(tk.END, f"Loaded {len(self.batch_data)} rows\n\n")
                for i, row in enumerate(self.batch_data[:10]):
                    self.batch_text.insert(tk.END, f"{i}: {row}\n")
                if len(self.batch_data) > 10:
                    self.batch_text.insert(tk.END, f"... and {len(self.batch_data) - 10} more rows\n")
                    
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load: {str(e)}")
    
    def apply_batch_correction(self):
        """Apply lookup table correction to batch data"""
        if not self.batch_data:
            messagebox.showwarning("Warning", "No batch data loaded")
            return
        
        if not self.current_lut:
            messagebox.showwarning("Warning", "No lookup table selected")
            return
        
        self.corrected_data = []
        for row in self.batch_data:
            new_row = list(row)
            try:
                if len(row) >= 1:
                    sensor_distance = float(row[0])
                    corrected = self.current_lut.reverse_lookup(sensor_distance)
                    if corrected is not None:
                        new_row.append(f"{corrected:.2f}")
                    else:
                        new_row.append("N/A")
            except ValueError:
                new_row.append("N/A")
            self.corrected_data.append(new_row)
        
        # Display preview
        self.batch_text.delete(1.0, tk.END)
        self.batch_text.insert(tk.END, f"Corrected {len(self.corrected_data)} rows\n")
        self.batch_text.insert(tk.END, "(Last column is corrected value)\n\n")
        for i, row in enumerate(self.corrected_data[:10]):
            self.batch_text.insert(tk.END, f"{i}: {row}\n")
        if len(self.corrected_data) > 10:
            self.batch_text.insert(tk.END, f"... and {len(self.corrected_data) - 10} more rows\n")
        
        messagebox.showinfo("Success", f"Applied correction to {len(self.corrected_data)} rows")
    
    def save_corrected_data(self):
        """Save corrected data to CSV"""
        if not self.corrected_data:
            messagebox.showwarning("Warning", "No corrected data to save")
            return
        
        filepath = filedialog.asksaveasfilename(
            title="Save Corrected Data",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if filepath:
            try:
                with open(filepath, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerows(self.corrected_data)
                messagebox.showinfo("Success", f"Saved: {filepath}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save: {str(e)}")


def main():
    root = tk.Tk()
    app = LookupTableGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
