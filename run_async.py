import sys
import os

# Projeyi path'e ekle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, request, jsonify
from datetime import datetime, timedelta
from app.database import test_query, get_kpi_stats, get_chart_data, get_comparison_data, get_filter_options, get_personel_details, get_arac_details

app = Flask(__name__)

@app.route('/')
def index():
    """Ana sayfa - sadece skeleton yükle"""
    from datetime import datetime, timedelta
    
    # Default tarih filtreleri hazırla
    default_start = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    default_end = datetime.now().strftime('%Y-%m-%d')
    
    # Filtre seçeneklerini çek (sadece bu hızlı)
    filter_success, filter_options = get_filter_options()
    if not filter_success:
        filter_options = {'devices': [], 'drivers': [], 'isletme_list': [], 'sbu_list': []}
    
    return render_template('index_async.html',
                         filter_options=filter_options,
                         default_start=default_start,
                         default_end=default_end)

@app.route('/api/kpis')
def api_kpis():
    """KPI'ları getir - AJAX endpoint"""
    filters = _get_filters_from_request()
    kpi_success, kpis = get_kpi_stats(filters)
    
    if kpi_success:
        return jsonify({'success': True, 'data': kpis})
    else:
        return jsonify({'success': False, 'error': 'KPI verileri alınamadı'})

@app.route('/api/table')
def api_table():
    """Tablo verilerini getir - AJAX endpoint"""
    filters = _get_filters_from_request()
    success, message, data = test_query(filters)
    
    if success:
        return jsonify({'success': True, 'data': data, 'message': message})
    else:
        return jsonify({'success': False, 'error': message})

@app.route('/api/chart-trend')
def api_chart_trend():
    """Trend grafiği verilerini getir - AJAX endpoint"""
    filters = _get_filters_from_request()
    chart_success, chart_data = get_chart_data(filters)
    
    if chart_success:
        return jsonify({'success': True, 'data': chart_data})
    else:
        return jsonify({'success': False, 'error': 'Grafik verileri alınamadı'})

@app.route('/api/chart-comparison')
def api_chart_comparison():
    """Karşılaştırma grafiği verilerini getir - AJAX endpoint"""
    filters = _get_filters_from_request()
    comparison_success, comparison_data = get_comparison_data(filters)
    
    if comparison_success:
        return jsonify({'success': True, 'data': comparison_data})
    else:
        return jsonify({'success': False, 'error': 'Karşılaştırma verileri alınamadı'})

def _get_filters_from_request():
    """Request'ten filtreleri çıkar"""
    filters = {}
    
    # Default: Son 7 gün
    if request.args.get('start_date'):
        filters['start_date'] = request.args.get('start_date')
    else:
        filters['start_date'] = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    
    if request.args.get('end_date'):
        filters['end_date'] = request.args.get('end_date')
    else:
        filters['end_date'] = datetime.now().strftime('%Y-%m-%d')
    
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
        filters['group_level'] = 'daily'
    
    return filters

@app.route('/personel/<operator>')
def personel_karnesi(operator):
    """Personel Detay Sayfası"""
    success, message, details = get_personel_details(operator)
    
    if not success:
        return render_template('error.html', message=message)
    
    return render_template('personel_karnesi.html', details=details)

@app.route('/arac/<forklift>')
def arac_karnesi(forklift):
    """Araç Detay Sayfası"""
    success, message, details = get_arac_details(forklift)
    
    if not success:
        return render_template('error.html', message=message)
    
    return render_template('arac_karnesi.html', details=details)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
