import streamlit as st
import sqlite3
from datetime import datetime, date, timedelta, time
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit.components.v1 as components
import base64

# ==========================================
# 1. إعدادات الصفحة و PWA Override
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
                const appleIcon = parentDoc.createElement('link'); appleIcon.rel = 'apple-touch-icon'; appleIcon.href = 'data:image/png;base64,{encoded_icon}'; head.appendChild(appleIcon);
                const manifestLink = parentDoc.createElement('link'); manifestLink.rel = 'manifest'; manifestLink.href = 'data:application/manifest+json;base64,{b64_manifest}'; head.appendChild(manifestLink);
            }} catch (e) {{}}
        </script>
        """
        components.html(js_code, height=0, width=0)
    except Exception as e:
        pass

inject_custom_pwa("icon.png", "طبيبي د. | Mon Médecin Dr.")

# دوال التوقيت
def get_tunis_time():
    return datetime.now(ZoneInfo("Africa/Tunis"))

def get_tunis_date():
    return get_tunis_time().date()

# تهيئة المتغيرات
if 'current_view' not in st.session_state: st.session_state.current_view = 'home'
if 'sec_auth' not in st.session_state: st.session_state.sec_auth = False
if 'doc_auth' not in st.session_state: st.session_state.doc_auth = False
if 'lang' not in st.session_state: st.session_state.lang = 'ar'
if 'patient_subview' not in st.session_state: st.session_state.patient_subview = 'book'
if 'doctor_subview' not in st.session_state: st.session_state.doctor_subview = 'rx'

def t(ar_text, fr_text):
    if st.session_state.lang == 'ar':
        return ar_text.replace("طابور", "صف")
    return fr_text

# تنسيق الوقت التقريبي بذكاء
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

# ==========================================
# 2. قاعدة البيانات
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
            subscription_active INTEGER, subscription_expiry TEXT, sec_pwd TEXT, doc_pwd TEXT, last_reset_date TEXT)''')
    try:
        c.execute("ALTER TABLE clinic_settings ADD COLUMN sec_pwd TEXT DEFAULT '0000'")
        c.execute("ALTER TABLE clinic_settings ADD COLUMN doc_pwd TEXT DEFAULT '0000'")
        c.execute("ALTER TABLE clinic_settings ADD COLUMN last_reset_date TEXT DEFAULT ''")
    except: pass
    c.execute('''CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, patient_name TEXT, patient_phone TEXT, appointment_date TEXT, 
            appointment_time TEXT, ticket_number INTEGER, status TEXT, visit_type TEXT, created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS medical_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT, patient_phone TEXT, patient_name TEXT, visit_date TEXT, 
            diagnosis TEXT, prescription TEXT, lab_tests TEXT, doctor_notes TEXT)''')
    
    if c.execute("SELECT COUNT(*) FROM clinic_settings").fetchone()[0] == 0:
        c.execute('''INSERT INTO clinic_settings VALUES (
                1, 'سامي بن يوسف', 'أخصائي طب الأطفال وحديثي الولادة', '21655000111', 
                'شارع الحبيب بورقيبة', '09:00', '16:00', 20, 60, 0, 1, '2026-12-31', '0000', '0000', '')''')
    conn.commit()
    conn.close()

init_db()

def get_clinic_settings():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM clinic_settings WHERE id = 1", conn)
    conn.close()
    return df.iloc[0]

settings = get_clinic_settings()

def generate_time_slots(start_str, end_str, slot_minutes, target_date):
    slots = []
    current = datetime.strptime(start_str, "%H:%M")
    end = datetime.strptime(end_str, "%H:%M")
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
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT appointment_time FROM appointments WHERE appointment_date = ? AND status != 'ملغى'", (target_date,))
    booked = [row[0] for row in c.fetchall()]
    conn.close()
    return booked

def get_next_ticket_number(target_date, target_time):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM appointments WHERE appointment_date = ? AND appointment_time <= ?", (target_date, target_time))
    count_before = c.fetchone()[0]
    conn.close()
    return count_before + 1

# ==========================================
# 3. التصميم (CSS)
# ==========================================
direction = "rtl" if st.session_state.lang == 'ar' else "ltr"
align = "right" if st.session_state.lang == 'ar' else "left"

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
    html, body, [class*="css"] {{ font-family: 'Cairo', sans-serif !important; direction: {direction}; text-align: {align}; }}
    .clinic-header {{ background: linear-gradient(135deg, #0f766e, #14b8a6); color: white; padding: 24px; border-radius: 20px; text-align: center; margin-bottom: 24px; box-shadow: 0 10px 25px rgba(13,148,136,0.2); }}
    .clinic-header h1 {{ margin: 0; font-size: 2.2rem; font-weight: 800; color: #fff; }}
    .clinic-header p {{ margin: 8px 0 0 0; font-size: 1.1rem; opacity: 0.9; }}
    .live-queue-box {{ background: linear-gradient(145deg, #0f172a, #1e293b); color: white; padding: 25px; border-radius: 20px; text-align: center; border: 2px solid #14b8a6; margin-bottom: 20px; }}
    .ticket-number-giant {{ font-size: 4.5rem; font-weight: 800; color: #2dd4bf; margin: 10px 0; }}
    .medical-card {{ background: #fff; border: 1px solid #e2e8f0; border-inline-start: 6px solid #0d9488; border-radius: 14px; padding: 18px; margin-bottom: 16px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }}
    .stButton > button {{ border-radius: 15px !important; transition: all 0.3s ease !important; border: 2px solid transparent !important; }}
    .stButton > button p {{ white-space: normal !important; word-wrap: break-word !important; line-height: 1.6 !important; font-size: 1.1rem !important; font-weight: 700 !important; }}
    button[kind="secondary"] {{ background-color: #f1f5f9 !important; color: #334155 !important; border: 2px solid #cbd5e1 !important; min-height: 90px !important; }}
    button[kind="secondary"]:hover {{ background-color: #e2e8f0 !important; border-color: #0d9488 !important; transform: translateY(-3px) !important; }}
    button[kind="primary"] {{ background: linear-gradient(135deg, #0d9488, #0f766e) !important; color: white !important; box-shadow: 0 8px 15px rgba(13,148,136,0.3) !important; min-height: 90px !important; }}
    button[kind="primary"]:hover {{ background: linear-gradient(135deg, #0f766e, #115e59) !important; transform: translateY(-3px) !important; }}
</style>
""", unsafe_allow_html=True)

if st.session_state.current_view == 'home':
    st.markdown("""<style>div[data-testid="column"] .stButton > button { min-height: 280px !important; background-color: #ffffff !important; border: 2px solid #cbd5e1 !important; box-shadow: 0 4px 10px rgba(0,0,0,0.05) !important; color: #1e293b !important; } div[data-testid="column"] .stButton > button p { font-size: 1.3rem !important; } div[data-testid="column"] .stButton > button:hover { border-color: #0d9488 !important; background-color: #f8fafc !important; transform: translateY(-5px) !important; box-shadow: 0 10px 25px rgba(13,148,136,0.2) !important; color: #0d9488 !important; }</style>""", unsafe_allow_html=True)

# الهيدر
doc_clean_name = settings['doctor_name'].replace('د.', '').replace('الدكتور', '').replace('Dr.', '').strip()
title_text = t(f"🩺 طبيبي د. {doc_clean_name}", f"🩺 Mon Médecin Dr. {doc_clean_name}")
st.markdown(f"""<div class="clinic-header"><h1>{title_text}</h1><p>{settings['specialty']} | 📞 {settings['phone']}</p></div>""", unsafe_allow_html=True)

if settings['subscription_active'] == 0:
    st.error(t("⚠️ خدمة العيادة الرقمية معلقة مؤقتاً. يرجى من الإدارة تجديد الاشتراك.", "⚠️ Service suspendu temporairement. Veuillez renouveler l'abonnement."))
    st.stop()

if st.session_state.current_view != 'home':
    if st.button(t("🏠 عودة إلى الشاشة الرئيسية", "🏠 Retour à l'accueil")):
        st.session_state.current_view = 'home'
        st.rerun()
    st.divider()

# ==============================================================================
# الشاشة الرئيسية
# ==============================================================================
if st.session_state.current_view == 'home':
    col_welcome, col_lang = st.columns([4, 1])
    with col_welcome: st.markdown(t("<h3 style='text-align: center; color:#334155; margin-top:5px;'>مرحباً بك، يرجى اختيار صفتك للدخول:</h3>", "<h3 style='text-align: center; color:#334155; margin-top:5px;'>Bienvenue, veuillez sélectionner votre accès :</h3>"), unsafe_allow_html=True)
    with col_lang:
        selected_lang = st.selectbox("🌐", ["العربية", "Français"], index=0 if st.session_state.lang == 'ar' else 1, label_visibility="collapsed")
        new_lang = 'ar' if selected_lang == "العربية" else 'fr'
        if new_lang != st.session_state.lang: st.session_state.lang = new_lang; st.rerun()
            
    st.write("") 
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button(t("📱\n\nالمريض / الحريف\n\nحجز موعد، تتبع الصف أو الدور\nومعاينة الوصفات الخاصة بك.", "📱\n\nPatient / Client\n\nRéserver, suivre la file\net voir vos ordonnances."), use_container_width=True):
            st.session_state.current_view = 'patient'; st.session_state.patient_subview = 'book'; st.rerun()
    with col2:
        if st.button(t("👩‍💻\n\nالكاتبة / الاستقبال\n\nإدارة الصف أو الدور وإدخال المرضى\nلقاعة الفحص (محمي برمز).", "👩‍💻\n\nSecrétaire / Accueil\n\nGérer la file d'attente\net l'accès (Protégé)."), use_container_width=True):
            st.session_state.current_view = 'secretary'; st.rerun()
    with col3:
        if st.button(t("👨‍⚕️\n\nالدكتور / الطبيب\n\nكتابة الوصفات، ملفات المرضى\nوإعدادات العيادة (محمي برمز).", "👨‍⚕️\n\nMédecin / Docteur\n\nOrdonnances, dossiers\net paramètres (Protégé)."), use_container_width=True):
            st.session_state.current_view = 'doctor'; st.session_state.doctor_subview = 'rx'; st.rerun()

# ==============================================================================
# واجهة المريض
# ==============================================================================
elif st.session_state.current_view == 'patient':
    @st.fragment(run_every=15)
    def live_queue_box():
        today_str = get_tunis_date().isoformat()
        conn = get_connection()
        today_df = pd.read_sql_query("SELECT * FROM appointments WHERE appointment_date = ? AND status != 'ملغى' ORDER BY appointment_time ASC", conn, params=(today_str,))
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
                <div>{t(f"المنتظرون: <b>{waiting_count}</b>", f"En attente: <b>{waiting_count}</b>")}</div>
            </div>
            """, unsafe_allow_html=True)
            
        with col_q2:
            st.markdown(t("#### ⏳ وقت الانتظار التقريبي", "#### ⏳ Temps d'attente estimé"))
            my_t = st.number_input(t("أدخل رقم تذكرتك:", "Votre numéro de ticket :"), min_value=1, value=current_num+1, key="patient_ticket_input")
            if my_t == current_num: 
                st.markdown(f"""
                <div style="background: #ecfdf5; border: 2px solid #10b981; border-radius: 14px; padding: 16px; text-align: center; margin-top: 10px;">
                    <div style="font-size: 1.3rem; font-weight: 800; color: #065f46;">
                        🎉 {t("دورك الآن! تفضل بالدخول إلى قاعة الفحص", "C'est votre tour ! Veuillez entrer.")}
                    </div>
                </div>
                """, unsafe_allow_html=True)
            elif my_t > current_num: 
                diff = my_t - current_num
                wait_mins = diff * int(settings['slot_minutes'])
                formatted_time = format_wait_time(wait_mins)
                
                if diff == 1:
                    patients_txt = t("مريض واحد فقط", "1 seul patient")
                elif diff == 2:
                    patients_txt = t("مريضان (2)", "2 patients")
                elif 3 <= diff <= 10:
                    patients_txt = t(f"{diff} مرضى", f"{diff} patients")
                else:
                    patients_txt = t(f"{diff} مريضاً", f"{diff} patients")

                st.markdown(f"""
                <div style="background: linear-gradient(135deg, #f0fdfa, #f8fafc); border: 2px solid #0d9488; border-radius: 14px; padding: 18px; margin-top: 10px; box-shadow: 0 4px 12px rgba(13,148,136,0.08); text-align: center;">
                    <div style="font-size: 1.1rem; color: #1e293b; margin-bottom: 8px;">
                        👥 {t("أمامك في الطابور:", "Devant vous :")} 
                        <span style="background: #ccfbf1; color: #0f766e; padding: 4px 12px; border-radius: 8px; font-weight: 800; font-size: 1.15rem;">
                            {patients_txt}
                        </span>
                    </div>
                    <div style="font-size: 1.25rem; font-weight: 800; color: #0f766e; margin-top: 8px;">
                        ⏳ {t("الوقت التقديري المتبقي:", "Temps estimé :")} 
                        <span style="color: #0d9488;">{formatted_time}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div style="background: #fffbeb; border: 2px solid #f59e0b; border-radius: 14px; padding: 14px; text-align: center; margin-top: 10px;">
                    <div style="font-size: 1.05rem; font-weight: 700; color: #92400e;">
                        ⚠️ {t("لقد مر دور هذه التذكرة. يرجى مراجعة الاستقبال.", "Votre tour est passé. Veuillez consulter l'accueil.")}
                    </div>
                </div>
                """, unsafe_allow_html=True)

    live_queue_box()
    st.divider()
    
    c_nav1, c_nav2 = st.columns(2)
    with c_nav1:
        if st.button(t("📅 حجز موعد جديد", "📅 Nouveau rendez-vous"), use_container_width=True, type="primary" if st.session_state.patient_subview == 'book' else "secondary"): st.session_state.patient_subview = 'book'; st.rerun()
    with c_nav2:
        if st.button(t("💊 أرشيف وصفاتي وتحاليلي", "💊 Mes ordonnances et analyses"), use_container_width=True, type="primary" if st.session_state.patient_subview == 'records' else "secondary"): st.session_state.patient_subview = 'records'; st.rerun()
            
    st.write("")

    if st.session_state.patient_subview == 'book':
        st.markdown(t("#### 📅 تفاصيل الحجز", "#### 📅 Détails de la réservation"))
        c1, c2 = st.columns(2)
        with c1:
            sel_date = st.date_input(t("اختر تاريخ الموعد:", "Date du rendez-vous :"), min_value=get_tunis_date())
            avail_slots = [s for s in generate_time_slots(settings['work_start'], settings['work_end'], settings['slot_minutes'], sel_date) if s not in get_booked_slots(sel_date.isoformat())]
            sel_time = st.selectbox(t("الوقت المتاح:", "Heure disponible :"), avail_slots) if avail_slots else None
            if not avail_slots: st.error(t("لا توجد أوقات متاحة في هذا اليوم.", "Aucun horaire disponible pour ce jour."))
        with c2:
            p_n = st.text_input(t("اسم المريض الكامل:", "Nom complet du patient :"))
            p_p = st.text_input(t("رقم الهاتف:", "Numéro de téléphone :"))
            
            st.markdown("""<style>div.stButton > button[kind="secondary"] { border-color: #0d9488 !important; }</style>""", unsafe_allow_html=True)
            if st.button(t("✅ تأكيد الحجز", "✅ Confirmer le rendez-vous"), type="secondary", use_container_width=True):
                if sel_time and p_n.strip() and p_p.strip():
                    new_ticket = get_next_ticket_number(sel_date.isoformat(), sel_time)
                    conn = get_connection()
                    conn.execute("INSERT INTO appointments (patient_name, patient_phone, appointment_date, appointment_time, ticket_number, status, visit_type, created_at) VALUES (?, ?, ?, ?, ?, 'في الانتظار', 'موعد مسبق', ?)", (p_n, p_p, sel_date.isoformat(), sel_time, new_ticket, get_tunis_time().strftime("%Y-%m-%d %H:%M")))
                    conn.commit(); conn.close()
                    st.success(t(f"تم الحجز بنجاح! رقمك في الطابور هو #{new_ticket} ليوم {sel_date} الساعة {sel_time}.", f"Réservé ! Votre numéro est #{new_ticket} pour le {sel_date} à {sel_time}."))
                else:
                    st.warning(t("يرجى التأكد من إدخال الاسم ورقم الهاتف واختيار الوقت.", "Veuillez entrer le nom, le téléphone et choisir une heure."))

    elif st.session_state.patient_subview == 'records':
        st.markdown(t("#### 💊 أدخل بياناتك للاطلاع على وصفاتك الطبية", "#### 💊 Entrez vos données pour voir vos ordonnances"))
        c_p1, c_p2 = st.columns(2)
        search_phone = c_p1.text_input(t("رقم الهاتف:", "Téléphone :"), key="search_ph")
        search_name = c_p2.text_input(t("اسم المريض (للتفريق بين ملفات العائلة):", "Nom du patient :"), key="search_nm")
        
        if st.button(t("بحث", "Rechercher")):
            if search_phone and search_name:
                conn = get_connection()
                rec_df = pd.read_sql_query("SELECT * FROM medical_records WHERE patient_phone = ? AND patient_name LIKE ? ORDER BY id DESC", conn, params=(search_phone, f"%{search_name}%"))
                conn.close()
                if not rec_df.empty:
                    for _, row in rec_df.iterrows():
                        st.markdown(f"""
                        <div class="medical-card">
                            <span style="background:#ccfbf1; padding:4px 10px; border-radius:10px; font-weight:bold; color:#0f766e;">📅 {row['visit_date']} | المريض: {row['patient_name']}</span>
                            <p style="margin-top:15px; font-size:1.1rem;"><b>🩺 {t("التشخيص:", "Diagnostic :")}</b> {row['diagnosis']}</p>
                            <div style="background:#f0fdf4; padding:12px; border-radius:8px; border:1px dashed #16a34a;"><b>💊 {t("الوصفة:", "Ordonnance :")}</b><br>{row['prescription']}</div>
                            <div style="background:#eff6ff; padding:12px; border-radius:8px; border:1px dashed #2563eb; margin-top:8px;"><b>🔬 {t("التحاليل:", "Analyses :")}</b><br>{row['lab_tests']}</div>
                            <div style="background:#fef3c7; padding:12px; border-radius:8px; border:1px dashed #d97706; margin-top:12px;"><b style="color:#b45309;">📌 {t("ملاحظات وتوصيات الطبيب:", "Notes et recommandations :")}</b><br><span style="color:#92400e;">{row['doctor_notes']}</span></div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.warning(t("لا يوجد ملف طبي مسجل بهذا الرقم والاسم معاً.", "Aucun dossier médical trouvé pour ce nom et numéro."))
            else:
                st.warning(t("الرجاء إدخال رقم الهاتف واسم المريض.", "Veuillez entrer le téléphone et le nom."))

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
                if sec_pwd == settings['sec_pwd']: st.session_state.sec_auth = True; st.rerun()
                else: st.error(t("الرمز غير صحيح!", "Mot de passe incorrect !"))
    else:
        st.subheader(t("👩‍💻 شاشة الكاتبة الفائقة السرعة", "👩‍💻 Écran Secrétaire (Rapide)"))
        today_str = get_tunis_date().isoformat()
        
        conn = get_connection()
        if settings['last_reset_date'] != today_str:
            conn.execute("UPDATE clinic_settings SET current_ticket = 0, last_reset_date = ? WHERE id = 1", (today_str,))
            conn.commit()
            
        today_df = pd.read_sql_query("SELECT * FROM appointments WHERE appointment_date = ? AND status != 'ملغى' ORDER BY appointment_time ASC", conn, params=(today_str,))
        
        in_exam = today_df[today_df['status'] == 'في الفحص']
        waiting = today_df[today_df['status'] == 'في الانتظار']
        
        m1, m2, m3 = st.columns(3)
        # تعديل هنا: التأكد من وجود بيانات قبل طلب .iloc[0]
        current_patient_display = f"#{in_exam.iloc[0]['ticket_number']} - {in_exam.iloc[0]['patient_name']}" if not in_exam.empty else t("لا أحد", "Aucun")
        next_patient_display = f"#{waiting.iloc[0]['ticket_number']} - {waiting.iloc[0]['patient_name']}" if not waiting.empty else t("فارغ", "Vide")
        
        m1.metric(t("🟢 في الفحص الآن", "🟢 En consultation"), current_patient_display)
        m2.metric(t("🟡 القادم في الصف", "🟡 Prochain patient"), next_patient_display)
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
                else:
                    st.warning(t("لا يوجد مرضى في الانتظار حالياً.", "Aucun patient en attente."))
                conn.commit(); st.rerun()
        with c_add:
            with st.form("walkin"):
                st.write(t("➕ إضافة مريض بدون موعد:", "➕ Ajouter un patient sans rendez-vous :"))
                w_n = st.text_input(t("اسم المريض:", "Nom :"))
                w_p = st.text_input(t("رقم الهاتف:", "Téléphone :"))
                if st.form_submit_button(t("قطع تذكرة", "Créer ticket")) and w_n:
                    new_t = len(today_df) + 1 
                    current_time_str = get_tunis_time().strftime("%H:%M")
                    conn.execute("INSERT INTO appointments (patient_name, patient_phone, appointment_date, appointment_time, ticket_number, status, visit_type) VALUES (?, ?, ?, ?, ?, 'في الانتظار', 'حضور مباشر')", (w_n, w_p, today_str, current_time_str, new_t))
                    conn.commit(); st.rerun()
        conn.close()

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
                if doc_pwd == settings['doc_pwd']: st.session_state.doc_auth = True; st.rerun()
                else: st.error(t("الرمز غير صحيح!", "Mot de passe incorrect !"))
    else:
        c_nav1, c_nav2 = st.columns(2)
        with c_nav1:
            if st.button(t("👨‍⚕️ مكتب الطبيب (إصدار الوصفات)", "👨‍⚕️ Bureau du médecin (Ordonnances)"), use_container_width=True, type="primary" if st.session_state.doctor_subview == 'rx' else "secondary"): st.session_state.doctor_subview = 'rx'; st.rerun()
        with c_nav2:
            if st.button(t("⚙️ إعدادات العيادة الخاصة", "⚙️ Paramètres de la clinique"), use_container_width=True, type="primary" if st.session_state.doctor_subview == 'settings' else "secondary"): st.session_state.doctor_subview = 'settings'; st.rerun()
                
        st.write("")
        
        if st.session_state.doctor_subview == 'rx':
            st.subheader(t("👨‍⚕️ إصدار الوصفات والتحاليل", "👨‍⚕️ Émission des ordonnances et analyses"))
            today_str = get_tunis_date().isoformat()
            conn = get_connection()
            in_exam = pd.read_sql_query("SELECT * FROM appointments WHERE appointment_date = ? AND status = 'في الفحص'", conn, params=(today_str,))
            
            # تعديل مشابه هنا لتجنب نفس الخطأ في شاشة الطبيب
            def_n = in_exam.iloc[0]['patient_name'] if not in_exam.empty else ""
            def_p = in_exam.iloc[0]['patient_phone'] if not in_exam.empty else ""
            
            c_info, c_hist = st.columns([2, 1])
            with c_info:
                if def_n: st.success(t(f"المريض الحالي: {def_n} | التذكرة: #{in_exam.iloc[0]['ticket_number']}", f"Patient actuel: {def_n} | Ticket: #{in_exam.iloc[0]['ticket_number']}"))
            with c_hist:
                if def_n and def_p:
                    past_visits = pd.read_sql_query("SELECT COUNT(*) FROM medical_records WHERE patient_name = ? AND patient_phone = ?", conn, params=(def_n, def_p)).iloc[0,0]
                    st.info(f"📁 زيارات سابقة لهذا المريض: {past_visits}")
                
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
            
            st.markdown("---")
            if d_n and d_rx:
                print_html = f"""
                <script>
                function printRx() {{
                    const rxWindow = window.open('', '', 'width=800,height=600');
                    rxWindow.document.write('<html><head><title>وصفة طبية</title><style>body{{font-family: Arial, sans-serif; direction: rtl; padding: 40px;}} .header{{text-align: center; border-bottom: 2px solid #000; padding-bottom: 10px; margin-bottom: 30px;}} .patient{{margin-bottom: 30px; font-weight: bold;}} .rx-body{{min-height: 300px; font-size: 18px; line-height: 1.8;}}</style></head><body>');
                    rxWindow.document.write('<div class="header"><h2>{settings["doctor_name"]}</h2><p>{settings["specialty"]}</p></div>');
                    rxWindow.document.write('<div class="patient">التاريخ: {today_str} <br> اسم المريض: {d_n}</div>');
                    rxWindow.document.write('<div class="rx-body"><h3>الوصفة الطبية:</h3><pre style="font-family: Arial; font-size: 18px;">{d_rx}</pre></div>');
                    rxWindow.document.write('<div style="text-align:center; margin-top:50px;">إمضاء الطبيب</div>');
                    rxWindow.document.write('</body></html>');
                    rxWindow.document.close();
                    rxWindow.focus();
                    setTimeout(function() {{ rxWindow.print(); rxWindow.close(); }}, 250);
                }}
                </script>
                <button onclick="printRx()" style="background-color: #0f766e; color: white; padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: bold; width: 100%;">🖨️ طباعة الوصفة الآن (مباشرة للطابعة)</button>
                """
                components.html(print_html, height=50)

            conn.close()
            
        elif st.session_state.doctor_subview == 'settings':
            st.markdown(t("### ⚙️ إعدادات العيادة الخاصة", "### ⚙️ Paramètres de la clinique"))
            with st.form("doctor_clinic_settings"):
                c_set1, c_set2 = st.columns(2)
                new_start = c_set1.time_input(t("⏰ بداية الدوام:", "⏰ Début:"), value=datetime.strptime(settings['work_start'], "%H:%M").time())
                new_end = c_set2.time_input(t("⏰ نهاية الدوام:", "⏰ Fin:"), value=datetime.strptime(settings['work_end'], "%H:%M").time())
                
                st.subheader(t("⏱️ إعدادات الطابور", "⏱️ Paramètres de la file"))
                new_slot = st.number_input(t("مدة الفحص التقديرية لكل مريض (بالدقائق):", "Durée estimée par patient (minutes) :"), min_value=5, value=int(settings['slot_minutes']))
                st.subheader(t("🔒 أرقام الدخول السرية", "🔒 Mots de passe d'accès"))
                new_doc_pwd = st.text_input(t("الرقم السري الخاص بالطبيب:", "Mot de passe du médecin :"), value=settings['doc_pwd'], type="password")
                new_sec_pwd = st.text_input(t("الرقم السري الخاص بالكاتبة:", "Mot de passe de la secrétaire :"), value=settings['sec_pwd'], type="password")
                
                if st.form_submit_button(t("💾 تحديث إعدادات العيادة", "💾 Mettre à jour les paramètres"), type="primary"):
                    conn = get_connection()
                    conn.execute("UPDATE clinic_settings SET work_start=?, work_end=?, slot_minutes=?, doc_pwd=?, sec_pwd=? WHERE id=1", 
                                 (new_start.strftime("%H:%M"), new_end.strftime("%H:%M"), new_slot, new_doc_pwd, new_sec_pwd))
                    conn.commit(); conn.close(); st.success(t("✅ تم تحديث إعدادات العيادة بنجاح!", "✅ Paramètres mis à jour avec succès !")); st.rerun()

# ==========================================
# 4. القائمة التوسيعية (ركن المطور فقط)
# ==========================================
with st.expander("⚙️ ركن المطور وإعدادات العيادة (SaaS)", expanded=False):
    st.markdown(t("### ⚙️ ركن المطور (SaaS)", "### ⚙️ Espace Développeur (SaaS)"))
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
    if st.button(t("🔄 إعادة ضبط الرموز لـ 0000", "🔄 Réinitialiser à 0000")):
        conn = get_connection()
        conn.execute("UPDATE clinic_settings SET sec_pwd='0000', doc_pwd='0000' WHERE id=1")
        conn.commit(); conn.close()
        st.session_state.sec_auth = False; st.session_state.doc_auth = False
        st.success(t("تمت إعادة ضبط الرموز لـ 0000 بنجاح.", "Mots de passe réinitialisés à 0000 avec succès."))
