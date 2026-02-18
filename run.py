import sys
import os

# Projeyi path'e ekle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from functools import wraps
from app.database import test_query, get_kpi_stats, get_chart_data, get_comparison_data, get_filter_options, get_personel_details, get_arac_details

app = Flask(__name__)
app.secret_key = 'sasa-secret-key-2026-adanakebap'

# Custom Jinja2 filter: Verimlilik yüzdelerini max 100 ile sınırla
@app.template_filter('cap_percentage')
def cap_percentage(value):
    """Yüzde değerini maksimum 100 ile sınırla"""
    try:
        val = float(value)
        return min(val, 100.0)
    except (ValueError, TypeError):
        return 0.0

# Hardcoded kullanıcı bilgileri
USERNAME = 'sasa@control-ix.com'
PASSWORD = 'sasa123'

def login_required(f):
    """Login kontrolü için decorator"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login sayfası"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == USERNAME and password == PASSWORD:
            session['logged_in'] = True
            session['username'] = username
            flash('Başarıyla giriş yaptınız!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Kullanıcı adı veya şifre hatalı!', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Çıkış yap"""
    session.clear()
    flash('Çıkış yaptınız.', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    from datetime import datetime, timedelta
    
    # Filtreleri al
    filters = {}
    
    # Quick Filter: Performans optimizasyonu - Default: Hiçbiri (ultra hızlı ilk yükleme)
    quick_filter = request.args.get('quick_filter', 'none')  # none, today, week, month, year, custom
    
    # Eğer hiçbir filtre seçilmemişse veri çekme
    if quick_filter == 'none':
        return render_template('index.html', 
                             db_status=True, 
                             db_message="Filtre seçin", 
                             data=None,
                             kpis={},
                             chart_data=[],
                             comparison_data=[],
                             filter_options={'devices': [], 'drivers': [], 'isletme_list': [], 'sbu_list': []},
                             current_filters={},
                             quick_filter=quick_filter)
    
    # Tarih hesapla
    today = datetime.now()
    
    if quick_filter == 'today':
        # Bugün (Default - En hızlı)
        filters['start_date'] = today.strftime('%Y-%m-%d')
        filters['end_date'] = today.strftime('%Y-%m-%d')
    elif quick_filter == 'week':
        # Son 7 gün
        filters['start_date'] = (today - timedelta(days=7)).strftime('%Y-%m-%d')
        filters['end_date'] = today.strftime('%Y-%m-%d')
    elif quick_filter == 'month':
        # Son 30 gün
        filters['start_date'] = (today - timedelta(days=30)).strftime('%Y-%m-%d')
        filters['end_date'] = today.strftime('%Y-%m-%d')
    elif quick_filter == 'year':
        # Son 365 gün
        filters['start_date'] = (today - timedelta(days=365)).strftime('%Y-%m-%d')
        filters['end_date'] = today.strftime('%Y-%m-%d')
    elif quick_filter == 'custom':
        # Özel tarih aralığı
        if request.args.get('start_date'):
            filters['start_date'] = request.args.get('start_date')
        else:
            filters['start_date'] = today.strftime('%Y-%m-%d')
        
        if request.args.get('end_date'):
            filters['end_date'] = request.args.get('end_date')
        else:
            filters['end_date'] = today.strftime('%Y-%m-%d')
    
    # Manuel tarih girilirse custom'a geç
    if request.args.get('start_date') or request.args.get('end_date'):
        quick_filter = 'custom'
        if request.args.get('start_date'):
            filters['start_date'] = request.args.get('start_date')
        if request.args.get('end_date'):
            filters['end_date'] = request.args.get('end_date')
    
    if request.args.get('isletme_filter'):
        filters['isletme_filter'] = request.args.get('isletme_filter')
    if request.args.get('sbu_filter'):
        filters['sbu_filter'] = request.args.get('sbu_filter')
    if request.args.get('device_filter'):
        filters['device_filter'] = request.args.get('device_filter')
    if request.args.get('driver_filter'):
        filters['driver_filter'] = request.args.get('driver_filter')
    if request.args.get('group_level'):
        filters['group_level'] = request.args.get('group_level')
    else:
        filters['group_level'] = 'daily'  # Varsayılan günlük
    
    # Verileri çek (TEK SQL QUERY)
    success, message, data = test_query(filters)
    
    # KPI'ları data'dan hesapla (SQL'siz - çok hızlı)
    kpi_success, kpis = get_kpi_stats(filters if filters else None, data if data else None)
    if not kpi_success:
        kpis = {}
    
    # Grafik verilerini data'dan hesapla (SQL'siz - çok hızlı)
    chart_success, chart_data = get_chart_data(filters if filters else None) if data else (True, [])
    if not chart_success:
        chart_data = []
    
    # Kıyaslama verilerini data'dan hesapla (SQL'siz - çok hızlı)
    comparison_success, comparison_data = get_comparison_data(filters if filters else None) if data else (True, [])
    if not comparison_success:
        comparison_data = []
    
    # Filtre seçeneklerini çek
    filter_success, filter_options = get_filter_options()
    if not filter_success:
        filter_options = {'devices': [], 'drivers': [], 'isletme_list': [], 'sbu_list': []}
    
    return render_template('index.html', 
                         db_status=success, 
                         db_message=message, 
                         data=data,
                         kpis=kpis,
                         chart_data=chart_data,
                         comparison_data=comparison_data,
                         filter_options=filter_options,
                         current_filters=filters,
                         quick_filter=quick_filter)

@app.route('/personel/<operator>')
@login_required
def personel_karnesi(operator):
    """Personel Detay Sayfası"""
    success, message, details = get_personel_details(operator)
    
    if not success:
        return render_template('error.html', message=message)
    
    return render_template('personel_karnesi.html', details=details)

@app.route('/arac/<forklift>')
@login_required
def arac_karnesi(forklift):
    """Araç Detay Sayfası"""
    success, message, details = get_arac_details(forklift)
    
    if not success:
        return render_template('error.html', message=message)
    
    return render_template('arac_karnesi.html', details=details)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
