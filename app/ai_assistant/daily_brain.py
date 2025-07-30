# File: app/ai_assistant/daily_brain.py
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import calendar

INSTANCE_PATH = Path(__file__).parents[2] / 'instance' / 'reports' / 'daily_checkins.xlsx'
STATIC_PATH   = Path(__file__).parents[1] / 'static'   / 'reports' / 'daily_checkins.xlsx'


def load_sheets() -> dict:
    for path in (INSTANCE_PATH, STATIC_PATH):
        try:
            xl = pd.ExcelFile(path)
            break
        except Exception:
            continue
    else:
        raise FileNotFoundError(f"Can't open daily_checkins.xlsx at {INSTANCE_PATH} or {STATIC_PATH}")

    data = {}
    for sheet in xl.sheet_names:
        df = xl.parse(sheet)
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        data[sheet] = df
    return data


def summarize_sales(df: pd.DataFrame) -> dict:
    df = df.copy()
    df['Revenue'] = pd.to_numeric(df['Revenue'], errors='coerce').fillna(0)
    df['Date_only'], df['Month'], df['Year'] = df['Date'].dt.date, df['Date'].dt.to_period('M'), df['Date'].dt.year
    daily   = df.groupby('Date_only')['Revenue'].sum().reset_index()
    monthly = df.groupby('Month')['Revenue'].sum().reset_index().rename(columns={'Month':'Period'})
    yearly  = df.groupby('Year')['Revenue'].sum().reset_index().rename(columns={'Year':'Period'})
    return {'daily': daily, 'monthly': monthly, 'yearly': yearly}


def summarize_counts(df: pd.DataFrame) -> dict:
    df = df.copy()
    df['Date_only'], df['Month'], df['Year'] = df['Date'].dt.date, df['Date'].dt.to_period('M'), df['Date'].dt.year
    daily   = df.groupby('Date_only').size().reset_index(name='count')
    monthly = df.groupby('Month').size().reset_index(name='count').rename(columns={'Month':'Period'})
    yearly  = df.groupby('Year').size().reset_index(name='count').rename(columns={'Year':'Period'})
    return {'daily': daily, 'monthly': monthly, 'yearly': yearly}


def summarize_attendance(df: pd.DataFrame) -> dict:
    df = df.copy()
    df['Attended'] = pd.to_numeric(df.get('Attended', 0), errors='coerce').fillna(0)
    df['No-Show']  = pd.to_numeric(df.get('No-Show',0), errors='coerce').fillna(0)
    df['Date_only'], df['Month'], df['Year'] = df['Date'].dt.date, df['Date'].dt.to_period('M'), df['Date'].dt.year
    daily   = df.groupby('Date_only')[['Attended','No-Show']].sum().reset_index()
    monthly = df.groupby('Month')[['Attended','No-Show']].sum().reset_index().rename(columns={'Month':'Period'})
    yearly  = df.groupby('Year')[['Attended','No-Show']].sum().reset_index().rename(columns={'Year':'Period'})
    return {'daily': daily, 'monthly': monthly, 'yearly': yearly}


def detect_opportunity_patterns(df: pd.DataFrame) -> pd.DataFrame:
    counts = df['Name'].value_counts()
    dup    = counts[counts>1].reset_index()
    dup.columns = ['Name','Count']
    return dup


def compute_comparisons(daily_df: pd.DataFrame, n_days: int=14) -> list:
    df = daily_df.copy().sort_values('Date_only').tail(n_days).reset_index(drop=True)
    df['Prev']  = df['Revenue'].shift(1).fillna(0)
    df['Delta'] = df['Revenue'] - df['Prev']
    df['PctΔ']  = df.apply(lambda r:(r['Delta']/r['Prev']*100) if r['Prev']>0 else 0, axis=1)
    df['Date']  = df['Date_only'].astype(str)
    return df[['Date','Revenue','Delta','PctΔ']].to_dict(orient='records')


def run_full_summary() -> dict:
    data       = load_sheets()
    sales      = summarize_sales(data['Sales'])
    leads      = summarize_counts(data['Leads'])
    consults   = summarize_counts(data['Consultations'])
    opps       = summarize_counts(data['Opportunities'])
    attendance = summarize_attendance(data['Attendance'])
    duplicates = detect_opportunity_patterns(data['Opportunities'])

    ms = sales['monthly'].copy()
    ms['Growth%'] = ms['Revenue'].pct_change()*100
    ms['Period']  = ms['Period'].astype(str)
    revenue_growth = ms[['Period','Growth%']].to_dict(orient='records')

    lm = leads['monthly'].copy().rename(columns={'count':'Leads'})
    cm = consults['monthly'].copy().rename(columns={'count':'Consultations'})
    cv = pd.merge(lm, cm, on='Period', how='outer').fillna(0)
    cv['Conversion%'] = cv.apply(lambda r:(r['Consultations']/r['Leads']*100) if r['Leads']>0 else 0, axis=1)
    lead_conv = cv[['Period','Conversion%']].to_dict(orient='records')

    return {
      'sales': sales,
      'leads': leads,
      'consultations': consults,
      'opportunities': opps,
      'attendance': attendance,
      'opportunity_duplicates': duplicates,
      'revenue_growth': revenue_growth,
      'lead_conversion_rate': lead_conv,
      'sales_trends': compute_comparisons(sales['daily'],n_days=14)
    }


def summarize_for_date(target_date: str) -> str:
    """
    One-day summary + day-over-day comparison + full metrics + detailed rows.
    """
    try:
        date_obj = datetime.fromisoformat(target_date).date()
    except Exception:
        return f"Invalid date format: {target_date}. Use YYYY-MM-DD."

    summary = run_full_summary()
    sales_df = summary['sales']['daily']
    if sales_df.empty:
        return "No sales data available."

    today_row = sales_df[sales_df['Date_only'] == date_obj]
    if today_row.empty:
        return f"No data for {date_obj}."

    revenue = float(today_row['Revenue'].iloc[0])
    y_date  = date_obj - timedelta(days=1)
    y_row   = sales_df[sales_df['Date_only'] == y_date]
    if y_row.empty:
        delta_str = "(no prior day)"
    else:
        y_rev     = float(y_row['Revenue'].iloc[0])
        diff      = revenue - y_rev
        pct       = (diff / y_rev * 100) if y_rev else 0
        direction = "up" if diff >= 0 else "down"
        delta_str = f"{direction.title()} ${abs(diff):,.2f} ({pct:+.1f}%) vs {y_date}"

    bullets = [
        f"Metrics for {date_obj}:",
        f"- Sales: ${revenue:,.2f}",
        f"- Comparison: {delta_str}",
        f"- Leads: {summary['leads']['daily'].loc[summary['leads']['daily']['Date_only'] == date_obj, 'count'].sum()}",
        f"- Consultations: {summary['consultations']['daily'].loc[summary['consultations']['daily']['Date_only'] == date_obj, 'count'].sum()}",
        f"- Opportunities: {summary['opportunities']['daily'].loc[summary['opportunities']['daily']['Date_only'] == date_obj, 'count'].sum()}",
        f"- Attendance: {summary['attendance']['daily'].loc[summary['attendance']['daily']['Date_only'] == date_obj, 'Attended'].sum()} present, {summary['attendance']['daily'].loc[summary['attendance']['daily']['Date_only'] == date_obj, 'No-Show'].sum()} no-shows"
    ]

    bullets.append("\nDetailed rows:")
    raw = {}
    try:
        raw = load_sheets()
    except Exception:
        pass

    for sheet_name, df_raw in raw.items():
        df = df_raw.copy()
        df['Date_only'] = pd.to_datetime(df['Date'], errors='coerce').dt.date
        df_date = df[df['Date_only'] == date_obj]
        if df_date.empty:
            bullets.append(f"{sheet_name}: No records.")
        else:
            bullets.append(f"{sheet_name} records:")
            for rec in df_date.to_dict(orient='records'):
                rec_str = ", ".join(f"{k}={v}" for k, v in rec.items())
                bullets.append(f"- {rec_str}")

    return "\n".join(bullets)


def summarize_range(start_date: str, end_date: str) -> str:
    """Summary for an arbitrary date range."""
    try:
        start = datetime.fromisoformat(start_date).date()
        end   = datetime.fromisoformat(end_date).date()
    except Exception:
        return f"Invalid date format: use YYYY-MM-DD for both start and end"
    if start > end:
        start, end = end, start

    summary = run_full_summary()
    sales_df = summary['sales']['daily']
    mask_sales = (sales_df['Date_only'] >= start) & (sales_df['Date_only'] <= end)
    total_sales = sales_df.loc[mask_sales, 'Revenue'].sum()

    leads_df = summary['leads']['daily']
    total_leads = int(leads_df.loc[mask_sales, 'count'].sum()) if 'count' in leads_df.columns else 0

    cons_df = summary['consultations']['daily']
    total_consults = int(cons_df.loc[mask_sales, 'count'].sum()) if 'count' in cons_df.columns else 0

    opps_df = summary['opportunities']['daily']
    total_opps = int(opps_df.loc[mask_sales, 'count'].sum()) if 'count' in opps_df.columns else 0

    att_df = summary['attendance']['daily']
    mask_att = (att_df['Date_only'] >= start) & (att_df['Date_only'] <= end)
    total_attended = int(att_df.loc[mask_att, 'Attended'].sum()) if 'Attended' in att_df.columns else 0
    total_noshow   = int(att_df.loc[mask_att, 'No-Show'].sum()) if 'No-Show' in att_df.columns else 0

    bullets = [
        f"Metrics from {start} to {end}:",
        f"- Total Sales: ${total_sales:,.2f}",
        f"- Total Leads: {total_leads}",
        f"- Total Consultations: {total_consults}",
        f"- Total Opportunities: {total_opps}",
        f"- Total Attendance: {total_attended} present, {total_noshow} no-shows"
    ]

    return "\n".join(bullets)
