import pandas as pd


def summarize_data(summary: dict, temperature: float = 0.5) -> str:
    """
    Offline version – NO OpenAI.
    Generate three sections:
    1) Historical trend stats (14-day style: avg / high / low)
    2) Raw bullet summary of today's metrics
    3) Simple rule-based commentary comparing today vs. yesterday
    """
    trends = summary.get("sales_trends", [])
    if len(trends) < 2:
        return "Not enough data for summary and comparison."

    # ---- 1) Trend statistics ----
    trends_df = pd.DataFrame(trends)
    avg_rev = trends_df["Revenue"].mean()
    max_rev = trends_df["Revenue"].max()
    min_rev = trends_df["Revenue"].min()

    trend_section = (
        f"Over the last {len(trends)} days:\n"
        f"- Average daily revenue: ${avg_rev:,.2f}\n"
        f"- Highest daily revenue: ${max_rev:,.2f}\n"
        f"- Lowest daily revenue: ${min_rev:,.2f}\n\n"
    )

    # ---- 2) Today's raw metrics ----
    yesterday = trends[-2]
    today = trends[-1]
    date = today.get("Date")
    rev = today.get("Revenue", 0) or 0

    def _count(df_key, col="count"):
        df = summary.get(df_key, {}).get("daily")
        if df is None or df.empty:
            return 0
        return int(df.loc[df["Date_only"].astype(str) == str(date), col].sum())

    leads = _count("leads")
    consults = _count("consultations")
    opportunities = _count("opportunities")

    att_df = summary.get("attendance", {}).get("daily")
    row = (
        att_df.loc[att_df["Date_only"].astype(str) == str(date)]
        if att_df is not None
        else None
    )
    attended = int(row["Attended"].sum()) if row is not None else 0
    noshow = int(row["No-Show"].sum()) if row is not None else 0

    raw = (
        f"Metrics for {date}:\n"
        f"- Total sales: ${rev:,.2f}\n"
        f"- Leads: {leads}\n"
        f"- Consultations: {consults}\n"
        f"- Opportunities: {opportunities}\n"
        f"- Attendance: {attended} present, {noshow} no-shows\n\n"
    )

    # ---- 3) Simple commentary vs yesterday ----
    y_rev = yesterday.get("Revenue", 0) or 0
    delta = rev - y_rev
    pct = (delta / y_rev * 100) if y_rev else 0
    dir_str = "up" if delta >= 0 else "down"

    comp = (
        f"Day-over-day: {dir_str.title()} ${abs(delta):,.2f} ({pct:+.1f}%) "
        f"compared to {yesterday.get('Date')}\n\n"
    )

    # Rule-based commentary (no AI)
    commentary_lines = []

    # Revenue vs average
    if rev >= avg_rev * 1.1:
        commentary_lines.append(
            "Great revenue day: today is clearly above the recent average."
        )
    elif rev <= avg_rev * 0.9:
        commentary_lines.append(
            "Revenue is below the recent average – consider pushing follow-ups and upsells."
        )
    else:
        commentary_lines.append(
            "Revenue is roughly in line with the recent average."
        )

    # Leads and consultations quality
    if leads > 0:
        conv_rate = (consults / leads * 100) if leads else 0
        if conv_rate >= 60:
            commentary_lines.append(
                f"Lead → consultation conversion is strong at about {conv_rate:.0f}%."
            )
        elif conv_rate > 0:
            commentary_lines.append(
                f"Lead → consultation conversion is around {conv_rate:.0f}%; "
                "review lead quality and booking scripts."
            )
        else:
            commentary_lines.append(
                "Leads were generated but none converted to consultations – review booking process."
            )

    # Attendance and no-shows
    total_booked = attended + noshow
    if total_booked > 0:
        no_show_rate = noshow / total_booked * 100
        if no_show_rate >= 20:
            commentary_lines.append(
                f"No-show rate is high at about {no_show_rate:.0f}%; "
                "tighten reminders and confirmation messages."
            )
        else:
            commentary_lines.append(
                f"No-show rate is reasonable at about {no_show_rate:.0f}%."
            )

    if not commentary_lines:
        commentary_lines.append(
            "No strong signals today – keep monitoring trends over the next few days."
        )

    commentary = "Commentary (offline mode):\n- " + "\n- ".join(commentary_lines) + "\n"

    return trend_section + raw + comp + commentary


def suggest_ideas(description: str, n_ideas: int = 5, temperature: float = 0.7) -> list[str]:
    """
    Offline version – NO OpenAI.
    Return a list of heuristic ideas based on keywords in the description.
    """
    desc_lower = (description or "").lower()
    ideas: list[str] = []

    if "lead" in desc_lower:
        ideas.extend(
            [
                "Set a daily target of new leads per channel (walk-ins, referrals, social).",
                "Add a simple lead magnet (free trial or assessment) to increase opt-ins.",
                "Review scripts used when contacting leads and tighten the call-to-action.",
            ]
        )

    if "retention" in desc_lower or "churn" in desc_lower:
        ideas.extend(
            [
                "Identify at-risk clients (low attendance) and schedule check-in calls.",
                "Launch a 4-week engagement challenge with small rewards for consistency.",
            ]
        )

    if "referral" in desc_lower:
        ideas.extend(
            [
                "Offer a clear ‘bring-a-friend’ referral bonus for both client and guest.",
                "Ask happy clients for referrals right after strong results or milestones.",
            ]
        )

    if not ideas:
        # Generic fallback ideas
        ideas = [
            "Increase proactive follow-ups with today’s leads and consultations.",
            "Review pricing and packages to highlight the most attractive options.",
            "Run a short-time promotion to reactivate inactive or low-attendance clients.",
            "Ask top clients for testimonials and use them in your communication.",
            "Block focused time each week to review KPIs and adjust actions.",
        ]

    return ideas[: max(1, n_ideas)]


def analyze_trends_and_suggest(summary: dict, temperature: float = 0.7) -> str:
    """
    Offline version – NO OpenAI.
    Provide simple strategic insight based on revenue growth and lead conversion arrays.
    """
    rev_growth = summary.get("revenue_growth", []) or []
    lead_conv = summary.get("lead_conversion_rate", []) or []

    text = []

    # Revenue growth
    if rev_growth:
        avg_growth = sum(rev_growth) / len(rev_growth)
        text.append(f"Average month-over-month revenue growth: {avg_growth:+.1f}%.")

        if avg_growth > 5:
            text.append(
                "Revenue trend is positive – consider reinvesting in marketing and staff training."
            )
        elif avg_growth < -5:
            text.append(
                "Revenue trend is negative – review pricing, offers, and lead flow urgently."
            )
        else:
            text.append(
                "Revenue is relatively stable – small optimizations in conversion and retention may help."
            )
    else:
        text.append("No revenue growth data available.")

    # Lead conversion
    if lead_conv:
        avg_conv = sum(lead_conv) / len(lead_conv)
        text.append(f"Average lead → consult conversion: {avg_conv:.1f}%.")

        if avg_conv >= 60:
            text.append(
                "Lead conversion is strong – focus now on closing consultations and increasing ticket size."
            )
        elif avg_conv >= 30:
            text.append(
                "Conversion is decent but has room to improve – refine scripts and qualify leads better."
            )
        else:
            text.append(
                "Conversion is low – audit lead sources and the first contact process."
            )
    else:
        text.append("No lead conversion data available.")

    # Tactical actions
    text.append("")
    text.append("Suggested tactical actions:")
    text.append(
        "- Schedule weekly reviews of leads, consultations, and attendance KPIs."
    )
    text.append(
        "- Implement or tighten reminder workflows (SMS/email) for consultations and sessions."
    )
    text.append(
        "- Identify top-performing offers or channels and double down on them."
    )

    return "\n".join(text)
