"""
Scheduler module for Master Scheduler application.
Handles all scheduling and labor cost calculation functionality.
"""

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Set the backend before importing pyplot
import matplotlib.pyplot as plt
from datetime import datetime, timedelta, date
import io
import base64

# Import our database module
import database as db

# ---- Helper Functions ----

def download_excel(df, sheet_name, filename):
    """Create a download link for an Excel file from a DataFrame"""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)

    b64 = base64.b64encode(output.getvalue()).decode()
    href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="{filename}.xlsx">Download Excel file</a>'
    return href


def parse_shift_hours(shift_str):
    """Parse a shift time string (e.g., '9am-5pm') into start_time, end_time, and hours"""
    if not shift_str or shift_str == "CLOSED":
        return None, None, 0

    try:
        if '-' in shift_str:
            start_time, end_time = shift_str.split('-')

            # Convert to 24-hour format for calculation
            def parse_time(time_str):
                # Remove whitespace
                time_str = time_str.strip()

                # Check if am/pm is specified
                if 'am' in time_str.lower():
                    time_val = float(time_str.lower().replace('am', ''))
                    return time_val if time_val != 12 else 0
                elif 'pm' in time_str.lower():
                    time_val = float(time_str.lower().replace('pm', ''))
                    return time_val + 12 if time_val != 12 else 12
                else:
                    # If no am/pm, assume reasonable values
                    time_val = float(time_str)
                    if time_val < 12:
                        # Assume morning shift starts and afternoon shifts
                        return time_val if time_val >= 5 else time_val + 12
                    else:
                        return time_val

            start_hour = parse_time(start_time)
            end_hour = parse_time(end_time)

            # Handle overnight shifts
            if end_hour <= start_hour:
                end_hour += 24

            # Calculate shift duration
            hours = end_hour - start_hour

            # Format times for database storage
            formatted_start = f"{int(start_hour):02d}:00:00"
            formatted_end = f"{int(end_hour % 24):02d}:00:00"

            return formatted_start, formatted_end, hours

        # If shift string doesn't follow expected format
        return None, None, 0

    except Exception as e:
        st.warning(f"Error parsing shift time: {shift_str}, Error: {str(e)}")
        return None, None, 0


# ---- Schedule Tab ----

def schedule_tab():
    """Schedule tab content"""
    st.markdown("<h2 class='sub-header'>Weekly Schedule</h2>", unsafe_allow_html=True)

    # Get restaurant settings
    settings = db.get_restaurant_settings()
    closed_days = settings['closed_days']

    # Date selector for schedule week
    col1, col2 = st.columns(2)
    with col1:
        # Default to current week's Monday
        default_date = datetime.now() - timedelta(days=datetime.now().weekday())
        start_date = st.date_input(
            "Week Starting Date",
            default_date,
            format="YYYY/MM/DD"
        )

    # Calculate end date (1 week from start date)
    end_date = start_date + timedelta(days=6)

    st.markdown(f"Schedule for week: **{start_date.strftime('%B %d, %Y')}** to **{end_date.strftime('%B %d, %Y')}**")

    # Create date columns for the week
    dates = [(start_date + timedelta(days=i)) for i in range(7)]
    date_strs = [d.strftime('%a %m/%d') for d in dates]
    date_closed = [d.strftime('%a') in closed_days for d in dates]

    # Get employee data
    employee_df = db.get_all_employees()

    if employee_df.empty:
        st.warning("No employees found. Please add employees in the Setup tab.")
        return

    # Get existing schedule data for this week
    schedule_data = db.get_schedule(start_date, end_date)

    # Create a schedule DataFrame with a row for each employee and columns for each day
    schedule_df = pd.DataFrame()
    schedule_df['Employee'] = employee_df['name']
    schedule_df['Position'] = employee_df['position']
    schedule_df['Employee ID'] = employee_df['id']  # Hidden column for reference

    # Add columns for each day
    for i, date_str in enumerate(date_strs):
        if date_closed[i]:
            schedule_df[date_str] = "CLOSED"
        else:
            schedule_df[date_str] = ""

    # Fill in existing schedule data
    if not schedule_data.empty:
        for _, row in schedule_data.iterrows():
            employee_id = row['employee_id']
            date_obj = pd.to_datetime(row['date']).date()
            date_idx = (date_obj - start_date).days

            if 0 <= date_idx < 7:
                date_str = date_strs[date_idx]

                if pd.notna(row['start_time']) and pd.notna(row['end_time']):
                    start_hour = pd.to_datetime(row['start_time']).hour
                    end_hour = pd.to_datetime(row['end_time']).hour

                    start_str = f"{start_hour if start_hour <= 12 else start_hour - 12}{'am' if start_hour < 12 else 'pm'}"
                    end_str = f"{end_hour if end_hour <= 12 else end_hour - 12}{'am' if end_hour < 12 else 'pm'}"
                    shift_str = f"{start_str}-{end_str}"

                    employee_idx = schedule_df[schedule_df['Employee ID'] == employee_id].index
                    if len(employee_idx) > 0:
                        schedule_df.loc[employee_idx[0], date_str] = shift_str

    # Display schedule editor
    st.markdown(
        "Enter shift times for each employee (e.g., '9am-5pm' or '10-6'). Days when restaurant is closed will be marked as CLOSED."
    )

    edited_schedule = st.data_editor(
        schedule_df,
        use_container_width=True,
        column_config={
            "Employee": st.column_config.TextColumn("Employee", disabled=True),
            "Position": st.column_config.TextColumn("Position", disabled=True),
            "Employee ID": st.column_config.NumberColumn("Employee ID", disabled=True),
            **{
                date: st.column_config.TextColumn(
                    date,
                    disabled=date_closed[i],
                    help="Format: Start-End (e.g., 9am-5pm)"
                ) for i, date in enumerate(date_strs)
            }
        },
        hide_index=True
    )

    # Save schedule button
    if st.button("Save Schedule"):
        with st.spinner("Saving schedule..."):
            save_success = save_schedule_to_db(edited_schedule, dates, date_strs, date_closed)
            if save_success:
                st.success("Schedule saved successfully!")

    # Calculate labor cost button
    if st.button("Calculate Schedule Labor Cost"):
        with st.spinner("Calculating labor costs and required sales..."):
            calculate_labor_costs(edited_schedule, dates, date_strs, date_closed, settings)
            st.success("Labor costs calculated successfully!")

    # Export and print options
    st.markdown("<h3 class='section-header'>Export and Share Schedule</h3>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("📄 Print Schedule", key="print_schedule"):
            st.info("Prepare schedule for printing... In a real application, this would generate a printer-friendly PDF.")

            printable_df = schedule_df.copy()
            if 'Employee ID' in printable_df.columns:
                printable_df = printable_df.drop(columns=['Employee ID'])

            st.dataframe(printable_df, use_container_width=True)

            st.markdown(download_excel(
                printable_df,
                f"Schedule_{start_date.strftime('%Y%m%d')}",
                f"Schedule_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}"
            ), unsafe_allow_html=True)

    with col2:
        if st.button("📧 Email Schedule to Staff", key="email_schedule"):
            st.info("In a real application, this would email the schedule to your staff.")

            with st.expander("Email Details"):
                st.text_input("From Email", value=f"{settings['name'].lower().replace(' ', '')}@example.com")
                st.text_area("Employee Emails", value="staff@example.com")
                st.text_input("Subject", value=f"Weekly Schedule: {start_date.strftime('%b %d')} - {end_date.strftime('%b %d')}")
                st.text_area("Message", value=f"Hello Team,\n\nAttached is the schedule for the week of {start_date.strftime('%B %d, %Y')}.\n\nThank you,\nManagement")

                if st.button("Send Email"):
                    st.success("Schedule email would be sent in a real application!")



def save_schedule_to_db(schedule_df, dates, date_strs, date_closed):
    """Save the edited schedule to the database"""
    try:
        for _, row in schedule_df.iterrows():
            employee_id = row['Employee ID']

            for i, date_str in enumerate(date_strs):
                if date_closed[i]:
                    continue  # Skip closed days

                date_obj = dates[i]
                shift_str = row[date_str]

                if shift_str and shift_str != "CLOSED":
                    # Parse the shift string
                    start_time, end_time, hours = parse_shift_hours(shift_str)

                    # Save to database (cost will be calculated later)
                    db.save_schedule(
                        employee_id=employee_id,
                        date=date_obj,
                        start_time=start_time,
                        end_time=end_time,
                        hours=hours
                    )
                else:
                    # Check if there's an existing entry to delete
                    existing_schedule = db.get_schedule_by_employee(employee_id, date_obj, date_obj)
                    if not existing_schedule.empty:
                        # This is a simplification - in a real app, we'd need to get the schedule_id
                        # Here we're assuming we can identify the record by employee_id and date
                        db.save_schedule(
                            employee_id=employee_id,
                            date=date_obj,
                            start_time=None,
                            end_time=None,
                            hours=0
                        )

        return True
    except Exception as e:
        st.error(f"Error saving schedule: {str(e)}")
        return False


def calculate_labor_costs(schedule_df, dates, date_strs, date_closed, settings):
    """Calculate labor costs for the schedule and save to the database"""
    # Get employee data to access pay rates
    employee_df = db.get_all_employees()

    # Dictionary to store daily labor costs
    daily_labor = {date_obj: {'total_hours': 0, 'regular_hours': 0, 'overtime_hours': 0, 'total_cost': 0}
                   for date_obj in dates}

    # Process each employee's schedule
    for _, row in schedule_df.iterrows():
        employee_id = row['Employee ID']
        employee_data = employee_df[employee_df['id'] == employee_id].iloc[0]

        pay_type = employee_data['pay_type']
        pay_rate = employee_data['pay_rate']

        # For weekly calculations
        weekly_hours = 0
        weekly_shifts = []

        # First pass: calculate hours for each day
        for i, date_str in enumerate(date_strs):
            if date_closed[i]:
                continue  # Skip closed days

            date_obj = dates[i]
            shift_str = row[date_str]

            if shift_str and shift_str != "CLOSED":
                # Parse the shift string
                start_time, end_time, hours = parse_shift_hours(shift_str)

                if hours > 0:
                    weekly_hours += hours
                    weekly_shifts.append((date_obj, hours))

        # Second pass: calculate costs with overtime consideration
        if pay_type == 'Hourly':
            # Calculate overtime (over 40 hours)
            if weekly_hours > 40:
                regular_hours = 40
                overtime_hours = weekly_hours - 40

                # Calculate how to distribute overtime hours
                remaining_ot = overtime_hours
                regular_remaining = regular_hours

                # Sort shifts by date
                weekly_shifts.sort(key=lambda x: x[0])

                # Assign hours to shifts
                for date_obj, shift_hours in weekly_shifts:
                    if regular_remaining > 0:
                        if shift_hours <= regular_remaining:
                            # All hours are regular
                            reg_hours = shift_hours
                            ot_hours = 0
                            regular_remaining -= shift_hours
                        else:
                            # Some hours are overtime
                            reg_hours = regular_remaining
                            ot_hours = shift_hours - regular_remaining
                            regular_remaining = 0
                    else:
                        # All hours are overtime
                        reg_hours = 0
                        ot_hours = shift_hours

                    # Calculate cost
                    regular_cost = reg_hours * pay_rate
                    overtime_cost = ot_hours * pay_rate * 1.5
                    total_cost = regular_cost + overtime_cost

                    # Update daily totals
                    daily_labor[date_obj]['total_hours'] += shift_hours
                    daily_labor[date_obj]['regular_hours'] += reg_hours
                    daily_labor[date_obj]['overtime_hours'] += ot_hours
                    daily_labor[date_obj]['total_cost'] += total_cost

                    # Save to database
                    db.save_schedule(
                        employee_id=employee_id,
                        date=date_obj,
                        start_time=start_time,
                        end_time=end_time,
                        hours=shift_hours,
                        cost=total_cost,
                        overtime=(ot_hours > 0)
                    )
            else:
                # No overtime
                for i, date_str in enumerate(date_strs):
                    if date_closed[i]:
                        continue

                    date_obj = dates[i]
                    shift_str = row[date_str]

                    if shift_str and shift_str != "CLOSED":
                        start_time, end_time, hours = parse_shift_hours(shift_str)

                        if hours > 0:
                            # Calculate cost
                            cost = hours * pay_rate

                            # Update daily totals
                            daily_labor[date_obj]['total_hours'] += hours
                            daily_labor[date_obj]['regular_hours'] += hours
                            daily_labor[date_obj]['total_cost'] += cost

                            # Save to database
                            db.save_schedule(
                                employee_id=employee_id,
                                date=date_obj,
                                start_time=start_time,
                                end_time=end_time,
                                hours=hours,
                                cost=cost,
                                overtime=False
                            )
        else:  # Salaried employee
            # For salaried employees, distribute weekly salary across working days
            # Count how many days they work
            working_days = sum(1 for i, date_str in enumerate(date_strs)
                               if not date_closed[i] and row[date_str] and row[date_str] != "CLOSED")

            if working_days > 0:
                daily_salary = pay_rate / working_days

                for i, date_str in enumerate(date_strs):
                    if date_closed[i]:
                        continue

                    date_obj = dates[i]
                    shift_str = row[date_str]

                    if shift_str and shift_str != "CLOSED":
                        start_time, end_time, hours = parse_shift_hours(shift_str)

                        # Update daily totals (using actual hours for reporting)
                        daily_labor[date_obj]['total_hours'] += hours
                        daily_labor[date_obj]['regular_hours'] += hours
                        daily_labor[date_obj]['total_cost'] += daily_salary

                        # Save to database
                        db.save_schedule(
                            employee_id=employee_id,
                            date=date_obj,
                            start_time=start_time,
                            end_time=end_time,
                            hours=hours,
                            cost=daily_salary,
                            overtime=False
                        )

    # Save daily labor totals to the labor_costs table
    labor_goal_pct = settings['labor_goal_percentage']

    for date_obj, labor_data in daily_labor.items():
        # Skip days with no labor
        if labor_data['total_cost'] == 0:
            continue

        # Calculate required sales to meet labor goal
        required_sales = labor_data['total_cost'] / (labor_goal_pct / 100) if labor_goal_pct > 0 else 0

        # Save to database
        db.save_labor_cost(
            date=date_obj,
            total_hours=labor_data['total_hours'],
            regular_hours=labor_data['regular_hours'],
            overtime_hours=labor_data['overtime_hours'],
            total_cost=labor_data['total_cost'],
            labor_goal_percentage=labor_goal_pct,
            required_sales=required_sales
        )

    # Store in session state for reports
    st.session_state.labor_week_start = dates[0]
    st.session_state.labor_week_end = dates[-1]

    # Display summary information
    st.markdown("<h3 class='section-header'>Schedule Summary</h3>", unsafe_allow_html=True)

    # Create summary table
    summary_data = []
    for date_obj, labor_data in daily_labor.items():
        if labor_data['total_cost'] > 0:  # Only include days with scheduled labor
            day_name = date_obj.strftime('%a')
            date_str = date_obj.strftime('%m/%d')
            total_hours = labor_data['total_hours']
            total_cost = labor_data['total_cost']
            required_sales = labor_data['total_cost'] / (labor_goal_pct / 100) if labor_goal_pct > 0 else 0

            summary_data.append({
                'Day': f"{day_name} {date_str}",
                'Total Hours': total_hours,
                'Labor Cost': total_cost,
                'Required Sales': required_sales,
                'Overtime Hours': labor_data['overtime_hours']
            })

    if summary_data:
        summary_df = pd.DataFrame(summary_data)

        # Add weekly totals row
        totals_row = {
            'Day': 'WEEKLY TOTAL',
            'Total Hours': summary_df['Total Hours'].sum(),
            'Labor Cost': summary_df['Labor Cost'].sum(),
            'Required Sales': summary_df['Required Sales'].sum(),
            'Overtime Hours': summary_df['Overtime Hours'].sum()
        }

        summary_df = pd.concat([summary_df, pd.DataFrame([totals_row])], ignore_index=True)

        # Display the summary table
        st.dataframe(
            summary_df,
            column_config={
                'Day': st.column_config.TextColumn("Day"),
                'Total Hours': st.column_config.NumberColumn("Total Hours", format="%.2f"),
                'Labor Cost': st.column_config.NumberColumn("Labor Cost", format="$%.2f"),
                'Required Sales': st.column_config.NumberColumn("Required Sales", format="$%.2f"),
                'Overtime Hours': st.column_config.NumberColumn("Overtime Hours", format="%.2f")
            },
            use_container_width=True,
            hide_index=True
        )

        # Visual summary
        st.markdown("<h4>Daily Labor Cost vs Required Sales</h4>", unsafe_allow_html=True)

        # Create bar chart
        fig, ax = plt.subplots(figsize=(10, 6))

        days = [row['Day'] for row in summary_data]
        labor_costs = [row['Labor Cost'] for row in summary_data]
        required_sales = [row['Required Sales'] for row in summary_data]

        x = range(len(days))
        width = 0.35

        ax.bar([i - width / 2 for i in x], labor_costs, width, label='Labor Cost', color='#3498db')
        ax.bar([i + width / 2 for i in x], required_sales, width, label='Required Sales', color='#e74c3c')

        # Add data labels
        for i, cost in enumerate(labor_costs):
            ax.text(i - width / 2, cost + 5, f"${cost:.0f}", ha='center', va='bottom')

        for i, sales in enumerate(required_sales):
            ax.text(i + width / 2, sales + 5, f"${sales:.0f}", ha='center', va='bottom')

        ax.set_ylabel('Amount ($)')
        ax.set_title('Daily Labor Cost vs Required Sales')
        ax.set_xticks(x)
        ax.set_xticklabels(days)
        ax.legend()

        plt.xticks(rotation=45)
        plt.tight_layout()

        st.pyplot(fig)

        # Calculate and display key metrics
        col1, col2, col3 = st.columns(3)

        with col1:
            total_labor_cost = summary_df.iloc[:-1]['Labor Cost'].sum()  # Exclude the total row
            st.metric("Total Weekly Labor Cost", f"${total_labor_cost:.2f}")

        with col2:
            total_required_sales = summary_df.iloc[:-1]['Required Sales'].sum()
            st.metric("Required Weekly Sales", f"${total_required_sales:.2f}")

        with col3:
            weekly_labor_pct = (total_labor_cost / total_required_sales * 100) if total_required_sales > 0 else 0
            st.metric("Projected Labor %", f"{weekly_labor_pct:.2f}%",
                      f"{labor_goal_pct - weekly_labor_pct:.2f}%" if weekly_labor_pct <= labor_goal_pct else f"{weekly_labor_pct - labor_goal_pct:.2f}%",
                      delta_color="normal" if weekly_labor_pct <= labor_goal_pct else "inverse")

    else:
        st.info("No labor data calculated yet. Schedule some shifts and click 'Calculate Schedule Labor Cost'.")
