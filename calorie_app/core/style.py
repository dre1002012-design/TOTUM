"""
core/style.py — thèmes, couleurs et fonctions CSS (visuel seulement)
"""

import streamlit as st

COLORS = {
    "brand":    "#ff7f3f", "brand2":   "#ffb347",
    "ink":      "#0d1b1e", "muted":    "#5f6b76",
    "energie":  "#ff7f3f", "proteines": "#2ca02c",
    "glucides": "#1f77b4", "lipides":   "#d62728",
    "fibres":   "#9467bd", "omega3":    "#00bcd4",
    "epa":      "#26a69a", "dha":       "#7e57c2",
    "omega6":   "#ffb300", "omega9":    "#8d6e63",
    "restant":  "#e0e0e0", "objectif":  "#bdbdbd",
    "ok":       "#5cb85c", "warn":      "#f0ad4e", "bad":"#d9534f",
}

def apply_mobile_css_and_topbar(logo_b64: str | None):
    """Applique le thème clair et le bandeau supérieur (même rendu que ton app actuelle)."""
    st.markdown(f"""
    <style>
    [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"], header, footer {{
        display:none!important;
    }}
    html, body, .stApp {{
      background:#fff !important;
      color:{COLORS['ink']} !important;
      font-size:15.5px;
      color-scheme: light;
    }}
    .block-container {{ padding-top:.8rem; padding-bottom:.8rem; max-width:1100px; }}
    .topbar {{ position:sticky; top:0; z-index:100; padding:.6rem 0; display:flex; justify-content:center; }}
    .topbar-logo {{ width:140px; height:140px; object-fit:contain; }}
    </style>
    """, unsafe_allow_html=True)

    logo_html = f"<img class='topbar-logo' src='data:image/png;base64,{logo_b64}' alt='logo'/>" if logo_b64 else ""
    st.markdown(f"<div class='topbar'>{logo_html}</div>", unsafe_allow_html=True)

def set_favicon_from_logo(logo_b64: str | None):
    """Change le favicon pour qu’il reprenne le logo."""
    if not logo_b64:
        return
    st.markdown(f"""
    <script>
      const link = document.querySelector("link[rel='icon']") || document.createElement('link');
      link.rel = 'icon';
      link.href = "data:image/png;base64,{logo_b64}";
      document.head.appendChild(link);
    </script>
    """, unsafe_allow_html=True)
