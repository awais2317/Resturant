"""
Reports module for Master Scheduler application.
Handles all reporting and analysis functionality.
"""

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta, date
import io
import base64
import numpy as np
# Import our modules
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


# ---- Report Functions ----

def reports_tab():
    """Reports tab content"""
    st.markdown("<h2 class='sub-header'>Labor Cost Reports</h2>", unsafe_allow_html=True)

    # Check if labor costs have been calculated
    if 'labor_week_start' in st.session_state and 'labor_week_end' in st.session_state:
        start_date = st.session_state.labor_week_start
        end_date = st.session_state.labor_week_end
    else:
        # Default to current week
        start_date = datetime.now().date() - timedelta(days=datetime.now().weekday())
        end_date = start_date + timedelta(days=6)

    # Date range selector
    col1, col2 = st.columns(2)
    with col1:
        selected_start = st.date_input("Start Date", start_date, key="report_start_date")
    with col2:
        selected_end = st.date_input("End Date", end_date, key="report_end_date")

    if selected_start > selected_end:
        st.error("End date must be after start date.")
        return

    # Get labor cost data
    labor_costs = db.get_labor_costs(selected_start, selected_end)

    if labor_costs.empty:
        st.warning(
            "No labor cost data available for the selected date range. Please calculate labor costs in the Schedule tab first.")
        return

    # Get restaurant settings
    settings = db.get_restaurant_settings()
    labor_goal = settings['labor_goal_percentage']

    # Summary metrics
    total_labor_cost = labor_costs['total_cost'].sum()
    total_required_sales = labor_costs['required_sales'].sum()
    actual_sales = labor_costs['actual_sales'].sum() if 'actual_sales' in labor_costs and not pd.isna(
        labor_costs['actual_sales']).all() else None

    # Create metrics columns
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Total Labor Cost", f"${total_labor_cost:.2f}")

    with col2:
        st.metric("Required Sales (Target)", f"${total_required_sales:.2f}")

    with col3:
        if actual_sales is not None and actual_sales > 0:
            actual_labor_pct = (total_labor_cost / actual_sales) * 100
            st.metric("Actual Labor %", f"{actual_labor_pct:.1f}%",
                      f"{labor_goal - actual_labor_pct:.1f}%" if actual_labor_pct < labor_goal else f"{actual_labor_pct - labor_goal:.1f}%",
                      delta_color="normal" if actual_labor_pct <= labor_goal else "inverse")
        else:
            projected_labor_pct = (total_labor_cost / total_required_sales) * 100 if total_required_sales > 0 else 0
            st.metric("Projected Labor %", f"{projected_labor_pct:.1f}%",
                      f"Target: {labor_goal:.1f}%")

            # Option to enter actual sales
            with st.expander("Enter Actual Sales Data"):
                st.markdown("Enter actual sales data to calculate true labor percentages:")

                # Get list of dates
                unique_dates = sorted(labor_costs['date'].unique())
                actual_sales_data = {}

                # Create form for sales entry
                with st.form("actual_sales_form"):
                    for date_str in unique_dates:
                        date_obj = pd.to_datetime(date_str).date()
                        formatted_date = date_obj.strftime("%a, %b %d")

                        # Get labor cost for this date
                        day_labor = labor_costs[labor_costs['date'] == date_str]['total_cost'].iloc[0]
                        day_required = labor_costs[labor_costs['date'] == date_str]['required_sales'].iloc[0]

                        col1, col2 = st.columns([2, 1])
                        with col1:
                            actual_sales_data[date_str] = st.number_input(
                                f"{formatted_date} (Labor: ${day_labor:.2f}, Required: ${day_required:.2f})",
                                min_value=0.0,
                                step=100.0,
                                format="%.2f"
                            )
                        with col2:
                            if actual_sales_data[date_str] > 0:
                                actual_pct = (day_labor / actual_sales_data[date_str]) * 100
                                st.markdown(f"Labor %: **{actual_pct:.1f}%**")

                    submitted = st.form_submit_button("Save Actual Sales")

                    if submitted:
                        # Update labor_costs table with actual sales
                        success = True
                        for date_str, sales_amount in actual_sales_data.items():
                            if sales_amount > 0:
                                # Get corresponding labor cost record
                                date_labor = labor_costs[labor_costs['date'] == date_str]
                                if not date_labor.empty:
                                    labor_id = date_labor.iloc[0]['id']

                                    # Update in database
                                    conn = db.get_db_connection()
                                    cursor = conn.cursor()
                                    cursor.execute(
                                        "UPDATE labor_costs SET actual_sales = ? WHERE id = ?",
                                        (sales_amount, labor_id)
                                    )
                                    conn.commit()
                                    conn.close()

                        if success:
                            st.success("Sales data saved successfully!")
                            st.rerun()

    # Daily breakdown
    st.markdown("<h3 class='section-header'>Daily Labor Costs & Sales Targets</h3>", unsafe_allow_html=True)

    # Prepare daily data
    daily_data = []
    for _, row in labor_costs.iterrows():
        date_str = pd.to_datetime(row['date']).strftime('%a %m/%d')
        has_actual = pd.notna(row['actual_sales']) and row['actual_sales'] > 0

        daily_row = {
            'Date': date_str,
            'Labor Cost': row['total_cost'],
            'Required Sales': row['required_sales'],
            'Projected Labor %': (row['total_cost'] / row['required_sales'] * 100) if row['required_sales'] > 0 else 0
        }

        if has_actual:
            daily_row['Actual Sales'] = row['actual_sales']
            daily_row['Actual Labor %'] = (row['total_cost'] / row['actual_sales'] * 100)
            daily_row['Variance'] = row['actual_sales'] - row['required_sales']

        daily_data.append(daily_row)

    daily_data_df = pd.DataFrame(daily_data)

    # Display the data
    st.dataframe(
        daily_data_df,
        column_config={
            "Date": st.column_config.TextColumn("Day"),
            "Labor Cost": st.column_config.NumberColumn("Labor Cost", format="$%.2f"),
            "Required Sales": st.column_config.NumberColumn("Required Sales", format="$%.2f"),
            "Projected Labor %": st.column_config.NumberColumn("Projected %", format="%.1f%%"),
            "Actual Sales": st.column_config.NumberColumn("Actual Sales", format="$%.2f"),
            "Actual Labor %": st.column_config.NumberColumn("Actual %", format="%.1f%%"),
            "Variance": st.column_config.NumberColumn("Variance", format="$%.2f")
        },
        use_container_width=True,
        hide_index=True
    )

    # Charts
    st.markdown("<h3 class='section-header'>Labor Cost Visualization</h3>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        # Daily labor cost chart
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.bar(daily_data_df['Date'], daily_data_df['Labor Cost'], color='#3498db')
        ax.set_title('Daily Labor Cost')
        ax.set_xlabel('Day')
        ax.set_ylabel('Labor Cost ($)')

        # Rotate x-axis labels for better readability
        plt.xticks(rotation=45)

        # Add data labels above each bar
        for i, v in enumerate(daily_data_df['Labor Cost']):
            ax.text(i, v + 5, f'${v:.2f}', ha='center')

        plt.tight_layout()
        st.pyplot(fig)

    with col2:
        # Daily required sales chart
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.bar(daily_data_df['Date'], daily_data_df['Required Sales'], color='#2ecc71')

        # Add actual sales line if available
        if 'Actual Sales' in daily_data_df.columns:
            ax2 = ax.twinx()
            ax2.plot(daily_data_df['Date'], daily_data_df['Actual Sales'],
                     marker='o', linestyle='-', color='#e74c3c', linewidth=2)
            ax2.set_ylabel('Actual Sales ($)')

            # Add legend
            ax.legend(['Required Sales'], loc='upper left')
            ax2.legend(['Actual Sales'], loc='upper right')

        ax.set_title('Daily Required Sales to Meet Labor Goal')
        ax.set_xlabel('Day')
        ax.set_ylabel('Required Sales ($)')

        # Rotate x-axis labels for better readability
        plt.xticks(rotation=45)

        # Add data labels above each bar
        for i, v in enumerate(daily_data_df['Required Sales']):
            ax.text(i, v + 5, f'${v:.2f}', ha='center')

        plt.tight_layout()
        st.pyplot(fig)

    # Get detailed employee schedule data for the period
    schedule_data = db.get_schedule(selected_start, selected_end)

    if not schedule_data.empty:
        # Employee breakdown
        st.markdown("<h3 class='section-header'>Employee Labor Cost Breakdown</h3>", unsafe_allow_html=True)

        # Group by employee
        employee_summary = schedule_data.groupby(['employee_id', 'name', 'position', 'pay_type', 'pay_rate']) \
            .agg({'hours': 'sum', 'cost': 'sum', 'overtime': 'sum'}) \
            .reset_index()

        # Rename columns
        employee_summary.columns = ['Employee ID', 'Employee', 'Position', 'Pay Type', 'Pay Rate',
                                    'Total Hours', 'Total Cost', 'Overtime Days']

        # Display the data
        st.dataframe(
            employee_summary,
            column_config={
                "Employee": st.column_config.TextColumn("Employee"),
                "Position": st.column_config.TextColumn("Position"),
                "Pay Type": st.column_config.TextColumn("Pay Type"),
                "Pay Rate": st.column_config.NumberColumn("Pay Rate", format="$%.2f"),
                "Total Hours": st.column_config.NumberColumn("Total Hours", format="%.1f"),
                "Total Cost": st.column_config.NumberColumn("Total Cost", format="$%.2f"),
                "Overtime Days": st.column_config.NumberColumn("Overtime Days")
            },
            use_container_width=True,
            hide_index=True
        )

        # Employee cost visualization
        position_costs = employee_summary.groupby('Position')['Total Cost'].sum().reset_index()

        fig, ax = plt.subplots(figsize=(10, 6))
        ax.pie(position_costs['Total Cost'], labels=position_costs['Position'], autopct='%1.1f%%', startangle=90)
        ax.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle
        plt.title('Labor Cost by Position')
        st.pyplot(fig)

        # Employee hours analysis
        st.markdown("<h3 class='section-header'>Employee Hours Analysis</h3>", unsafe_allow_html=True)

        col1, col2 = st.columns(2)

        with col1:
            # Hours by position
            position_hours = employee_summary.groupby('Position')['Total Hours'].sum().reset_index()

            fig, ax = plt.subplots(figsize=(10, 6))
            bars = ax.bar(position_hours['Position'], position_hours['Total Hours'], color='#3498db')

            # Add data labels
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width() / 2., height + 0.5,
                        f'{height:.1f}', ha='center', va='bottom')

            ax.set_xlabel('Position')
            ax.set_ylabel('Total Hours')
            ax.set_title('Hours by Position')
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()
            st.pyplot(fig)

        with col2:
            # Hours by employee
            top_employees = employee_summary.sort_values('Total Hours', ascending=False).head(10)

            fig, ax = plt.subplots(figsize=(10, 6))
            bars = ax.barh(top_employees['Employee'], top_employees['Total Hours'], color='#2ecc71')

            # Add data labels
            for i, bar in enumerate(bars):
                width = bar.get_width()
                ax.text(width + 0.5, bar.get_y() + bar.get_height() / 2.,
                        f'{width:.1f}', ha='left', va='center')

            ax.set_xlabel('Total Hours')
            ax.set_title('Top Employees by Hours')
            plt.tight_layout()
            st.pyplot(fig)

        # Labor vs Sales Analysis
        if 'Actual Sales' in daily_data_df.columns and not daily_data_df['Actual Sales'].isna().all():
            st.markdown("<h3 class='section-header'>Labor vs Sales Analysis</h3>", unsafe_allow_html=True)

            # Create labor percentage chart
            fig, ax = plt.subplots(figsize=(10, 6))

            # Bar chart for actual sales
            ax.bar(daily_data_df['Date'], daily_data_df['Actual Sales'], color='#3498db', alpha=0.7,
                   label='Actual Sales')

            # Line chart for labor percentage on secondary y-axis
            ax2 = ax.twinx()
            ax2.plot(daily_data_df['Date'], daily_data_df['Actual Labor %'],
                     marker='o', linestyle='-', color='#e74c3c', linewidth=2, label='Labor %')

            # Add target line
            ax2.axhline(y=labor_goal, color='#e74c3c', linestyle='--', label=f'Target ({labor_goal:.1f}%)')

            # Add data labels
            for i, v in enumerate(daily_data_df['Actual Labor %']):
                ax2.text(i, v + 0.5, f'{v:.1f}%', ha='center')

            ax.set_xlabel('Day')
            ax.set_ylabel('Sales ($)')
            ax2.set_ylabel('Labor %')
            ax.set_title('Daily Sales vs Labor %')

            # Combine legends
            lines1, labels1 = ax.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax.legend(lines1 + lines2, labels1 + labels2, loc='upper left')

            plt.xticks(rotation=45)
            plt.tight_layout()
            st.pyplot(fig)

            # Labor efficiency analysis
            if len(daily_data_df) > 0:
                st.markdown("<h4>Labor Efficiency Analysis</h4>", unsafe_allow_html=True)

                # Calculate metrics
                sales_per_labor_hour = 0
                sales_per_labor_dollar = 0

                if not schedule_data.empty and 'hours' in schedule_data.columns:
                    total_hours = schedule_data['hours'].sum()
                    if total_hours > 0:
                        sales_per_labor_hour = daily_data_df['Actual Sales'].sum() / total_hours

                if total_labor_cost > 0:
                    sales_per_labor_dollar = daily_data_df['Actual Sales'].sum() / total_labor_cost

                col1, col2 = st.columns(2)

                with col1:
                    st.metric("Sales per Labor Hour", f"${sales_per_labor_hour:.2f}")

                with col2:
                    st.metric("Sales per Labor Dollar", f"${sales_per_labor_dollar:.2f}")

                st.info("""
                        **Labor Efficiency Guide:**
                        - **Sales per Labor Hour**: Higher values indicate more efficient staffing. Target values vary by restaurant type.
                        - **Sales per Labor Dollar**: Shows how many sales dollars generated for each dollar spent on labor. 
                          Higher values (typically >4) indicate good efficiency.
                        """)

        # Download reports
        st.markdown("<h3 class='section-header'>Download Reports</h3>", unsafe_allow_html=True)

        col1, col2 = st.columns(2)

        with col1:
            # Download labor cost report
            if not labor_costs.empty:
                st.markdown(
                    download_excel(
                        labor_costs,
                        "Labor_Cost_Report",
                        f"Labor_Cost_Report_{selected_start.strftime('%Y%m%d')}_{selected_end.strftime('%Y%m%d')}"
                    ),
                    unsafe_allow_html=True
                )

        with col2:
            # Download schedule
            if not schedule_data.empty:
                st.markdown(
                    download_excel(
                        schedule_data,
                        "Schedule_Report",
                        f"Schedule_Report_{selected_start.strftime('%Y%m%d')}_{selected_end.strftime('%Y%m%d')}"
                    ),
                    unsafe_allow_html=True
                )

        # Labor optimization insights
        st.markdown("<h3 class='section-header'>Labor Optimization Insights</h3>", unsafe_allow_html=True)

        # Generate insights based on the data
        insights = []

        # Check for overtime
        # Check for overtime
        if not schedule_data.empty and 'overtime' in schedule_data.columns:
            overtime_shifts = schedule_data[schedule_data['overtime'] == 1]
            if not overtime_shifts.empty:
                # Calculate overtime cost (must convert Series to scalar values)
                regular_cost = (overtime_shifts['hours'] * overtime_shifts['pay_rate']).sum()
                actual_cost = overtime_shifts['cost'].sum()
                overtime_cost = actual_cost - regular_cost
                insights.append(
                    f"You have {len(overtime_shifts)} shifts with overtime, costing approximately ${overtime_cost:.2f} extra.")
        # Check for high labor percentages
        if 'Actual Labor %' in daily_data_df.columns:
            high_labor_days = daily_data_df[daily_data_df['Actual Labor %'] > labor_goal]
            if not high_labor_days.empty:
                insights.append(
                    f"You have {len(high_labor_days)} days where labor percentage exceeds your goal of {labor_goal}%.")

        # Check for scheduling gaps
        if not employee_summary.empty:
            total_employees = len(employee_summary)
            total_positions = len(employee_summary['Position'].unique())
            if total_employees < 2 * total_positions:
                insights.append(
                    "You may have positions with insufficient backup coverage. Consider cross-training employees.")

        # Display insights
        if insights:
            for insight in insights:
                st.warning(insight)

            st.markdown("""
                    ### Optimization Recommendations:

                    1. **Minimize Overtime**: Schedule employees just under 40 hours when possible to avoid overtime premiums.

                    2. **Match Schedule to Sales**: Adjust staff levels during slower periods to maintain your labor percentage target.

                    3. **Cross-train Staff**: Train employees to handle multiple positions for better schedule flexibility.

                    4. **Stagger Shifts**: Instead of having all staff arrive and leave at the same time, stagger start/end times to match customer flow.

                    5. **Monitor Daily**: Track actual vs. projected labor costs daily to make quick adjustments.
                    """)
        else:
            st.success(
                "Your labor scheduling appears optimized based on the current data. Continue monitoring for further optimization opportunities.")


def staffing_guide_tab():
    """Staffing Guide tab content"""
    st.markdown("<h2 class='sub-header'>Staffing Guide</h2>", unsafe_allow_html=True)

    # Check if labor costs have been calculated
    if 'labor_week_start' in st.session_state and 'labor_week_end' in st.session_state:
        start_date = st.session_state.labor_week_start
        end_date = st.session_state.labor_week_end
    else:
        # Default to current week
        start_date = datetime.now().date() - timedelta(days=datetime.now().weekday())
        end_date = start_date + timedelta(days=6)

    # Date range selector
    col1, col2 = st.columns(2)
    with col1:
        selected_start = st.date_input("Start Date", start_date, key="staffing_start_date")
    with col2:
        selected_end = st.date_input("End Date", end_date, key="staffing_end_date")

    if selected_start > selected_end:
        st.error("End date must be after start date.")
        return

    # Get schedule data
    schedule_data = db.get_schedule(selected_start, selected_end)

    if schedule_data.empty:
        st.warning("No schedule data available for the selected date range.")
        return

    # Generate staffing guide
    st.markdown("""
    <div class='info-box'>
    This staffing guide shows how many employees are scheduled for each position per day. 
    Use this to identify overstaffing, understaffing, or imbalanced coverage across roles.
    </div>
    """, unsafe_allow_html=True)

    # Get restaurant settings for closed days
    settings = db.get_restaurant_settings()
    closed_days = settings['closed_days']

    # Create a staffing summary
    # First, get all dates in the range
    date_range = [selected_start + timedelta(days=i) for i in range((selected_end - selected_start).days + 1)]
    date_strs = [d.strftime('%a %m/%d') for d in date_range]

    # Filter out closed days
    open_dates = [d for d in date_range if d.strftime('%a') not in closed_days]
    open_date_strs = [d.strftime('%a %m/%d') for d in open_dates]

    if not open_dates:
        st.info("There are no open days in the selected date range.")
        return

    # Get all positions
    all_positions = schedule_data['position'].unique()

    # Create staffing dataframe
    staffing_data = []

    for date_obj in open_dates:
        date_str = date_obj.strftime('%a %m/%d')
        day_staff = {'Day': date_str}

        # Filter schedule data for this date
        day_schedule = schedule_data[pd.to_datetime(schedule_data['date']).dt.date == date_obj]

        # Count staff by position
        for position in all_positions:
            position_count = day_schedule[day_schedule['position'] == position]
            # Only count entries with hours > 0
            staff_count = len(position_count[position_count['hours'] > 0])
            day_staff[position] = staff_count

        staffing_data.append(day_staff)

    # Create DataFrame
    if staffing_data:
        staffing_df = pd.DataFrame(staffing_data)

        # Fill NaN values with 0
        staffing_df = staffing_df.fillna(0)

        # Display the staffing guide
        st.markdown("<h3 class='section-header'>Daily Staffing by Position</h3>", unsafe_allow_html=True)
        st.dataframe(staffing_df, use_container_width=True, hide_index=True)

        # Staffing visualization
        st.markdown("<h3 class='section-header'>Staffing Visualization</h3>", unsafe_allow_html=True)

        # Create a stacked bar chart
        fig, ax = plt.subplots(figsize=(12, 6))
        bottom = np.zeros(len(staffing_df))

        # Create a colormap for positions
        position_colors = plt.cm.viridis(np.linspace(0, 1, len(all_positions)))

        for i, position in enumerate(all_positions):
            if position in staffing_df.columns:
                values = staffing_df[position].values
                ax.bar(staffing_df['Day'], values, bottom=bottom, label=position, color=position_colors[i])

                # Add data labels at the center of each segment
                for j, v in enumerate(values):
                    if v > 0:  # Only add label if there's a value
                        ax.text(j, bottom[j] + v / 2, int(v), ha='center', va='center',
                                color='white', fontweight='bold')

                bottom += values

        ax.set_title('Daily Staffing by Position')
        ax.set_xlabel('Day')
        ax.set_ylabel('Number of Staff')
        ax.legend(title='Position')

        plt.xticks(rotation=45)
        plt.tight_layout()
        st.pyplot(fig)

        # Staffing analysis
        st.markdown("<h3 class='section-header'>Staffing Analysis</h3>", unsafe_allow_html=True)

        col1, col2 = st.columns(2)

        with col1:
            # Calculate daily staffing levels
            staffing_df['Total Staff'] = staffing_df.drop('Day', axis=1).sum(axis=1)

            # Calculate average staff per day of week
            staffing_df['Day of Week'] = [d.strftime('%a') for d in open_dates]
            day_avg = staffing_df.groupby('Day of Week')['Total Staff'].mean().reset_index()

            # Sort by day of week
            day_order = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            day_avg['Day of Week'] = pd.Categorical(day_avg['Day of Week'], categories=day_order, ordered=True)
            day_avg = day_avg.sort_values('Day of Week')

            fig, ax = plt.subplots(figsize=(10, 6))
            bars = ax.bar(day_avg['Day of Week'], day_avg['Total Staff'], color='#3498db')

            # Add data labels
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width() / 2., height + 0.1,
                        f'{height:.1f}', ha='center', va='bottom')

            ax.set_xlabel('Day of Week')
            ax.set_ylabel('Average Staff Count')
            ax.set_title('Average Staff by Day of Week')
            plt.tight_layout()
            st.pyplot(fig)

        with col2:
            # Position distribution across the week
            position_totals = staffing_df.drop(['Day', 'Day of Week', 'Total Staff'], axis=1).sum()
            position_percentage = position_totals / position_totals.sum() * 100

            position_data = pd.DataFrame({
                'Position': position_totals.index,
                'Staff Count': position_totals.values,
                'Percentage': position_percentage.values
            })

            fig, ax = plt.subplots(figsize=(10, 6))
            pie = ax.pie(position_data['Staff Count'], labels=position_data['Position'],
                         autopct='%1.1f%%', startangle=90, colors=position_colors)
            ax.axis('equal')
            plt.title('Position Distribution')
            st.pyplot(fig)

        # Staffing efficiency analysis
        st.markdown("<h3 class='section-header'>Staffing Efficiency Analysis</h3>", unsafe_allow_html=True)

        # Get sales data if available
        labor_costs = db.get_labor_costs(selected_start, selected_end)

        if not labor_costs.empty and 'actual_sales' in labor_costs.columns and not labor_costs[
            'actual_sales'].isna().all():
            # Merge staffing data with sales data
            merged_data = []

            for i, row in staffing_df.iterrows():
                day_obj = open_dates[i]
                day_data = labor_costs[pd.to_datetime(labor_costs['date']).dt.date == day_obj]

                if not day_data.empty and pd.notna(day_data.iloc[0]['actual_sales']):
                    sales = day_data.iloc[0]['actual_sales']
                    staff_count = row['Total Staff']

                    merged_data.append({
                        'Day': row['Day'],
                        'Staff Count': staff_count,
                        'Sales': sales,
                        'Sales per Staff': sales / staff_count if staff_count > 0 else 0
                    })

            if merged_data:
                merged_df = pd.DataFrame(merged_data)

                col1, col2 = st.columns(2)

                with col1:
                    st.metric("Avg Sales per Staff Member",
                              f"${merged_df['Sales per Staff'].mean():.2f}",
                              help="Higher values indicate more efficient staffing")

                with col2:
                    # Calculate correlation between staff count and sales
                    corr = merged_df['Staff Count'].corr(merged_df['Sales'])
                    st.metric("Staff-Sales Correlation",
                              f"{corr:.2f}",
                              help="Values closer to 1.0 indicate better staffing alignment with sales")

                # Plot Sales per Staff
                fig, ax = plt.subplots(figsize=(10, 6))
                ax.bar(merged_df['Day'], merged_df['Sales per Staff'], color='#2ecc71')
                ax.set_title('Sales per Staff Member by Day')
                ax.set_xlabel('Day')
                ax.set_ylabel('Sales per Staff ($)')

                # Add average line
                avg_sales_per_staff = merged_df['Sales per Staff'].mean()
                ax.axhline(y=avg_sales_per_staff, color='#e74c3c', linestyle='--',
                           label=f'Average (${avg_sales_per_staff:.2f})')

                # Add data labels
                for i, v in enumerate(merged_df['Sales per Staff']):
                    ax.text(i, v + 100, f'${v:.2f}', ha='center')

                plt.xticks(rotation=45)
                ax.legend()
                plt.tight_layout()
                st.pyplot(fig)

                # Show staffing recommendations
                st.markdown("<h4>Staffing Recommendations</h4>", unsafe_allow_html=True)

                # Calculate optimal staff based on average sales per staff member
                optimal_staffing = []

                for i, row in merged_df.iterrows():
                    current_staff = row['Staff Count']
                    sales = row['Sales']
                    optimal_staff = round(sales / avg_sales_per_staff) if avg_sales_per_staff > 0 else 0

                    change = optimal_staff - current_staff

                    optimal_staffing.append({
                        'Day': row['Day'],
                        'Current Staff': current_staff,
                        'Optimal Staff': optimal_staff,
                        'Difference': change,
                        'Action': 'Increase' if change > 0 else ('Decrease' if change < 0 else 'No Change')
                    })

                optimal_df = pd.DataFrame(optimal_staffing)

                # Display the optimal staffing table
                st.dataframe(
                    optimal_df,
                    column_config={
                        'Day': st.column_config.TextColumn('Day'),
                        'Current Staff': st.column_config.NumberColumn('Current Staff'),
                        'Optimal Staff': st.column_config.NumberColumn('Optimal Staff'),
                        'Difference': st.column_config.NumberColumn('Difference'),
                        'Action': st.column_config.TextColumn('Recommended Action')
                    },
                    use_container_width=True,
                    hide_index=True
                )

                st.markdown("""
                **Staffing Optimization Tips:**

                1. **Balance Staff Count**: Adjust your staffing levels based on the recommendations above to maintain consistent sales per staff member.

                2. **Shift Timing**: Even if staff count is optimal, make sure shifts are aligned with peak business hours.

                3. **Cross-Training**: Ensure staff can handle multiple positions to increase flexibility.

                4. **Regular Monitoring**: Review this staffing guide weekly as business patterns change.
                """)
            else:
                st.info("Not enough sales data to generate staffing efficiency analysis.")
        else:
            st.info("Enter actual sales data in the Reports tab to enable staffing efficiency analysis.")

        # Download staffing guide
        st.markdown("<h3 class='section-header'>Download Staffing Guide</h3>", unsafe_allow_html=True)
        st.markdown(download_excel(staffing_df, "Staffing_Guide",
                                   f"Staffing_Guide_{selected_start.strftime('%Y%m%d')}_{selected_end.strftime('%Y%m%d')}"),
                    unsafe_allow_html=True)

        # Advanced position-specific guide
        with st.expander("Position-Specific Staffing Recommendations"):
            st.markdown("### Position Requirements by Day")

            # Create a more detailed guide for each position with justifications
            for position in all_positions:
                if position in staffing_df.columns:
                    st.markdown(f"#### {position} Staffing")

                    # Calculate average staff for this position by day of week
                    position_by_day = staffing_df.groupby('Day of Week')[position].mean().reset_index()
                    position_by_day['Day of Week'] = pd.Categorical(
                        position_by_day['Day of Week'], categories=day_order, ordered=True)
                    position_by_day = position_by_day.sort_values('Day of Week')

                    # Create position-specific bar chart
                    fig, ax = plt.subplots(figsize=(10, 4))
                    bars = ax.bar(position_by_day['Day of Week'], position_by_day[position], color='#9b59b6')

                    # Add data labels
                    for bar in bars:
                        height = bar.get_height()
                        ax.text(bar.get_x() + bar.get_width() / 2., height + 0.05,
                                f'{height:.1f}', ha='center', va='bottom')

                    ax.set_xlabel('Day of Week')
                    ax.set_ylabel('Average Staff Count')
                    ax.set_title(f'Average {position} Staff by Day')
                    plt.tight_layout()
                    st.pyplot(fig)

                    # Provide position-specific recommendations
                    if position == 'Manager':
                        st.markdown("""
                        - Ensure at least one manager is scheduled for all operating hours
                        - Consider overlapping managers during peak periods for better supervision
                        - Reduce to minimal coverage during historically slow periods
                        """)
                    elif position in ['Chef', 'Cook']:
                        st.markdown("""
                        - Scale kitchen staff based on projected sales volume
                        - Stagger shift start/end times for prep and clean-up
                        - Consider having at least one experienced cook at all times
                        """)
                    elif position in ['Server', 'Bartender', 'Host']:
                        st.markdown("""
                        - Front-of-house staff should be scheduled based on projected customer count
                        - Use hourly sales data to identify peak periods requiring additional staffing
                        - Schedule strongest servers during busiest shifts and highest-revenue sections
                        """)
                    else:
                        st.markdown("""
                        - Schedule based on operational needs and historic patterns
                        - Consider cross-training with other positions for better flexibility
                        - Adjust staffing based on overall business volume
                        """)
    else:
        st.warning("No staffing data available for the selected date range.")
