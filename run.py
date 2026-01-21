import sys
import os

# Projeyi path'e ekle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, request, jsonify
from app.database import test_query, get_kpi_stats, get_chart_data, get_comparison_data, get_filter_options, get_personel_details, get_arac_details

app = Flask(__name__)

@app.route('/')
def index():
    # Filtreleri al
    filters = {}
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
    
    # Verileri çek
    success, message, data = test_query(filters if filters else None)
    
    # KPI'ları çek
    kpi_success, kpis = get_kpi_stats(filters if filters else None)
    if not kpi_success:
        kpis = {}
    
    # Grafik verilerini çek
    chart_success, chart_data = get_chart_data(filters if filters else None)
    if not chart_success:
        chart_data = []
    
    # Kıyaslama verilerini çek
    comparison_success, comparison_data = get_comparison_data(filters if filters else None)
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
                         current_filters=filters)

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
    app.run(debug=True, port=5000)
