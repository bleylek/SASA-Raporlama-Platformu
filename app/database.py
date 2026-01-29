import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    """Database bağlantısı oluştur"""
    return psycopg2.connect(
        host=os.getenv('DB_HOST'),
        port=os.getenv('DB_PORT'),
        database=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD')
    )

def get_kpi_stats(filters=None, data_rows=None):
    """KPI istatistiklerini data'dan hesapla - Çok hızlı"""
    try:
        # Eğer data varsa ondan hesapla (SQL'e gitmeden)
        if data_rows:
            return True, {
                'total_devices': len(set(row[0] for row in data_rows)),
                'active_devices': len(set(row[0] for row in data_rows)),
                'total_records': len(data_rows),
                'total_working_time': sum(float(row[6]) for row in data_rows),
                'avg_moving_time': sum(float(row[7]) for row in data_rows) / len(data_rows) if data_rows else 0
            }
        
        # Fallback: Basit sayımlar
        conn = get_db_connection()
        cursor = conn.cursor()
        tenant_id = os.getenv('TENANT_ID')
        
        cursor.execute("""
            SELECT COUNT(DISTINCT name) FROM device WHERE tenant_id = %s
        """, [tenant_id])
        total_devices = cursor.fetchone()[0] or 0
        
        cursor.close()
        conn.close()
        
        return True, {
            'total_devices': total_devices,
            'active_devices': total_devices,
            'total_records': 0,
            'total_working_time': 0,
            'avg_moving_time': 0
        }
    except Exception as e:
        print("KPI error:", str(e))
        return False, {}

def get_chart_data(filters=None):
    """Trend Grafiği: test_query sonuçlarından günlük ortalama hesapla"""
    try:
        # test_query'den veri al
        success, message, rows = test_query(filters)
        if not success or not rows:
            return True, []
        
        # Günlük toplamları hesapla
        daily_data = {}
        for row in rows:
            # row format: forklift, operatör, tarih, isletme, sbu, vardiya, calisma_dk, hareket_dk, durma_dk, hareket_verim, forklift_verim, operator_verim
            tarih = row[2]  # DD.MM.YYYY
            calisma_dk = float(row[6])
            hareket_dk = float(row[7])
            hareket_verim = float(row[9])
            
            if tarih not in daily_data:
                daily_data[tarih] = {
                    'calisma': 0,
                    'hareket': 0,
                    'count': 0
                }
            
            daily_data[tarih]['calisma'] += calisma_dk
            daily_data[tarih]['hareket'] += hareket_dk
            daily_data[tarih]['count'] += 1
        
        # Günlük ortalama verimlilik hesapla
        result = []
        for tarih in sorted(daily_data.keys(), key=lambda x: x.split('.')[::-1]):  # Sort by YYYY.MM.DD
            data = daily_data[tarih]
            avg_verimlilik = (data['hareket'] / data['calisma'] * 100) if data['calisma'] > 0 else 0
            result.append([
                tarih,
                round(data['calisma'], 2),
                round(data['hareket'], 2),
                round(avg_verimlilik, 2),
                data['count']
            ])
        
        return True, result
    except Exception as e:
        import traceback
        print("Chart data error:", str(e))
        print(traceback.format_exc())
        return False, []

def get_comparison_data(filters=None):
    """Kıyaslama Grafiği: test_query sonuçlarından İşletme/SBU toplamları"""
    try:
        # test_query'den veri al
        success, message, rows = test_query(filters)
        if not success or not rows:
            return True, []
        
        # İşletme/SBU bazında toplamları hesapla
        comparison_data = {}
        for row in rows:
            # row format: forklift, operatör, tarih, isletme, sbu, vardiya, calisma_dk, hareket_dk, durma_dk, hareket_verim, forklift_verim, operator_verim
            isletme = row[3]
            sbu = row[4]
            calisma_dk = float(row[6])
            hareket_dk = float(row[7])
            
            key = (isletme, sbu)
            if key not in comparison_data:
                comparison_data[key] = {
                    'calisma': 0,
                    'hareket': 0
                }
            
            comparison_data[key]['calisma'] += calisma_dk
            comparison_data[key]['hareket'] += hareket_dk
        
        # Verimlilik hesapla ve sırala
        result = []
        for (isletme, sbu), data in comparison_data.items():
            verimlilik = (data['hareket'] / data['calisma'] * 100) if data['calisma'] > 0 else 0
            result.append([
                isletme,
                sbu,
                round(data['calisma'], 2),
                round(data['hareket'], 2),
                round(verimlilik, 2)
            ])
        
        # Verimliliğe göre sırala (yüksekten düşüğe)
        result.sort(key=lambda x: x[4], reverse=True)
        
        return True, result[:10]  # Top 10
    except Exception as e:
        import traceback
        print("Comparison data error:", str(e))
        print(traceback.format_exc())
        return False, []

def test_query(filters=None):
    """Aggregate verimlilik raporu - Range-based intersection calculation"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        tenant_id = os.getenv('TENANT_ID')
        
        # Filtre parametrelerini hazırla
        date_filter = ""
        device_filter = ""
        driver_filter = ""
        params = [tenant_id]
        
        if filters:
            if filters.get('start_date'):
                date_filter = " AND tk.ts >= (EXTRACT(EPOCH FROM TIMESTAMP %s) * 1000)::bigint"
                params.append(filters['start_date'])
            if filters.get('end_date'):
                date_filter += " AND tk.ts < (EXTRACT(EPOCH FROM (TIMESTAMP %s + INTERVAL '1 day')) * 1000)::bigint"
                params.append(filters['end_date'])
            if filters.get('device_filter'):
                device_filter = " AND d.name = %s"
                params.append(filters['device_filter'])
            if filters.get('driver_filter'):
                driver_filter = " AND (kv_json ->> 'driverName') = %s"
                params.append(filters['driver_filter'])
        
        query = """
        WITH device_to_isletme AS (
            SELECT
                d.id AS device_id,
                a_isletme.id AS isletme_id,
                a_isletme.name AS isletme_name
            FROM relation r
            JOIN device d ON d.id = r.to_id
            JOIN asset a_isletme ON a_isletme.id = r.from_id
            WHERE r.relation_type = 'forklift-isletme'
        ),
        isletme_to_sbu AS (
            SELECT
                a_isletme.id AS isletme_id,
                a_sbu.id AS sbu_id,
                a_sbu.name AS sbu_name
            FROM relation r
            JOIN asset a_isletme ON a_isletme.id = r.to_id
            JOIN asset a_sbu ON a_sbu.id = r.from_id
            WHERE r.relation_type = 'isletme-sbu'
        ),
        base AS (
            SELECT 
                d.name AS device_name,
                tk.entity_id,
                tk.ts,
                kd.key AS key_name,
                dtb.isletme_name,
                its.sbu_name,
                CASE 
                    WHEN tk.bool_v IS NOT NULL THEN tk.bool_v::text
                    WHEN tk.str_v IS NOT NULL THEN tk.str_v
                    WHEN tk.long_v IS NOT NULL THEN tk.long_v::text
                    WHEN tk.dbl_v IS NOT NULL THEN tk.dbl_v::text
                    WHEN tk.json_v IS NOT NULL THEN tk.json_v::text
                    ELSE NULL
                END AS key_value
            FROM ts_kv tk
            LEFT JOIN key_dictionary kd ON kd.key_id = tk.key
            LEFT JOIN device d ON d.id = tk.entity_id
            LEFT JOIN device_to_isletme dtb ON dtb.device_id = d.id
            LEFT JOIN isletme_to_sbu its ON its.isletme_id = dtb.isletme_id
            WHERE d.tenant_id = %s """ + date_filter + device_filter + """
        ),
        json_rows AS (
            SELECT 
                device_name,
                entity_id,
                ts,
                isletme_name,
                sbu_name,
                jsonb_object_agg(key_name, key_value) AS kv_json
            FROM base
            GROUP BY device_name, entity_id, ts, isletme_name, sbu_name
        ),
        parsed AS (
            SELECT
                device_name,
                COALESCE(isletme_name, '-') AS isletme,
                COALESCE(sbu_name, '-') AS sbu,
                to_timestamp(ts/1000.0) AT TIME ZONE 'Europe/Istanbul' AS end_time,
                COALESCE(NULLIF(kv_json ->> 'deltaWorkingTime','')::numeric, 0) AS work_seconds,
                COALESCE(NULLIF(kv_json ->> 'movingTime','')::numeric, 0) AS move_seconds,
                COALESCE((kv_json ->> 'driverName'), '-') AS driver_name
            FROM json_rows
            WHERE (kv_json ->> 'deltaWorkingTime') IS NOT NULL
                AND COALESCE(NULLIF(kv_json ->> 'deltaWorkingTime','')::numeric, 0) > 0
                """ + driver_filter + """
        ),
        ranges AS (
            SELECT
                device_name,
                isletme,
                sbu,
                end_time,
                end_time - (work_seconds || ' seconds')::interval AS start_time,
                work_seconds,
                move_seconds,
                driver_name
            FROM parsed
            WHERE work_seconds > 0
        ),
        days_expanded AS (
            SELECT
                device_name,
                isletme,
                sbu,
                start_time,
                end_time,
                work_seconds,
                move_seconds,
                driver_name,
                generate_series(
                    DATE(start_time),
                    DATE(end_time),
                    '1 day'::interval
                )::date AS day
            FROM ranges
        ),
        shifts AS (
            SELECT day, '3. Vardiya (00:00-08:00)' AS vardiya, 
                   (day || ' 00:00:00')::timestamp AS shift_start,
                   (day || ' 08:00:00')::timestamp AS shift_end
            FROM (SELECT DISTINCT day FROM days_expanded) d
            UNION ALL
            SELECT day, '1. Vardiya (08:00-16:00)' AS vardiya,
                   (day || ' 08:00:00')::timestamp AS shift_start,
                   (day || ' 16:00:00')::timestamp AS shift_end
            FROM (SELECT DISTINCT day FROM days_expanded) d
            UNION ALL
            SELECT day, '2. Vardiya (16:00-00:00)' AS vardiya,
                   (day || ' 16:00:00')::timestamp AS shift_start,
                   (day || ' 23:59:59.999999')::timestamp AS shift_end
            FROM (SELECT DISTINCT day FROM days_expanded) d
        ),
        shift_intersections AS (
            SELECT
                de.device_name,
                de.isletme,
                de.sbu,
                de.driver_name,
                s.day,
                s.vardiya,
                de.start_time,
                de.end_time,
                s.shift_start,
                s.shift_end,
                GREATEST(de.start_time, s.shift_start) AS inter_start,
                LEAST(de.end_time, s.shift_end) AS inter_end,
                de.work_seconds,
                de.move_seconds
            FROM days_expanded de
            JOIN shifts s ON s.day = de.day
            WHERE GREATEST(de.start_time, s.shift_start) < LEAST(de.end_time, s.shift_end)
        ),
        alloc AS (
            SELECT
                device_name,
                isletme,
                sbu,
                driver_name,
                day,
                vardiya,
                start_time,
                end_time,
                work_seconds AS total_work_seconds,
                move_seconds AS total_move_seconds,
                EXTRACT(EPOCH FROM (inter_end - inter_start))::numeric AS intersection_seconds,
                CASE
                    WHEN work_seconds > 0 THEN
                        (EXTRACT(EPOCH FROM (inter_end - inter_start))::numeric / work_seconds) * move_seconds
                    ELSE 0
                END AS allocated_move_seconds
            FROM shift_intersections
        ),
        driver_timeline AS (
            SELECT
                device_name,
                isletme,
                sbu,
                day,
                vardiya,
                driver_name,
                MIN(start_time) AS first_start,
                MAX(end_time) AS last_end,
                SUM(intersection_seconds) AS driver_work_seconds
            FROM alloc
            GROUP BY device_name, isletme, sbu, day, vardiya, driver_name
        ),
        agg_seconds AS (
            SELECT
                device_name,
                isletme,
                sbu,
                day,
                vardiya,
                SUM(intersection_seconds) AS shift_work_seconds,
                SUM(allocated_move_seconds) AS shift_move_seconds,
                STRING_AGG(DISTINCT driver_name, ' → ' ORDER BY driver_name) AS operator_list
            FROM alloc
            GROUP BY device_name, isletme, sbu, day, vardiya
        )
        SELECT
            device_name AS forklift,
            operator_list AS operatör,
            TO_CHAR(day, 'DD.MM.YYYY') AS tarih,
            isletme,
            sbu,
            vardiya,
            ROUND((shift_work_seconds / 60.0)::numeric, 2) AS calisma_dk,
            ROUND((shift_move_seconds / 60.0)::numeric, 2) AS hareket_dk,
            ROUND(((shift_work_seconds - shift_move_seconds) / 60.0)::numeric, 2) AS durma_dk,
            -- Hareket Verimliliği
            ROUND(
                CASE
                    WHEN shift_work_seconds > 0 THEN
                        ((shift_move_seconds / shift_work_seconds) * 100)::numeric
                    ELSE 0
                END, 2
            ) AS hareket_verim,
            -- Forklift Verimliliği (vardiya = 480 dk = 28800 sn)
            ROUND(
                ((shift_work_seconds / 28800.0) * 100)::numeric, 2
            ) AS forklift_verim,
            -- Operatör Verimliliği (aynı hesap)
            ROUND(
                ((shift_work_seconds / 28800.0) * 100)::numeric, 2
            ) AS operator_verim
        FROM agg_seconds
        ORDER BY day DESC, device_name, vardiya
        LIMIT 100
        """
        
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return True, f"{len(rows)} satır veri geldi! (Range-based calculation)", rows
    except Exception as e:
        import traceback
        print("SQL Error:", str(e))
        print(traceback.format_exc())
        return False, f"Hata: {str(e)}", None

def get_filter_options():
    """Filtre dropdown'ları için seçenekleri getir (İşletme ve SBU dahil)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        tenant_id = os.getenv('TENANT_ID')
        
        # Araç listesi
        cursor.execute("""
            SELECT DISTINCT d.name 
            FROM device d 
            WHERE d.tenant_id = %s 
            ORDER BY d.name
        """, [tenant_id])
        devices = [row[0] for row in cursor.fetchall()]
        
        # Sürücü listesi
        cursor.execute("""
            SELECT DISTINCT tk.str_v 
            FROM ts_kv tk
            LEFT JOIN key_dictionary kd ON kd.key_id = tk.key
            LEFT JOIN device d ON d.id = tk.entity_id
            WHERE d.tenant_id = %s AND kd.key = 'driverName' AND tk.str_v IS NOT NULL
            ORDER BY tk.str_v
            LIMIT 100
        """, [tenant_id])
        drivers = [row[0] for row in cursor.fetchall()]
        
        # İşletme listesi
        cursor.execute("""
            WITH device_to_isletme AS (
                SELECT DISTINCT a_isletme.name AS isletme_name
                FROM relation r
                JOIN device d ON d.id = r.to_id
                JOIN asset a_isletme ON a_isletme.id = r.from_id
                WHERE r.relation_type = 'forklift-isletme'
                AND d.tenant_id = %s
            )
            SELECT isletme_name 
            FROM device_to_isletme 
            ORDER BY isletme_name
        """, [tenant_id])
        isletme_list = [row[0] for row in cursor.fetchall()]
        
        # SBU listesi
        cursor.execute("""
            WITH isletme_to_sbu AS (
                SELECT DISTINCT a_sbu.name AS sbu_name
                FROM relation r
                JOIN asset a_isletme ON a_isletme.id = r.to_id
                JOIN asset a_sbu ON a_sbu.id = r.from_id
                WHERE r.relation_type = 'isletme-sbu'
            )
            SELECT sbu_name 
            FROM isletme_to_sbu 
            ORDER BY sbu_name
        """)
        sbu_list = [row[0] for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return True, {
            'devices': devices, 
            'drivers': drivers,
            'isletme_list': isletme_list,
            'sbu_list': sbu_list
        }
    except Exception as e:
        return False, str(e)

def get_personel_details(driver_name):
    """Personel Karnesi: Operatörün detaylı bilgileri"""
    try:
        # test_query'den operatör verisini al
        filters = {'driver_filter': driver_name}
        success, message, rows = test_query(filters)
        
        if not success or not rows:
            return False, "Veri bulunamadı", None
        
        # Toplam istatistikler
        total_calisma = sum(float(row[6]) for row in rows)
        total_hareket = sum(float(row[7]) for row in rows)
        avg_hareket_verim = sum(float(row[9]) for row in rows) / len(rows)
        avg_forklift_verim = sum(float(row[10]) for row in rows) / len(rows)
        
        # Kullanılan araçlar
        araclar = {}
        for row in rows:
            forklift = row[0]
            if forklift not in araclar:
                araclar[forklift] = {'calisma': 0, 'count': 0}
            araclar[forklift]['calisma'] += float(row[6])
            araclar[forklift]['count'] += 1
        
        # Günlük detaylar
        gunluk = []
        for row in rows:
            gunluk.append({
                'forklift': row[0],
                'tarih': row[2],
                'vardiya': row[5],
                'calisma_dk': float(row[6]),
                'hareket_dk': float(row[7]),
                'verimlilik': float(row[9])
            })
        
        details = {
            'operator': driver_name,
            'total_calisma': round(total_calisma, 2),
            'total_hareket': round(total_hareket, 2),
            'total_calisma_saat': round(total_calisma / 60, 2),
            'avg_hareket_verim': round(avg_hareket_verim, 2),
            'avg_forklift_verim': round(avg_forklift_verim, 2),
            'araclar': araclar,
            'gunluk': gunluk,
            'kayit_sayisi': len(rows)
        }
        
        return True, "OK", details
    except Exception as e:
        import traceback
        print("Personel details error:", str(e))
        print(traceback.format_exc())
        return False, str(e), None

def get_arac_details(device_name):
    """Araç Karnesi: Forklift'in detaylı bilgileri"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        tenant_id = os.getenv('TENANT_ID')
        
        # 1. test_query'den forklift verisini al
        filters = {'device_filter': device_name}
        success, message, rows = test_query(filters)
        
        if not success or not rows:
            return False, "Veri bulunamadı", None
        
        # Toplam istatistikler
        total_motor_saati = sum(float(row[6]) for row in rows) / 60  # Saat cinsinden
        avg_verimlilik = sum(float(row[10]) for row in rows) / len(rows)
        
        # Kullanan personeller
        personeller = {}
        for row in rows:
            operator = row[1]
            if operator not in personeller:
                personeller[operator] = {'calisma': 0, 'count': 0}
            personeller[operator]['calisma'] += float(row[6])
            personeller[operator]['count'] += 1
        
        # Günlük detaylar
        gunluk = []
        for row in rows:
            gunluk.append({
                'operator': row[1],
                'tarih': row[2],
                'vardiya': row[5],
                'calisma_dk': float(row[6]),
                'verimlilik': float(row[10])
            })
        
        # 2. Tüm uplink verileri (son 100 kayıt)
        cursor.execute("""
            WITH base AS (
                SELECT 
                    tk.ts,
                    kd.key AS key_name,
                    CASE 
                        WHEN tk.bool_v IS NOT NULL THEN tk.bool_v::text
                        WHEN tk.str_v IS NOT NULL THEN tk.str_v
                        WHEN tk.long_v IS NOT NULL THEN tk.long_v::text
                        WHEN tk.dbl_v IS NOT NULL THEN tk.dbl_v::text
                        WHEN tk.json_v IS NOT NULL THEN tk.json_v::text
                        ELSE NULL
                    END AS key_value
                FROM ts_kv tk
                LEFT JOIN key_dictionary kd ON kd.key_id = tk.key
                LEFT JOIN device d ON d.id = tk.entity_id
                WHERE d.tenant_id = %s 
                    AND d.name = %s
                ORDER BY tk.ts DESC
                LIMIT 1000
            ),
            json_rows AS (
                SELECT 
                    ts,
                    jsonb_object_agg(key_name, key_value) AS kv_json
                FROM base
                GROUP BY ts
            )
            SELECT 
                to_timestamp(ts/1000.0) AT TIME ZONE 'Europe/Istanbul' AS timestamp,
                kv_json
            FROM json_rows
            ORDER BY ts DESC
            LIMIT 100
        """, (tenant_id, device_name))
        
        uplink_data = []
        for row in cursor.fetchall():
            timestamp, data = row
            uplink_data.append({
                'timestamp': timestamp,
                'data': data
            })
        
        cursor.close()
        conn.close()
        
        details = {
            'forklift': device_name,
            'total_motor_saati': round(total_motor_saati, 2),
            'avg_verimlilik': round(avg_verimlilik, 2),
            'personeller': personeller,
            'gunluk': gunluk,
            'uplink_data': uplink_data,
            'kayit_sayisi': len(rows)
        }
        
        return True, "OK", details
    except Exception as e:
        import traceback
        print("Arac details error:", str(e))
        print(traceback.format_exc())
        return False, str(e), None
