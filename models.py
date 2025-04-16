from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


# Item Type table (replacing Item_Type sheet)
class ItemType(db.Model):
    __tablename__ = 'item_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255))
    items = db.relationship('InventoryItem', backref='item_type', lazy=True)


# Location table (replacing Locations sheet)
class Location(db.Model):
    __tablename__ = 'locations'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255))
    items = db.relationship('InventoryItem', backref='location_info', lazy=True)


# Main Inventory Items
class InventoryItem(db.Model):
    __tablename__ = 'inventory_items'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    item_type_id = db.Column(db.Integer, db.ForeignKey('item_types.id'), nullable=False)
    manufacturer = db.Column(db.String(100))
    model = db.Column(db.String(100))
    serial_number = db.Column(db.String(100), unique=True)
    intake_date = db.Column(db.DateTime, default=datetime.now)
    disposal_date = db.Column(db.DateTime)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'))
    pm_required = db.Column(db.Boolean, default=False)
    condition_code = db.Column(db.Integer, default=1)  # 1=New, 2=Good, 3=Fair, 4=Poor, 5=Unusable

    # New fields
    currently_checked_out = db.Column(db.Boolean, default=False)
    last_check_in_date = db.Column(db.DateTime)
    last_check_out_date = db.Column(db.DateTime)

    # Relationships
    tank = db.relationship('Tank', backref='inventory_item', uselist=False, cascade="all, delete-orphan")
    bcd = db.relationship('BCD', backref='inventory_item', uselist=False, cascade="all, delete-orphan")
    regulator = db.relationship('Regulator', backref='inventory_item', uselist=False, cascade="all, delete-orphan")
    mask = db.relationship('Mask', backref='inventory_item', uselist=False, cascade="all, delete-orphan")
    checkouts = db.relationship('CheckoutRecord', backref='item', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Item {self.id}: {self.manufacturer} {self.model}>"


# Tank specific data (replacing Tank_Inventory sheet)
class Tank(db.Model):
    __tablename__ = 'tanks'
    id = db.Column(db.Integer, primary_key=True)
    inventory_item_id = db.Column(db.Integer, db.ForeignKey('inventory_items.id'), unique=True)
    tank_number = db.Column(db.String(50))
    hydro_date = db.Column(db.DateTime)
    vip_date = db.Column(db.DateTime)
    tank_material = db.Column(db.String(50))
    working_pressure = db.Column(db.Integer)
    gas_type = db.Column(db.String(50))
    maintenance_records = db.relationship('TankMaintenanceRecord', backref='tank', lazy=True)

    def __repr__(self):
        return f"<Tank {self.id}>"

    def is_hydro_due(self):
        if not self.hydro_date:
            return False
        # Hydro test every 5 years
        next_hydro = self.hydro_date.replace(year=self.hydro_date.year + 5)
        return next_hydro <= datetime.now()

    def is_vip_due(self):
        if not self.vip_date:
            return False
        # VIP every year
        next_vip = self.vip_date.replace(year=self.vip_date.year + 1)
        return next_vip <= datetime.now()

    def get_next_hydro_date(self):
        if not self.hydro_date:
            return None
        return self.hydro_date.replace(year=self.hydro_date.year + 5)

    def get_next_vip_date(self):
        if not self.vip_date:
            return None
        return self.vip_date.replace(year=self.vip_date.year + 1)

    def maintenance_due(self):
        return self.is_hydro_due() or self.is_vip_due()

    def next_maintenance_date(self):
        next_hydro = self.get_next_hydro_date()
        next_vip = self.get_next_vip_date()

        if next_hydro and next_vip:
            return min(next_hydro, next_vip)
        elif next_hydro:
            return next_hydro
        elif next_vip:
            return next_vip
        return None

    def next_maintenance_type(self):
        if not self.maintenance_due():
            return None

        next_hydro = self.get_next_hydro_date()
        next_vip = self.get_next_vip_date()

        if next_hydro and next_vip:
            if next_hydro <= next_vip:
                return "Hydro Test"
            else:
                return "VIP Inspection"
        elif self.is_hydro_due():
            return "Hydro Test"
        elif self.is_vip_due():
            return "VIP Inspection"
        return None

class TankMaintenanceRecord(db.Model):
    __tablename__ = 'tank_maintenance_records'
    id = db.Column(db.Integer, primary_key=True)
    tank_id = db.Column(db.Integer, db.ForeignKey('tanks.id'))
    date = db.Column(db.DateTime, default=datetime.now)
    maintenance_type = db.Column(db.String(100))  # Hydro Test or VIP Inspection
    notes = db.Column(db.Text)

    def __repr__(self):
        return f"<Tank Maintenance Record {self.id}>"
# BCD maintenance data
class BCD(db.Model):
    __tablename__ = 'bcds'
    id = db.Column(db.Integer, primary_key=True)
    inventory_item_id = db.Column(db.Integer, db.ForeignKey('inventory_items.id'), unique=True)
    last_maintenance = db.Column(db.DateTime)
    next_maintenance = db.Column(db.DateTime)

    maintenance_records = db.relationship('MaintenanceRecord', backref='bcd', lazy=True)

    def __repr__(self):
        return f"<BCD {self.id}>"

    def is_maintenance_due(self):
        if not self.next_maintenance:
            return False
        return self.next_maintenance <= datetime.now()


# Add regulator-specific data
class Regulator(db.Model):
    __tablename__ = 'regulators'
    id = db.Column(db.Integer, primary_key=True)
    inventory_item_id = db.Column(db.Integer, db.ForeignKey('inventory_items.id'), unique=True)
    has_computer = db.Column(db.Boolean, default=False)  # New field for working computer
    last_service_date = db.Column(db.DateTime)

    def is_maintenance_due(self):
        """Check if regulator maintenance is due"""
        if not self.last_service_date:
            return False
        # Regulator service every year
        next_service = self.last_service_date.replace(year=self.last_service_date.year + 1)
        return next_service <= datetime.now()

    def get_next_service_date(self):
        """Get the next service date for the regulator"""
        if not self.last_service_date:
            return None
        return self.last_service_date.replace(year=self.last_service_date.year + 1)
    def __repr__(self):
        return f"<Regulator {self.id}>"


# Add mask-specific data
class Mask(db.Model):
    __tablename__ = 'masks'
    id = db.Column(db.Integer, primary_key=True)
    inventory_item_id = db.Column(db.Integer, db.ForeignKey('inventory_items.id'), unique=True)
    has_comms = db.Column(db.Boolean, default=False)  # New field for communication device
    size = db.Column(db.String(20))

    def __repr__(self):
        return f"<Mask {self.id}>"


# Maintenance Records for BCDs and other equipment
class MaintenanceRecord(db.Model):
    __tablename__ = 'maintenance_records'
    id = db.Column(db.Integer, primary_key=True)
    bcd_id = db.Column(db.Integer, db.ForeignKey('bcds.id'))
    date = db.Column(db.DateTime, default=datetime.now)
    maintenance_type = db.Column(db.String(100))
    notes = db.Column(db.Text)

    def __repr__(self):
        return f"<Maintenance Record {self.id}>"

class InventoryMaintenanceRecord(db.Model):
    __tablename__ = 'inventory_maintenance_records'
    id = db.Column(db.Integer, primary_key=True)
    inventory_item_id = db.Column(db.Integer, db.ForeignKey('inventory_items.id'))
    date = db.Column(db.DateTime, default=datetime.now)
    maintenance_type = db.Column(db.String(100))
    notes = db.Column(db.Text)

    inventory_item = db.relationship('InventoryItem', backref='maintenance_records')

    def __repr__(self):
        return f"<Inventory Maintenance Record {self.id}>"
# New table for tracking checkouts
class CheckoutRecord(db.Model):
    __tablename__ = 'checkout_records'
    id = db.Column(db.Integer, primary_key=True)
    inventory_item_id = db.Column(db.Integer, db.ForeignKey('inventory_items.id'))
    person_name = db.Column(db.String(100), nullable=False)
    checkout_date = db.Column(db.DateTime, default=datetime.now)
    checkin_date = db.Column(db.DateTime)
    checkout_condition = db.Column(db.Integer)  # Condition at checkout
    checkin_condition = db.Column(db.Integer)  # Condition at check-in
    notes = db.Column(db.Text)

    def __repr__(self):
        return f"<Checkout Record {self.id}>"