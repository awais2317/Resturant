import streamlit as st
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Set the backend before importing pyplot
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

# Import other modules
import database as db
import scheduler as sch
import reports as rpt






# Configuration
APP_TITLE = "Master Scheduler - Labor Cost & Schedule Optimization"


def main():
    """Main application function"""
    # Initialize the database
    db.init_db()

    # Set page configuration
    st.set_page_config(
        page_title="Master Scheduler - Labor Cost & Schedule Optimization",
        page_icon="📆",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # Custom CSS for better styling
    st.markdown("""
    <style>
        .main-header {
            font-size: 2.5rem;
            color: #2c3e50;
            text-align: center;
            margin-bottom: 1rem;
        }
        .sub-header {
            font-size: 1.8rem;
            color: #3498db;
            margin-bottom: 0.8rem;
        }
        .section-header {
            font-size: 1.5rem;
            color: #e67e22;
            margin-top: 1rem;
            margin-bottom: 0.5rem;
        }
        .info-box {
            padding: 1rem;
            background-color: #d1ecf1;
            border-radius: 0.5rem;
            border: 1px solid #bee5eb;
            color: #0c5460;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 24px;
        }
        .stTabs [data-baseweb="tab"] {
            height: 50px;
            white-space: pre-wrap;
            background-color: #f8f9fa;
            border-radius: 4px 4px 0 0;
            gap: 1px;
            padding-top: 10px;
            padding-bottom: 10px;
        }
        .stTabs [aria-selected="true"] {
            background-color: #3498db;
            color: white;
        }
    </style>
    """, unsafe_allow_html=True)

    # Application header
    st.markdown("<h1 class='main-header'>Master Scheduler</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center; margin-top: -15px;'>Labor Cost & Schedule Optimization Tool</h3>",
                unsafe_allow_html=True)

    st.markdown("""
    <div class='info-box'>
    This tool helps you optimize labor costs by creating efficient schedules, tracking labor percentages, and providing insights to reduce wasted labor hours. 
    Enter your employee information, set your labor cost goals, and generate schedules that help you meet your financial targets.
    </div>
    """, unsafe_allow_html=True)

    # Create tabs for different sections
    tab1, tab2, tab3, tab4 = st.tabs([
        "📝 Setup", "📅 Schedule", "📊 Reports", "📊 Staffing Guide"
    ])

    with tab1:
        setup_tab()

    with tab2:
        sch.schedule_tab()

    with tab3:
        rpt.reports_tab()

    with tab4:
        rpt.staffing_guide_tab()


def setup_tab():
    """Setup tab content"""
    st.markdown("<h2 class='sub-header'>Restaurant Configuration</h2>", unsafe_allow_html=True)

    # Get restaurant settings from database
    settings = db.get_restaurant_settings()

    col1, col2 = st.columns(2)

    with col1:
        restaurant_name = st.text_input("Restaurant Name", settings['name'])
        labor_goal = st.number_input("Labor Cost Goal (%)", min_value=5.0, max_value=50.0,
                                     value=settings['labor_goal_percentage'], step=0.5)

    with col2:
        closed_days = st.multiselect(
            "Select days when restaurant is closed:",
            options=['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
            default=settings['closed_days']
        )

    # Save settings button
    if st.button("Save Settings"):
        db.update_restaurant_settings(
            name=restaurant_name,
            labor_goal_percentage=labor_goal,
            closed_days=closed_days
        )
        st.success("Restaurant settings saved successfully!")

    st.markdown("<h2 class='sub-header'>Employee Information</h2>", unsafe_allow_html=True)
    st.markdown("Add your employees, their positions, and pay rates below:")

    # Get employee data from database
    employee_df = db.get_all_employees()

    # Function to add new employee
    def add_employee_form():
        if not new_name:
            st.warning("Employee name is required")
            return

        db.add_employee(
            name=new_name,
            position=new_position,
            pay_type=new_pay_type,
            pay_rate=new_pay_rate,
            weekly_hours=new_weekly_hours if new_pay_type == 'Salary' else 0
        )
        st.rerun()

    # Add employee form
    with st.expander("Add New Employee", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            new_name = st.text_input("Employee Name")
            new_position = st.selectbox(
                "Position",
                ["Manager", "Chef", "Cook", "Server", "Bartender", "Host", "Dishwasher", "Busser", "Other"]
            )

        with col2:
            new_pay_type = st.selectbox("Pay Type", ["Hourly", "Salary"])
            new_pay_rate = st.number_input("Pay Rate ($)", min_value=0.0, value=15.0, step=0.5)
            new_weekly_hours = st.number_input("Weekly Hours (Salary Only)", min_value=0, value=40,
                                               help="Only applicable for salaried employees")

        st.button("Add Employee", on_click=add_employee_form)

    # Function to handle employee data updates
    def update_employees(edited_df):
        # Compare with original data to find changes
        if len(edited_df) > 0 and len(employee_df) > 0:
            for index, row in edited_df.iterrows():
                # Check if this is a new row (no ID)
                if 'id' not in row or pd.isna(row['id']):
                    db.add_employee(
                        name=row['name'],
                        position=row['position'],
                        pay_type=row['pay_type'],
                        pay_rate=row['pay_rate'],
                        weekly_hours=row['weekly_hours'] if row['pay_type'] == 'Salary' else 0
                    )
                else:
                    # Check if row has changed
                    original_row = employee_df[employee_df['id'] == row['id']]
                    if not original_row.empty:
                        original_row = original_row.iloc[0]

                        # Only update if something changed
                        if (row['name'] != original_row['name'] or
                                row['position'] != original_row['position'] or
                                row['pay_type'] != original_row['pay_type'] or
                                row['pay_rate'] != original_row['pay_rate'] or
                                row['weekly_hours'] != original_row['weekly_hours']):
                            db.update_employee(
                                employee_id=row['id'],
                                name=row['name'],
                                position=row['position'],
                                pay_type=row['pay_type'],
                                pay_rate=row['pay_rate'],
                                weekly_hours=row['weekly_hours']
                            )

        st.rerun()

    # Display and edit employee table
    if not employee_df.empty:
        # Filter columns to display
        display_columns = ['id', 'name', 'position', 'pay_type', 'pay_rate', 'weekly_hours', 'active']
        display_df = employee_df[display_columns].copy()

        edited_df = st.data_editor(
            display_df,
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "id": st.column_config.NumberColumn("ID", disabled=True, required=True),
                "name": st.column_config.TextColumn("Name", required=True),
                "position": st.column_config.SelectboxColumn(
                    "Position",
                    options=["Manager", "Chef", "Cook", "Server", "Bartender", "Host", "Dishwasher", "Busser", "Other"],
                    required=True
                ),
                "pay_type": st.column_config.SelectboxColumn(
                    "Pay Type",
                    options=["Hourly", "Salary"],
                    required=True
                ),
                "pay_rate": st.column_config.NumberColumn(
                    "Pay Rate ($)",
                    min_value=0,
                    format="$%.2f",
                    required=True
                ),
                "weekly_hours": st.column_config.NumberColumn(
                    "Weekly Hours",
                    help="Only applies to salaried employees",
                    min_value=0,
                    max_value=168,
                    step=1
                ),
                "active": st.column_config.CheckboxColumn("Active", disabled=True)
            },
            hide_index=True
        )

        if st.button("Save Employee Changes"):
            update_employees(edited_df)
    else:
        st.info("No employees found. Add employees using the form above.")


# Run the application
if __name__ == "__main__":
    main()
