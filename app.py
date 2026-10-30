import streamlit as st
import sqlite3
from datetime import datetime, date, timedelta
import pandas as pd

# ==========================================
# 1. إعدادات الصفحة و Session State
# ==========================================
st.set_page_config(
    page_title="طبيبي د. | Mon Médecin Dr.",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# تهيئة المتغيرات الأساسية والتنقلات الفرعية
if 'current_view' not in st.session_state:
    st.session_state.current_view = 'home'
if 'sec_auth' not in st.session_state:
    st.session_state.sec_auth = False
if 'doc_auth' not in st.session_state:
    st.session_state.doc_auth = False
if 'lang' not in st.session_state:
    st.session_state.lang = 'ar'

# متغيرات التنقل داخل الأقسام (لتحويلها إلى مربعات ملونة بدل التبويبات)
if 'patient_subview' not in st.session_state:
    st.session_state.patient_subview = 'book'  # 'book' or 'records'
if 'doctor_subview' not in st.session_state:
    st.session_state.doctor_subview = 'rx'     # 'rx' or 'settings'

def t(ar_text, fr_text):
    return ar_text if st.session_state.lang == 'ar' else fr_text

# ==========================================
# 2. قاعدة البيانات المحلية (SQLite)
# ==========================================
DB_FILE = "clinic_saas.db"

def get_connection():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS clinic_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1), doctor_name TEXT, specialty TEXT, phone TEXT, address TEXT,
            work_start TEXT, work_end TEXT, slot_minutes INTEGER, consultation_price INTEGER, current_ticket INTEGER,
            subscription_active INTEGER, subscription_expiry TEXT, sec_pwd TEXT, doc_pwd TEXT)''')
    try:
        c.execute("ALTER TABLE clinic_settings ADD COLUMN sec_pwd TEXT DEFAULT '0000'")
        c.execute("ALTER TABLE clinic_settings ADD COLUMN doc_pwd TEXT DEFAULT '0000'")
    except: pass
    c.execute('''CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, patient_name TEXT, patient_phone TEXT, appointment_date TEXT, 
            appointment_time TEXT, ticket_number INTEGER, status TEXT, visit_type TEXT, created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS medical_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT, patient_phone TEXT, patient_name TEXT, visit_date TEXT, 
            diagnosis TEXT, prescription TEXT, lab_tests TEXT, doctor_notes TEXT)''')
    
    c.execute("SELECT COUNT(*) FROM clinic_settings")
    if c.fetchone()[0] == 0:
        c.execute('''INSERT INTO clinic_settings VALUES (
                1, 'سامي بن يوسف', 'أخصائي طب الأطفال وحديثي الولادة', '21655000111', 
                'شارع الحبيب بورقيبة - الطابق 2', '09:00', '16:00', 20, 60, 2, 1, '2026-12-31', '0000', '0000')''')
        today_str = date.today().isoformat()
        sample_appointments = [
            ('أحمد التونسي', '98111222', today_str, '09:00', 1, 'مكتمل', 'موعد مسبق', datetime.now().strftime("%Y-%m-%d %H:%M")),
            ('مريم العبيدي', '55333444', today_str, '09:20', 2, 'في الفحص', 'موعد مسبق', datetime.now().strftime("%Y-%m-%d %H:%M")),
            ('سلوى المنصوري', '97888999', today_str, '10:00', 3, 'في الانتظار', 'حضور مباشر', datetime.now().strftime("%Y-%m-%d %H:%M")),
        ]
        c.executemany('''INSERT INTO appointments (patient_name, patient_phone, appointment_date, appointment_time, ticket_number, status, visit_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', sample_appointments)
        sample_records = [
            ('55333444', 'مريم العبيدي', today_str, 'التهاب اللوزتين', 'Amoxicilline 500mg\nDoliprane', '- NFS', 'الراحة التامة ومراقبة الحرارة كل 4 ساعات.')
        ]
        c.executemany('''INSERT INTO medical_records (patient_phone, patient_name, visit_date, diagnosis, prescription, lab_tests, doctor_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)''', sample_records)
    conn.commit()
    conn.close()

init_db()

def get_clinic_settings():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM clinic_settings WHERE id = 1", conn)
    conn.close()
    return df.iloc[0]

settings = get_clinic_settings()

def generate_time_slots(start_str, end_str, slot_minutes):
    slots = []
    current = datetime.strptime(start_str, "%H:%M")
    end = datetime.strptime(end_str, "%H:%M")
    while current < end:
        slots.append(current.strftime("%H:%M"))
        current += timedelta(minutes=int(slot_minutes))
    return slots

def get_booked_slots(target_date):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT appointment_time FROM appointments WHERE appointment_date = ? AND status != 'ملغى'", (target_date,))
    booked = [row[0] for row in c.fetchall()]
    conn.close()
    return booked

def get_next_ticket_number(target_date):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT MAX(ticket_number) FROM appointments WHERE appointment_date = ?", (target_date,))
    max_ticket = c.fetchone()[0]
    conn.close()
    return 1 if max_ticket is None else max_ticket + 1


# ==========================================
# 3. إعدادات اللغة والتصميم العام (CSS)
# ==========================================
direction = "rtl" if st.session_state.lang == 'ar' else "ltr"
align = "right" if st.session_state.lang == 'ar' else "left"

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
    html, body, [class*="css"] {{
        font-family: 'Cairo', sans-serif !important;
        direction: {direction};
        text-align: {align};
    }}
    
    .clinic-header {{ background: linear-gradient(135deg, #0f766e, #14b8a6); color: white; padding: 24px; border-radius: 20px; text-align: center; margin-bottom: 24px; box-shadow: 0 10px 25px rgba(13,148,136,0.2); }}
    .clinic-header h1 {{ margin: 0; font-size: 2.2rem; font-weight: 800; color: #fff; }}
    .clinic-header p {{ margin: 8px 0 0 0; font-size: 1.1rem; opacity: 0.9; }}
    
    .live-queue-box {{ background: linear-gradient(145deg, #0f172a, #1e293b); color: white; padding: 25px; border-radius: 20px; text-align: center; border: 2px solid #14b8a6; margin-bottom: 20px; }}
    .ticket-number-giant {{ font-size: 4.5rem; font-weight: 800; color: #2dd4bf; margin: 10px 0; }}
    .medical-card {{ background: #fff; border: 1px solid #e2e8f0; border-inline-start: 6px solid #0d9488; border-radius: 14px; padding: 18px; margin-bottom: 16px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }}
    
    /* === تصميم الأزرار العامة لتصبح مربعات ملونة تدعم التفاف النص === */
    .stButton > button {{
        border-radius: 15px !important;
        transition: all 0.3s ease !important;
        border: 2px solid transparent !important;
    }}
    
    /* إجبار النص على الظهور كاملاً وعدم تقطيعه بنقاط (...) */
    .stButton > button p {{
        white-space: normal !important;
        word-wrap: break-word !important;
        line-height: 1.6 !important;
        font-size: 1.1rem !important;
        font-weight: 700 !important;
    }}

    /* المربع غير النشط (الأقسام الفرعية) */
    button[kind="secondary"] {{
        background-color: #f1f5f9 !important;
        color: #334155 !important;
        border: 2px solid #cbd5e1 !important;
        min-height: 90px !important;
    }}
    button[kind="secondary"]:hover {{
        background-color: #e2e8f0 !important;
        border-color: #0d9488 !important;
        transform: translateY(-3px) !important;
    }}

    /* المربع النشط (الملون بخلفية جميلة) */
    button[kind="primary"] {{
        background: linear-gradient(135deg, #0d9488, #0f766e) !important;
        color: white !important;
        box-shadow: 0 8px 15px rgba(13,148,136,0.3) !important;
        min-height: 90px !important;
    }}
    button[kind="primary"]:hover {{
        background: linear-gradient(135deg, #0f766e, #115e59) !important;
        transform: translateY(-3px) !important;
    }}
</style>
""", unsafe_allow_html=True)

# CSS خاص بالصفحة الرئيسية فقط لتكبير المربعات لتصبح ضخمة
if st.session_state.current_view == 'home':
    st.markdown("""
    <style>
        div[data-testid="column"] .stButton > button {
            min-height: 280px !important; /* ارتفاع ضخم للمربع */
            background-color: #ffffff !important;
            border: 2px solid #cbd5e1 !important;
            box-shadow: 0 4px 10px rgba(0,0,0,0.05) !important;
            color: #1e293b !important;
        }
        div[data-testid="column"] .stButton > button p {
            font-size: 1.3rem !important; /* تكبير خط الصفحة الرئيسية */
        }
        div[data-testid="column"] .stButton > button:hover {
            border-color: #0d9488 !important;
            background-color: #f8fafc !important;
            transform: translateY(-5px) !important;
            box-shadow: 0 10px 25px rgba(13,148,136,0.2) !important;
            color: #0d9488 !important;
        }
    </style>
    """, unsafe_allow_html=True)


# ==========================================
# الهيدر الموحد لجميع الشاشات
# ==========================================
doc_clean_name = settings['doctor_name'].replace('د.', '').replace('الدكتور', '').replace('Dr.', '').strip()
title_text = t(f"🩺 طبيبي د. {doc_clean_name}", f"🩺 Mon Médecin Dr. {doc_clean_name}")

st.markdown(f"""
<div class="clinic-header">
    <h1>{title_text}</h1>
    <p>{settings['specialty']} | 📞 {settings['phone']}</p>
</div>
""", unsafe_allow_html=True)

if settings['subscription_active'] == 0:
    st.error(t("⚠️ خدمة العيادة الرقمية معلقة مؤقتاً. يرجى من الإدارة تجديد الاشتراك.", "⚠️ Service suspendu temporairement. Veuillez renouveler l'abonnement."))
    st.stop()

if st.session_state.current_view != 'home':
    if st.button(t("🏠 عودة إلى الشاشة الرئيسية", "🏠 Retour à l'accueil")):
        st.session_state.current_view = 'home'
        st.rerun()
    st.divider()

# ==============================================================================
# الشاشة الرئيسية (المربعات الكبيرة الضخمة)
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
        btn_patient = t("📱\n\nالمريض / الحريف\n\nحجز موعد، تتبع الصف أو الدور\nومعاينة الوصفات الخاصة بك.", "📱\n\nPatient / Client\n\nRéserver, suivre la file\net voir vos ordonnances.")
        if st.button(btn_patient, use_container_width=True):
            st.session_state.current_view = 'patient'
            st.session_state.patient_subview = 'book' # افتراضياً يفتح على حجز موعد
            st.rerun()

    with col2:
        btn_sec = t("👩‍💻\n\nالكاتبة / الاستقبال\n\nإدارة الصف أو الدور وإدخال المرضى\nلقاعة الفحص (محمي برمز).", "👩‍💻\n\nSecrétaire / Accueil\n\nGérer la file d'attente\net l'accès (Protégé).")
        if st.button(btn_sec, use_container_width=True):
            st.session_state.current_view = 'secretary'
            st.rerun()

    with col3:
        btn_doc = t("👨‍⚕️\n\nالدكتور / الطبيب\n\nكتابة الوصفات، ملفات المرضى\nوإعدادات العيادة (محمي برمز).", "👨‍⚕️\n\nMédecin / Docteur\n\nOrdonnances, dossiers\net paramètres (Protégé).")
        if st.button(btn_doc, use_container_width=True):
            st.session_state.current_view = 'doctor'
            st.session_state.doctor_subview = 'rx' # افتراضياً يفتح على الوصفات
            st.rerun()


# ==============================================================================
# واجهة المريض (مربعات ملونة للتنقل بدل التبويبات)
# ==============================================================================
elif st.session_state.current_view == 'patient':
    today_str = date.today().isoformat()
    conn = get_connection()
    today_df = pd.read_sql_query("SELECT * FROM appointments WHERE appointment_date = ? AND status != 'ملغى' ORDER BY ticket_number ASC", conn, params=(today_str,))
    conn.close()
    
    waiting_count = len(today_df[today_df['status'] == 'في الانتظار'])
    in_exam_df = today_df[today_df['status'] == 'في الفحص']
    current_num = int(in_exam_df.iloc[0]['ticket_number']) if not in_exam_df.empty else int(settings['current_ticket'])
    
    col_q1, col_q2 = st.columns([1.2, 1])
    with col_q1:
        st.markdown(f"""
        <div class="live-queue-box">
            <span style="background:#ef4444; padding:4px 12px; border-radius:50px;">{t("🔴 مباشر من قاعة الانتظار", "🔴 En direct de la salle d'attente")}</span>
            <div style="margin-top:10px;">{t("الطبيب يفحص حالياً تذكرة رقم:", "Le médecin consulte actuellement le numéro :")}</div>
            <div class="ticket-number-giant">#{current_num}</div>
            <div>{t(f"المنتظرون: <b>{waiting_count}</b> | معدل الفحص: <b>{settings['slot_minutes']} د</b>", f"En attente: <b>{waiting_count}</b> | Durée moy: <b>{settings['slot_minutes']} min</b>")}</div>
        </div>
        """, unsafe_allow_html=True)
        
    with col_q2:
        st.markdown(t("#### 🔍 احسب دورك وقت الخروج", "#### 🔍 Calculez votre temps d'attente"))
        my_t = st.number_input(t("أدخل رقم تذكرتك:", "Votre numéro de ticket :"), min_value=1, value=current_num+1)
        if my_t == current_num:
            st.success(t("دورك الآن! تفضل بالدخول.", "C'est votre tour ! Veuillez entrer."))
        elif my_t > current_num:
            st.info(t(f"بقي أمامك {my_t - current_num} مرضى (حوالي {(my_t - current_num) * int(settings['slot_minutes'])} دقيقة).", f"Il y a {my_t - current_num} patients avant vous (environ {(my_t - current_num) * int(settings['slot_minutes'])} minutes)."))

    st.divider()
    
    # === مربعات التنقل الخاصة بالمريض (بدل التبويبات) ===
    c_nav1, c_nav2 = st.columns(2)
    with c_nav1:
        if st.button(t("📅 حجز موعد جديد", "📅 Nouveau rendez-vous"), use_container_width=True, type="primary" if st.session_state.patient_subview == 'book' else "secondary"):
            st.session_state.patient_subview = 'book'
            st.rerun()
    with c_nav2:
        if st.button(t("💊 أرشيف وصفاتي وتحاليلي", "💊 Mes ordonnances et analyses"), use_container_width=True, type="primary" if st.session_state.patient_subview == 'records' else "secondary"):
            st.session_state.patient_subview = 'records'
            st.rerun()
            
    st.write("")

    # === محتوى قسم المريض بناءً على المربع النشط ===
    if st.session_state.patient_subview == 'book':
        st.markdown(t("#### 📅 تفاصيل الحجز", "#### 📅 Détails de la réservation"))
        c1, c2 = st.columns(2)
        with c1:
            sel_date = st.date_input(t("اختر تاريخ الموعد:", "Date du rendez-vous :"), min_value=date.today())
            avail_slots = [s for s in generate_time_slots(settings['work_start'], settings['work_end'], settings['slot_minutes']) if s not in get_booked_slots(sel_date.isoformat())]
            sel_time = st.selectbox(t("الوقت المتاح:", "Heure disponible :"), avail_slots) if avail_slots else None
        with c2:
            p_n = st.text_input(t("اسم المريض الكامل:", "Nom complet du patient :"))
            p_p = st.text_input(t("رقم الهاتف (لمتابعة الملف الطبي):", "Numéro de téléphone :"))
            
            # زر التأكيد 
            st.markdown("""<style>div.stButton > button[kind="secondary"] { border-color: #0d9488 !important; }</style>""", unsafe_allow_html=True)
            if st.button(t("✅ تأكيد الحجز", "✅ Confirmer le rendez-vous"), type="secondary", use_container_width=True) and sel_time and p_n:
                new_ticket = get_next_ticket_number(sel_date.isoformat())
                conn = get_connection()
                conn.execute("INSERT INTO appointments (patient_name, patient_phone, appointment_date, appointment_time, ticket_number, status, visit_type) VALUES (?, ?, ?, ?, ?, 'في الانتظار', 'موعد مسبق')", (p_n, p_p, sel_date.isoformat(), sel_time, new_ticket))
                conn.commit(); conn.close()
                st.success(t(f"تم الحجز! رقمك هو #{new_ticket} ليوم {sel_date} على الساعة {sel_time}.", f"Réservé ! Votre numéro est #{new_ticket} pour le {sel_date} à {sel_time}."))

    elif st.session_state.patient_subview == 'records':
        st.markdown(t("#### 💊 أدخل رقم هاتفك لترى تاريخك الطبي كاملاً", "#### 💊 Entrez votre téléphone pour voir votre historique médical"))
        search_phone = st.text_input(t("رقم الهاتف:", "Téléphone :"), key="search_ph")
        if search_phone:
            conn = get_connection()
            rec_df = pd.read_sql_query("SELECT * FROM medical_records WHERE patient_phone = ? ORDER BY id DESC", conn, params=(search_phone,))
            conn.close()
            if not rec_df.empty:
                for _, row in rec_df.iterrows():
                    st.markdown(f"""
                    <div class="medical-card">
                        <span style="background:#ccfbf1; padding:4px 10px; border-radius:10px; font-weight:bold; color:#0f766e;">📅 {row['visit_date']}</span>
                        <p style="margin-top:15px; font-size:1.1rem;"><b>🩺 {t("التشخيص:", "Diagnostic :")}</b> {row['diagnosis']}</p>
                        <div style="background:#f0fdf4; padding:12px; border-radius:8px; border:1px dashed #16a34a;"><b>💊 {t("الوصفة:", "Ordonnance :")}</b><br>{row['prescription']}</div>
                        <div style="background:#eff6ff; padding:12px; border-radius:8px; border:1px dashed #2563eb; margin-top:8px;"><b>🔬 {t("التحاليل:", "Analyses :")}</b><br>{row['lab_tests']}</div>
                        
                        <div style="background:#fef3c7; padding:12px; border-radius:8px; border:1px dashed #d97706; margin-top:12px;">
                            <b style="color:#b45309;">📌 {t("ملاحظات وتوصيات الطبيب:", "Notes et recommandations :")}</b><br>
                            <span style="color:#92400e;">{row['doctor_notes']}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.warning(t("لا يوجد ملف طبي مسجل بهذا الرقم.", "Aucun dossier médical trouvé pour ce numéro."))


# ==============================================================================
# واجهة الكاتبة (محمية برمز)
# ==============================================================================
elif st.session_state.current_view == 'secretary':
    if not st.session_state.sec_auth:
        col_c1, col_c2, col_c3 = st.columns([1,2,1])
        with col_c2:
            st.markdown(t("<h3 style='text-align:center;'>🔒 تسجيل دخول الكاتبة</h3>", "<h3 style='text-align:center;'>🔒 Connexion Secrétaire</h3>"), unsafe_allow_html=True)
            sec_pwd = st.text_input(t("رمز الدخول:", "Mot de passe :"), type="password")
            if st.button(t("دخول", "Connexion"), use_container_width=True, type="primary"):
                if sec_pwd == settings['sec_pwd']:
                    st.session_state.sec_auth = True
                    st.rerun()
                else:
                    st.error(t("الرمز غير صحيح!", "Mot de passe incorrect !"))
    else:
        st.subheader(t("👩‍💻 شاشة الكاتبة الفائقة السرعة", "👩‍💻 Écran Secrétaire (Rapide)"))
        today_str = date.today().isoformat()
        conn = get_connection()
        today_df = pd.read_sql_query("SELECT * FROM appointments WHERE appointment_date = ? ORDER BY ticket_number ASC", conn, params=(today_str,))
        
        in_exam = today_df[today_df['status'] == 'في الفحص']
        waiting = today_df[today_df['status'] == 'في الانتظار']
        
        m1, m2, m3 = st.columns(3)
        m1.metric(t("🟢 في الفحص الآن", "🟢 En consultation"), f"#{in_exam.iloc[0]['ticket_number']}" if not in_exam.empty else t("لا أحد", "Aucun"))
        m2.metric(t("🟡 القادم في الصف", "🟡 Prochain patient"), f"#{waiting.iloc[0]['ticket_number']}" if not waiting.empty else t("فارغ", "Vide"))
        m3.metric(t("👥 المنتظرون بالخارج", "👥 En attente"), len(waiting))
        
        st.divider()
        c_btn, c_add = st.columns([1,1])
        with c_btn:
            st.info(t("لتحديث رقم الشاشة المضيئة للمرضى بالخارج، اضغطي الزر الأخضر:", "Pour mettre à jour l'écran des patients, appuyez sur le bouton vert :"))
            if st.button(t("⏭️ نداء المريض التالي (إدخال للفحص)", "⏭️ Appeler le patient suivant"), type="primary", use_container_width=True):
                c = conn.cursor()
                c.execute("UPDATE appointments SET status = 'مكتمل' WHERE appointment_date = ? AND status = 'في الفحص'", (today_str,))
                if not waiting.empty:
                    next_id, next_t = waiting.iloc[0]['id'], waiting.iloc[0]['ticket_number']
                    c.execute("UPDATE appointments SET status = 'في الفحص' WHERE id = ?", (int(next_id),))
                    c.execute("UPDATE clinic_settings SET current_ticket = ? WHERE id = 1", (int(next_t),))
                    st.success(f"تم نداء #{next_t}")
                conn.commit(); st.rerun()
        with c_add:
            with st.form("walkin"):
                st.write(t("➕ إضافة مريض بدون موعد:", "➕ Ajouter un patient sans rendez-vous :"))
                w_n = st.text_input(t("اسم المريض:", "Nom :"))
                w_p = st.text_input(t("رقم الهاتف:", "Téléphone :"))
                if st.form_submit_button(t("قطع تذكرة", "Créer ticket")) and w_n:
                    new_t = get_next_ticket_number(today_str)
                    conn.execute("INSERT INTO appointments (patient_name, patient_phone, appointment_date, appointment_time, ticket_number, status, visit_type) VALUES (?, ?, ?, ?, ?, 'في الانتظار', 'حضور مباشر')", (w_n, w_p, today_str, datetime.now().strftime("%H:%M"), new_t))
                    conn.commit(); st.rerun()
        conn.close()

# ==============================================================================
# واجهة الطبيب (مربعات ملونة للتنقل) + إعدادات العيادة
# ==============================================================================
elif st.session_state.current_view == 'doctor':
    if not st.session_state.doc_auth:
        col_c1, col_c2, col_c3 = st.columns([1,2,1])
        with col_c2:
            st.markdown(t("<h3 style='text-align:center;'>🔒 تسجيل دخول الطبيب</h3>", "<h3 style='text-align:center;'>🔒 Connexion Médecin</h3>"), unsafe_allow_html=True)
            doc_pwd = st.text_input(t("رمز الدخول:", "Mot de passe :"), type="password", key="doc_login_pwd")
            if st.button(t("دخول", "Connexion"), use_container_width=True, type="primary"):
                if doc_pwd == settings['doc_pwd']:
                    st.session_state.doc_auth = True
                    st.rerun()
                else:
                    st.error(t("الرمز غير صحيح!", "Mot de passe incorrect !"))
    else:
        
        # === مربعات التنقل الخاصة بالطبيب (بدل التبويبات) ===
        c_nav1, c_nav2 = st.columns(2)
        with c_nav1:
            if st.button(t("👨‍⚕️ مكتب الطبيب (إصدار الوصفات)", "👨‍⚕️ Bureau du médecin (Ordonnances)"), use_container_width=True, type="primary" if st.session_state.doctor_subview == 'rx' else "secondary"):
                st.session_state.doctor_subview = 'rx'
                st.rerun()
        with c_nav2:
            if st.button(t("⚙️ إعدادات العيادة الخاصة", "⚙️ Paramètres de la clinique"), use_container_width=True, type="primary" if st.session_state.doctor_subview == 'settings' else "secondary"):
                st.session_state.doctor_subview = 'settings'
                st.rerun()
                
        st.write("")
        
        # === محتوى قسم الطبيب بناءً على المربع النشط ===
        if st.session_state.doctor_subview == 'rx':
            st.subheader(t("👨‍⚕️ إصدار الوصفات والتحاليل", "👨‍⚕️ Émission des ordonnances et analyses"))
            today_str = date.today().isoformat()
            conn = get_connection()
            in_exam = pd.read_sql_query("SELECT * FROM appointments WHERE appointment_date = ? AND status = 'في الفحص'", conn, params=(today_str,))
            def_n = in_exam.iloc[0]['patient_name'] if not in_exam.empty else ""
            def_p = in_exam.iloc[0]['patient_phone'] if not in_exam.empty else ""
            
            if def_n:
                st.success(t(f"المريض الحالي: {def_n} | التذكرة: #{in_exam.iloc[0]['ticket_number']}", f"Patient actuel: {def_n} | Ticket: #{in_exam.iloc[0]['ticket_number']}"))
                
            with st.form("rx"):
                col1, col2 = st.columns(2)
                d_n = col1.text_input(t("اسم المريض:", "Nom du patient :"), value=def_n)
                d_p = col2.text_input(t("رقم الهاتف (ليرى المريض وصفته):", "Téléphone :"), value=def_p)
                d_diag = st.text_input(t("🩺 التشخيص (Diagnostic):", "🩺 Diagnostic :"))
                
                c_rx, c_lab = st.columns(2)
                d_rx = c_rx.text_area(t("💊 الوصفة (Ordonnance):", "💊 Ordonnance :"), height=150)
                d_lab = c_lab.text_area(t("🔬 التحاليل (Analyses):", "🔬 Analyses :"), height=150)
                d_notes = st.text_input(t("📌 ملاحظات وتوصيات للمريض:", "📌 Notes pour le patient :"))
                
                if st.form_submit_button(t("💾 حفظ في ملف المريض الدائم", "💾 Enregistrer le dossier"), type="primary"):
                    if d_n and d_p:
                        conn.execute("INSERT INTO medical_records (patient_phone, patient_name, visit_date, diagnosis, prescription, lab_tests, doctor_notes) VALUES (?, ?, ?, ?, ?, ?, ?)", (d_p, d_n, today_str, d_diag, d_rx, d_lab, d_notes))
                        conn.commit()
                        st.success(t("✅ تم حفظ الوصفة والتحاليل الدائمة للمريض!", "✅ Dossier enregistré avec succès !"))
                    else:
                        st.error(t("الاسم ورقم الهاتف ضروريان.", "Le nom et le téléphone sont obligatoires."))
            conn.close()
            
        elif st.session_state.doctor_subview == 'settings':
            st.markdown(t("### ⚙️ إعدادات العيادة الخاصة", "### ⚙️ Paramètres de la clinique"))
            st.info(t("هذه الإعدادات خاصة بك فقط وتتحكم في تنظيم عمل العيادة.", "Ces paramètres contrôlent l'organisation de votre clinique."))
            
            with st.form("doctor_clinic_settings"):
                st.subheader(t("⏱️ إعدادات الطابور", "⏱️ Paramètres de la file"))
                new_slot = st.number_input(t("مدة الفحص التقديرية لكل مريض (بالدقائق):", "Durée estimée par patient (minutes) :"), min_value=5, value=int(settings['slot_minutes']))
                
                st.subheader(t("🔒 أرقام الدخول السرية", "🔒 Mots de passe d'accès"))
                new_doc_pwd = st.text_input(t("الرقم السري الخاص بالطبيب:", "Mot de passe du médecin :"), value=settings['doc_pwd'], type="password")
                new_sec_pwd = st.text_input(t("الرقم السري الخاص بالكاتبة:", "Mot de passe de la secrétaire :"), value=settings['sec_pwd'], type="password")
                
                if st.form_submit_button(t("💾 تحديث إعدادات العيادة", "💾 Mettre à jour les paramètres"), type="primary"):
                    conn = get_connection()
                    conn.execute("UPDATE clinic_settings SET slot_minutes=?, doc_pwd=?, sec_pwd=? WHERE id=1", (new_slot, new_doc_pwd, new_sec_pwd))
                    conn.commit()
                    conn.close()
                    st.success(t("✅ تم تحديث إعدادات العيادة بنجاح!", "✅ Paramètres mis à jour avec succès !"))
                    st.rerun()

# ==========================================
# 4. القائمة التوسيعية (ركن المطور فقط) - تم نقلها للأسفل
# ==========================================
with st.expander("⚙️ ركن المطور وإعدادات العيادة (SaaS)", expanded=False):
    st.markdown(t("### ⚙️ ركن المطور (SaaS)", "### ⚙️ Espace Développeur (SaaS)"))
    st.info(t("مفتوح لتسهيل العرض. سيتم إغلاقه لاحقاً.", "Ouvert pour la démo. Sera sécurisé plus tard."))
    with st.form("saas_admin_form"):
        st.subheader(t("إعدادات وهوية العيادة", "Identité de la clinique"))
        new_doc_name = st.text_input(t("اسم الطبيب:", "Nom du médecin:"), value=settings['doctor_name'])
        new_specialty = st.text_input(t("الاختصاص:", "Spécialité:"), value=settings['specialty'])
        new_phone = st.text_input(t("رقم هاتف العيادة:", "Téléphone:"), value=settings['phone'])
        st.subheader(t("💰 حالة الاشتراك", "💰 Abonnement"))
        sub_status = st.selectbox(t("حالة الاشتراك:", "Statut:"), [1, 0], index=0 if settings['subscription_active']==1 else 1, format_func=lambda x: t("✅ مفعّل", "✅ Actif") if x==1 else t("⛔ موقوف", "⛔ Suspendu"))
        if st.form_submit_button(t("💾 حفظ الهوية", "💾 Enregistrer"), type="primary"):
            conn = get_connection()
            conn.execute('''UPDATE clinic_settings SET doctor_name=?, specialty=?, phone=?, subscription_active=? WHERE id=1''', (new_doc_name, new_specialty, new_phone, sub_status))
            conn.commit(); conn.close(); st.rerun()
            
    st.divider()
    st.markdown(t("#### 🔒 إعادة ضبط رموز المرور", "#### 🔒 Réinitialisation des mots de passe"))
    if st.button(t("🔄 إعادة ضبط الرموز لـ 0000", "🔄 Réinitialiser à 0000")):
        conn = get_connection()
        conn.execute("UPDATE clinic_settings SET sec_pwd='0000', doc_pwd='0000' WHERE id=1")
        conn.commit(); conn.close()
        st.session_state.sec_auth = False
        st.session_state.doc_auth = False
        st.success(t("تمت إعادة ضبط الرموز لـ 0000 بنجاح.", "Mots de passe réinitialisés à 0000 avec succès."))
