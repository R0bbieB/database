#!/usr/bin/env python
# migration.py - Script to migrate data from Excel to SQL database
import pandas as pd
import numpy as np
from datetime import datetime
import os
import sys
import logging
import sqlite3
import time
import re

# Setup logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    filename='migration.log')
logger = logging.getLogger('migration')


# Helper functions for data cleaning
def clean_string(value):
    """Clean string values, convert NaN to empty string"""
    if pd.isna(value):
        return ''
    return str(value).strip()


def clean_int(value, default=0):
    """Convert to int with error handling"""
    if pd.isna(value):
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        logger.warning(f"Could not convert value '{value}' to integer, using default {default}")
        return default


def clean_bool(value, default=False):
    """Convert to boolean with error handling"""
    if pd.isna(value):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.lower() in ('yes', 'true', 't', '1', 'y')
    return default


def clean_date(value):
    """Convert to date with error handling"""
    if pd.isna(value):
        return None
    try:
        return pd.to_datetime(value)
    except:
        logger.warning(f"Error converting date value: {value}")
        return None


def extract_tank_number(value):
    """Extract the numeric part of a tank ID if present"""
    if not value:
        return None

    # Try to extract a number from the string
    match = re.search(r'(\d+)', str(value))
    if match:
        return match.group(1)
    return value


def migrate_data(excel_file, db_file=None):
    """Migrate data directly to SQLite database"""
    # Set default db_file if not provided
    if db_file is None:
        # Try to find the instance folder
        instance_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'instance'))
        if not os.path.exists(instance_dir):
            instance_dir = os.path.abspath('instance')
        db_file = os.path.join(instance_dir, 'inventory.db')

    logger.info(f"Starting direct migration from {excel_file} to {db_file}")

    # Ensure the database directory exists
    os.makedirs(os.path.dirname(db_file), exist_ok=True)

    # Backup existing database if it exists
    if os.path.exists(db_file):
        backup_file = f"{db_file}.backup.{int(time.time())}"
        try:
            import shutil
            shutil.copy2(db_file, backup_file)
            logger.info(f"Created database backup: {backup_file}")
        except Exception as e:
            logger.warning(f"Could not create database backup: {e}")

    # Connect to the SQLite database directly
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    try:
        # Read Excel sheets with error handling
        try:
            excel_data = pd.read_excel(excel_file, sheet_name=None)
            logger.info(f"Successfully read Excel file. Found sheets: {list(excel_data.keys())}")
        except Exception as e:
            logger.error(f"Failed to read Excel file: {e}")
            print(f"Error: Failed to read Excel file: {e}")
            return

        # Create tables
        logger.info("Creating database tables")

        # Drop existing tables if they exist
        tables = [
            "checkout_records",
            "maintenance_records",
            "tanks",
            "masks",
            "regulators",
            "bcds",
            "inventory_items",
            "locations",
            "item_types"
        ]

        for table in tables:
            cursor.execute(f"DROP TABLE IF EXISTS {table}")

        # Create tables
        cursor.execute('''
        CREATE TABLE item_types (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT
        )
        ''')

        cursor.execute('''
        CREATE TABLE locations (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT
        )
        ''')

        cursor.execute('''
        CREATE TABLE inventory_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_type_id INTEGER NOT NULL,
            manufacturer TEXT,
            model TEXT,
            serial_number TEXT,
            intake_date TIMESTAMP,
            disposal_date TIMESTAMP,
            location_id INTEGER,
            pm_required BOOLEAN DEFAULT 0,
            condition_code INTEGER DEFAULT 1,
            currently_checked_out BOOLEAN DEFAULT 0,
            last_check_in_date TIMESTAMP,
            last_check_out_date TIMESTAMP,
            FOREIGN KEY (item_type_id) REFERENCES item_types (id),
            FOREIGN KEY (location_id) REFERENCES locations (id)
        )
        ''')

        cursor.execute('''
        CREATE TABLE bcds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inventory_item_id INTEGER UNIQUE,
            last_maintenance TIMESTAMP,
            next_maintenance TIMESTAMP,
            FOREIGN KEY (inventory_item_id) REFERENCES inventory_items (id)
        )
        ''')

        cursor.execute('''
        CREATE TABLE regulators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inventory_item_id INTEGER UNIQUE,
            has_computer BOOLEAN DEFAULT 0,
            last_service_date TIMESTAMP,
            FOREIGN KEY (inventory_item_id) REFERENCES inventory_items (id)
        )
        ''')

        cursor.execute('''
        CREATE TABLE masks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inventory_item_id INTEGER UNIQUE,
            has_comms BOOLEAN DEFAULT 0,
            size TEXT,
            FOREIGN KEY (inventory_item_id) REFERENCES inventory_items (id)
        )
        ''')

        cursor.execute('''
        CREATE TABLE tanks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inventory_item_id INTEGER UNIQUE,
            tank_number TEXT,
            hydro_date TIMESTAMP,
            vip_date TIMESTAMP,
            tank_material TEXT,
            working_pressure INTEGER,
            gas_type TEXT,
            FOREIGN KEY (inventory_item_id) REFERENCES inventory_items (id)
        )
        ''')

        cursor.execute('''
        CREATE TABLE maintenance_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bcd_id INTEGER,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            maintenance_type TEXT,
            notes TEXT,
            FOREIGN KEY (bcd_id) REFERENCES bcds (id)
        )
        ''')

        cursor.execute('''
        CREATE TABLE checkout_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inventory_item_id INTEGER,
            person_name TEXT NOT NULL,
            checkout_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            checkin_date TIMESTAMP,
            checkout_condition INTEGER,
            checkin_condition INTEGER,
            notes TEXT,
            FOREIGN KEY (inventory_item_id) REFERENCES inventory_items (id)
        )
        ''')

        conn.commit()
        logger.info("Created database tables")

        # Migrate Item Types
        if 'Item_Type' in excel_data:
            logger.info("Processing Item_Type sheet")
            item_types_df = excel_data['Item_Type']

            for _, row in item_types_df.iterrows():
                try:
                    item_id = clean_int(row['ID'])
                    name = clean_string(row['Item Type'])

                    cursor.execute(
                        "INSERT INTO item_types (id, name, description) VALUES (?, ?, ?)",
                        (item_id, name, "")
                    )
                except Exception as e:
                    logger.error(f"Error processing item type: {e}")

            conn.commit()
            logger.info(f"Imported {len(item_types_df)} item types")
        else:
            logger.warning("Item_Type sheet not found")

        # Migrate Locations
        if 'Locations' in excel_data:
            logger.info("Processing Locations sheet")
            locations_df = excel_data['Locations']

            for _, row in locations_df.iterrows():
                try:
                    location_id = clean_int(row['ID'])
                    name = clean_string(row['Location'])

                    cursor.execute(
                        "INSERT INTO locations (id, name, description) VALUES (?, ?, ?)",
                        (location_id, name, "")
                    )
                except Exception as e:
                    logger.error(f"Error processing location: {e}")

            conn.commit()
            logger.info(f"Imported {len(locations_df)} locations")
        else:
            logger.warning("Locations sheet not found")

        # Track serial numbers to avoid duplicates
        used_serials = set()
        inventory_items_processed = 0
        inventory_items_created = 0
        bcd_count = 0
        regulator_count = 0
        mask_count = 0

        # Migrate Inventory items
        if 'Inventory' in excel_data:
            logger.info("Processing Inventory sheet")
            inventory_df = excel_data['Inventory']

            for _, row in inventory_df.iterrows():
                try:
                    # Skip rows without an ID
                    if pd.isna(row['ID']):
                        continue

                    item_id = clean_int(row['ID'])
                    inventory_items_processed += 1

                    # Extract values
                    item_type_id = clean_int(row.get('Item Type Lookup'), default=None)
                    manufacturer = clean_string(row.get('Item Manufacturer', ''))
                    model = clean_string(row.get('Item Model', ''))
                    serial_number = clean_string(row.get('Item Seriel Number', ''))

                    # Make serial number unique if needed
                    original_serial = serial_number
                    counter = 1
                    while serial_number in used_serials and serial_number:
                        serial_number = f"{original_serial}-{counter}"
                        counter += 1

                    if serial_number:
                        used_serials.add(serial_number)

                    # Handle dates
                    intake_date = clean_date(row.get('Intake Date'))
                    disposal_date = clean_date(row.get('Disposal Date'))

                    intake_date_str = intake_date.isoformat() if intake_date else None
                    disposal_date_str = disposal_date.isoformat() if disposal_date else None

                    location_id = clean_int(row.get('Location'), default=1)
                    pm_required = 1 if clean_bool(row.get('PM Required')) else 0
                    condition_code = clean_int(row.get('Condition Code', 1))

                    # Skip if no item type
                    if not item_type_id:
                        logger.warning(f"Skipping inventory item {item_id}: Missing type_id")
                        continue

                    # Insert into inventory_items
                    cursor.execute('''
                    INSERT INTO inventory_items 
                    (id, item_type_id, manufacturer, model, serial_number, 
                     intake_date, disposal_date, location_id, pm_required, condition_code)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        item_id, item_type_id, manufacturer, model, serial_number,
                        intake_date_str, disposal_date_str, location_id, pm_required, condition_code
                    ))

                    inventory_items_created += 1

                    # For BCDs (type ID 1)
                    if item_type_id == 1:
                        next_maint_date = None
                        if intake_date:
                            next_maint_date = intake_date.replace(year=intake_date.year + 1).isoformat()

                        cursor.execute('''
                        INSERT INTO bcds (inventory_item_id, last_maintenance, next_maintenance)
                        VALUES (?, ?, ?)
                        ''', (
                            item_id, intake_date_str, next_maint_date
                        ))
                        bcd_count += 1

                    # For Regulators (type ID 2)
                    elif item_type_id == 2:
                        cursor.execute('''
                        INSERT INTO regulators (inventory_item_id, has_computer, last_service_date)
                        VALUES (?, ?, ?)
                        ''', (
                            item_id, 0, intake_date_str
                        ))
                        regulator_count += 1

                    # For Masks (type ID 4)
                    elif item_type_id == 4:
                        size = clean_string(row.get('Size', ''))
                        cursor.execute('''
                        INSERT INTO masks (inventory_item_id, has_comms, size)
                        VALUES (?, ?, ?)
                        ''', (
                            item_id, 0, size
                        ))
                        mask_count += 1
                except Exception as e:
                    logger.error(f"Error processing inventory item {item_id}: {e}")
                    continue

            conn.commit()
            logger.info(f"Processed {inventory_items_processed} inventory items, created {inventory_items_created}")
            logger.info(f"Created {bcd_count} BCDs, {regulator_count} regulators, {mask_count} masks")
        else:
            logger.warning("Inventory sheet not found")

        # Process Tanks separately
        tanks_processed = 0
        tanks_created = 0

        if 'Tank_Inventory' in excel_data:
            logger.info("Processing Tank_Inventory sheet")
            tanks_df = excel_data['Tank_Inventory']

            # Get last inventory item ID
            cursor.execute("SELECT MAX(id) FROM inventory_items")
            result = cursor.fetchone()
            next_inventory_id = (result[0] or 0) + 1

            # Process each tank row
            for _, row in tanks_df.iterrows():
                try:
                    # Get tank ID and number
                    tank_id = clean_string(row.get('Tank ID', ''))
                    tank_number = clean_string(row.get('Tank Number', ''))

                    if not tank_id and not tank_number:
                        logger.warning("Skipping tank record with no ID or number")
                        continue

                    tanks_processed += 1

                    # Extract values
                    manufacturer = clean_string(row.get('Manufacturer', ''))

                    # Handle dates
                    hydro_date = clean_date(row.get('Hydro Date'))
                    vip_date = clean_date(row.get('VIP Date'))

                    hydro_date_str = hydro_date.isoformat() if hydro_date else None
                    vip_date_str = vip_date.isoformat() if vip_date else None

                    tank_material = clean_string(row.get('Tank Material', ''))
                    working_pressure = clean_int(row.get('Working Pressure', 3000))
                    gas_type = clean_string(row.get('Gas Type', 'Air'))

                    # Extract numeric part of tank ID if possible, otherwise use the original
                    extracted_id = extract_tank_number(tank_id)

                    # Create inventory item with the original tank ID as the serial number
                    unique_serial = tank_id
                    original_serial = unique_serial
                    counter = 1

                    # Make sure serial is unique
                    while unique_serial in used_serials:
                        unique_serial = f"{original_serial}-{counter}"
                        counter += 1

                    used_serials.add(unique_serial)

                    # Create inventory item for this tank
                    cursor.execute('''
                    INSERT INTO inventory_items 
                    (id, item_type_id, manufacturer, model, serial_number, 
                     intake_date, location_id, pm_required, condition_code)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        next_inventory_id,
                        7,  # Tank type ID
                        manufacturer,
                        tank_number,
                        unique_serial,  # Use original tank ID as serial
                        datetime.now().isoformat(),
                        1,  # Default location
                        1,  # PM required
                        2  # Default condition
                    ))

                    # Create tank record - use tank_number for the tank_number field
                    cursor.execute('''
                    INSERT INTO tanks 
                    (inventory_item_id, tank_number, hydro_date, vip_date, 
                     tank_material, working_pressure, gas_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        next_inventory_id,
                        tank_number,  # Use provided tank number
                        hydro_date_str,
                        vip_date_str,
                        tank_material,
                        working_pressure,
                        gas_type
                    ))

                    tanks_created += 1
                    next_inventory_id += 1

                    # Commit every 10 tanks
                    if tanks_created % 10 == 0:
                        conn.commit()
                        logger.info(f"Committed {tanks_created} tanks so far")

                except Exception as e:
                    logger.error(f"Error processing tank: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    continue

            conn.commit()
            logger.info(f"Processed {tanks_processed} tanks, created {tanks_created} new tank records")
        else:
            logger.warning("Tank_Inventory sheet not found")

        # Count records in each table
        counts = {}
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = cursor.fetchone()[0]

        # Summarize
        summary = f"""
Migration completed successfully:
- {counts['item_types']} item types
- {counts['locations']} locations
- {counts['inventory_items']} inventory items
- {counts['tanks']} tanks
- {counts['bcds']} BCDs
- {counts['regulators']} regulators
- {counts['masks']} masks
"""
        logger.info(summary)
        print(summary)

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed with error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        print(f"Migration failed: {e}")
        print("Check migration.log for details")
    finally:
        conn.close()


if __name__ == "__main__":
    import sys

    # Get the filename from arguments or use default
    filename = 'Inventory.xlsx'  # Default filename with correct case
    for arg in sys.argv[1:]:
        if not arg.startswith("--"):
            filename = arg
            break

    print(f"Starting migration with file: {filename}")
    migrate_data(filename)