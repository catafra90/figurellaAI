from flask import Blueprint, render_template, request, redirect, url_for, flash

consultation_bp = Blueprint(
    "consultation",
    __name__,
    url_prefix="/consultation"
)  # no template_folder override needed

@consultation_bp.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        first = (request.form.get("first_name") or "").strip()
        last  = (request.form.get("last_name") or "").strip()
        if not first and not last:
            flash("Please enter at least a first or last name.", "warning")
            return render_template("consultation/index.html", first=first, last=last)
        flash(f"Captured: {first} {last}".strip(), "success")
        return redirect(url_for("consultation.index"))

    return render_template("consultation/index.html")
