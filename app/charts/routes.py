from flask import Blueprint, render_template

charts_bp = Blueprint('charts', __name__, template_folder='templates')

@charts_bp.route('/charts')
def dashboard():
    return render_template('charts/dashboard.html', active_page='charts')

@charts_bp.route('/')
def index():
    return render_template('index.html', active_page='home')

