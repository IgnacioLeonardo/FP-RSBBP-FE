import streamlit as st
from neo4j import GraphDatabase
import pandas as pd
import urllib.parse

# --- 1. KONFIGURASI DATABASE NEO4J ---
URI = "neo4j+s://94a80fb4.databases.neo4j.io"
AUTH = ("neo4j", "Kizq6HBqDDgKUhW3f5JPkHxqGlO1nKHwejkM_UhJYfw")

@st.cache_resource
def get_db_driver():
    try:
        driver = GraphDatabase.driver(URI, auth=AUTH)
        driver.verify_connectivity()
        return driver
    except Exception as e:
        st.error(f"Gagal terhubung ke Neo4j: {e}")
        return None

# --- 2. FUNGSI QUERY (BACKEND) ---
def get_hybrid_recommendations(driver, user_id, limit=12):
    query = """
    MATCH (target:User {userId: $userId})-[r1:RATED]->(m:Movie)<-[r2:RATED]-(other:User)
    WHERE r1.rating >= 4.0 AND r2.rating >= 4.0
    WITH target, other, COUNT(m) AS common_movies, 
         COLLECT(r1.rating) AS target_ratings, COLLECT(r2.rating) AS other_ratings
    WHERE common_movies > 2
    
    WITH target, other, common_movies,
         REDUCE(s = 0.0, k in range(0, size(target_ratings)-1) | s + target_ratings[k] * other_ratings[k]) AS dot_product,
         REDUCE(s = 0.0, r in target_ratings | s + r^2) AS target_norm_sq,
         REDUCE(s = 0.0, r in other_ratings | s + r^2) AS other_norm_sq
    
    WITH target, other, dot_product / (sqrt(target_norm_sq) * sqrt(other_norm_sq)) AS user_similarity
    WHERE user_similarity > 0.6
    
    MATCH (other)-[r:RATED]->(rec:Movie)
    WHERE NOT EXISTS( (target)-[:RATED]->(rec) )
    
    WITH target, rec, SUM(r.rating * user_similarity) AS cf_score
    
    OPTIONAL MATCH (target)-[r_target:RATED]->(:Movie)-[:IN_GENRE]->(g:Genre)<-[:IN_GENRE]-(rec)
    WHERE r_target.rating >= 4.0
    
    WITH rec, cf_score, COUNT(DISTINCT g) AS matching_genres
    
    RETURN rec.title AS title, 
           HEAD([(rec)-[:IN_GENRE]->(g) | g.name]) AS genre, 
           (cf_score + (matching_genres * 0.7)) AS raw_score
    ORDER BY raw_score DESC
    LIMIT $limit
    """
    with driver.session() as session:
        return [record.data() for record in session.run(query, userId=user_id, limit=limit)]

def get_user_history(driver, user_id):
    query = """
    MATCH (u:User {userId: $uid})-[r:RATED]->(m:Movie)
    
    RETURN m.title AS title, 
           r.rating AS rating, 
           HEAD([(m)-[:IN_GENRE]->(g) | g.name]) AS genre
    ORDER BY r.rating DESC LIMIT 5
    """
    with driver.session() as session:
        return [record.data() for record in session.run(query, uid=user_id)]

# --- 3. PAGE CONFIG & CSS ---
st.set_page_config(
    page_title="Sistem Rekomendasi Film",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&display=swap');
    
    :root {
        --background: hsl(230, 20%, 6%);
        --foreground: hsl(210, 20%, 95%);
        --card: hsl(230, 18%, 10%);
        --primary: hsl(38, 92%, 50%);
        --muted: hsl(230, 15%, 18%);
        --glass-border: hsl(230, 15%, 22%);
        --radius: 0.75rem;
    }
    
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    .stApp {
        background: var(--background);
        font-family: 'Outfit', sans-serif;
    }

    .bg-effects { position: fixed; inset: 0; pointer-events: none; z-index: 0; }
    .bg-glow-1 { position: absolute; top: 0; left: 25%; width: 500px; height: 500px; background: rgba(234, 179, 8, 0.03); border-radius: 50%; filter: blur(120px); }
    .bg-glow-2 { position: absolute; bottom: 0; right: 25%; width: 400px; height: 400px; background: rgba(225, 29, 72, 0.03); border-radius: 50%; filter: blur(100px); }

    .header { text-align: center; padding: 2rem 0; position: relative; z-index: 10; }
    .title { font-size: 2.5rem; font-weight: 700; margin-bottom: 0.5rem; color: white; }
    .title-gradient { background: linear-gradient(to right, var(--primary), hsl(45, 100%, 60%), var(--primary)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .subtitle { color: #9ca3af; font-size: 1rem; }

    .glass-card {
        background: rgba(255, 255, 255, 0.03);
        backdrop-filter: blur(20px);
        border: 1px solid var(--glass-border);
        border-radius: var(--radius);
        padding: 1.2rem;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1);
        position: relative;
        z-index: 10;
    }

    .stNumberInput input { 
        background: var(--muted) !important; 
        color: white !important; 
        border: 1px solid var(--glass-border) !important; 
        border-radius: 8px !important; 
        padding: 0.5rem !important;
    }
    .stButton button { 
        background: var(--primary) !important; 
        color: #1a1a1a !important; 
        font-weight: bold !important; 
        border: none !important; 
        border-radius: 8px !important; 
        padding: 0.5rem 1rem !important;
    }

    .movie-grid-container {
        max-height: 600px;
        overflow-y: auto;
        overflow-x: hidden;
        padding-right: 8px;
    }
    
    .movie-grid-container::-webkit-scrollbar {
        width: 8px;
    }
    
    .movie-grid-container::-webkit-scrollbar-track {
        background: var(--muted);
        border-radius: 4px;
    }
    
    .movie-grid-container::-webkit-scrollbar-thumb {
        background: var(--primary);
        border-radius: 4px;
    }
    
    .movie-grid { 
        display: grid; 
        grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); 
        gap: 0.8rem;
        padding: 4px;
    }
    
    .movie-card { 
        position: relative; 
        border-radius: 8px;
        overflow: hidden; 
        background: var(--card); 
        transition: all 0.2s ease; 
        border: 1px solid rgba(255,255,255,0.05);
        height: 120px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        padding: 12px;
    }
    
    .movie-card:hover { 
        transform: translateY(-3px); 
        border-color: var(--primary); 
        z-index: 10; 
        box-shadow: 0 4px 12px rgba(234, 179, 8, 0.1);
    }
    
    .movie-info { 
        padding: 0;
        background: transparent;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    
    .movie-title { 
        font-weight: 600; 
        color: white; 
        font-size: 0.9rem;
        margin-bottom: 4px;
        line-height: 1.2;
        display: -webkit-box;
        -webkit-line-clamp: 3;
        -webkit-box-orient: vertical;  
        overflow: hidden;
    }
    
    .movie-genre {
        font-size: 0.75rem; 
        color: #bbb;
    }
    
    .movie-match-badge { 
        position: absolute; 
        top: 8px; 
        right: 8px; 
        background: rgba(234, 179, 8, 0.15);
        color: var(--primary); 
        padding: 2px 6px; 
        border-radius: 4px; 
        font-weight: bold; 
        font-size: 0.7rem;
        border: 1px solid rgba(234, 179, 8, 0.3);
    }

    .history-item { 
        display: flex; 
        align-items: center; 
        gap: 0.8rem; 
        padding: 12px 8px; 
        border-bottom: 1px solid rgba(255,255,255,0.05);
        transition: background 0.2s;
    }
    
    .history-item:hover {
        background: rgba(255,255,255,0.02);
    }
    
    .history-icon { 
        background: var(--muted); 
        width: 36px; 
        height: 36px; 
        display: flex; 
        align-items: center; 
        justify-content: center; 
        border-radius: 6px; 
        font-size: 1.1rem;
        flex-shrink: 0;
    }
    
    [data-testid="column"] {
        padding: 0 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

# --- 4. LAYOUT APLIKASI ---

st.markdown('<div class="bg-effects"><div class="bg-glow-1"></div><div class="bg-glow-2"></div></div>', unsafe_allow_html=True)

st.markdown("""
<div class="header">
    <div style="font-size: 4rem; margin-bottom: 10px;">🎬</div>
    <h1 class="title"><span class="title-gradient">Movie</span>Mind</h1>
    <p class="subtitle">Intelligent Recommendations powered by <span style="color: #f59e0b;">Neo4j Graph</span></p>
</div>
""", unsafe_allow_html=True)

c1, c2 = st.columns([3, 1])
with c1:
    user_id = st.number_input("🔍 Masukkan User ID", min_value=1, value=1, key="user_input")
with c2:
    st.markdown('<div style="padding-top: 1.7rem;">', unsafe_allow_html=True)
    search_clicked = st.button("✨ Cari Film", use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

# --- 5. LOGIKA UTAMA ---

if search_clicked:
    driver = get_db_driver()
    if driver:
        history_data = get_user_history(driver, user_id)
        rec_data = get_hybrid_recommendations(driver, user_id, limit=12)

        col_left, col_right = st.columns([1, 2.5], gap="large")

        # --- KOLOM KIRI: RIWAYAT ---
        with col_left:
            st.markdown("""
            <div class="glass-card">
                <h3 style="color:white; margin-bottom:20px; border-left: 4px solid #f59e0b; padding-left:10px; font-size: 1.2rem;">
                    ⏱️ Riwayat User #{}</h3>
            """.format(user_id), unsafe_allow_html=True)

            if history_data:
                for item in history_data:
                    genre_text = item['genre'] if item['genre'] else "Unknown"
                    st.markdown(f"""
                    <div class="history-item">
                        <div class="history-icon">👁️</div>
                        <div style="flex:1; min-width: 0;">
                            <div style="color:white; font-weight:500; font-size: 0.9rem;">{item['title']}</div>
                            <div style="color:#888; font-size:0.75rem;">{genre_text}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.markdown('<div style="color:#888; padding: 20px; text-align:center;">Tidak ada data riwayat.</div></div>', unsafe_allow_html=True)

        # --- KOLOM KANAN: REKOMENDASI ---
        with col_right:
            st.markdown("""
            <div class="glass-card">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
                    <h3 style="color:white; margin:0; font-size:1.2rem;">✨ Top Picks</h3>
                    <span style="color:#888; font-size:0.85rem;">Based on your taste</span>
                </div>
                <div class="movie-grid-container">
                    <div class="movie-grid">
            """, unsafe_allow_html=True)

            if rec_data:
                max_score = rec_data[0]['raw_score'] if rec_data else 1
                
                for movie in rec_data:
                    match_percent = int((movie['raw_score'] / max_score) * 98)
                    genre_text = movie['genre'] if movie['genre'] else "Unknown"
                    
                    st.markdown(f"""
                    <div class="movie-card" title="{movie['title']}">
                        <div class="movie-match-badge">
                            {match_percent}%
                        </div>
                        <div class="movie-info">
                            <div class="movie-title">{movie['title']}</div>
                            <div class="movie-genre">{genre_text}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                
                st.markdown("</div></div></div>", unsafe_allow_html=True)
            else:
                st.markdown('</div></div><div style="color:#888; padding: 20px; text-align:center;">Tidak ada rekomendasi yang tersedia. Coba user ID lain.</div></div>', unsafe_allow_html=True)

st.markdown("""
<div style="text-align:center; color:#555; margin-top:50px; padding-bottom:30px; font-size: 0.9rem;">
    Powered by <strong style="color: #f59e0b;">Graph Machine Learning</strong> • Built with Neo4j & Streamlit
</div>
""", unsafe_allow_html=True)