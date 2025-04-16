from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_migrate import Migrate
from datetime import datetime, timedelta
import os
import calendar
from sqlalchemy import extract, and_, or_, func
from models import db, ItemType, Location, InventoryItem, Tank, BCD, Regulator, Mask, MaintenanceRecord, CheckoutRecord
import sys
import webbrowser

def create_app(test_config=None):
    # Create and configure the app
    app = Flask(__name__, instance_relative_config=True)

    @app.template_filter('nl2br')
    def nl2br_filter(s):
        """Convert newlines to HTML line breaks"""
        if s is None:
            return ""
        s = str(s)
        return s.replace('\n', '<br>\n')

    if test_config and 'INSTANCE_PATH' in test_config:
        instance_path = test_config['INSTANCE_PATH']
    elif getattr(sys, 'frozen', False):
        # Running from PyInstaller bundle
        instance_path = os.path.join(os.path.dirname(sys.executable), 'instance')
    else:
        # Normal Python run
        instance_path = app.instance_path
    # Ensure the instance folder exists
    try:
        os.makedirs(app.instance_path, exist_ok=True)
        # Only show path in debug mode
        if app.debug:
            print(f"Using instance path: {app.instance_path}")
    except OSError:
        pass

    # Configuration
    app.config.from_mapping(
        SECRET_KEY='inventory_management_secret_key',
        SQLALCHEMY_DATABASE_URI=f'sqlite:///{os.path.join(app.instance_path, "inventory.db")}',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    # Initialize Flask extensions
    db.init_app(app)
    migrate = Migrate(app, db)

    # Create database tables if they don't exist
    with app.app_context():
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        existing_tables = inspector.get_table_names()

        if not existing_tables:
            if app.debug:
                print("No tables found. Creating database tables...")
            try:
                db.create_all()

                # Seed initial data
                if app.debug:
                    print("Seeding initial data...")

                # Create item types
                item_types = [
                    ItemType(id=1, name="BCD", description="Buoyancy Control Device"),
                    ItemType(id=2, name="Regulator", description="Scuba Regulator"),
                    ItemType(id=3, name="Wetsuit", description="Diving Wetsuit"),
                    ItemType(id=4, name="Mask", description="Diving Mask"),
                    ItemType(id=5, name="Fins", description="Diving Fins"),
                    ItemType(id=6, name="Gloves", description="Diving Gloves"),
                    ItemType(id=7, name="Tank", description="Scuba Tank"),
                    ItemType(id=8, name="Dive Computer", description="Dive Computer"),
                    ItemType(id=9, name="Weight Belt", description="Weight Belt"),
                    ItemType(id=10, name="Other", description="Other Equipment")
                ]

                for item_type in item_types:
                    db.session.add(item_type)

                # Create locations
                locations = [
                    Location(id=1, name="Tech Locker", description="Technical Equipment Storage"),
                    Location(id=2, name="Gear Locker", description="General Gear Storage"),
                    Location(id=3, name="Maintenance Locker", description="Items in Maintenance")
                ]

                for location in locations:
                    db.session.add(location)

                # Commit the changes
                db.session.commit()
                if app.debug:
                    print("Database initialization complete!")
            except Exception as e:
                if app.debug:
                    print(f"Error creating database tables: {e}")
        else:
            if app.debug:
                print(f"Using existing database tables: {existing_tables}")

    @app.context_processor
    def inject_now():
        """Add current datetime to all templates"""
        return {'now': datetime.now()}

    @app.context_processor
    def inject_global_data():
        """Add global data to all templates, like BCDs for maintenance modal"""
        global_data = {}
        try:
            # Get all BCDs with necessary details for the maintenance modal
            bcds = BCD.query.all()
            global_bcds = []

            for bcd in bcds:
                item = InventoryItem.query.get(bcd.inventory_item_id)
                if not item:
                    continue

                bcd_data = {
                    'id': bcd.id,
                    'manufacturer': item.manufacturer,
                    'model': item.model,
                    'serial_number': item.serial_number,
                    'is_maintenance_due': bcd.is_maintenance_due()
                }
                global_bcds.append(bcd_data)

            global_data['global_bcds'] = global_bcds

            # Get all Tanks with necessary details for the maintenance modal
            tanks = Tank.query.all()
            global_tanks = []

            for tank in tanks:
                item = InventoryItem.query.get(tank.inventory_item_id)
                if not item:
                    continue

                tank_data = {
                    'id': tank.id,
                    'manufacturer': item.manufacturer,
                    'model': item.model,
                    'serial_number': item.serial_number,
                    'maintenance_due': tank.maintenance_due()
                }
                global_tanks.append(tank_data)

            global_data['global_tanks'] = global_tanks

            # Get all Regulators with necessary details for the maintenance modal
            regulators = Regulator.query.all()
            global_regulators = []

            for regulator in regulators:
                item = InventoryItem.query.get(regulator.inventory_item_id)
                if not item:
                    continue

                regulator_data = {
                    'id': regulator.id,
                    'manufacturer': item.manufacturer,
                    'model': item.model,
                    'serial_number': item.serial_number
                }
                global_regulators.append(regulator_data)

            global_data['global_regulators'] = global_regulators

            # Get other items (not BCDs, Tanks, or Regulators)
            other_items = InventoryItem.query.filter(
                ~InventoryItem.id.in_(
                    db.session.query(BCD.inventory_item_id).filter(BCD.inventory_item_id.isnot(None))
                ),
                ~InventoryItem.id.in_(
                    db.session.query(Tank.inventory_item_id).filter(Tank.inventory_item_id.isnot(None))
                ),
                ~InventoryItem.id.in_(
                    db.session.query(Regulator.inventory_item_id).filter(Regulator.inventory_item_id.isnot(None))
                )
            ).all()

            global_other_items = []
            for item in other_items:
                if item.item_type:
                    type_name = item.item_type.name
                else:
                    type_name = "Unknown"

                other_item_data = {
                    'id': item.id,
                    'manufacturer': item.manufacturer,
                    'model': item.model,
                    'serial_number': item.serial_number,
                    'type_name': type_name
                }
                global_other_items.append(other_item_data)

            global_data['global_other_items'] = global_other_items

        except Exception as e:
            # In case of error, provide empty lists
            global_data['global_bcds'] = []
            global_data['global_tanks'] = []
            global_data['global_regulators'] = []
            global_data['global_other_items'] = []
            print(f"Error in global data context processor: {str(e)}")

        return global_data
    # Routes

    @app.route('/')
    def home():
        """Dashboard homepage"""
        try:
            # Count total items
            total_items = InventoryItem.query.count()

            # Count BCDs due for maintenance
            bcds_due = BCD.query.filter(BCD.next_maintenance <= datetime.now()).count()

            # Count tanks due for maintenance
            tanks_due = 0
            tanks = Tank.query.all()
            for tank in tanks:
                if tank.maintenance_due():
                    tanks_due += 1

            # Count regulators due for maintenance
            regulators_due = 0
            regulators = Regulator.query.all()
            for regulator in regulators:
                if regulator.last_service_date:
                    next_service = regulator.last_service_date.replace(year=regulator.last_service_date.year + 1)
                    if next_service <= datetime.now():
                        regulators_due += 1

            # Count items checked out
            items_checked_out = InventoryItem.query.filter_by(currently_checked_out=True).count()

            # Get upcoming maintenance (next 30 days)
            upcoming_maintenance = []

            # Check upcoming BCD maintenance
            thirty_days_from_now = datetime.now() + timedelta(days=30)
            bcds = BCD.query.filter(
                BCD.next_maintenance > datetime.now(),
                BCD.next_maintenance <= thirty_days_from_now
            ).all()

            for bcd in bcds:
                item = InventoryItem.query.get(bcd.inventory_item_id)
                if item:
                    upcoming_maintenance.append({
                        'id': bcd.id,
                        'type_id': 1,  # BCD type_id
                        'manufacturer': item.manufacturer,
                        'model': item.model,
                        'type_name': 'BCD',
                        'maintenance_type': 'Annual Service',
                        'due_date': bcd.next_maintenance.strftime('%m/%d/%Y')
                    })

            # Check upcoming Tank maintenance (VIP and Hydro tests)
            for tank in tanks:
                # Check for upcoming VIP
                if tank.vip_date:
                    next_vip = tank.get_next_vip_date()
                    if next_vip > datetime.now() and next_vip <= thirty_days_from_now:
                        item = InventoryItem.query.get(tank.inventory_item_id)
                        if item:
                            upcoming_maintenance.append({
                                'id': tank.id,
                                'type_id': 7,  # Tank type_id
                                'manufacturer': item.manufacturer,
                                'model': item.model,
                                'type_name': 'Tank',
                                'maintenance_type': 'VIP Inspection',
                                'due_date': next_vip.strftime('%m/%d/%Y')
                            })

                # Check for upcoming Hydro test
                if tank.hydro_date:
                    next_hydro = tank.get_next_hydro_date()
                    if next_hydro > datetime.now() and next_hydro <= thirty_days_from_now:
                        item = InventoryItem.query.get(tank.inventory_item_id)
                        if item:
                            upcoming_maintenance.append({
                                'id': tank.id,
                                'type_id': 7,  # Tank type_id
                                'manufacturer': item.manufacturer,
                                'model': item.model,
                                'type_name': 'Tank',
                                'maintenance_type': 'Hydro Test',
                                'due_date': next_hydro.strftime('%m/%d/%Y')
                            })

            # Check upcoming Regulator maintenance
            for regulator in regulators:
                if regulator.last_service_date:
                    next_service = regulator.last_service_date.replace(year=regulator.last_service_date.year + 1)
                    if next_service > datetime.now() and next_service <= thirty_days_from_now:
                        item = InventoryItem.query.get(regulator.inventory_item_id)
                        if item:
                            upcoming_maintenance.append({
                                'id': regulator.id,
                                'type_id': 2,  # Regulator type_id
                                'manufacturer': item.manufacturer,
                                'model': item.model,
                                'type_name': 'Regulator',
                                'maintenance_type': 'Annual Service',
                                'due_date': next_service.strftime('%m/%d/%Y')
                            })

            return render_template('home.html',
                                   total_items=total_items,
                                   bcd_maintenance_due=bcds_due,
                                   tank_maintenance_due=tanks_due,
                                   regulator_maintenance_due=regulators_due,
                                   total_maintenance_due=bcds_due + tanks_due + regulators_due,
                                   items_checked_out=items_checked_out,
                                   upcoming_maintenance=upcoming_maintenance)
        except Exception as e:
            import traceback
            trace = traceback.format_exc()
            print(f"Detailed error in home route: {trace}")
            flash(f"Error: {str(e)}", "error")
            return render_template('home.html', total_items=0, bcd_maintenance_due=0,
                                   tank_maintenance_due=0, regulator_maintenance_due=0,
                                   total_maintenance_due=0, items_checked_out=0,
                                   upcoming_maintenance=[])

    @app.route('/inventory')
    def inventory_list():
        """Display all items in inventory"""
        try:
            # Get all item types for grouping
            item_types = ItemType.query.all()

            # Create a dictionary to hold items by type
            items_by_type = {}

            # For each item type, get all items
            for item_type in item_types:
                items = InventoryItem.query.filter_by(item_type_id=item_type.id).all()
                # Add location name to each item
                for item in items:
                    if item.location_info:
                        item.location_name = item.location_info.name
                    else:
                        item.location_name = "Unknown"

                # Only add to dictionary if there are items of this type
                if items:
                    items_by_type[item_type.name] = items

            # Get total count
            total_items = InventoryItem.query.count()

            return render_template('inventory_list.html',
                                   items_by_type=items_by_type,
                                   total_items=total_items)
        except Exception as e:
            import traceback
            trace = traceback.format_exc()
            print(f"Error in inventory list: {trace}")
            flash(f"Error loading inventory: {str(e)}", "error")
            return render_template('inventory_list.html', items_by_type={}, total_items=0)


    @app.route('/tanks')
    def tanks_list():
        """Display all tanks with maintenance information"""
        try:
            # Get all tanks
            all_tanks = Tank.query.all()
            tanks = []

            # Prepare tanks by adding maintenance information
            for tank in all_tanks:
                # Get the inventory item associated with the tank
                item = tank.inventory_item
                if not item:
                    continue

                # Create a dictionary with all the needed information
                tank_data = {
                    'id': tank.id,
                    'inventory_id': item.id,
                    'Tank_ID': tank.id,
                    'Tank_Number': tank.tank_number,
                    'Manufacturer': item.manufacturer,
                    'Serial_Number': item.serial_number,
                    'Hydro_Date': tank.hydro_date,
                    'VIP_Date': tank.vip_date,
                    'Tank_Material': tank.tank_material,
                    'Working_Pressure': tank.working_pressure,
                    'Gas_Type': tank.gas_type,
                    'location': item.location_id,
                    'condition_code': item.condition_code,
                    'maintenance_due': tank.maintenance_due(),
                    'next_maintenance_type': tank.next_maintenance_type(),
                    'next_maintenance_date': tank.next_maintenance_date(),
                    'currently_checked_out': item.currently_checked_out
                }

                # Format dates for display
                if tank.hydro_date:
                    tank_data['Hydro_Date_Formatted'] = tank.hydro_date.strftime('%m/%d/%Y')
                else:
                    tank_data['Hydro_Date_Formatted'] = 'Not Available'

                if tank.vip_date:
                    tank_data['VIP_Date_Formatted'] = tank.vip_date.strftime('%m/%d/%Y')
                else:
                    tank_data['VIP_Date_Formatted'] = 'Not Available'

                # Next hydro date (5 years after last)
                if tank.hydro_date:
                    next_hydro = tank.get_next_hydro_date()
                    tank_data['next_hydro_date'] = next_hydro
                    tank_data['next_hydro_date_Formatted'] = next_hydro.strftime('%m/%d/%Y')
                else:
                    tank_data['next_hydro_date'] = None
                    tank_data['next_hydro_date_Formatted'] = 'Not Available'

                # Next VIP date (1 year after last)
                if tank.vip_date:
                    next_vip = tank.get_next_vip_date()
                    tank_data['next_vip_date'] = next_vip
                    tank_data['next_vip_date_Formatted'] = next_vip.strftime('%m/%d/%Y')
                else:
                    tank_data['next_vip_date'] = None
                    tank_data['next_vip_date_Formatted'] = 'Not Available'

                # Next maintenance date and type
                next_maint_date = tank.next_maintenance_date()
                if next_maint_date:
                    tank_data['next_maintenance_date_Formatted'] = next_maint_date.strftime('%m/%d/%Y')
                else:
                    tank_data['next_maintenance_date_Formatted'] = 'Not Available'

                tanks.append(tank_data)

            # Group tanks by maintenance status
            tanks_by_status = {
                'due': [],
                'upcoming': [],
                'current': []
            }

            now = datetime.now()
            thirty_days_from_now = now + timedelta(days=30)

            for tank in tanks:
                if tank['maintenance_due']:
                    tanks_by_status['due'].append(tank)
                elif tank['next_maintenance_date'] and tank['next_maintenance_date'] <= thirty_days_from_now:
                    tanks_by_status['upcoming'].append(tank)
                else:
                    tanks_by_status['current'].append(tank)

            # Sort each group by next maintenance date
            for status in tanks_by_status:
                tanks_by_status[status] = sorted(
                    tanks_by_status[status],
                    key=lambda x: x['next_maintenance_date'] or datetime(9999, 12, 31)
                )

            # Get count of tanks due for maintenance
            maintenance_due = len(tanks_by_status['due'])

            return render_template('tanks_list.html',
                                   tanks=tanks,
                                   tanks_by_status=tanks_by_status,
                                   total_tanks=len(tanks),
                                   maintenance_due=maintenance_due)
        except Exception as e:
            import traceback
            trace = traceback.format_exc()
            print(f"Error in tanks list: {trace}")
            flash(f"Error loading tanks: {str(e)}", "error")
            return render_template('tanks_list.html', tanks=[], tanks_by_status={},
                                   total_tanks=0, maintenance_due=0)

    @app.route('/tank/<int:tank_id>')
    def tank_detail(tank_id):
        """Display detailed information for a specific tank"""
        try:
            # Get tank by ID
            tank = Tank.query.get_or_404(tank_id)
            item = tank.inventory_item

            # Create a dictionary with all tank data
            tank_data = {
                'id': tank.id,
                'inventory_id': item.id,
                'Tank_ID': tank.id,
                'Tank_Number': tank.tank_number,
                'Manufacturer': item.manufacturer,
                'Serial_Number': item.serial_number,
                'Hydro_Date': tank.hydro_date,
                'VIP_Date': tank.vip_date,
                'Tank_Material': tank.tank_material,
                'Working_Pressure': tank.working_pressure,
                'Gas_Type': tank.gas_type,
                'location': item.location_id,
                'condition_code': item.condition_code,
                'maintenance_due': tank.maintenance_due(),
                'next_maintenance_type': tank.next_maintenance_type(),
                'next_maintenance_date': tank.next_maintenance_date(),
                'currently_checked_out': item.currently_checked_out
            }

            # Format dates for display
            if tank.hydro_date:
                tank_data['Hydro_Date_Formatted'] = tank.hydro_date.strftime('%m/%d/%Y')
            else:
                tank_data['Hydro_Date_Formatted'] = 'Not Available'

            if tank.vip_date:
                tank_data['VIP_Date_Formatted'] = tank.vip_date.strftime('%m/%d/%Y')
            else:
                tank_data['VIP_Date_Formatted'] = 'Not Available'

            # Next hydro date (5 years after last)
            if tank.hydro_date:
                next_hydro = tank.get_next_hydro_date()
                tank_data['next_hydro_date'] = next_hydro
                tank_data['next_hydro_date_Formatted'] = next_hydro.strftime('%m/%d/%Y')
            else:
                tank_data['next_hydro_date'] = None
                tank_data['next_hydro_date_Formatted'] = 'Not Available'

            # Next VIP date (1 year after last)
            if tank.vip_date:
                next_vip = tank.get_next_vip_date()
                tank_data['next_vip_date'] = next_vip
                tank_data['next_vip_date_Formatted'] = next_vip.strftime('%m/%d/%Y')
            else:
                tank_data['next_vip_date'] = None
                tank_data['next_vip_date_Formatted'] = 'Not Available'

            # Next maintenance date and type
            next_maint_date = tank.next_maintenance_date()
            if next_maint_date:
                tank_data['next_maintenance_date_Formatted'] = next_maint_date.strftime('%m/%d/%Y')
            else:
                tank_data['next_maintenance_date_Formatted'] = 'Not Available'

            # Get checkout history
            checkouts = CheckoutRecord.query.filter_by(inventory_item_id=item.id).order_by(
                CheckoutRecord.checkout_date.desc()).all()

            return render_template('tank_detail.html', tank=tank_data, checkouts=checkouts)
        except Exception as e:
            import traceback
            trace = traceback.format_exc()
            print(f"Error in tank detail: {trace}")
            flash(f"Error loading tank details: {str(e)}", "error")
            return redirect(url_for('tanks_list'))

    @app.route('/checkout/<int:item_id>', methods=['GET', 'POST'])
    def checkout_item(item_id):
        """Checkout an item to a person"""
        item = InventoryItem.query.get_or_404(item_id)

        if request.method == 'POST':
            if item.currently_checked_out:
                flash("This item is already checked out.", "error")
                return redirect(url_for('inventory_list'))

            # Get form data
            person_name = request.form.get('person_name')
            notes = request.form.get('notes', '')

            # Create checkout record
            checkout = CheckoutRecord(
                inventory_item_id=item.id,
                person_name=person_name,
                checkout_date=datetime.now(),
                checkout_condition=item.condition_code,
                notes=notes
            )

            # Update item status
            item.currently_checked_out = True
            item.last_check_out_date = datetime.now()

            # Save to database
            db.session.add(checkout)
            db.session.commit()

            flash(f"Item checked out to {person_name}", "success")
            return redirect(url_for('inventory_list'))

        return render_template('checkout_form.html', item=item)

    @app.route('/checkin/<int:item_id>', methods=['GET', 'POST'])
    def checkin_item(item_id):
        """Check in an item"""
        item = InventoryItem.query.get_or_404(item_id)

        if request.method == 'POST':
            if not item.currently_checked_out:
                flash("This item is not checked out.", "error")
                return redirect(url_for('inventory_list'))

            # Get form data
            condition_code = int(request.form.get('condition_code'))
            notes = request.form.get('notes', '')

            # Find the active checkout record
            checkout = CheckoutRecord.query.filter_by(
                inventory_item_id=item.id,
                checkin_date=None
            ).order_by(CheckoutRecord.checkout_date.desc()).first()

            if checkout:
                # Update checkout record
                checkout.checkin_date = datetime.now()
                checkout.checkin_condition = condition_code
                checkout.notes = checkout.notes + "\n\nCheck-in notes: " + notes if notes else checkout.notes

            # Update item status
            item.currently_checked_out = False
            item.last_check_in_date = datetime.now()
            item.condition_code = condition_code

            # Save to database
            db.session.commit()

            flash("Item checked in successfully", "success")
            return redirect(url_for('inventory_list'))

        # Get the current checkout record for this item
        checkout = CheckoutRecord.query.filter_by(
            inventory_item_id=item.id,
            checkin_date=None
        ).order_by(CheckoutRecord.checkout_date.desc()).first()

        return render_template('checkin_form.html', item=item, checkout=checkout)

    @app.route('/item/<int:item_id>')
    def item_detail(item_id):
        """Display detailed information for a specific inventory item"""
        item = InventoryItem.query.get_or_404(item_id)

        # Get type name
        type_name = "Unknown"
        if item.item_type:
            type_name = item.item_type.name

        # Get location name
        location_name = "Unknown"
        if item.location_info:
            location_name = item.location_info.name

        # Get checkout history
        checkouts = CheckoutRecord.query.filter_by(inventory_item_id=item.id).order_by(
            CheckoutRecord.checkout_date.desc()).all()

        # Get type-specific data
        mask_data = None
        if type_name == "Mask" and item.mask:
            mask_data = item.mask

        regulator_data = None
        if type_name == "Regulator" and item.regulator:
            regulator_data = item.regulator

        bcd_data = None
        maintenance_records = []
        if type_name == "BCD" and item.bcd:
            bcd_data = item.bcd
            maintenance_records = MaintenanceRecord.query.filter_by(bcd_id=bcd_data.id).order_by(
                MaintenanceRecord.date.desc()).all()

        tank_data = None
        if type_name == "Tank" and item.tank:
            tank_data = item.tank

        return render_template('item_detail.html',
                               item=item,
                               type_name=type_name,
                               location_name=location_name,
                               checkouts=checkouts,
                               mask_data=mask_data,
                               regulator_data=regulator_data,
                               bcd_data=bcd_data,
                               tank_data=tank_data,
                               maintenance_records=maintenance_records)

    @app.route('/maintenance')
    def maintenance():
        """Display BCD maintenance information"""
        try:
            # Get all BCDs
            bcds = BCD.query.all()
            bcd_data = []

            for bcd in bcds:
                # Get the inventory item
                item = InventoryItem.query.get(bcd.inventory_item_id)
                if not item:
                    continue

                # Create a data object for the template
                data = {
                    'id': bcd.id,
                    'item_id': item.id,
                    'manufacturer': item.manufacturer,
                    'model': item.model,
                    'serial_number': item.serial_number,
                    'last_maintenance': bcd.last_maintenance,
                    'last_maintenance_formatted': bcd.last_maintenance.strftime(
                        '%m/%d/%Y') if bcd.last_maintenance else 'Not Available',
                    'next_maintenance': bcd.next_maintenance,
                    'next_maintenance_formatted': bcd.next_maintenance.strftime(
                        '%m/%d/%Y') if bcd.next_maintenance else 'Not Available',
                    'maintenance_due': bcd.is_maintenance_due(),
                    'maintenance_records_count': MaintenanceRecord.query.filter_by(bcd_id=bcd.id).count()
                }

                bcd_data.append(data)

            # Sort with maintenance due items first
            bcd_data = sorted(bcd_data,
                              key=lambda x: (not x['maintenance_due'],
                                             x['next_maintenance'] or datetime(9999, 12, 31)))

            return render_template('maintenance.html', bcds=bcd_data)

        except Exception as e:
            import traceback
            trace = traceback.format_exc()
            print(f"Error in maintenance: {trace}")
            flash(f"Error loading maintenance data: {str(e)}", "error")
            return render_template('maintenance.html', bcds=[])

    @app.route('/maintenance/<int:bcd_id>', methods=['GET', 'POST'])
    def maintenance_detail(bcd_id):
        """Show and add maintenance records for a BCD"""
        try:
            bcd = BCD.query.get_or_404(bcd_id)
            item = InventoryItem.query.get_or_404(bcd.inventory_item_id)

            if request.method == 'POST':
                # Add new maintenance record
                maintenance_date = datetime.strptime(request.form['date'], '%Y-%m-%d')
                maintenance_type = request.form['type']
                notes = request.form['notes']

                record = MaintenanceRecord(
                    bcd_id=bcd.id,
                    date=maintenance_date,
                    maintenance_type=maintenance_type,
                    notes=notes
                )

                # Update BCD's maintenance dates
                bcd.last_maintenance = maintenance_date
                bcd.next_maintenance = maintenance_date.replace(year=maintenance_date.year + 1)

                try:
                    db.session.add(record)
                    db.session.commit()
                    flash('Maintenance record added successfully!', 'success')
                except Exception as e:
                    db.session.rollback()
                    flash(f'Error adding record: {str(e)}', 'error')

                return redirect(url_for('maintenance_detail', bcd_id=bcd.id))

            # Get maintenance history
            maintenance_records = MaintenanceRecord.query.filter_by(bcd_id=bcd.id).order_by(
                MaintenanceRecord.date.desc()).all()

            return render_template('maintenance_detail.html',
                                   bcd=bcd,
                                   item=item,
                                   maintenance_records=maintenance_records,
                                   today=datetime.now().strftime('%Y-%m-%d'))

        except Exception as e:
            import traceback
            trace = traceback.format_exc()
            print(f"Error in maintenance detail: {trace}")
            flash(f"Error loading maintenance details: {str(e)}", "error")
            return redirect(url_for('maintenance'))

    @app.route('/add', methods=['GET', 'POST'])
    def add_item():
        """Add a new item to inventory"""
        if request.method == 'POST':
            try:
                # Process form data
                item_type_id = int(request.form['item_type'])
                manufacturer = request.form['manufacturer']
                model = request.form['model']
                serial_number = request.form['serial']
                intake_date = datetime.strptime(request.form['intake_date'], '%Y-%m-%d')
                location_id = int(request.form['location'])
                pm_required = 'pm_required' in request.form
                condition_code = int(request.form['condition'])

                # Create the item
                item = InventoryItem(
                    item_type_id=item_type_id,
                    manufacturer=manufacturer,
                    model=model,
                    serial_number=serial_number,
                    intake_date=intake_date,
                    location_id=location_id,
                    pm_required=pm_required,
                    condition_code=condition_code
                )

                db.session.add(item)
                db.session.flush()  # Get the ID before committing

                # Add specific data based on item type
                # For BCD (assuming type ID 1)
                if item_type_id == 1:
                    bcd = BCD(
                        inventory_item_id=item.id,
                        last_maintenance=intake_date,
                        next_maintenance=intake_date.replace(year=intake_date.year + 1)
                    )
                    db.session.add(bcd)

                # For Regulator (assuming type ID 2)
                elif item_type_id == 2:
                    has_computer = 'has_computer' in request.form
                    regulator = Regulator(
                        inventory_item_id=item.id,
                        has_computer=has_computer,
                        last_service_date=intake_date
                    )
                    db.session.add(regulator)

                # For Mask (assuming type ID 4)
                elif item_type_id == 4:
                    has_comms = 'has_comms' in request.form
                    size = request.form.get('size', '')
                    mask = Mask(
                        inventory_item_id=item.id,
                        has_comms=has_comms,
                        size=size
                    )
                    db.session.add(mask)

                # For Tank (assuming type ID 7)
                elif item_type_id == 7:
                    tank_number = request.form.get('tank_number', '')
                    hydro_date = None
                    if request.form.get('hydro_date'):
                        hydro_date = datetime.strptime(request.form['hydro_date'], '%Y-%m-%d')

                    vip_date = None
                    if request.form.get('vip_date'):
                        vip_date = datetime.strptime(request.form['vip_date'], '%Y-%m-%d')

                    tank = Tank(
                        inventory_item_id=item.id,
                        tank_number=tank_number,
                        hydro_date=hydro_date,
                        vip_date=vip_date,
                        tank_material=request.form.get('tank_material', ''),
                        working_pressure=int(request.form.get('working_pressure', 3000)),
                        gas_type=request.form.get('gas_type', 'Air')
                    )
                    db.session.add(tank)

                db.session.commit()
                flash('Equipment added successfully!', 'success')
                return redirect(url_for('add_item'))

            except Exception as e:
                db.session.rollback()
                import traceback
                trace = traceback.format_exc()
                print(f"Error adding item: {trace}")
                flash(f'Error: {str(e)}', 'error')

        # Get item types and locations for the form
        item_types = ItemType.query.all()
        locations = Location.query.all()

        return render_template('add_item.html',
                               item_types=item_types,
                               locations=locations,
                               today=datetime.now().strftime('%Y-%m-%d'))

    @app.route('/search', methods=['GET', 'POST'])
    def search():
        """Search for items by serial number, manufacturer, or model"""
        results = []
        search_term = ""

        if request.method == 'POST':
            search_term = request.form.get('search_term', '').strip()
        else:
            search_term = request.args.get('search_term', '').strip()

        if search_term:
            try:
                # Search in serial number, manufacturer, or model
                results = InventoryItem.query.filter(
                    or_(
                        InventoryItem.serial_number.ilike(f'%{search_term}%'),
                        InventoryItem.manufacturer.ilike(f'%{search_term}%'),
                        InventoryItem.model.ilike(f'%{search_term}%')
                    )
                ).all()

                # Add location and type names
                for item in results:
                    if item.location_info:
                        item.location_name = item.location_info.name
                    else:
                        item.location_name = "Unknown"

                    if item.item_type:
                        item.type_name = item.item_type.name
                    else:
                        item.type_name = "Unknown"
            except Exception as e:
                import traceback
                trace = traceback.format_exc()
                print(f"Error in search: {trace}")
                flash(f"Error performing search: {str(e)}", "error")

        return render_template('search.html',
                               results=results,
                               search_term=search_term)

    @app.route('/reports')
    def reports():
        """Show available reports"""
        current_month = datetime.now().month
        current_year = datetime.now().year

        return render_template('reports.html',
                               current_month=current_month,
                               current_year=current_year)

    @app.route('/reports/monthly/<int:year>/<int:month>')
    def monthly_report(year, month):
        """Generate monthly activity report"""
        try:
            # Get start and end dates for the month
            month_name = calendar.month_name[month]
            start_date = datetime(year, month, 1)

            # Get the last day of the month
            if month == 12:
                end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = datetime(year, month + 1, 1) - timedelta(days=1)

            end_date = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59)

            # Get all activities for the month

            # 1. Maintenance records
            maintenance_records = MaintenanceRecord.query.filter(
                MaintenanceRecord.date >= start_date,
                MaintenanceRecord.date <= end_date
            ).order_by(MaintenanceRecord.date).all()

            # Add BCD and inventory item data to each record
            for record in maintenance_records:
                record.bcd_data = record.bcd
                record.item = record.bcd.inventory_item

            # 2. Checkout records
            checkouts = CheckoutRecord.query.filter(
                CheckoutRecord.checkout_date >= start_date,
                CheckoutRecord.checkout_date <= end_date
            ).order_by(CheckoutRecord.checkout_date).all()

            # Add inventory item data to each checkout
            for checkout in checkouts:
                checkout.item = InventoryItem.query.get(checkout.inventory_item_id)
                if checkout.item and checkout.item.item_type:
                    checkout.type_name = checkout.item.item_type.name
                else:
                    checkout.type_name = "Unknown"

            # 3. Check-in records
            checkins = CheckoutRecord.query.filter(
                CheckoutRecord.checkin_date >= start_date,
                CheckoutRecord.checkin_date <= end_date
            ).order_by(CheckoutRecord.checkin_date).all()

            # Add inventory item data to each check-in
            for checkin in checkins:
                checkin.item = InventoryItem.query.get(checkin.inventory_item_id)
                if checkin.item and checkin.item.item_type:
                    checkin.type_name = checkin.item.item_type.name
                else:
                    checkin.type_name = "Unknown"

            # Count summary
            maintenance_count = len(maintenance_records)
            checkouts_count = len(checkouts)
            checkins_count = len(checkins)
            total_activities = maintenance_count + checkouts_count + checkins_count

            return render_template('monthly_report.html',
                                   year=year,
                                   month=month,
                                   month_name=month_name,
                                   start_date=start_date,
                                   end_date=end_date,
                                   maintenance_records=maintenance_records,
                                   checkouts=checkouts,
                                   checkins=checkins,
                                   maintenance_count=maintenance_count,
                                   checkouts_count=checkouts_count,
                                   checkins_count=checkins_count,
                                   total_activities=total_activities)

        except Exception as e:
            import traceback
            trace = traceback.format_exc()
            print(f"Error generating monthly report: {trace}")
            flash(f"Error generating report: {str(e)}", "error")
            return redirect(url_for('reports'))

    @app.route('/checkouts')
    def checkout_history():
        """Display all checkout records"""
        try:
            # Get all checkout records ordered by most recent first
            checkouts = CheckoutRecord.query.order_by(CheckoutRecord.checkout_date.desc()).all()

            # Add item information to each checkout
            for checkout in checkouts:
                checkout.item = InventoryItem.query.get(checkout.inventory_item_id)
                if checkout.item and checkout.item.item_type:
                    checkout.type_name = checkout.item.item_type.name
                else:
                    checkout.type_name = "Unknown"

            return render_template('checkout_history.html',
                                   checkouts=checkouts,
                                   now=datetime.now())
        except Exception as e:
            import traceback
            trace = traceback.format_exc()
            print(f"Error in checkout history: {trace}")
            flash(f"Error loading checkout history: {str(e)}", "error")
            return render_template('checkout_history.html', checkouts=[], now=datetime.now())

    @app.route('/quick-maintenance', methods=['POST'])
    def quick_maintenance():
        """Add a maintenance record from anywhere in the application"""
        try:
            # Get form data
            item_type = request.form.get('item_type')
            maintenance_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d')
            maintenance_type = request.form.get('type')
            notes = request.form.get('notes', '')
            generate_report = request.args.get('generate_report') == '1' or request.form.get('generate_report') == '1'

            # Process based on equipment type
            if item_type == 'bcd':
                bcd_id = request.form.get('bcd_id')

                # Validate BCD exists
                bcd = BCD.query.get_or_404(bcd_id)

                # Create maintenance record
                record = MaintenanceRecord(
                    bcd_id=bcd.id,
                    date=maintenance_date,
                    maintenance_type=maintenance_type,
                    notes=notes
                )

                # Update BCD maintenance dates
                bcd.last_maintenance = maintenance_date
                bcd.next_maintenance = maintenance_date.replace(year=maintenance_date.year + 1)

                # Save to database
                db.session.add(record)
                db.session.commit()

                flash('BCD maintenance record added successfully!', 'success')
                redirect_id = bcd.id

            elif item_type == 'tank':
                tank_id = request.form.get('tank_id')

                # Validate Tank exists
                tank = Tank.query.get_or_404(tank_id)

                # Create maintenance record
                record = TankMaintenanceRecord(
                    tank_id=tank.id,
                    date=maintenance_date,
                    maintenance_type=maintenance_type,
                    notes=notes
                )

                # Update Tank dates based on maintenance type
                if maintenance_type == 'Hydro Test':
                    tank.hydro_date = maintenance_date
                elif maintenance_type == 'VIP Inspection':
                    tank.vip_date = maintenance_date

                # Save to database
                db.session.add(record)
                db.session.commit()

                flash('Tank maintenance record added successfully!', 'success')
                redirect_id = tank.id

            elif item_type == 'regulator':
                regulator_id = request.form.get('regulator_id')

                # Validate Regulator exists
                regulator = Regulator.query.get_or_404(regulator_id)

                # Update regulator service date
                regulator.last_service_date = maintenance_date

                # Create generic maintenance record in inventory_maintenance_records
                record = InventoryMaintenanceRecord(
                    inventory_item_id=regulator.inventory_item_id,
                    date=maintenance_date,
                    maintenance_type=maintenance_type,
                    notes=notes
                )

                # Save to database
                db.session.add(record)
                db.session.commit()

                flash('Regulator maintenance record added successfully!', 'success')
                redirect_id = regulator.id

            else:  # Other equipment
                inventory_id = request.form.get('inventory_id')

                # Validate item exists
                item = InventoryItem.query.get_or_404(inventory_id)

                # Create generic maintenance record
                record = InventoryMaintenanceRecord(
                    inventory_item_id=item.id,
                    date=maintenance_date,
                    maintenance_type=maintenance_type,
                    notes=notes
                )

                # Save to database
                db.session.add(record)
                db.session.commit()

                flash('Maintenance record added successfully!', 'success')
                redirect_id = item.id

            # If generate report is checked, redirect to the monthly report page
            if generate_report:
                # Get the current month and year for the report
                current_month = datetime.now().month
                current_year = datetime.now().year
                return redirect(url_for('monthly_report', year=current_year, month=current_month))
            else:
                # Redirect based on item type
                if item_type == 'bcd':
                    return redirect(url_for('maintenance_detail', bcd_id=redirect_id))
                elif item_type == 'tank':
                    return redirect(url_for('tank_detail', tank_id=redirect_id))
                else:
                    return redirect(url_for('item_detail', item_id=redirect_id))

        except Exception as e:
            db.session.rollback()
            import traceback
            trace = traceback.format_exc()
            print(f"Error in quick maintenance: {trace}")
            flash(f'Error adding maintenance record: {str(e)}', 'error')
            return redirect(url_for('home'))
    @app.route('/reports/yearly/<int:year>')
    def yearly_report(year):
        """Generate yearly maintenance report"""
        try:
            # Get start and end dates for the year
            start_date = datetime(year, 1, 1)
            end_date = datetime(year, 12, 31, 23, 59, 59)

            # Get all maintenance records for the year
            maintenance_records = MaintenanceRecord.query.filter(
                MaintenanceRecord.date >= start_date,
                MaintenanceRecord.date <= end_date
            ).order_by(MaintenanceRecord.date).all()

            # Add BCD and inventory item data to each record
            for record in maintenance_records:
                record.bcd_data = record.bcd
                record.item = record.bcd.inventory_item

            # Group by month
            maintenance_by_month = {}
            for i in range(1, 13):
                maintenance_by_month[i] = []

            for record in maintenance_records:
                month = record.date.month
                maintenance_by_month[month].append(record)

            # Get maintenance due counts by month
            monthly_stats = []

            for month_num in range(1, 13):
                # Set to the last day of the month
                if month_num == 12:
                    month_end = datetime(year + 1, 1, 1) - timedelta(days=1)
                else:
                    month_end = datetime(year, month_num + 1, 1) - timedelta(days=1)

                # Calculate maintenance stats as of the end of the month
                bcd_maintenance_due = 0
                tank_maintenance_due = 0

                # For BCDs, check if next_maintenance was due
                bcds = BCD.query.all()
                for bcd in bcds:
                    if bcd.next_maintenance and bcd.next_maintenance <= month_end:
                        bcd_maintenance_due += 1

                # For tanks, check if hydro or VIP was due
                tanks = Tank.query.all()
                for tank in tanks:
                    # Check hydro
                    if tank.hydro_date:
                        next_hydro = tank.hydro_date.replace(year=tank.hydro_date.year + 5)
                        if next_hydro <= month_end:
                            tank_maintenance_due += 1
                            continue

                    # Check VIP
                    if tank.vip_date:
                        next_vip = tank.vip_date.replace(year=tank.vip_date.year + 1)
                        if next_vip <= month_end:
                            tank_maintenance_due += 1

                # Add to stats
                monthly_stats.append({
                    'month': month_num,
                    'month_name': calendar.month_name[month_num],
                    'maintenance_count': len(maintenance_by_month[month_num]),
                    'bcd_maintenance_due': bcd_maintenance_due,
                    'tank_maintenance_due': tank_maintenance_due,
                    'total_maintenance_due': bcd_maintenance_due + tank_maintenance_due
                })

            # Calculate yearly summary
            total_maintenance = len(maintenance_records)
            maintenance_by_type = {}

            for record in maintenance_records:
                maint_type = record.maintenance_type
                if maint_type not in maintenance_by_type:
                    maintenance_by_type[maint_type] = 0
                maintenance_by_type[maint_type] += 1

            return render_template('yearly_report.html',
                                   year=year,
                                   maintenance_records=maintenance_records,
                                   maintenance_by_month=maintenance_by_month,
                                   monthly_stats=monthly_stats,
                                   total_maintenance=total_maintenance,
                                   maintenance_by_type=maintenance_by_type)

        except Exception as e:
            import traceback
            trace = traceback.format_exc()
            print(f"Error generating yearly report: {trace}")
            flash(f"Error generating report: {str(e)}", "error")
            return redirect(url_for('reports'))

    # Add CLI commands for database management
    @app.cli.command("init-db")
    def init_db_command():
        """Clear existing data and create new tables."""
        db.drop_all()
        db.create_all()
        print("Initialized the database.")


    @app.route('/debug')
    def debug_database():
        """Debug route to check database content"""
        debug_info = {}

        try:
            # Get item types
            types = ItemType.query.all()
            debug_info['types_status'] = 200
            debug_info['types_count'] = len(types)
            debug_info['types_data'] = [{'ID': t.id, 'Item Type': t.name} for t in types]
        except Exception as e:
            debug_info['types_status'] = 500
            debug_info['types_error'] = str(e)

        try:
            # Get locations
            locations = Location.query.all()
            debug_info['locations_status'] = 200
            debug_info['locations_count'] = len(locations)
            debug_info['locations_data'] = [{'ID': l.id, 'Location': l.name} for l in locations]
        except Exception as e:
            debug_info['locations_status'] = 500
            debug_info['locations_error'] = str(e)

        try:
            # Get items
            items = InventoryItem.query.all()
            debug_info['items_status'] = 200
            debug_info['items_count'] = len(items)
            if items:
                debug_info['items_sample'] = [{
                    'id': i.id,
                    'type_id': i.item_type_id,
                    'manufacturer': i.manufacturer,
                    'model': i.model,
                    'serial': i.serial_number,
                    'location_id': i.location_id,
                    'condition': i.condition_code
                } for i in items[:5]]  # Just show first 5 for sample
        except Exception as e:
            debug_info['items_status'] = 500
            debug_info['items_error'] = str(e)

        try:
            # Get maintenance due count
            bcds = BCD.query.filter(BCD.next_maintenance <= datetime.now()).count()
            debug_info['maintenance_status'] = 200
            debug_info['maintenance_count'] = bcds
        except Exception as e:
            debug_info['maintenance_status'] = 500
            debug_info['maintenance_error'] = str(e)

        # Get BCD count and sample
        try:
            bcds = BCD.query.all()
            debug_info['bcds_count'] = len(bcds)
            if bcds:
                debug_info['bcds_sample'] = [{
                    'id': b.id,
                    'inventory_item_id': b.inventory_item_id,
                    'last_maintenance': str(b.last_maintenance) if b.last_maintenance else None,
                    'next_maintenance': str(b.next_maintenance) if b.next_maintenance else None
                } for b in bcds[:3]]  # Just show first 3 for sample
        except Exception as e:
            debug_info['bcds_error'] = str(e)

        return render_template('debug.html', debug_info=debug_info)

    @app.cli.command("seed-db")
    def seed_db_command():
        """Seed the database with initial data."""
        # Create item types
        item_types = [
            ItemType(id=1, name="BCD", description="Buoyancy Control Device"),
            ItemType(id=2, name="Regulator", description="Scuba Regulator"),
            ItemType(id=3, name="Wetsuit", description="Diving Wetsuit"),
            ItemType(id=4, name="Mask", description="Diving Mask"),
            ItemType(id=5, name="Fins", description="Diving Fins"),
            ItemType(id=6, name="Gloves", description="Diving Gloves"),
            ItemType(id=7, name="Tank", description="Scuba Tank"),
            ItemType(id=8, name="Dive Computer", description="Dive Computer"),
            ItemType(id=9, name="Weight Belt", description="Weight Belt"),
            ItemType(id=10, name="Other", description="Other Equipment")
        ]

        for item_type in item_types:
            db.session.add(item_type)

        # Create locations
        locations = [
            Location(id=1, name="Tech Locker", description="Technical Equipment Storage"),
            Location(id=2, name="Gear Locker", description="General Gear Storage"),
            Location(id=3, name="Maintenance Locker", description="Items in Maintenance")
        ]

        for location in locations:
            db.session.add(location)

        db.session.commit()
        print("Database seeded with initial data.")

    @app.cli.command("migrate-excel")
    def migrate_excel_command():
        """Migrate data from Excel file to database."""
        from migration import migrate_data
        migrate_data('Inventory.xlsx')
        print("Data migration completed.")

    return app


# Create the application instance
if __name__ == '__main__':
    import webbrowser
    import threading
    import time
    import logging
    import sys

    # Try to import and show splash screen
    try:
        from splash import show_splash

        # Show splash screen in a separate thread
        splash_thread = threading.Thread(target=show_splash)
        splash_thread.daemon = True  # Make thread exit when main program exits
        splash_thread.start()
    except ImportError:
        print("Starting Dive Equipment Inventory Management System...")

    # Suppress Flask development server logs
    cli = sys.modules['flask.cli']
    cli.show_server_banner = lambda *x: None  # Suppress banner

    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

    # Create and configure the app
    app = create_app()


    # Function to open browser after a short delay
    def open_browser():
        time.sleep(2.5)  # Give the server (and splash screen) time to start
        url = "http://localhost:8000"
        webbrowser.open(url)


    # Start the browser opening thread
    threading.Thread(target=open_browser).start()

    # Run the Flask app with minimal output
    app.run(debug=False, port=8000, host='localhost', use_reloader=False)
