"""
Database module for Master Scheduler application.
Handles all database operations and connections.
"""

import sqlite3
import json
import os
import pandas as pd
from datetime import datetime

# Database file path
DB_PATH = "master_scheduler.db"

# ---- Database Connection ----

def get_db_connection():
    """Create a database connection and return the connection object"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # This enables column access by name
    return conn


def init_db():
    """Initialize the database with tables if they don't exist"""
    # Check if database file exists
    db_exists = os.path.exists(DB_PATH)

    conn = get_db_connection()
    cursor = conn.cursor()

    # Create employees table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        position TEXT NOT NULL,
        pay_type TEXT NOT NULL,
        pay_rate REAL NOT NULL,
        weekly_hours INTEGER,
        active BOOLEAN DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Create schedules table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER NOT NULL,
        date DATE NOT NULL,
        start_time TIME,
        end_time TIME,
        hours REAL,
        cost REAL,
        overtime BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (employee_id) REFERENCES employees (id)
    )
    ''')

    # Create labor_costs table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS labor_costs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date DATE NOT NULL,
        total_hours REAL NOT NULL,
        regular_hours REAL NOT NULL,
        overtime_hours REAL NOT NULL,
        total_cost REAL NOT NULL,
        labor_goal_percentage REAL,
        required_sales REAL,
        actual_sales REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Create restaurant_settings table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS restaurant_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        labor_goal_percentage REAL DEFAULT 25.0,
        closed_days TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # If this is a new database, insert default settings
    if not db_exists:
        cursor.execute('''
        INSERT INTO restaurant_settings (name, labor_goal_percentage, closed_days)
        VALUES (?, ?, ?)
        ''', ('My Restaurant', 25.0, json.dumps([])))

        # Insert sample employees for testing
        sample_employees = [
            ('John Smith', 'Manager', 'Salary', 1000.00, 40),
            ('Jane Doe', 'Chef', 'Hourly', 22.50, 40),
            ('Mike Johnson', 'Server', 'Hourly', 15.00, 30),
            ('Sarah Williams', 'Bartender', 'Hourly', 18.00, 35),
            ('Robert Davis', 'Cook', 'Hourly', 20.00, 40)
        ]

        cursor.executemany('''
        INSERT INTO employees (name, position, pay_type, pay_rate, weekly_hours)
        VALUES (?, ?, ?, ?, ?)
        ''', sample_employees)

    conn.commit()
    conn.close()


# ---- Employee CRUD Operations ----

def get_all_employees():
    """Retrieve all active employees"""
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM employees WHERE active = 1 ORDER BY name", conn)
    conn.close()
    return df


def add_employee(name, position, pay_type, pay_rate, weekly_hours=0):
    """Add a new employee to the database"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
    INSERT INTO employees (name, position, pay_type, pay_rate, weekly_hours)
    VALUES (?, ?, ?, ?, ?)
    ''', (name, position, pay_type, pay_rate, weekly_hours))

    employee_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return employee_id


def update_employee(employee_id, name=None, position=None, pay_type=None, pay_rate=None, weekly_hours=None):
    """Update an existing employee's information"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get current employee data
    cursor.execute("SELECT * FROM employees WHERE id = ?", (employee_id,))
    employee = cursor.fetchone()

    if not employee:
        conn.close()
        return False

    # Update with new values or keep existing ones
    name = name if name is not None else employee['name']
    position = position if position is not None else employee['position']
    pay_type = pay_type if pay_type is not None else employee['pay_type']
    pay_rate = pay_rate if pay_rate is not None else employee['pay_rate']
    weekly_hours = weekly_hours if weekly_hours is not None else employee['weekly_hours']

    cursor.execute('''
    UPDATE employees
    SET name = ?, position = ?, pay_type = ?, pay_rate = ?, weekly_hours = ?, updated_at = CURRENT_TIMESTAMP
    WHERE id = ?
    ''', (name, position, pay_type, pay_rate, weekly_hours, employee_id))

    conn.commit()
    conn.close()

    return True


def delete_employee(employee_id):
    """Soft delete an employee (mark as inactive)"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
    UPDATE employees
    SET active = 0, updated_at = CURRENT_TIMESTAMP
    WHERE id = ?
    ''', (employee_id,))

    conn.commit()
    conn.close()

    return True


# ---- Schedule Operations ----

def save_schedule(employee_id, date, start_time=None, end_time=None, hours=None, cost=None, overtime=False):
    """Save or update a schedule entry for an employee on a specific date"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if a schedule entry already exists for this employee on this date
    cursor.execute('''
    SELECT id FROM schedules
    WHERE employee_id = ? AND date = ?
    ''', (employee_id, date))

    existing_entry = cursor.fetchone()

    if existing_entry:
        # Update existing entry
        cursor.execute('''
        UPDATE schedules
        SET start_time = ?, end_time = ?, hours = ?, cost = ?, overtime = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        ''', (start_time, end_time, hours, cost, overtime, existing_entry['id']))
    else:
        # Create new entry
        cursor.execute('''
        INSERT INTO schedules (employee_id, date, start_time, end_time, hours, cost, overtime)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (employee_id, date, start_time, end_time, hours, cost, overtime))

    conn.commit()
    conn.close()

    return True


def get_schedule(start_date, end_date):
    """Retrieve schedule data for a date range"""
    conn = get_db_connection()

    query = '''
    SELECT s.*, e.name, e.position, e.pay_type, e.pay_rate
    FROM schedules s
    JOIN employees e ON s.employee_id = e.id
    WHERE s.date BETWEEN ? AND ?
    ORDER BY s.date, e.name
    '''

    schedule_df = pd.read_sql_query(query, conn, params=[start_date, end_date])
    conn.close()

    return schedule_df


def get_schedule_by_employee(employee_id, start_date, end_date):
    """Retrieve schedule data for a specific employee in a date range"""
    conn = get_db_connection()

    query = '''
    SELECT s.*, e.name, e.position, e.pay_type, e.pay_rate
    FROM schedules s
    JOIN employees e ON s.employee_id = e.id
    WHERE s.employee_id = ? AND s.date BETWEEN ? AND ?
    ORDER BY s.date
    '''

    schedule_df = pd.read_sql_query(query, conn, params=[employee_id, start_date, end_date])
    conn.close()

    return schedule_df


def delete_schedule(schedule_id):
    """Delete a schedule entry"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))

    conn.commit()
    conn.close()

    return True


# ---- Labor Cost Operations ----

def save_labor_cost(date, total_hours, regular_hours, overtime_hours, total_cost,
                    labor_goal_percentage=None, required_sales=None, actual_sales=None):
    """Save or update labor cost data for a specific date"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if an entry already exists for this date
    cursor.execute("SELECT id FROM labor_costs WHERE date = ?", (date,))
    existing_entry = cursor.fetchone()

    if existing_entry:
        # Update existing entry
        cursor.execute('''
        UPDATE labor_costs
        SET total_hours = ?, regular_hours = ?, overtime_hours = ?, total_cost = ?,
            labor_goal_percentage = ?, required_sales = ?, actual_sales = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        ''', (total_hours, regular_hours, overtime_hours, total_cost,
              labor_goal_percentage, required_sales, actual_sales,
              existing_entry['id']))
    else:
        # Create new entry
        cursor.execute('''
        INSERT INTO labor_costs (date, total_hours, regular_hours, overtime_hours, total_cost,
                              labor_goal_percentage, required_sales, actual_sales)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (date, total_hours, regular_hours, overtime_hours, total_cost,
              labor_goal_percentage, required_sales, actual_sales))

    conn.commit()
    conn.close()

    return True


def get_labor_costs(start_date, end_date):
    """Retrieve labor cost data for a date range"""
    conn = get_db_connection()

    query = '''
    SELECT *
    FROM labor_costs
    WHERE date BETWEEN ? AND ?
    ORDER BY date
    '''

    labor_costs_df = pd.read_sql_query(query, conn, params=[start_date, end_date])
    conn.close()

    return labor_costs_df


def get_labor_costs_by_period(period_type, period_value):
    """
    Retrieve labor cost data by period type (daily, weekly, monthly, yearly)
    period_value should be:
    - for daily: a specific date string 'YYYY-MM-DD'
    - for weekly: a week number and year tuple (week_num, year)
    - for monthly: a month and year tuple (month, year)
    - for yearly: a year value (e.g. 2025)
    """
    conn = get_db_connection()

    if period_type == 'daily':
        query = "SELECT * FROM labor_costs WHERE date = ?"
        params = [period_value]

    elif period_type == 'weekly':
        week_num, year = period_value
        query = '''
        SELECT * FROM labor_costs 
        WHERE strftime('%W', date) = ? AND strftime('%Y', date) = ?
        ORDER BY date
        '''
        params = [f"{week_num:02d}", str(year)]

    elif period_type == 'monthly':
        month, year = period_value
        query = '''
        SELECT * FROM labor_costs 
        WHERE strftime('%m', date) = ? AND strftime('%Y', date) = ?
        ORDER BY date
        '''
        params = [f"{month:02d}", str(year)]

    elif period_type == 'yearly':
        query = '''
        SELECT * FROM labor_costs 
        WHERE strftime('%Y', date) = ?
        ORDER BY date
        '''
        params = [str(period_value)]

    else:
        conn.close()
        raise ValueError(f"Invalid period type: {period_type}")

    labor_costs_df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    return labor_costs_df


# ---- Restaurant Settings Operations ----

def get_restaurant_settings():
    """Retrieve restaurant settings"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM restaurant_settings LIMIT 1")
    settings = cursor.fetchone()

    # Convert closed_days from JSON string to list
    if settings and settings['closed_days']:
        settings = dict(settings)
        settings['closed_days'] = json.loads(settings['closed_days'])

    conn.close()

    return settings


def update_restaurant_settings(name=None, labor_goal_percentage=None, closed_days=None):
    """Update restaurant settings"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get current settings
    cursor.execute("SELECT * FROM restaurant_settings LIMIT 1")
    current_settings = cursor.fetchone()

    if not current_settings:
        # Create settings if they don't exist
        cursor.execute('''
        INSERT INTO restaurant_settings (name, labor_goal_percentage, closed_days)
        VALUES (?, ?, ?)
        ''', ('My Restaurant', 25.0, json.dumps([])))

        cursor.execute("SELECT * FROM restaurant_settings LIMIT 1")
        current_settings = cursor.fetchone()

    # Update with new values or keep existing ones
    name = name if name is not None else current_settings['name']
    labor_goal_percentage = labor_goal_percentage if labor_goal_percentage is not None else current_settings[
        'labor_goal_percentage']

    if closed_days is not None:
        closed_days_json = json.dumps(closed_days)
    else:
        closed_days_json = current_settings['closed_days']

    cursor.execute('''
    UPDATE restaurant_settings
    SET name = ?, labor_goal_percentage = ?, 
        closed_days = ?, updated_at = CURRENT_TIMESTAMP
    WHERE id = ?
    ''', (name, labor_goal_percentage, closed_days_json, current_settings['id']))

    conn.commit()
    conn.close()

    return True