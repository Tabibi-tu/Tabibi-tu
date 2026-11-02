import streamlit as st
import sqlite3
import os
import random
import string
import json
import time
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit.components.v1 as components
import base64
import html 

# محاولة استيراد PostgreSQL
try:
    import psycopg2
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

# ==========================================
# 1. إعدادات الصفحة
# ==========================================
st.set_page_config(
    page_title="طبيبي د. | Mon Médecin Dr.",
    page_icon="icon.png",
    layout="wide",
    initial_sidebar_state="collapsed"
)

def inject_custom_pwa(icon_path, app_name):
    try:
        with open(icon_path, "rb") as image_file:
            encoded_icon = base64.b64encode(image_file.read()).decode()
        manifest_data = f"""{{
            "name": "{app_name}", "short_name": "{app_name}", "start_url": ".", "display": "standalone",
            "background_color": "#ffffff", "theme_color": "#0d9488",
            "icons": [{{ "src": "data:image/png;base64,{encoded_icon}", "sizes": "192x192", "type": "image/png" }}]
        }}"""
        b64_manifest = base64.b64encode(manifest_data.encode('utf-8')).decode('utf-8')
        js_code = f"""
        <script>
            try {{
                const parentDoc = window.parent.document;
                const head = parentDoc.querySelector('head');
                parentDoc.title = "{app_name}";
                const manifestLink = parentDoc.createElement('link'); manifestLink.rel = 'manifest'; manifestLink.href = 'data:application/manifest+json;base64,{b64_manifest}'; head.appendChild(manifestLink);
            }} catch (e) {{}}
        </script>
        """
        components.html(js_code, height=0, width=0)
    except Exception:
        pass

inject_custom_pwa("icon.png", "طبيبي د. | Mon Médecin Dr.")

# دوال التوقيت
def get_tunis_time():
    return datetime.now(ZoneInfo("Africa/Tunis"))

def get_tunis_date():
    return get_tunis_time().date()

DAYS_AR = {0: "الإثنين", 1: "الثلاثاء", 2: "الأربعاء", 3: "الخميس", 4: "الجمعة", 5: "السبت", 6: "الأحد"}
DAYS_FR = {0: "Lundi", 1: "Mardi", 2: "Mercredi", 3: "Jeudi", 4: "Vendredi", 5: "Samedi", 6: "Dimanche"}

if 'current_view' not in st.session_state: st.session_state.current_view = 'home'
if 'sec_auth' not in st.session_state: st.session_state.sec_auth = False
if 'doc_auth' not in st.session_state: st.session_state.doc_auth = False
if 'lang' not in st.session_state: st.session_state.lang = 'ar'
if 'patient_subview' not in st.session_state: st.session_state.patient_subview = 'book'
if 'doctor_subview' not in st.session_state: st.session_state.doctor_subview = 'rx'
if 'login_attempts' not in st.session_state: st.session_state.login_attempts = 0

def t(ar_text, fr_text):
    if st.session_state.lang == 'ar':
        return ar_text.replace("طابور", "صف").replace("الطابور", "الصف")
    return fr_text

def format_wait_time(minutes):
    if minutes <= 0: return t("دورك الآن!", "C'est votre tour !")
    h = minutes // 60
    m = minutes % 60
    if st.session_state.lang == 'ar':
        res = ""
        if h == 1: res += "ساعة"
        elif h == 2: res += "ساعتان"
        elif h > 2: res += f"{h} ساعات"
        if m > 0:
            if h > 0: res += " و "
            res += f"{m} دقيقة"
        return res if res else "أقل من دقيقة"
    else:
        res = ""
        if h > 0: res += f"{h}h "
        if m > 0: res += f"{m}min"
        return res.strip()

def generate_short_code():
    # رمز بسيط جداً: حرف واحد + 3 أرقام (مثال: C-592)
    letter = random.choice(string.ascii_uppercase)
    nums = ''.join(random.choices(string.digits, k=3))
    return f"{letter}-{nums}"

# ==========================================
# 2. قاعدة البيانات المحسنة والآمنة
# ==========================================
DB_FILE = "clinic_saas.db"

def get_db_url():
    try:
        if "DATABASE_URL" in st.secrets:
            return st.secrets["DATABASE_URL"]
    except Exception:
        pass
    return os.environ.get("DATABASE_URL", "")

def is_postgres():
    url = get_db_url()
    return bool(url and PSYCOPG2_AVAILABLE)

def get_connection():
    if is_postgres():
         return psycopg2.connect(get_db_url())
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def execute_query(query, params=(), fetch=False, retries=3):
    for attempt in range(retries):
        conn = get_connection()
        try:
            c = conn.cursor()
            if is_postgres():
                query = query.replace("?", "%s").replace("AUTOINCREMENT", "")
                if "INTEGER PRIMARY KEY" in query and "SERIAL" not in query and "CHECK" not in query:
                    query = query.replace("id INTEGER PRIMARY KEY", "id SERIAL PRIMARY KEY")
            
            c.execute(query, params)
            res = c.fetchall() if fetch else None
            conn.commit()
            return res
        except Exception as e:
            if "locked" in str(e).lower() and attempt < retries - 1:
                time.sleep(0.3)
                continue
            raise e
        finally:
            conn.close()

def read_df(query, params=()):
    conn = get_connection()
    try:
        if is_postgres():
            query = query.replace("?", "%s")
        df = pd.read_sql_query(query, conn, params=params)
        return df
    finally:
        conn.close()

def init_db():
    execute_query('''CREATE TABLE IF NOT EXISTS clinic_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1), 
            doctor_name TEXT DEFAULT 'سامي بن يوسف', 
            specialty TEXT DEFAULT 'طب عام', 
            phone TEXT DEFAULT '21600000000', 
            address TEXT DEFAULT '',
            work_start TEXT DEFAULT '09:00', 
            work_end TEXT DEFAULT '16:00', 
            slot_minutes INTEGER DEFAULT 20, 
            consultation_price INTEGER DEFAULT 60, 
            current_ticket INTEGER DEFAULT 0,
            subscription_active INTEGER DEFAULT 1, 
            subscription_expiry TEXT DEFAULT '2026-12-31',
            sec_pwd TEXT DEFAULT '0000', 
            doc_pwd TEXT DEFAULT '0000', 
            last_reset_date TEXT DEFAULT '',
            work_days TEXT DEFAULT '0,1,2,3,4,5', 
            urgent_approver TEXT DEFAULT 'both', 
            absence_notice TEXT DEFAULT '')''')

    new_settings_cols = [
        ("sec_pwd", "TEXT DEFAULT '0000'"),
        ("doc_pwd", "TEXT DEFAULT '0000'"),
        ("last_reset_date", "TEXT DEFAULT ''"),
        ("work_days", "TEXT DEFAULT '0,1,2,3,4,5'"),
        ("urgent_approver", "TEXT DEFAULT 'both'"),
        ("absence_notice", "TEXT DEFAULT ''")
    ]
    for col, defn in new_settings_cols:
        try: execute_query(f"ALTER TABLE clinic_settings ADD COLUMN {col} {defn}")
        except Exception: pass
            
    execute_query('''CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            patient_name TEXT, 
            patient_phone TEXT, 
            appointment_date TEXT, 
            appointment_time TEXT, 
            ticket_number INTEGER, 
            status TEXT, 
            visit_type TEXT, 
            visit_reason TEXT DEFAULT 'غير محدد',
            urgent_note TEXT DEFAULT '',
            app_code TEXT DEFAULT '', 
            created_at TEXT)''')

    new_app_cols = [
        ("visit_reason", "TEXT DEFAULT 'غير محدد'"),
        ("urgent_note", "TEXT DEFAULT ''"),
        ("app_code", "TEXT DEFAULT ''")
    ]
    for col, defn in new_app_cols:
        try: execute_query(f"ALTER TABLE appointments ADD COLUMN {col} {defn}")
        except Exception: pass

    try:
        if is_postgres():
             execute_query("CREATE UNIQUE INDEX IF NOT EXISTS uq_booked_slot ON appointments (appointment_date, appointment_time) WHERE visit_type = 'موعد مسبق' AND status <> 'ملغى'")
        else:
             execute_query("CREATE UNIQUE INDEX IF NOT EXISTS uq_booked_slot ON appointments (appointment_date, appointment_time) WHERE visit_type = 'موعد مسبق' AND status != 'ملغى'")
    except Exception:
        pass

    execute_query('''CREATE TABLE IF NOT EXISTS medical_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            patient_phone TEXT, 
            patient_name TEXT, 
            visit_date TEXT, 
            diagnosis TEXT, 
            prescription TEXT, 
            lab_tests TEXT, 
            doctor_notes TEXT)''')
    
    try:
        count_res = execute_query("SELECT COUNT(*) FROM clinic_settings", fetch=True)
        if count_res and count_res[0][0] == 0:
            execute_query('''INSERT INTO clinic_settings (id) VALUES (1)''')
    except Exception:
        pass

init_db()

def get_clinic_settings():
    try:
        df = read_df("SELECT * FROM clinic_settings WHERE id = 1")
        if df.empty:
            return {}
        row_dict = df.iloc[0].to_dict()
        defaults = {
            'doctor_name': 'سامي بن يوسف', 'specialty': 'طب عام', 'phone': '21600000000',
            'work_start': '09:00', 'work_end': '16:00', 'slot_minutes': 20, 'consultation_price': 60,
            'current_ticket': 0, 'subscription_active': 1, 'sec_pwd': '0000', 'doc_pwd': '0000',
            'last_reset_date': '', 'work_days': '0,1,2,3,4,5', 'urgent_approver': 'both', 'absence_notice': ''
        }
        for k, v in defaults.items():
            if k not in row_dict or pd.isna(row_dict[k]) or row_dict[k] is None:
                row_dict[k] = v
        return row_dict
    except Exception:
        return {}

settings = get_clinic_settings()

def get_working_days_list():
    raw = str(settings.get('work_days', '0,1,2,3,4,5'))
    return [int(x) for x in raw.split(',') if x.strip().isdigit()]

def find_next_working_day(from_date):
    work_days = get_working_days_list()
    if not work_days:
        return from_date + timedelta(days=1)
    candidate = from_date + timedelta(days=1)
    for _ in range(14):
        if candidate.weekday() in work_days:
            return candidate
        candidate += timedelta(days=1)
    return candidate

def generate_time_slots(start_str, end_str, slot_minutes, target_date):
    work_days = get_working_days_list()
    if target_date.weekday() not in work_days:
        return []
    slots = []
    try:
        current = datetime.strptime(start_str, "%H:%M")
        end = datetime.strptime(end_str, "%H:%M")
    except ValueError:
        current = datetime.strptime("09:00", "%H:%M")
        end = datetime.strptime("16:00", "%H:%M")
        
    now_tunis = get_tunis_time()
    while current < end:
        slot_time_str = current.strftime("%H:%M")
        if target_date == now_tunis.date():
            if current.time() > now_tunis.time():
                slots.append(slot_time_str)
        else:
            slots.append(slot_time_str)
        current += timedelta(minutes=int(slot_minutes))
    return slots

def get_booked_slots(target_date):
    try:
        res = execute_query("SELECT appointment_time FROM appointments WHERE appointment_date = ? AND status NOT IN ('ملغى', 'طلب استعجالي')", (target_date,), fetch=True)
        return [row[0] for row in res] if res else []
    except Exception:
        return []

def get_first_available_date(start_date, work_start, work_end, slot_minutes):
    """دالة ذكية للبحث عن أقرب يوم يحتوي على أوقات فارغة للحجز"""
    candidate_date = start_date
    for _ in range(14): # يبحث في الأسبوعين القادمين كحد أقصى
        if candidate_date.weekday() in get_working_days_list():
            all_slots = generate_time_slots(work_start, work_end, slot_minutes, candidate_date)
            booked_set = set(get_booked_slots(candidate_date.isoformat()))
            avail_slots = [s for s in all_slots if s not in booked_set]
            if avail_slots:
                return candidate_date # وجد يوم فيه أوقات فارغة
        candidate_date += timedelta(days=1)
    return start_date # إذا كانت كل الأيام ممتلئة يرجع لليوم الافتراضي

def recalculate_tickets(target_date):
    try:
        df = read_df("SELECT id, appointment_time FROM appointments WHERE appointment_date = ? AND status NOT IN ('ملغى', 'طلب استعجالي', 'مكتمل') ORDER BY appointment_time ASC, id ASC", (target_date,))
        max_t = execute_query("SELECT MAX(ticket_number) FROM appointments WHERE appointment_date = ? AND status = 'مكتمل'", (target_date,), fetch=True)
        start_idx = max_t[0][0] if max_t and max_t[0][0] else 0
        for i, row in enumerate(df.itertuples(), start=start_idx + 1):
             execute_query("UPDATE appointments SET ticket_number = ? WHERE id = ?", (i, int(row.id)))
    except Exception:
        pass

def update_current_ticket(today_str):
    try:
        res = execute_query("SELECT ticket_number FROM appointments WHERE appointment_date = ? AND status = 'مكتمل' ORDER BY ticket_number DESC LIMIT 1", (today_str,), fetch=True)
        current = res[0][0] if res else 0
        execute_query("UPDATE clinic_settings SET current_ticket = ? WHERE id = 1", (current,))
        settings['current_ticket'] = current
    except Exception:
        pass

# ==========================================
# 3. التصميم (CSS)
# ==========================================
direction = "rtl" if st.session_state.lang == 'ar' else "ltr"
align = "right" if st.session_state.lang == 'ar' else "left"

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
    html, body, [class*="css"] {{ font-family: 'Cairo', sans-serif !important; direction: {direction}; text-align: {align}; }}
    .clinic-header {{ background: linear-gradient(135deg, #0f766e, #14b8a6); color: white; padding: 24px; border-radius: 20px; text-align: center; margin-bottom: 20px; box-shadow: 0 10px 25px rgba(13,148,136,0.2); }}
    .clinic-header h1 {{ margin: 0; font-size: 2.2rem; font-weight: 800; color: #fff; }}
    .clinic-header p {{ margin: 8px 0 0 0; font-size: 1.1rem; opacity: 0.9; }}
    .live-queue-box {{ background: linear-gradient(145deg, #0f172a, #1e293b); color: white; padding: 25px; border-radius: 20px; text-align: center; border: 2px solid #14b8a6; margin-bottom: 20px; }}
    .ticket-number-giant {{ font-size: 4.5rem; font-weight: 800; color: #2dd4bf; margin: 10px 0; }}
    .medical-card {{ background: #fff; border: 1px solid #e2e8f0; border-inline-start: 6px solid #0d9488; border-radius: 14px; padding: 18px; margin-bottom: 16px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }}
    .urgent-card {{ background: #fef2f2; border: 2px solid #ef4444; border-radius: 14px; padding: 15px; margin-bottom: 12px; }}
    .stButton > button {{ border-radius: 15px !important; transition: all 0.3s ease !important; border: 2px solid transparent !important; }}
    .stButton > button p {{ white-space: normal !important; word-wrap: break-word !important; line-height: 1.6 !important; font-size: 1.05rem !important; font-weight: 700 !important; }}
    button[kind="secondary"] {{ background-color: #f1f5f9 !important; color: #334155 !important; border: 2px solid #cbd5e1 !important; min-height: 75px !important; }}
    button[kind="secondary"]:hover {{ background-color: #e2e8f0 !important; border-color: #0d9488 !important; transform: translateY(-2px) !important; }}
    button[kind="primary"] {{ background: linear-gradient(135deg, #0d9488, #0f766e) !important; color: white !important; box-shadow: 0 8px 15px rgba(13,148,136,0.3) !important; min-height: 75px !important; }}
</style>
""", unsafe_allow_html=True)

if st.session_state.current_view == 'home':
    st.markdown("""<style>div[data-testid="column"] .stButton > button { min-height: 260px !important; background-color: #ffffff !important; border: 2px solid #cbd5e1 !important; box-shadow: 0 4px 10px rgba(0,0,0,0.05) !important; color: #1e293b !important; } div[data-testid="column"] .stButton > button p { font-size: 1.25rem !important; } div[data-testid="column"] .stButton > button:hover { border-color: #0d9488 !important; background-color: #f8fafc !important; transform: translateY(-5px) !important; color: #0d9488 !important; }</style>""", unsafe_allow_html=True)

doc_clean_name = str(settings.get('doctor_name', '')).replace('د.', '').replace('الدكتور', '').replace('Dr.', '').strip()
title_text = t(f"🩺 طبيبي د. {doc_clean_name}", f"🩺 Mon Médecin Dr. {doc_clean_name}")
st.markdown(f"""<div class="clinic-header"><h1>{title_text}</h1><p>{settings.get('specialty', '')} | 📞 {settings.get('phone', '')}</p></div>""", unsafe_allow_html=True)

if settings.get('absence_notice'):
    st.warning(f"📢 **تنبيه من العيادة:** {html.escape(settings.get('absence_notice'))}")

if settings.get('subscription_active', 1) == 0:
    st.error(t("⚠️ خدمة العيادة الرقمية معلقة مؤقتاً. يرجى من الإدارة تجديد الاشتراك.", "⚠️ Service suspendu temporairement."))
    st.stop()

if st.session_state.current_view != 'home':
    if st.button(t("🏠 عودة إلى الشاشة الرئيسية", "🏠 Retour à l'accueil")):
        st.session_state.current_view = 'home'
        st.rerun()
    st.divider()

def render_urgent_requests_box(role):
    approver_setting = settings.get('urgent_approver', 'both')
    if approver_setting != 'both' and approver_setting != role:
        return
    today_str = get_tunis_date().isoformat()
    urgent_df = read_df("SELECT * FROM appointments WHERE status = 'طلب استعجالي' AND appointment_date = ? ORDER BY id DESC", (today_str,))
    if not urgent_df.empty:
        st.markdown(t("### 🚨 طلبات مواعيد استعجالية لليوم تنتظر المصادقة", "### 🚨 Demandes urgentes d'aujourd'hui"))
        for _, u_row in urgent_df.iterrows():
            safe_name = html.escape(str(u_row['patient_name']))
            safe_phone = html.escape(str(u_row['patient_phone']))
            safe_note = html.escape(str(u_row.get('urgent_note', 'حالة طارئة')))
            
            st.markdown(f"""
            <div class="urgent-card">
                <b style="color:#b91c1c; font-size:1.1rem;">🚨 المريض: {safe_name} | 📞 {safe_phone}</b><br>
                <span>📅 كود الطلب: {u_row['app_code']} | 📝 السبب: <b>{safe_note}</b></span>
            </div>
            """, unsafe_allow_html=True)
            ca1, ca2, ca3 = st.columns([1, 1, 1])
            if ca1.button(t(f"✅ قبول وإدراج بالصف", f"✅ Accepter"), key=f"acc_{role}_{u_row['id']}", type="primary"):
                now_str = get_tunis_time().strftime("%H:%M")
                execute_query("UPDATE appointments SET status = 'في الانتظار', appointment_time = ?, visit_type = 'استعجالي مصادق عليه' WHERE id = ?", (now_str, int(u_row['id'])))
                recalculate_tickets(u_row['appointment_date'])
                st.success(t("تم قبول الحالة الاستعجالية وإدراجها في الصف!", "Demande urgente acceptée !"))
                st.rerun()
            if ca2.button(t(f"❌ اعتذار / رفض", f"❌ Refuser"), key=f"rej_{role}_{u_row['id']}"):
                execute_query("UPDATE appointments SET status = 'ملغى' WHERE id = ?", (int(u_row['id']),))
                st.info(t("تم إلغاء الطلب.", "Demande refusée."))
                st.rerun()
            wa_num = safe_phone.replace(" ", "")
            if not wa_num.startswith("216") and len(wa_num) == 8:
                wa_num = "216" + wa_num
            safe_doc_name = html.escape(doc_clean_name)
            ca3.markdown(f"<a href='https://wa.me/{wa_num}?text=مرحبا، تم قبول طلبكم الاستعجالي في عيادة د. {safe_doc_name}' target='_blank' style='display:inline-block; background:#22c55e; color:white; padding:10px 16px; border-radius:10px; text-decoration:none; font-weight:bold; text-align:center; width:100%;'>💬 إشعار واتساب</a>", unsafe_allow_html=True)
        st.divider()

# ==============================================================================
# الشاشة الرئيسية
# ==============================================================================
if st.session_state.current_view == 'home':
    col_welcome, col_lang = st.columns([4, 1])
    with col_welcome:
        st.markdown(t("<h3 style='text-align: center; color:#334155; margin-top:5px;'>مرحباً بك، يرجى اختيار صفتك للدخول:</h3>", "<h3 style='text-align: center; color:#334155; margin-top:5px;'>Bienvenue, veuillez sélectionner votre accès :</h3>"), unsafe_allow_html=True)
    with col_lang:
        selected_lang = st.selectbox("🌐", ["العربية", "Français"], index=0 if st.session_state.lang == 'ar' else 1, label_visibility="collapsed")
        new_lang = 'ar' if selected_lang == "العربية" else 'fr'
        if new_lang != st.session_state.lang:
            st.session_state.lang = new_lang
            st.rerun()
            
    st.write("") 
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button(t("📱\n\nالمريض / الحريف\n\nحجز موعد، طلب استعجالي، تتبع الصف\nومعاينة وصفاتك الطبية.", "📱\n\nPatient / Client\n\nRéserver, urgence, suivre la file\net voir vos ordonnances."), use_container_width=True):
            st.session_state.current_view = 'patient'; st.session_state.patient_subview = 'book'; st.rerun()
    with col2:
        if st.button(t("👩‍💻\n\nالكاتبة / الاستقبال\n\nإدارة وتعديل الصف، إضافة مرضى\nوالمصادقة على المواعيد (محمي).", "👩‍💻\n\nSecrétaire / Accueil\n\nGérer et modifier la file\net les urgences (Protégé)."), use_container_width=True):
            st.session_state.current_view = 'secretary'; st.rerun()
    with col3:
        if st.button(t("👨‍⚕️\n\nالدكتور / الطبيب\n\nإصدار الوصفات، أيام العمل، الغياب\nوإعدادات العيادة (محمي).", "👨‍⚕️\n\nMédecin / Docteur\n\nOrdonnances, jours de travail,\nabsence et paramètres (Protégé)."), use_container_width=True):
            st.session_state.current_view = 'doctor'; st.session_state.doctor_subview = 'rx'; st.rerun()

# ==============================================================================
# واجهة المريض
# ==============================================================================
elif st.session_state.current_view == 'patient':
    @st.fragment(run_every=15)
    def live_queue_box():
        today_str = get_tunis_date().isoformat()
        update_current_ticket(today_str)
        today_df = read_df("SELECT * FROM appointments WHERE appointment_date = ? AND status NOT IN ('ملغى', 'طلب استعجالي') ORDER BY ticket_number ASC", (today_str,))
        
        waiting_count = len(today_df[today_df['status'] == 'في الانتظار'])
        in_exam_df = today_df[today_df['status'] == 'في الفحص']
        current_num = int(in_exam_df.iloc[0]['ticket_number']) if not in_exam_df.empty else int(settings.get('current_ticket', 0))
        
        col_q1, col_q2 = st.columns([1.2, 1])
        with col_q1:
            st.markdown(f"""
            <div class="live-queue-box">
                <span style="background:#ef4444; padding:4px 12px; border-radius:50px;">{t("🔴 مباشر من قاعة الانتظار", "🔴 En direct de la salle d'attente")}</span>
                <div style="margin-top:10px;">{t("الطبيب يفحص حالياً تذكرة رقم:", "Le médecin consulte actuellement le numéro :")}</div>
                <div class="ticket-number-giant">#{current_num}</div>
                <div>{t(f"المنتظرون في الصف: <b>{waiting_count}</b>", f"En attente: <b>{waiting_count}</b>")}</div>
            </div>
            """, unsafe_allow_html=True)
            
        with col_q2:
            st.markdown(t("#### ⏳ وقت الانتظار التقريبي", "#### ⏳ Temps d'attente estimé"))
            my_code = st.text_input(t("أدخل رمز موعدك (مثال C-592):", "Code de rendez-vous :"), key="patient_code_input").strip().upper()
            
            if my_code:
                my_row = read_df("SELECT * FROM appointments WHERE appointment_date = ? AND app_code = ?", (today_str, my_code))
                if not my_row.empty:
                    my_status = my_row.iloc[0]['status']
                    my_t_num = my_row.iloc[0]['ticket_number']
                    
                    if my_status == 'في الفحص':
                        st.markdown(f"""<div style="background: #ecfdf5; border: 2px solid #10b981; border-radius: 14px; padding: 16px; text-align: center; margin-top: 10px;"><div style="font-size: 1.3rem; font-weight: 800; color: #065f46;">🎉 {t("دورك الآن! تفضل بالدخول إلى قاعة الفحص", "C'est votre tour ! Veuillez entrer.")}</div></div>""", unsafe_allow_html=True)
                    elif my_status == 'مكتمل' or my_status == 'ملغى':
                        st.markdown(f"""<div style="background: #fffbeb; border: 2px solid #f59e0b; border-radius: 14px; padding: 14px; text-align: center; margin-top: 10px;"><div style="font-size: 1.05rem; font-weight: 700; color: #92400e;">⚠️ {t("هذا الموعد منتهي أو ملغى.", "Ce rendez-vous est terminé ou annulé.")}</div></div>""", unsafe_allow_html=True)
                    elif my_status == 'طلب استعجالي':
                        st.info(t("طلبك الاستعجالي قيد المراجعة والمصادقة من العيادة.", "Votre demande est en cours de validation."))
                    else:
                        my_t_order = read_df("SELECT COUNT(*) as cnt FROM appointments WHERE appointment_date = ? AND status = 'في الانتظار' AND ticket_number < ?", (today_str, my_t_num)).iloc[0]['cnt']
                        wait_mins = my_t_order * int(settings.get('slot_minutes', 20))
                        formatted_time = format_wait_time(wait_mins)
                        
                        if my_t_order == 0: patients_txt = t("دورك هو القادم مباشرة!", "Vous êtes le prochain !")
                        elif my_t_order == 1: patients_txt = t("مريض واحد فقط", "1 seul patient")
                        elif my_t_order == 2: patients_txt = t("مريضان (2)", "2 patients")
                        elif 3 <= my_t_order <= 10: patients_txt = t(f"{my_t_order} مرضى", f"{my_t_order} patients")
                        else: patients_txt = t(f"{my_t_order} مريضاً", f"{my_t_order} patients")

                        st.markdown(f"""
                        <div style="background: linear-gradient(135deg, #f0fdfa, #f8fafc); border: 2px solid #0d9488; border-radius: 14px; padding: 18px; margin-top: 10px; text-align: center;">
                            <div style="font-size: 1.1rem; color: #1e293b; margin-bottom: 8px;">👥 {t("أمامك في الصف:", "Devant vous :")} <span style="background: #ccfbf1; color: #0f766e; padding: 4px 12px; border-radius: 8px; font-weight: 800; font-size: 1.15rem;">{patients_txt}</span></div>
                            <div style="font-size: 1.25rem; font-weight: 800; color: #0f766e; margin-top: 8px;">⏳ {t("الوقت التقديري المتبقي:", "Temps estimé :")} <span style="color: #0d9488;">{formatted_time}</span></div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.warning(t("الرمز غير صحيح أو لا يوجد موعد اليوم بهذا الرمز.", "Code incorrect ou pas de rdv aujourd'hui."))

    live_queue_box()
    st.divider()
    
    c_nav1, c_nav2, c_nav3 = st.columns(3)
    with c_nav1:
        if st.button(t("📅 حجز موعد عادي", "📅 Rendez-vous normal"), use_container_width=True, type="primary" if st.session_state.patient_subview == 'book' else "secondary"):
            st.session_state.patient_subview = 'book'; st.rerun()
    with c_nav2:
        if st.button(t("🚨 طلب موعد استعجالي", "🚨 Demande urgente"), use_container_width=True, type="primary" if st.session_state.patient_subview == 'urgent' else "secondary"):
            st.session_state.patient_subview = 'urgent'; st.rerun()
    with c_nav3:
        if st.button(t("💊 وصفاتي وتتبع حجزي", "💊 Ordonnances & Suivi"), use_container_width=True, type="primary" if st.session_state.patient_subview == 'records' else "secondary"):
            st.session_state.patient_subview = 'records'; st.rerun()
            
    st.write("")

    if st.session_state.patient_subview == 'book':
        work_start = settings.get('work_start','09:00')
        work_end = settings.get('work_end','16:00')
        slot_mins = int(settings.get('slot_minutes', 20))
        
        work_days_list = get_working_days_list()
        work_days_names = [DAYS_AR[d] if st.session_state.lang == 'ar' else DAYS_FR[d] for d in work_days_list]
        st.caption(t(f"🗓️ أيام عمل العيادة: {' ، '.join(work_days_names)} (من {work_start} إلى {work_end})", f"🗓️ Jours d'ouverture : {', '.join(work_days_names)}"))
        
        # دالة البحث الذكي عن أول يوم شاغر تلقائياً
        suggested_date = get_first_available_date(get_tunis_date(), work_start, work_end, slot_mins)
        
        c1, c2 = st.columns(2)
        with c1:
            sel_date = st.date_input(t("اختر تاريخ الموعد:", "Date du rendez-vous :"), value=suggested_date, min_value=get_tunis_date())
            is_work_day = sel_date.weekday() in work_days_list
            if not is_work_day:
                st.error(t("⚠️ العيادة مغلقة في هذا اليوم. يرجى اختيار يوم آخر من أيام العمل.", "⚠️ La clinique est fermée ce jour-là."))
                avail_slots = []
            else:
                booked_set = set(get_booked_slots(sel_date.isoformat()))
                avail_slots = [s for s in generate_time_slots(work_start, work_end, slot_mins, sel_date) if s not in booked_set]
                if not avail_slots:
                    st.warning(t("لا توجد أوقات متاحة في هذا اليوم، يرجى اختيار يوم موالي.", "Aucun horaire disponible pour ce jour, choisissez un autre."))
            sel_time = st.selectbox(t("الوقت المتاح:", "Heure disponible :"), avail_slots) if avail_slots else None
            
            visit_reasons = [
                t("غير محدد (اختياري)", "Non spécifié (Optionnel)"),
                t("عيادة أولى (فحص جديد)", "Première consultation"),
                t("مراقبة / متابعة (Contrôle)", "Contrôle / Suivi"),
                t("تجديد وصفة طبية", "Renouvellement d'ordonnance"),
                t("استشارة نتائج تحاليل", "Résultats d'analyses")
            ]
            sel_reason = st.selectbox(t("نوع الموعد (اختياري):", "Motif du rendez-vous (Optionnel) :"), visit_reasons)
            
        with c2:
            p_n = st.text_input(t("اسم المريض الكامل:", "Nom complet du patient :"))
            p_p = st.text_input(t("رقم الهاتف:", "Numéro de téléphone :"))
            
            if st.button(t("✅ تأكيد الحجز", "✅ Confirmer le rendez-vous"), type="primary", use_container_width=True):
                if is_work_day and sel_time and p_n.strip() and p_p.strip():
                    new_code = generate_short_code() # توليد الرمز البسيط الجديد
                    try:
                        execute_query('''INSERT INTO appointments 
                            (patient_name, patient_phone, appointment_date, appointment_time, ticket_number, status, visit_type, visit_reason, app_code, created_at) 
                            VALUES (?, ?, ?, ?, 0, 'في الانتظار', 'موعد مسبق', ?, ?, ?)''',
                            (p_n.strip(), p_p.strip(), sel_date.isoformat(), sel_time, sel_reason, new_code, get_tunis_time().strftime("%Y-%m-%d %H:%M")))
                        recalculate_tickets(sel_date.isoformat())
                        st.success(t(f"✅ تم الحجز بنجاح! رمزك السري هو: {new_code}", f"✅ Réservé ! Code de suivi: {new_code}"))
                        st.info(t("يرجى الاحتفاظ بهذا الرمز (حرف وثلاثة أرقام) لتتبع دورك في الطابور عبر التطبيق.", "Gardez ce code pour suivre votre tour."))
                    except Exception as e:
                        if "unique" in str(e).lower():
                            st.error(t("عذراً، هذا الموعد حجز للتو. يرجى اختيار وقت آخر.", "Désolé, cet horaire vient d'être réservé."))
                        else:
                            st.error(t("حدث خطأ تقني أثناء الحجز، يرجى المحاولة من جديد.", "Erreur technique, réessayez."))
                else:
                    st.warning(t("يرجى التأكد من اختيار يوم، وقت متاح، وإدخال الاسم ورقم الهاتف.", "Veuillez remplir tous les champs obligatoires."))

    elif st.session_state.patient_subview == 'urgent':
        st.markdown(t("#### 🚨 طلب موعد استعجالي (خارج المواعيد العادية)", "#### 🚨 Demande de rendez-vous urgent"))
        st.info(t("يتم إرسال طلبك مباشرة للعيادة للمصادقة عليه وإدراجك في صف اليوم حسب الأولوية.", "Votre demande sera envoyée pour validation rapide."))
        with st.form("urgent_req_form"):
            u_name = st.text_input(t("اسم المريض الكامل:", "Nom complet du patient :"))
            u_phone = st.text_input(t("رقم الهاتف للتواصل:", "Numéro de téléphone :"))
            u_note = st.text_area(t("اذكر باختصار سبب الاستعجال / الأعراض:", "Motif de l'urgence / Symptômes :"), placeholder=t("مثال: حرارة مرتفعة جداً، ألم حاد...", "Ex: Forte fièvre, douleur aiguë..."))
            if st.form_submit_button(t("🚀 إرسال الطلب الاستعجالي", "🚀 Envoyer la demande urgente"), type="primary"):
                if u_name.strip() and u_phone.strip():
                    today_str = get_tunis_date().isoformat()
                    now_str = get_tunis_time().strftime("%H:%M")
                    new_code = generate_short_code()
                    execute_query('''INSERT INTO appointments 
                        (patient_name, patient_phone, appointment_date, appointment_time, ticket_number, status, visit_type, visit_reason, urgent_note, app_code, created_at) 
                        VALUES (?, ?, ?, ?, 0, 'طلب استعجالي', 'طلب استعجالي', 'حالة استعجالية', ?, ?, ?)''',
                        (u_name.strip(), u_phone.strip(), today_str, now_str, u_note.strip(), new_code, get_tunis_time().strftime("%Y-%m-%d %H:%M")))
                    st.success(t(f"✅ تم إرسال طلبك الاستعجالي! رمز التتبع الخاص بك هو: {new_code}", f"✅ Demande envoyée ! Code: {new_code}"))
                else:
                    st.error(t("يرجى إدخال الاسم ورقم الهاتف.", "Le nom et le téléphone sont obligatoires."))

    elif st.session_state.patient_subview == 'records':
        st.markdown(t("#### 💊 أدخل بياناتك للاطلاع على وصفاتك الطبية وتتبع مواعيدك", "#### 💊 Entrez vos données pour voir vos ordonnances et rendez-vous"))
        c_p1, c_p2 = st.columns(2)
        search_phone = c_p1.text_input(t("رقم الهاتف:", "Téléphone :"), key="search_ph")
        search_name = c_p2.text_input(t("اسم المريض (إجباري للمطابقة السرية):", "Nom du patient (Obligatoire) :"), key="search_nm")
        
        if st.button(t("🔍 بحث وعرض", "🔍 Rechercher"), type="primary"):
            if search_phone.strip() and search_name.strip():
                if is_postgres():
                    app_query = "SELECT * FROM appointments WHERE patient_phone = %s AND patient_name ILIKE %s ORDER BY appointment_date DESC, id DESC LIMIT 5"
                    rec_query = "SELECT * FROM medical_records WHERE patient_phone = %s AND patient_name ILIKE %s ORDER BY id DESC"
                else:
                    app_query = "SELECT * FROM appointments WHERE patient_phone = ? AND LOWER(patient_name) LIKE LOWER(?) ORDER BY appointment_date DESC, id DESC LIMIT 5"
                    rec_query = "SELECT * FROM medical_records WHERE patient_phone = ? AND LOWER(patient_name) LIKE LOWER(?) ORDER BY id DESC"
                
                app_df = read_df(app_query, (search_phone.strip(), f"%{search_name.strip()}%"))
                if not app_df.empty:
                    st.markdown(t("##### 📅 حالة مواعيدك وطلباتك الأخيرة:", "##### 📅 Statut de vos rendez-vous :"))
                    for _, a_row in app_df.iterrows():
                        st_badge = a_row['status']
                        code_txt = f"الرمز: {a_row['app_code']}" if a_row['app_code'] else ""
                        safe_p_name = html.escape(str(a_row['patient_name']))
                        st.info(f"👤 **{safe_p_name}** | 📅 التاريخ: **{a_row['appointment_date']}** ({a_row['appointment_time']}) | 📌 الحالة: **{st_badge}** | {code_txt}")
                
                rec_df = read_df(rec_query, (search_phone.strip(), f"%{search_name.strip()}%"))
                if not rec_df.empty:
                    st.markdown(t("##### 💊 الوصفات الطبية المسجلة:", "##### 💊 Ordonnances enregistrées :"))
                    for _, row in rec_df.iterrows():
                        safe_r_name = html.escape(str(row['patient_name']))
                        safe_diag = html.escape(str(row['diagnosis'])) if row['diagnosis'] else ''
                        safe_rx = html.escape(str(row['prescription'])) if row['prescription'] else ''
                        safe_lab = html.escape(str(row['lab_tests'])) if row['lab_tests'] else ''
                        safe_notes = html.escape(str(row['doctor_notes'])) if row['doctor_notes'] else ''

                        st.markdown(f"""
                        <div class="medical-card">
                            <span style="background:#ccfbf1; padding:4px 10px; border-radius:10px; font-weight:bold; color:#0f766e;">📅 {row['visit_date']} | المريض: {safe_r_name}</span>
                            <p style="margin-top:15px; font-size:1.1rem;"><b>🩺 {t("التشخيص:", "Diagnostic :")}</b> {safe_diag}</p>
                            <div style="background:#f0fdf4; padding:12px; border-radius:8px; border:1px dashed #16a34a;"><b>💊 {t("الوصفة:", "Ordonnance :")}</b><br>{safe_rx}</div>
                            <div style="background:#eff6ff; padding:12px; border-radius:8px; border:1px dashed #2563eb; margin-top:8px;"><b>🔬 {t("التحاليل:", "Analyses :")}</b><br>{safe_lab}</div>
                            <div style="background:#fef3c7; padding:12px; border-radius:8px; border:1px dashed #d97706; margin-top:12px;"><b style="color:#b45309;">📌 {t("ملاحظات وتوصيات الطبيب:", "Notes et recommandations :")}</b><br><span style="color:#92400e;">{safe_notes}</span></div>
                        </div>
                        """, unsafe_allow_html=True)
                elif app_df.empty:
                    st.warning(t("لا توجد مواعيد أو وصفات طبية مطابقة.", "Aucun dossier trouvé."))
            else:
                st.warning(t("الرجاء إدخال رقم الهاتف واسم المريض للمطابقة.", "Veuillez entrer le téléphone et le nom."))

# ==============================================================================
# واجهة الكاتبة
# ==============================================================================
elif st.session_state.current_view == 'secretary':
    if not st.session_state.sec_auth:
        col_c1, col_c2, col_c3 = st.columns([1,2,1])
        with col_c2:
            st.markdown(t("<h3 style='text-align:center;'>🔒 تسجيل دخول الكاتبة</h3>", "<h3 style='text-align:center;'>🔒 Connexion Secrétaire</h3>"), unsafe_allow_html=True)
            sec_pwd = st.text_input(t("رمز الدخول:", "Mot de passe :"), type="password")
            if st.button(t("دخول", "Connexion"), use_container_width=True, type="primary"):
                if st.session_state.login_attempts >= 4:
                     st.error(t("تجاوزت عدد المحاولات، حاول لاحقاً.", "Trop de tentatives."))
                elif sec_pwd == str(settings.get('sec_pwd', '0000')):
                    st.session_state.sec_auth = True
                    st.session_state.login_attempts = 0
                    st.rerun()
                else:
                    st.session_state.login_attempts += 1
                    st.error(t("الرمز غير صحيح!", "Mot de passe incorrect !"))
    else:
        st.subheader(t("👩‍💻 شاشة الكاتبة وإدارة الصف", "👩‍💻 Écran Secrétaire & Gestion de la file"))
        today_str = get_tunis_date().isoformat()
        
        if settings.get('last_reset_date', '') != today_str:
            try:
                execute_query("UPDATE clinic_settings SET current_ticket = 0, last_reset_date = ? WHERE id = 1", (today_str,))
            except Exception:
                execute_query("UPDATE clinic_settings SET current_ticket = 0 WHERE id = 1")
            settings['current_ticket'] = 0
            settings['last_reset_date'] = today_str
            
        render_urgent_requests_box('secretary')
            
        today_df = read_df("SELECT * FROM appointments WHERE appointment_date = ? AND status NOT IN ('ملغى', 'طلب استعجالي') ORDER BY ticket_number ASC, appointment_time ASC", (today_str,))
        
        in_exam = today_df[today_df['status'] == 'في الفحص']
        waiting = today_df[today_df['status'] == 'في الانتظار']
        
        m1, m2, m3 = st.columns(3)
        current_patient_display = f"#{in_exam.iloc[0]['ticket_number']} - {html.escape(str(in_exam.iloc[0]['patient_name']))}" if not in_exam.empty else t("لا أحد", "Aucun")
        next_patient_display = f"#{waiting.iloc[0]['ticket_number']} - {html.escape(str(waiting.iloc[0]['patient_name']))}" if not waiting.empty else t("فارغ", "Vide")
        
        m1.metric(t("🟢 في الفحص الآن", "🟢 En consultation"), current_patient_display)
        m2.metric(t("🟡 القادم في الصف", "🟡 Prochain patient"), next_patient_display)
        m3.metric(t("👥 المنتظرون بالخارج", "👥 En attente"), len(waiting))
        
        st.divider()
        c_btn, c_add = st.columns([1, 1])
        with c_btn:
            st.info(t("لتحديث رقم الشاشة للمرضى وإدخال المريض التالي للفحص:", "Pour appeler le patient suivant en salle de consultation :"))
            if st.button(t("⏭️ نداء المريض التالي (إدخال للفحص)", "⏭️ Appeler le patient suivant"), type="primary", use_container_width=True):
                execute_query("UPDATE appointments SET status = 'مكتمل' WHERE appointment_date = ? AND status = 'في الفحص'", (today_str,))
                if not waiting.empty:
                    next_id = int(waiting.iloc[0]['id'])
                    execute_query("UPDATE appointments SET status = 'في الفحص' WHERE id = ?", (next_id,))
                    update_current_ticket(today_str)
                    st.success("تم نداء المريض التالي")
                else:
                    st.warning(t("لا يوجد مرضى في الانتظار حالياً.", "Aucun patient en attente."))
                st.rerun()
                
        with c_add:
            with st.form("walkin"):
                st.write(t("➕ **إضافة مريض مباشر في الصف:**", "➕ **Ajouter un patient à la file :**"))
                cw1, cw2 = st.columns(2)
                w_n = cw1.text_input(t("اسم المريض:", "Nom :"))
                w_p = cw2.text_input(t("رقم الهاتف:", "Téléphone :"))
                w_reason = st.selectbox(t("نوع الزيارة:", "Motif :"), [t("عيادة أولى", "Première consultation"), t("مراقبة / Contrôle", "Contrôle"), t("استعجالي مباشر", "Urgence directe"), t("تجديد وصفة", "Renouvellement")])
                if st.form_submit_button(t("🎫 قطع تذكرة وإدراج بالصف", "🎫 Créer ticket")) and w_n.strip():
                    new_code = generate_short_code()
                    current_time_str = get_tunis_time().strftime("%H:%M")
                    execute_query('''INSERT INTO appointments 
                        (patient_name, patient_phone, appointment_date, appointment_time, ticket_number, status, visit_type, visit_reason, app_code, created_at) 
                        VALUES (?, ?, ?, ?, 0, 'في الانتظار', 'حضور مباشر', ?, ?, ?)''',
                        (w_n.strip(), w_p.strip(), today_str, current_time_str, w_reason, new_code, get_tunis_time().strftime("%Y-%m-%d %H:%M")))
                    recalculate_tickets(today_str)
                    st.rerun()

        st.divider()
        st.subheader(t("📋 إدارة وتعديل الصف لليوم (تقديم، تأخير، أو إلغاء)", "📋 Gérer et modifier la file d'aujourd'hui"))
        all_today_df = read_df("SELECT * FROM appointments WHERE appointment_date = ? ORDER BY ticket_number ASC, id ASC", (today_str,))
        if not all_today_df.empty:
            avail_slots_for_edit = generate_time_slots(settings.get('work_start','09:00'), settings.get('work_end','16:00'), int(settings.get('slot_minutes', 20)), get_tunis_date())
            for _, p_row in all_today_df.iterrows():
                safe_name = html.escape(str(p_row['patient_name']))
                with st.expander(f"🎫 #{p_row['ticket_number']} | 👤 {safe_name} | 🕒 {p_row['appointment_time']} | 📌 {p_row['status']}"):
                    ec1, ec2, ec3, ec4 = st.columns([1, 1, 1, 1])
                    new_t_num = ec1.number_input(t("الترتيب الداخلي:", "Ordre :"), min_value=0, value=int(p_row['ticket_number']), key=f"tnum_{p_row['id']}")
                    status_opts = ['في الانتظار', 'في الفحص', 'مكتمل', 'ملغى', 'طلب استعجالي']
                    curr_st_idx = status_opts.index(p_row['status']) if p_row['status'] in status_opts else 0
                    new_status = ec2.selectbox(t("الحالة:", "Statut :"), status_opts, index=curr_st_idx, key=f"st_{p_row['id']}")
                    
                    curr_time = p_row['appointment_time']
                    opts_time = avail_slots_for_edit + [curr_time] if curr_time not in avail_slots_for_edit else avail_slots_for_edit
                    new_time = ec3.selectbox(t("التوقيت:", "Heure :"), opts_time, index=opts_time.index(curr_time) if curr_time in opts_time else 0, key=f"tm_{p_row['id']}")
                    
                    if ec4.button(t("💾 حفظ التعديل", "💾 Enregistrer"), key=f"sv_{p_row['id']}", type="primary"):
                        execute_query("UPDATE appointments SET ticket_number = ?, status = ?, appointment_time = ? WHERE id = ?",
                                      (int(new_t_num), new_status, new_time, int(p_row['id'])))
                        if new_status == 'في الفحص' or new_status == 'مكتمل':
                            update_current_ticket(today_str)
                        st.success(t("تم تحديث بيانات المريض في الصف!", "Mis à jour !"))
                        st.rerun()
        else:
            st.info(t("لا يوجد مرضى مسجلون في صف اليوم حتى الآن.", "Aucun patient enregistré aujourd'hui."))

# ==============================================================================
# واجهة الطبيب
# ==============================================================================
elif st.session_state.current_view == 'doctor':
    if not st.session_state.doc_auth:
        col_c1, col_c2, col_c3 = st.columns([1,2,1])
        with col_c2:
            st.markdown(t("<h3 style='text-align:center;'>🔒 تسجيل دخول الطبيب</h3>", "<h3 style='text-align:center;'>🔒 Connexion Médecin</h3>"), unsafe_allow_html=True)
            doc_pwd = st.text_input(t("رمز الدخول:", "Mot de passe :"), type="password", key="doc_login_pwd")
            if st.button(t("دخول", "Connexion"), use_container_width=True, type="primary"):
                if st.session_state.login_attempts >= 4:
                     st.error(t("تجاوزت عدد المحاولات، حاول لاحقاً.", "Trop de tentatives."))
                elif doc_pwd == str(settings.get('doc_pwd', '0000')):
                    st.session_state.doc_auth = True
                    st.session_state.login_attempts = 0
                    st.rerun()
                else:
                    st.session_state.login_attempts += 1
                    st.error(t("الرمز غير صحيح!", "Mot de passe incorrect !"))
    else:
        render_urgent_requests_box('doctor')

        c_nav1, c_nav2 = st.columns(2)
        with c_nav1:
            if st.button(t("👨‍⚕️ مكتب الطبيب (إصدار الوصفات)", "👨‍⚕️ Bureau du médecin (Ordonnances)"), use_container_width=True, type="primary" if st.session_state.doctor_subview == 'rx' else "secondary"):
                st.session_state.doctor_subview = 'rx'; st.rerun()
        with c_nav2:
            if st.button(t("⚙️ إعدادات العمل والغياب الاستعجالي", "⚙️ Paramètres, Jours & Absence"), use_container_width=True, type="primary" if st.session_state.doctor_subview == 'settings' else "secondary"):
                st.session_state.doctor_subview = 'settings'; st.rerun()
                
        st.write("")
        
        if st.session_state.doctor_subview == 'rx':
            today_str = get_tunis_date().isoformat()
            in_exam = read_df("SELECT * FROM appointments WHERE appointment_date = ? AND status = 'في الفحص'", (today_str,))
            completed_today = read_df("SELECT COUNT(*) as cnt FROM appointments WHERE appointment_date = ? AND status = 'مكتمل'", (today_str,)).iloc[0]['cnt']
            
            def_n = in_exam.iloc[0]['patient_name'] if not in_exam.empty else ""
            def_p = in_exam.iloc[0]['patient_phone'] if not in_exam.empty else ""
            def_reason = in_exam.iloc[0].get('visit_reason', '') if not in_exam.empty else ""
            
            c_info, c_hist, c_rev = st.columns([2, 1, 1])
            with c_info:
                if def_n:
                    safe_dn = html.escape(str(def_n))
                    st.success(t(f"🟢 المريض الحالي: {safe_dn} | التذكرة: #{in_exam.iloc[0]['ticket_number']} | ({def_reason})", f"🟢 Patient actuel: {safe_dn}"))
                else:
                    st.info(t("لا يوجد مريض في قاعة الفحص حالياً.", "Aucun patient en salle d'examen."))
            with c_hist:
                if def_n and def_p:
                    past_visits = read_df("SELECT COUNT(*) as cnt FROM medical_records WHERE patient_name = ? AND patient_phone = ?", (def_n, def_p)).iloc[0]['cnt']
                    st.info(f"📁 زيارات سابقة: {past_visits}")
            with c_rev:
                est_rev = int(completed_today) * int(settings.get('consultation_price', 60))
                st.metric(t("💼 فحوصات مكتملة اليوم", "💼 Consultations"), f"{completed_today} ({est_rev} DT)")

            templates = {
                t("-- اختر قالباً سريعاً (اختياري) --", "-- Modèle rapide --"): ("", "", ""),
                t("نزلة برد / التهاب حلق عادي", "Grippe / Pharyngite"): ("التهاب فيروسي بالحلق", "Paracétamol 1000mg (1x3/j)\nVitamine C 1000mg (1/j)", "الراحة وشرب السوائل الدافئة"),
                t("التهاب لوزتين حاد", "Angine bactérienne"): ("التهاب اللوزتين الحاد", "Amoxicilline 1g (1x2/j pendant 7j)\nParacétamol 1000mg", "إكمال المضاد الحيوي بالكامل"),
                t("مراقبة دورية / تحاليل شاملة", "Bilan standard"): ("فحص دوري شامل", "مكمل غذائي متعدد الفيتامينات", "العودة بعد ظهور نتائج التحاليل")
            }
            sel_tpl = st.selectbox(t("⚡ تعبئة سريعة من القوالب الجاهزة:", "⚡ Remplissage rapide :"), list(templates.keys()))
            tpl_diag, tpl_rx, tpl_notes = templates[sel_tpl]

            with st.form("rx"):
                st.caption("ملاحظة: الاسم ورقم الهاتف فقط ضروريان، باقي الحقول اختيارية.")
                col1, col2 = st.columns(2)
                d_n = col1.text_input(t("اسم المريض:", "Nom du patient :"), value=def_n)
                d_p = col2.text_input(t("رقم الهاتف (ليرى المريض وصفته):", "Téléphone :"), value=def_p)
                d_diag = st.text_input(t("🩺 التشخيص (Diagnostic) [اختياري]:", "🩺 Diagnostic [Optionnel] :"), value=tpl_diag)
                
                c_rx, c_lab = st.columns(2)
                d_rx = c_rx.text_area(t("💊 الوصفة (Ordonnance) [اختياري]:", "💊 Ordonnance [Optionnel] :"), value=tpl_rx, height=150)
                d_lab = c_lab.text_area(t("🔬 التحاليل (Analyses) [اختياري]:", "🔬 Analyses [Optionnel] :"), height=150)
                d_notes = st.text_input(t("📌 ملاحظات وتوصيات للمريض [اختياري]:", "📌 Notes [Optionnel] :"), value=tpl_notes)
                
                if st.form_submit_button(t("💾 حفظ الملف وإكمال الفحص", "💾 Enregistrer le dossier"), type="primary"):
                    if d_n.strip() and d_p.strip():
                        execute_query("INSERT INTO medical_records (patient_phone, patient_name, visit_date, diagnosis, prescription, lab_tests, doctor_notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                      (d_p.strip(), d_n.strip(), today_str, d_diag.strip(), d_rx.strip(), d_lab.strip(), d_notes.strip()))
                        
                        if not in_exam.empty:
                            execute_query("UPDATE appointments SET status = 'مكتمل' WHERE id = ?", (int(in_exam.iloc[0]['id']),))
                            update_current_ticket(today_str)
                            
                        st.success(t("✅ تم حفظ الملف الطبي للمريض بنجاح!", "✅ Dossier enregistré avec succès !"))
                    else:
                        st.error(t("الاسم ورقم الهاتف ضروريان לחفظ الملف.", "Le nom et le téléphone sont obligatoires."))
            
            st.markdown("---")
            if d_n and d_rx.strip():
                rx_html = f"""<html dir="rtl"><body style="font-family:Arial,sans-serif;padding:40px;line-height:1.8;">
<h2 style="text-align:center;border-bottom:2px solid #000;padding-bottom:10px;">د. {html.escape(doc_clean_name)}</h2>
<p style="text-align:center;color:#555;">{html.escape(str(settings.get('specialty', '')))}</p>
<p style="margin-top:30px;"><b>التاريخ:</b> {today_str} <br><b>اسم المريض:</b> {html.escape(d_n)}</p>
<div style="min-height:300px;margin-top:20px;"><h3>الوصفة الطبية:</h3><pre style="font-family:Arial,sans-serif;font-size:18px;white-space:pre-wrap;">{html.escape(d_rx)}</pre></div>
<p style="text-align:center;margin-top:50px;"><b>إمضاء وختم الطبيب</b></p>
</body></html>"""
                
                safe_rx_json = json.dumps(rx_html).replace("</", "<\\/")
                
                print_script = f"""
                <script>
                function printRx() {{
                    try {{
                        const rxWindow = window.open('', '', 'width=800,height=600');
                        rxWindow.document.write({safe_rx_json});
                        rxWindow.document.close();
                        rxWindow.focus();
                        setTimeout(function() {{ rxWindow.print(); rxWindow.close(); }}, 250);
                    }} catch (e) {{ alert("حدث خطأ في الطباعة."); }}
                }}
                </script>
                <button onclick="printRx()" style="background-color: #0f766e; color: white; padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: bold; width: 100%;">🖨️ طباعة الوصفة الآن (مباشرة للطابعة)</button>
                """
                components.html(print_script, height=50)
            
        elif st.session_state.doctor_subview == 'settings':
            st.markdown(t("### ⚙️ إعدادات أوقات وأيام العمل والمواعيد الاستعجالية", "### ⚙️ Paramètres de travail et d'urgence"))
            with st.form("doctor_clinic_settings"):
                c_set1, c_set2, c_set3 = st.columns(3)
                new_start = c_set1.time_input(t("⏰ بداية الدوام:", "⏰ Début:"), value=datetime.strptime(settings.get('work_start', '09:00'), "%H:%M").time())
                new_end = c_set2.time_input(t("⏰ نهاية الدوام:", "⏰ Fin:"), value=datetime.strptime(settings.get('work_end', '16:00'), "%H:%M").time())
                new_slot = c_set3.number_input(t("⏱️ مدة الفحص (دقائق):", "⏱️ Durée (min) :"), min_value=5, value=int(settings.get('slot_minutes', 20)))
                
                current_work_days = get_working_days_list()
                selected_days = st.multiselect(
                    t("🗓️ أيام العمل الأسبوعية المتاحة للحجز:", "🗓️ Jours de travail :"),
                    options=list(DAYS_AR.keys()),
                    default=current_work_days,
                    format_func=lambda x: DAYS_AR[x] if st.session_state.lang == 'ar' else DAYS_FR[x]
                )

                approver_map = {
                    'both': t("الطبيب والكاتبة معاً", "Médecin et Secrétaire"),
                    'doctor': t("الطبيب فقط", "Médecin uniquement"),
                    'secretary': t("الكاتبة فقط", "Secrétaire uniquement")
                }
                curr_app = settings.get('urgent_approver', 'both')
                new_approver = st.selectbox(
                    t("🚨 من يصادق على طلبات المواعيد الاستعجالية؟", "🚨 Qui valide les demandes urgentes ?"),
                    options=['both', 'doctor', 'secretary'],
                    index=['both', 'doctor', 'secretary'].index(curr_app) if curr_app in ['both', 'doctor', 'secretary'] else 0,
                    format_func=lambda x: approver_map[x]
                )

                new_price = st.number_input(t("💰 تعريفة العيادة التقديرية [اختياري]:", "💰 Tarif consultation [Optionnel]:"), min_value=0, value=int(settings.get('consultation_price', 60)))
                
                st.subheader(t("🔒 أرقام الدخول السرية", "🔒 Mots de passe d'accès"))
                cp1, cp2 = st.columns(2)
                new_doc_pwd = cp1.text_input(t("الرقم السري للطبيب:", "Mot de passe médecin :"), value=str(settings.get('doc_pwd', '0000')), type="password")
                new_sec_pwd = cp2.text_input(t("الرقم السري للكاتبة:", "Mot de passe secrétaire :"), value=str(settings.get('sec_pwd', '0000')), type="password")
                
                if st.form_submit_button(t("💾 حفظ كافة الإعدادات", "💾 Enregistrer les paramètres"), type="primary"):
                    days_str = ",".join(str(d) for d in sorted(selected_days))
                    try:
                        execute_query('''UPDATE clinic_settings 
                            SET work_start=?, work_end=?, slot_minutes=?, work_days=?, urgent_approver=?, consultation_price=?, doc_pwd=?, sec_pwd=? 
                            WHERE id=1''', 
                            (new_start.strftime("%H:%M"), new_end.strftime("%H:%M"), int(new_slot), days_str, new_approver, int(new_price), new_doc_pwd, new_sec_pwd))
                        st.success(t("✅ تم تحديث إعدادات العيادة بنجاح!", "✅ Paramètres mis à jour !"))
                    except Exception:
                        st.error(t("حدث خطأ. تأكد من تحديث قاعدة البيانات.", "Erreur lors de la mise à jour."))
                    st.rerun()

            st.divider()
            st.markdown(t("### 📆 إعلام بالغياب وتأجيل المواعيد أوتوماتيكياً", "### 📆 Déclarer une absence et reporter automatiquement"))
            st.info(t("عند إعلان الغياب ليوم معين، سيقوم النظام أوتوماتيكياً بترحيل جميع مواعيد ذلك اليوم إلى يوم العمل الجديد الذي تختاره، مع نشر تنبيه للمرضى.", "Les rendez-vous seront automatiquement déplacés."))
            with st.form("absence_postpone_form"):
                ca_1, ca_2 = st.columns(2)
                abs_date = ca_1.date_input(t("تاريخ يوم الغياب:", "Date d'absence :"), min_value=get_tunis_date())
                suggested_next = find_next_working_day(abs_date)
                new_target_date = ca_2.date_input(t("ترحيل المواعيد أوتوماتيكياً إلى يوم:", "Reporter les RDV au :"), value=suggested_next, min_value=get_tunis_date())
                custom_notice = st.text_input(t("رسالة التنبيه للمرضى في الواجهة (اتركها فارغة لإخفاء التنبيه):", "Message d'alerte aux patients :"),
                                              value=settings.get('absence_notice', ''),
                                              placeholder=t("مثال: يعتذر الدكتور عن التواجد يوم كذا، وتم ترحيل المواعيد ليوم كذا.", "Ex: Le docteur sera absent..."))
                
                c_sub1, c_sub2 = st.columns(2)
                if c_sub1.form_submit_button(t("🔄 تأكيد الغياب وترحيل المواعيد أوتوماتيكياً", "🔄 Confirmer et reporter les RDV"), type="primary"):
                    abs_str = abs_date.isoformat()
                    target_str = new_target_date.isoformat()
                    try:
                        affected = read_df("SELECT COUNT(*) as cnt FROM appointments WHERE appointment_date = ? AND status = 'في الانتظار'", (abs_str,)).iloc[0]['cnt']
                        
                        execute_query("UPDATE appointments SET appointment_date = ?, appointment_time = '' WHERE appointment_date = ? AND status = 'في الانتظار'", (target_str, abs_str))
                        recalculate_tickets(target_str)
                        
                        notice_msg = custom_notice.strip() if custom_notice.strip() else f"تم تأجيل مواعيد يوم {abs_str} تلقائياً إلى يوم {target_str} بسبب غياب طارئ."
                        execute_query("UPDATE clinic_settings SET absence_notice = ? WHERE id = 1", (notice_msg,))
                        st.success(t(f"✅ تم ترحيل {affected} موعداً بنجاح من يوم {abs_str} إلى يوم {target_str} وتحديث أرقام الصف!", f"✅ {affected} rendez-vous reportés !"))
                    except Exception:
                        st.error("حدث خطأ أثناء الترحيل.")
                    st.rerun()
                if c_sub2.form_submit_button(t("🗑️ مسح رسالة التنبيه من الواجهة", "🗑️ Effacer l'alerte")):
                    try:
                        execute_query("UPDATE clinic_settings SET absence_notice = '' WHERE id = 1")
                    except Exception:
                        pass
                    st.success(t("تم إخفاء رسالة التنبيه.", "Alerte effacée."))
                    st.rerun()

# ==========================================
# 4. القائمة التوسيعية (ركن المطور فقط)
# ==========================================
with st.expander("⚙️ ركن المطور وإعدادات العيادة (SaaS)", expanded=False):
    db_status = "🟢 متصل بـ Neon PostgreSQL (ذاكرة دائمة)" if is_postgres() else "🟡 متصل بـ SQLite محلي (أضف DATABASE_URL في Secrets للربط مع Neon)"
    st.caption(f"حالة قاعدة البيانات: **{db_status}**")
    with st.form("saas_admin_form"):
        st.subheader(t("إعدادات وهوية العيادة", "Identité de la clinique"))
        new_doc_name = st.text_input(t("اسم الطبيب:", "Nom du médecin:"), value=settings.get('doctor_name', ''))
        new_specialty = st.text_input(t("الاختصاص:", "Spécialité:"), value=settings.get('specialty', ''))
        new_phone = st.text_input(t("رقم هاتف العيادة:", "Téléphone:"), value=settings.get('phone', ''))
        st.subheader(t("💰 حالة الاشتراك", "💰 Abonnement"))
        sub_status = st.selectbox(t("حالة الاشتراك:", "Statut:"), [1, 0], index=0 if settings.get('subscription_active', 1)==1 else 1, format_func=lambda x: t("✅ مفعّل", "✅ Actif") if x==1 else t("⛔ موقوف", "⛔ Suspendu"))
        if st.form_submit_button(t("💾 حفظ الهوية", "💾 Enregistrer"), type="primary"):
            execute_query('''UPDATE clinic_settings SET doctor_name=?, specialty=?, phone=?, subscription_active=? WHERE id=1''', (new_doc_name, new_specialty, new_phone, sub_status))
            st.rerun()
            
    st.divider()
    if st.button(t("🔄 إعادة ضبط الرموز السرية لـ 0000", "🔄 Réinitialiser les codes à 0000")):
        execute_query("UPDATE clinic_settings SET sec_pwd='0000', doc_pwd='0000' WHERE id=1")
        st.session_state.sec_auth = False; st.session_state.doc_auth = False
        st.success(t("تمت إعادة ضبط الرموز لـ 0000 بنجاح.", "Mots de passe réinitialisés à 0000."))
