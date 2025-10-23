import os
from openai import OpenAI, OpenAIError
import pandas as pd

# Instantiate new v1 OpenAI client (reads OPENAI_API_KEY from env)
client = OpenAI()
# Default ChatGPT model
MODEL = os.getenv("GPT_MODEL", "gpt-3.5-turbo")


def summarize_data(summary: dict, temperature: float = 0.5) -> str:
    """
    Generate three sections:
    1) Historical trend stats (14-day average, high, low)
    2) Raw bullet summary of today's metrics
    3) GPT-powered commentary comparing today vs. yesterday
    """
    # Extract 14-day sales trend data
    trends = summary.get("sales_trends", [])
    if len(trends) < 2:
        return "Not enough data for summary and comparison."

    # Build trend statistics
    trends_df = pd.DataFrame(trends)
    avg_rev = trends_df['Revenue'].mean()
    max_rev = trends_df['Revenue'].max()
    min_rev = trends_df['Revenue'].min()
    trend_section = (
        f"Over the last {len(trends)} days:\n"
        f"- Average daily revenue: ${avg_rev:,.2f}\n"
        f"- Highest daily revenue: ${max_rev:,.2f}\n"
        f"- Lowest daily revenue: ${min_rev:,.2f}\n\n"
    )

    yesterday = trends[-2]
    today     = trends[-1]
    date      = today.get("Date")
    rev       = today.get("Revenue", 0)

    # Helper to fetch counts
    def _count(df_key, col="count"):
        df = summary.get(df_key, {}).get("daily")
        if df is None or df.empty:
            return 0
        return int(df.loc[df["Date_only"].astype(str) == date, col].sum())

    leads         = _count("leads")
    consults      = _count("consultations")
    opportunities = _count("opportunities")
    att_df        = summary.get("attendance", {}).get("daily")
    row           = att_df.loc[att_df["Date_only"].astype(str) == date] if att_df is not None else None
    attended      = int(row["Attended"].sum()) if row is not None else 0
    noshow        = int(row["No-Show"].sum()) if row is not None else 0

    # Build raw bullet summary
    raw = (
        f"Metrics for {date}:\n"
        f"- Total sales: ${rev:,.2f}\n"
        f"- Leads: {leads}\n"
        f"- Consultations: {consults}\n"
        f"- Opportunities: {opportunities}\n"
        f"- Attendance: {attended} present, {noshow} no-shows\n\n"
    )

    # Compute deltas
    delta   = rev - yesterday.get("Revenue", 0)
    pct     = (delta / yesterday.get("Revenue") * 100) if yesterday.get("Revenue") else 0
    dir_str = "up" if delta >= 0 else "down"
    comp    = (
        f"Day-over-day: {dir_str.title()} ${abs(delta):,.2f} ({pct:+.1f}%) "
        f"compared to {yesterday.get('Date')}\n\n"
    )

    # Prompt for GPT commentary
    prompt = (
        "You are a gym analytics assistant. Here are the trend stats, today's metrics, and comparison:\n\n"
        + trend_section
        + raw
        + comp
        + "Please provide a concise commentary highlighting key insights and actionable suggestions."
    )

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "Provide clear, actionable gym performance commentary based on metrics."},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=250
        )
        commentary = resp.choices[0].message.content.strip()
    except OpenAIError:
        commentary = "Unable to generate commentary at this time."

    # Combine and return full summary
    return trend_section + raw + comp + commentary


def suggest_ideas(description: str, n_ideas: int = 5, temperature: float = 0.7) -> list[str]:
    """
    Given an opportunity description, return a list of actionable ideas.
    """
    prompt = (
        f"You are a creative gym strategist. Suggest {n_ideas} actionable ideas based on this opportunity:\n"
        f"{description}\nIdeas:"
    )
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "Generate focused gym business ideas."},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=200
        )
        content = resp.choices[0].message.content
    except OpenAIError:
        return ["No ideas available at this time."]

    ideas = []
    for line in content.splitlines():
        text = line.lstrip('0123456789. ').strip()
        if text:
            ideas.append(text)
    return ideas or [content]


def analyze_trends_and_suggest(summary: dict, temperature: float = 0.7) -> str:
    """
    Provide strategic insights based on multi-month trend data.
    """
    rev_growth = summary.get("revenue_growth", [])
    lead_conv  = summary.get("lead_conversion_rate", [])
    prompt = (
        "You are a gym business analyst.\n"
        f"Recent MoM revenue growth: {rev_growth}\n"
        f"Recent lead->consult conversion rates: {lead_conv}\n"
        "1) Top 3 strategic opportunities?\n"
        "2) Three tactical actions to improve metrics."
    )
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "Provide actionable gym strategy based on data."},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=300
        )
        return resp.choices[0].message.content.strip()
    except OpenAIError:
        return "Unable to perform deep analysis at this time."
