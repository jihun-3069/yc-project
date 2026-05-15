# placeholder for original app8.py
# app8.py
import streamlit as st
from streamlit_folium import st_folium
import folium
from folium import DivIcon
from folium.plugins import PolyLineTextPath
import json
import os
import base64
import math
import heapq
import requests
import re
import textwrap
import pandas as pd
import numpy as np
from functools import lru_cache

# --- 경로 자동 설정 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
def get_path(filename):
    return os.path.join(BASE_DIR, filename).replace("\\", "/")

def get_project_asset_path(filename):
    return os.path.abspath(os.path.join(BASE_DIR, "..", "..", filename)).replace("\\", "/")

# --- 1. CSS (app2 디자인 그대로 유지) ---
st.set_page_config(page_title="Yeongcheon Transit Simulator (app7)", layout="wide")
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap');
    html, body, [data-testid="stSidebar"], .stApp {
        font-family: 'Outfit', sans-serif;
        background-color: #f8f9fa !important;
    }
    .detail-header { 
        font-size: 2.2rem !important; font-weight: 800 !important; color: #191f28 !important; 
        margin-bottom: 25px; border-bottom: 3px solid #e5e8eb; padding-bottom: 10px; 
    }
    .step-card {
        background: #ffffff !important; border-radius: 12px; padding: 18px; margin-bottom: 15px; 
        border-left: 6px solid #3498db; box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }
    .step-title { font-weight: 800; font-size: 1.1rem; color: #191f28; margin-bottom: 6px; }
    .step-body { font-size: 1rem; color: #333d4b; line-height: 1.5; }
    .step-time { font-weight: 800; color: #3498db; margin-top: 10px; font-size: 1.1rem; }
    
    /* 요약 타임라인 바 디자인 */
    .summary-container {
        margin-bottom: 40px; padding: 15px 0 10px 0;
    }
    .summary-bar {
        display: flex; align-items: flex-end; width: 100%; height: 45px; 
        background: #f1f3f5; border-radius: 8px; position: relative; overflow: visible;
    }
    .summary-segment {
        display: flex; flex-direction: column; justify-content: flex-end; height: 100%;
        position: relative;
    }
    .wait-label {
        position: absolute; top: -28px; left: 0; width: 100%; text-align: center;
        font-size: 0.75rem; color: #8b95a1; font-weight: 700; white-space: nowrap;
    }
    .summary-pill {
        display: flex; align-items: center; justify-content: center; gap: 4px; 
        height: 34px; border-radius: 6px; color: white; font-weight: 700; 
        font-size: 0.85rem; margin: 0 1px; white-space: nowrap; min-width: max-content;
    }
    .summary-walk { background: #adb5bd !important; }
    .summary-wait-zone {
        background: repeating-linear-gradient(45deg, #e5e8eb, #e5e8eb 5px, #f1f3f5 5px, #f1f3f5 10px);
        height: 34px; border-radius: 4px; margin: 0 1px; border: 1px dashed #ced4da;
    }
    
    /* 사이드바 글자색 보정 */
    [data-testid="stSidebar"] {
        color: #191f28 !important;
    }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3, [data-testid="stSidebar"] p, [data-testid="stSidebar"] label {
        color: #191f28 !important;
    }
    .stRadio label p {
        color: #191f28 !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. Data Loading ---
@st.cache_data
def get_detailed_roads(mtime=0):
    cache_path = get_path("yeongcheon_roads_cache.json")
    if os.path.exists(cache_path):
        with open(cache_path, 'r', encoding='utf-8') as f: return json.load(f)
    return None

@st.cache_data
def get_light_roads(mtime=0, max_features=1400):
    cache_path = get_path("yeongcheon_roads_cache.json")
    if not os.path.exists(cache_path):
        return None
    with open(cache_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    features = data.get("features", [])
    if len(features) <= max_features:
        return data
    stride = max(1, math.ceil(len(features) / max_features))
    light_features = []
    for feature in features[::stride]:
        geom = feature.get("geometry", {})
        if geom.get("type") == "LineString":
            coords = geom.get("coordinates", [])
            if len(coords) > 12:
                step = max(1, math.ceil(len(coords) / 12))
                geom = {**geom, "coordinates": coords[::step]}
        light_features.append({**feature, "geometry": geom})
    return {"type": data.get("type", "FeatureCollection"), "features": light_features}

@st.cache_data
def load_schedule_csv():
    path = get_path("route_day_summary_fixed.csv")
    if os.path.exists(path): return pd.read_csv(path)
    return None

df_schedule = load_schedule_csv()

@st.cache_data
def load_yci_scores_for_map():
    path = get_path("yci_v2_region_scores.csv")
    if not os.path.exists(path):
        return {}
    df = pd.read_csv(path, encoding='utf-8-sig')
    return {
        str(row["region_name"]): {
            "score": float(row["YCI_v2"]),
            "grade": str(row["yci_v2_grade"]),
            "delta": float(row.get("delta_yci", 0) or 0),
        }
        for _, row in df.iterrows()
    }

yci_scores_for_map = load_yci_scores_for_map()

def get_region_name_from_feature(feature):
    return feature.get("properties", {}).get("adm_nm", "").split()[-1]

def yci_fill_color(score):
    if score >= 70:
        return "#5fb6ac"
    if score >= 55:
        return "#8fcfc7"
    if score >= 40:
        return "#c4ded9"
    if score >= 30:
        return "#d9e8e4"
    return "#edf2ef"

def yci_region_style(feature):
    name = get_region_name_from_feature(feature)
    score = yci_scores_for_map.get(name, {}).get("score", 0)
    return {
        "fillColor": yci_fill_color(score),
        "color": "#2f4f4d",
        "weight": 1.15,
        "fillOpacity": 0.92,
        "opacity": 0.42,
    }

def yci_region_highlight(feature):
    return {
        "fillColor": "#9fe8dc",
        "color": "#0f766e",
        "weight": 2.6,
        "fillOpacity": 0.96,
        "opacity": 0.9,
    }

def polygon_label_point(geom):
    coords = geom.get("coordinates", [])
    if not coords:
        return None
    if geom.get("type") == "MultiPolygon":
        rings = [poly[0] for poly in coords if poly and poly[0]]
        ring = max(rings, key=len) if rings else None
    elif geom.get("type") == "Polygon":
        ring = coords[0] if coords else None
    else:
        ring = None
    if not ring:
        return None
    avg_lng = sum(p[0] for p in ring) / len(ring)
    avg_lat = sum(p[1] for p in ring) / len(ring)
    return [avg_lat, avg_lng]

def district_label_html(name, score):
    score_html = f"<span>{score:.0f}</span>" if score else ""
    return f"""
    <div class="district-label">
        <strong>{name}</strong>
        {score_html}
    </div>
    """

def hub_marker_html(name, selected=False):
    cls = "hub-marker selected" if selected else "hub-marker"
    return f"""
    <div class="{cls}" title="{name}">
        <div class="hub-core"></div>
    </div>
    """

@st.cache_data
def load_pinpoint_data_uri():
    pin_path = get_project_asset_path("Group 6.png")
    if not os.path.exists(pin_path):
        return None
    with open(pin_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("ascii")
    return f"data:image/png;base64,{encoded}"

def destination_marker_html():
    pin_src = load_pinpoint_data_uri()
    if pin_src:
        return f"""
        <div class="destination-marker">
            <img class="destination-pin-image" src="{pin_src}" alt="경마공원" />
            <div class="destination-label">경마공원</div>
        </div>
        """
    return """
    <div class="destination-marker fallback">
        <div class="destination-pin-fallback">★</div>
        <div class="destination-label">경마공원</div>
    </div>
    """

def get_precise_interval(route_id, d_mode, t_mode):
    if df_schedule is None: return 20
    is_weekend = ("주말" in d_mode)
    
    # 1. 요일 필터링 (주말은 토/일 합산하여 보수적으로 처리)
    if is_weekend:
        df_sat = df_schedule[(df_schedule['route_no'].astype(str) == str(route_id)) & (df_schedule['day_flag'] == "SATURDAY")]
        df_sun = df_schedule[(df_schedule['route_no'].astype(str) == str(route_id)) & (df_schedule['day_flag'].str.contains("SUNDAY|HOLIDAY", na=False))]
        if not df_sat.empty and not df_sun.empty:
            df_r = df_sat if df_sat.iloc[0]['run_count'] <= df_sun.iloc[0]['run_count'] else df_sun
        elif not df_sat.empty: df_r = df_sat
        else: df_r = df_sun
    else:
        df_r = df_schedule[(df_schedule['route_no'].astype(str) == str(route_id)) & (df_schedule['day_flag'] == "WEEKDAY")]
    
    if df_r.empty: return 15 if route_id.startswith("55") else 45
    
    row = df_r.iloc[0]
    times = str(row['times_csv']).split(',')
    
    # 2. 시간대 필터링
    if "오전" in t_mode:
        count = len([t for t in times if "08:00" <= t <= "10:00"])
        return 120 / (count + 0.5) if count > 0 else 240 # 운행 없으면 4시간 페널티
    elif "오후" in t_mode:
        count = len([t for t in times if "17:00" <= t <= "19:00"])
        return 120 / (count + 0.5) if count > 0 else 240
    
    # 하루 평균
    return (720 / (len(times) + 0.5)) / 2

@st.cache_data
def load_all_v5(mtime):
    # Cache busted to apply 111-2 bus route data
    json_path = get_path("bus_routes.json")
    if not os.path.exists(json_path): return {}, {}, {}
    
    # 캐시를 강제로 무효화하기 위해 파일의 마지막 수정 시간을 확인
    mtime = os.path.getmtime(json_path)
    
    with open(json_path, 'r', encoding='utf-8') as f: data = json.load(f)
    
    graph, all_stops = {}, {}
    # UI용 노선 목록 (언더바 포함 노선은 시스템에서 완전히 배제)
    filtered_bus_routes = {}
    
    for r_no, r_info in data.items():
        # 시스템 데이터(_) 제외
        if "_" in r_no: continue 
        # 55번, 555번의 하이픈(-) 파생 노선만 특정해서 제외
        if r_no.startswith("55-") or r_no.startswith("555-"): continue
        # [추가] 111-1번 노선 제외 (55번 이용 유도)
        if r_no == "111-1": continue
        
        filtered_bus_routes[r_no] = r_info
        stops = r_info['stops']
        
        # ID를 문자열로 통일
        for s in stops: s['id'] = str(s['id'])
        
        for i in range(len(stops)-1):
            s1, s2 = stops[i], stops[i+1]
            sid1, sid2 = s1['id'], s2['id']
            if not (35.85 < s1['lat'] < 36.25 and 128.7 < s1['lng'] < 129.15): continue
            if not (35.85 < s2['lat'] < 36.25 and 128.7 < s2['lng'] < 129.15): continue
            
            dist = math.sqrt((s1['lat']-s2['lat'])**2 + (s1['lng']-s2['lng'])**2)
            if sid1 not in graph: graph[sid1] = []
            graph[sid1].append({"to": sid2, "dist": dist, "route": r_no})
            all_stops[sid1] = s1; all_stops[sid2] = s2
            
    stop_items = sorted(all_stops.values(), key=lambda x: x['lat'])
    for i in range(len(stop_items)):
        s1 = stop_items[i]
        for j in range(i + 1, len(stop_items)):
            s2 = stop_items[j]
            if abs(s2['lat'] - s1['lat']) > 0.01: break 
            dist = math.sqrt((s1['lat']-s2['lat'])**2 + (s1['lng']-s2['lng'])**2)
            if dist < 0.004: 
                sid1, sid2 = s1['id'], s2['id'] # 이미 위에서 str 변환됨
                if sid1 == sid2: continue 
                if sid1 not in graph: graph[sid1] = []
                if sid2 not in graph: graph[sid2] = []
                graph[sid1].append({"to": sid2, "dist": dist, "route": "도보"})
                graph[sid2].append({"to": sid1, "dist": dist, "route": "도보"})
                
    try:
        # 보성리, 대평모텔 등의 특수 연결로직 (ID가 문자열임을 보장)
        boseong_id = next((k for k,v in all_stops.items() if v['name']=='보성리(목성)'), None)
        daepyeong_id = next((k for k,v in all_stops.items() if v['name']=='대평모텔건너'), None)
        if boseong_id and daepyeong_id:
            dist_shortcut = math.sqrt((all_stops[boseong_id]['lat'] - all_stops[daepyeong_id]['lat'])**2 + (all_stops[boseong_id]['lng'] - all_stops[daepyeong_id]['lng'])**2)
            graph[boseong_id].append({"to": daepyeong_id, "dist": dist_shortcut, "route": "222"})
            
        bugyeong_id = next((k for k,v in all_stops.items() if v['name']=='부경산업 앞'), None)
        if bugyeong_id and daepyeong_id:
            dist_shortcut = math.sqrt((all_stops[bugyeong_id]['lat'] - all_stops[daepyeong_id]['lat'])**2 + (all_stops[bugyeong_id]['lng'] - all_stops[daepyeong_id]['lng'])**2)
            graph[bugyeong_id].append({"to": daepyeong_id, "dist": dist_shortcut, "route": "222"})
    except Exception:
        pass
                
    return graph, all_stops, filtered_bus_routes

@st.cache_data
def get_road_geometry_safe(coords_tuple):
    coords = list(coords_tuple)
    return coords if len(coords) >= 2 else coords


def point_in_polygon(lat, lng, ring):
    """Ray casting: 점(lat,lng)이 링(좌표 리스트) 내부인지 확인"""
    x, y = lng, lat
    n = len(ring)
    inside = False
    p1x, p1y = ring[0][0], ring[0][1]
    for i in range(1, n + 1):
        p2x, p2y = ring[i % n][0], ring[i % n][1]
        if min(p1y, p2y) < y <= max(p1y, p2y):
            if x < max(p1x, p2x):
                if p1y != p2y:
                    x_int = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x < x_int:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside

def is_in_yeongcheon(lat, lng, emd_rings):
    """영천시 읍면동 폴리곤 목록 중 하나라도 내부이면 True"""
    for ring in emd_rings:
        if point_in_polygon(lat, lng, ring):
            return True
    return False

def get_region_name_at_point(lat, lng, emd_data_dict):
    if not emd_data_dict:
        return None
    for feature in emd_data_dict.get('features', []):
        geom = feature.get('geometry', {})
        rings = []
        if geom.get('type') == 'Polygon':
            rings = [geom.get('coordinates', [[]])[0]]
        elif geom.get('type') == 'MultiPolygon':
            rings = [poly[0] for poly in geom.get('coordinates', []) if poly and poly[0]]

        for ring in rings:
            if ring and point_in_polygon(lat, lng, ring):
                return get_region_name_from_feature(feature)
    return None

def get_admin_center_by_region(region_name):
    if not region_name:
        return None
    return next((h for h in hotspot_11 if h['name'].startswith(region_name)), None)

def point_to_segment_dist(py, px, y1, x1, y2, x2):
    """점(px, py)와 선분(x1,y1)-(x2,y2) 사이의 거리 (위경도 단순 계산)"""
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.sqrt((px-x1)**2 + (py-y1)**2)
    t = ((px - x1) * dx + (py - y1) * dy) / (dx*dx + dy*dy)
    t = max(0, min(1, t))
    nearest_x = x1 + t * dx
    nearest_y = y1 + t * dy
    return math.sqrt((px - nearest_x)**2 + (py - nearest_y)**2)

def find_nearest_route_insert_index(route_sids, new_sid, stops):
    """새 정류장을 기존 노선에서 가장 가까운 구간 뒤에 삽입할 위치를 찾는다."""
    if new_sid not in stops or len(route_sids) < 2:
        return len(route_sids)

    target = stops[new_sid]
    best_idx, best_dist = len(route_sids), float("inf")
    for idx in range(len(route_sids) - 1):
        sid_a, sid_b = str(route_sids[idx]), str(route_sids[idx + 1])
        if sid_a not in stops or sid_b not in stops:
            continue
        stop_a, stop_b = stops[sid_a], stops[sid_b]
        dist = point_to_segment_dist(
            target['lat'],
            target['lng'],
            stop_a['lat'],
            stop_a['lng'],
            stop_b['lat'],
            stop_b['lng'],
        )
        if dist < best_dist:
            best_dist = dist
            best_idx = idx + 1
    return best_idx

# --- [최적화] 노선 정렬 및 캐싱 로직 분리 ---
def natural_sort_key(s):
    priority = 0 if s and s[0].isdigit() else 1
    parts = [(0, int(t)) if t.isdigit() else (1, t.lower()) for t in re.split(r'(\d+)', s) if t]
    return (priority, parts)

@st.cache_data
def get_emd_rings(emd_data_dict):
    rings = []
    if emd_data_dict:
        for feature in emd_data_dict['features']:
            geom = feature['geometry']
            if geom['type'] == 'Polygon':
                rings.append(geom['coordinates'][0])
            elif geom['type'] == 'MultiPolygon':
                for poly in geom['coordinates']:
                    rings.append(poly[0])
    return rings


def get_admin_centers():
    return [
        {"name": "금호읍 행정복지센터", "lat": 35.93317, "lng": 128.87781},
        {"name": "청통면 행정복지센터", "lat": 35.99212, "lng": 128.82300},
        {"name": "신녕면 행정복지센터", "lat": 36.04536, "lng": 128.78946},
        {"name": "화산면 행정복지센터", "lat": 36.02037, "lng": 128.85233},
        {"name": "화북면 행정복지센터", "lat": 36.10820, "lng": 128.91936},
        {"name": "화남면 행정복지센터", "lat": 36.05914, "lng": 128.88911},
        {"name": "자양면 행정복지센터", "lat": 36.07848, "lng": 129.01855},
        {"name": "임고면 행정복지센터", "lat": 36.02109, "lng": 128.97393},
        {"name": "고경면 행정복지센터", "lat": 36.00157, "lng": 129.04584},
        {"name": "북안면 행정복지센터", "lat": 35.915225, "lng": 129.009873},
        {"name": "대창면 행정복지센터", "lat": 35.88173, "lng": 128.87570},
        {"name": "동부동 행정복지센터", "lat": 35.97449, "lng": 128.94255},
        {"name": "중앙동 행정복지센터", "lat": 35.97394, "lng": 128.93214},
        {"name": "서부동 행정복지센터", "lat": 35.96365, "lng": 128.92138},
        {"name": "완산동 행정복지센터", "lat": 35.96162, "lng": 128.94064},
        {"name": "남부동 행정복지센터", "lat": 35.94164, "lng": 128.93565},
    ]

# 파일 수정 시간을 인자로 전달하여 데이터가 바뀌면 자동으로 캐시를 갱신하게 함
json_path_for_cache = get_path("bus_routes.json")
road_cache_path = get_path("yeongcheon_roads_cache.json")
mtime_val = os.path.getmtime(json_path_for_cache) if os.path.exists(json_path_for_cache) else 0
road_mtime = os.path.getmtime(road_cache_path) if os.path.exists(road_cache_path) else 0
base_graph, all_stops, base_bus_routes = load_all_v5(mtime_val)
hotspot_11 = get_admin_centers()
road_lookup = {}
emd_path = get_path("yeongcheon_emd.geojson")
emd_data = json.load(open(emd_path, "r", encoding="utf-8")) if os.path.exists(emd_path) else None

# --- [추가] 세션 기반 그래프 및 데이터 관리 ---
if 'active_graph' not in st.session_state:
    import copy
    st.session_state.active_graph = copy.deepcopy(base_graph)
if 'active_bus_routes' not in st.session_state:
    import copy
    st.session_state.active_bus_routes = copy.deepcopy(base_bus_routes)

# 길찾기에 사용할 데이터는 세션 데이터를 우선함
graph_data = st.session_state.active_graph
bus_routes = st.session_state.active_bus_routes

# --- 3. Route Editor State ---
baseline_cache_path = get_path("baseline_paths_v2.json")
precomputed_paths = {}
if os.path.exists(baseline_cache_path):
    try:
        with open(baseline_cache_path, 'r', encoding='utf-8') as f:
            precomputed_paths = json.load(f)
    except: pass

if 'res' not in st.session_state: st.session_state.res = None
if 'last_click' not in st.session_state: st.session_state.last_click = None
if 'edit_mode' not in st.session_state: st.session_state.edit_mode = False
if 'edit_route_no' not in st.session_state: st.session_state.edit_route_no = None
if 'modified_stops' not in st.session_state: st.session_state.modified_stops = []
if 'selected_red_sid' not in st.session_state: st.session_state.selected_red_sid = None
if 'last_processed_click' not in st.session_state: st.session_state.last_processed_click = None
if 'path_cache' not in st.session_state: st.session_state.path_cache = precomputed_paths.copy()
if 'yci_dashboard_cache' not in st.session_state: st.session_state.yci_dashboard_cache = None
if 'selected_center_name' not in st.session_state: st.session_state.selected_center_name = None
if 'route_version' not in st.session_state: st.session_state.route_version = 0
if 'yci_monitor_rows_cache' not in st.session_state: st.session_state.yci_monitor_rows_cache = {}
if 'suppress_555_for_55_scenario' not in st.session_state: st.session_state.suppress_555_for_55_scenario = False

@lru_cache(maxsize=256)
def get_route_color(route_name):
    if route_name == "도보": return "#475569"
    # 하늘색 배경과 겹치는 파란색 계열을 배제한 선명한 팔레트
    colors = [
        "#0f766e", "#14b8a6", "#0369a1", "#7c3aed", "#c2410c", "#be123c",
        "#0891b2", "#059669", "#2563eb", "#9333ea", "#ea580c", "#dc2626",
        "#0d9488", "#0284c7", "#4f46e5", "#db2777", "#16a34a", "#ca8a04"
    ]
    # 주요 노선 고정 색상 (파란색 제외)
    fixed = {"55": 0, "555": 1, "220-2": 2, "111-2": 3, "612": 4}
    if route_name in fixed: return colors[fixed[route_name]]
    
    # SHA256 해시로 변별력 강화
    import hashlib
    h = hashlib.sha256(str(route_name).encode()).hexdigest()
    idx = int(h, 16) % len(colors)
    
    # 주요 노선 색상과 충돌 시 인덱스 점프
    if idx in fixed.values():
        idx = (idx + 7) % len(colors)
    return colors[idx]

def dijkstra_v73(start_lat, start_lng, dest_lat, dest_lng, custom_graph=None):
    # A* 기반 고속 탐색
    def heuristic(lat, lng):
        return math.sqrt((lat - dest_lat)**2 + (lng - dest_lng)**2) * 111 / 30 * 60

    start_nodes_candidates = []
    for sid, stop in all_stops.items():
        d = math.sqrt((start_lat-stop['lat'])**2 + (start_lng-stop['lng'])**2)
        start_nodes_candidates.append((d, sid))
    start_nodes_candidates.sort()
    
    start_nodes = []
    for i, (d, sid) in enumerate(start_nodes_candidates):
        if d < 0.008 or i < 3: start_nodes.append((d, sid))
        else: break
    
    end_nodes = {}
    for sid, stop in all_stops.items():
        d = math.sqrt((dest_lat-stop['lat'])**2 + (dest_lng-stop['lng'])**2)
        if d < 0.015: end_nodes[sid] = d
        
    if not start_nodes or not end_nodes: return None
    
    queue = []
    g_scores = {}
    for d, sid in start_nodes:
        walk_time = (d * 111) / 4.5 * 60
        walk_penalty = walk_time * 2.5
        h = heuristic(all_stops[sid]['lat'], all_stops[sid]['lng'])
        g_scores[(sid, None)] = walk_penalty
        heapq.heappush(queue, (h + walk_penalty, walk_penalty, sid, None, walk_time, 0))
    closed_set = set()
    predecessors = {}

    best_final_node = None
    min_final_cost = float('inf')
    final_actual_time = 0
    
    target_graph = custom_graph if custom_graph is not None else graph_data

    while queue:
        f, g, u, last_r, a_time, trans = heapq.heappop(queue)
        
        if (u, last_r) in closed_set:
            continue
        closed_set.add((u, last_r))
        
        if u in end_nodes:
            # 마지막 정류장에서 하차 시 탐색 종료 (도보 거리 페널티는 최소화하여 가장 가까운 정류장 선택)
            total_g = g + (end_nodes[u] * 0.1) 
            if total_g < min_final_cost:
                min_final_cost = total_g
                best_final_node = (u, last_r)
                final_actual_time = a_time # 마지막 도보 시간(final_walk)을 합산하지 않음
                break 

        if u in target_graph:
            for edge in target_graph[u]:
                v = edge['to']
                r_v = edge['route']
                if st.session_state.get('suppress_555_for_55_scenario') and str(r_v).startswith("555"):
                    continue
                is_walk = (r_v == "도보")
                t_travel = (edge['dist'] * 111) / (4.5 if is_walk else 30) * 60
                
                is_t = (last_r != r_v)
                wait, penalty = 0, 0
                if is_walk:
                    penalty += t_travel * 2.0 # 도보 가중치 강화
                    if is_t:
                        wait = 2
                        penalty += 20
                elif is_t:
                    wait = get_precise_interval(r_v, day_mode, time_mode)
                    
                    # --- 노선 등급별 차등 페널티 (환승 유연성 강화) ---
                    is_main = r_v.startswith("55")
                    if is_main:
                        penalty += 5   # 간선 노선은 환승 부담 거의 없음
                    elif r_v in ["111", "111-1"]:
                        penalty += 150 # 너무 삥 도는 노선은 강력 기피
                    else:
                        penalty += 50  # 일반 지선 환승 부담을 120 -> 50으로 완화
                    
                    # --- 청통면 거점 특별 우대 (222-1번 우선) ---
                    is_cheongtong = (abs(start_lat - 35.9865) < 0.01 and abs(start_lng - 128.8512) < 0.01)
                    if is_cheongtong:
                        if r_v == "222-1":
                            penalty = 5  # 최우선 순위
                        elif r_v == "222":
                            penalty += 200 # 청통에서는 222번 기피
                    
                    if any(c.isalpha() for c in r_v):
                        penalty += 40  # 읍면 지선/마을버스는 추가 페널티
                    
                    # --- 동일 계열간 환승 인센티브 (55 -> 55-1 등) ---
                    prev_family = last_r.split('-')[0].strip() if last_r else ""
                    curr_family = r_v.split('-')[0].strip()
                    if last_r and prev_family == curr_family:
                        wait = min(wait, 3)
                        penalty = 10 
                
                # --- 속도 차별화 ---
                speed = 30 # 기본 30km/h
                if r_v.startswith("555"): speed = 42 # 555번 급행은 더 빠름
                elif r_v.startswith("55"): speed = 35 # 55번 일반도 큰길이라 빠름
                elif is_walk: speed = 4.5
                
                t_travel = (edge['dist'] * 111) / speed * 60
                
                new_a = a_time + t_travel + wait
                new_g = g + t_travel + wait + penalty
                if (v, r_v) in closed_set: continue
                if (v, r_v) not in g_scores or g_scores[(v, r_v)] > new_g:
                    g_scores[(v, r_v)] = new_g
                    predecessors[(v, r_v)] = (u, last_r, new_a)
                    new_f = new_g + heuristic(all_stops[v]['lat'], all_stops[v]['lng'])
                    heapq.heappush(queue, (new_f, new_g, v, r_v, new_a, trans + (1 if is_t and not is_walk and last_r else 0)))

    if best_final_node:
        full_path = []
        curr = best_final_node
        re_visited = set()
        while curr in predecessors and curr not in re_visited:
            re_visited.add(curr)
            prev_u, prev_r, arr_t = predecessors[curr]
            full_path.append((curr[0], curr[1], arr_t))
            if prev_r is None:
                full_path.append((prev_u, curr[1], 0))
                break
            curr = (prev_u, prev_r)
        
        return {"path": full_path[::-1], "time": final_actual_time, "start_coord": [start_lat, start_lng]}
    return None


# --- 4. Figma exact app shell ---
FIGMA_FILE_URL = "https://www.figma.com/design/pcA6RdjJgHsETe7zgKH8Ur/Untitled?node-id=9-7029"
PAGES = ["Home", "About YCI", "Reports"]

def qp_get(name, default):
    value = st.query_params.get(name, default)
    if isinstance(value, list):
        value = value[0] if value else default
    return value

current_page = qp_get("page", "Home")
if current_page not in PAGES:
    current_page = "Home"

day_key = qp_get("day", "weekday")
time_key = qp_get("time", "morning")
day_mode = "주말 (토/일)" if day_key == "weekend" else "평일 (월~금)"
time_mode_map = {
    "morning": "오전 (입장: 08~10시)",
    "evening": "오후 (퇴장: 17~19시)",
    "all": "하루 전체 평균",
}
time_mode = time_mode_map.get(time_key, "오전 (입장: 08~10시)")

if "ui_page" not in st.session_state:
    st.session_state.ui_page = current_page
if "ui_day" not in st.session_state:
    st.session_state.ui_day = day_key
if "ui_time" not in st.session_state:
    st.session_state.ui_time = time_key

st.session_state.ui_page = current_page
st.session_state.ui_day = day_key
st.session_state.ui_time = time_key
day_mode = "주말 (토/일)" if day_key == "weekend" else "평일 (월~금)"
time_mode = time_mode_map.get(time_key, "오전 (입장: 08~10시)")

def qurl(page=None, day=None, time=None):
    page = page or current_page
    day = day or day_key
    time = time or time_key
    return f"?page={page.replace(' ', '%20')}&day={day}&time={time}"

def same_tab_attrs(url):
    return f"""href="{url}" target="_self\""""

EXACT_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@500;700&family=Nanum+Gothic:wght@400;700;800&family=Noto+Sans+KR:wght@400;500;700;800&display=swap');
:root {{
  --teal: #0f766e;
  --teal2: #14b8a6;
  --line: #b1d0ce;
  --ink: #1f1f21;
  --muted: #64748b;
  --panel: #f7f7f7;
}}
html, body, .stApp {{
  width: 100%;
  min-height: 900px;
  overflow-x: hidden;
  overflow-y: auto;
  background: #ffffff !important;
  font-family: 'Noto Sans KR', 'Nanum Gothic', sans-serif;
}}
[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], footer {{ display: none !important; }}
[data-testid="stSidebar"], [data-testid="collapsedControl"] {{ display: none !important; }}
[data-testid="stAppViewContainer"] > .main {{ background: #ffffff !important; }}
.block-container {{
  width: 1440px !important;
  max-width: 1440px !important;
  min-width: 1440px !important;
  height: 900px !important;
  padding: 0 !important;
  margin: 0 auto !important;
  position: relative !important;
  left: 0 !important;
  top: 0 !important;
  overflow: visible !important;
  transform-origin: top left !important;
}}
.yci-exact {{
  position: absolute;
  left: 0;
  top: 0;
  width: 1440px;
  height: 900px;
  background: white;
  color: var(--ink);
  overflow: hidden;
}}
.yci-topbar {{ position:absolute; left:258px; top:0; width:1182px; height:50px; background:#0f8377; color:#ecfeff; z-index:1; }}
.yci-top-title {{ position:absolute; left:53px; top:14px; font:700 15px/24px 'Nanum Gothic'; }}
.yci-top-sub {{ font:400 10px/24px 'Nanum Gothic'; opacity:.9; margin-left:4px; }}
.yci-export {{ display:none; }}
.yci-kebab {{ display:none; }}
.yci-sidebar {{ position:absolute; left:0; top:0; width:280px; height:840px; background:#f7f7f7; border:5px solid rgba(15,118,110,.3); border-left:0; border-radius:0 20px 20px 0; z-index:10; box-sizing:border-box; }}
.yci-sidebar.simple{{height: 900px;}} .yci-sidebar.simple .yci-divider {{display: none; box-shadow:none; }}
.yci-title {{ position:absolute; left:26px; top:26px; font:600 25px/24px 'DM Sans'; }}
.yci-place {{ position:absolute; left:23px; top:67px; width:197px; height:34px; border-radius:10px; background:#fff; font:700 15px/34px 'Nanum Gothic'; padding-left:10px; box-sizing:border-box; }}
.yci-divider {{ position:absolute; left:6px; top:124px; width:268px; height:1px; background:#c4c4c4; box-shadow:0 195px 0 #c4c4c4, 0 540px 0 #c4c4c4; }}
.side-section-title {{ position:absolute; left:24px; font:700 15px/24px 'Nanum Gothic'; color:#1f1f21; }}
.menu-label {{ top:144px; }}
.nav-item {{ position:absolute; left:24px; width:210px; height:24px; font:500 15px/24px 'DM Sans'; color:#1f1f21 !important; text-decoration:none !important; display:flex; align-items:center; gap:14px; }}
.nav-item.active {{ color:#0f766e !important; font-weight:700; }}
.nav-home {{ top:182px; }} .nav-about {{ top:219px; }} .nav-reports {{ top:257px; }}
.nav-icon {{ width:18px; text-align:center; font-size:15px; }}
.analysis-title {{ top:339px; }}
.side-label {{ position:absolute; left:24px; font:400 12px/18px 'Noto Sans KR'; color:#475569; }}
.day-label {{ top:381px; }} .time-label {{ top:469px; }}
.segment {{ position:absolute; left:24px; top:405px; width:232px; height:42px; border-radius:8px; background:#f1f5f9; border:1px solid #0f766e; box-sizing:border-box;}}
.segment a {{ position:absolute; top:4px; width:110px; height:30px; border-radius:7px; text-align:center; font:500 13px/34px 'Noto Sans KR'; color:#64748b; text-decoration:none; }}
.segment a:first-child {{ left:4px; }} .segment a:last-child {{ right:4px; }}
.segment a.active {{ background:#0f766e; color:#fff; }}
.time-option {{ position:absolute; left:24px; width:232px; height:38px; border-radius:8px; box-sizing:border-box; padding-left:16px; font:500 13px/38px 'Noto Sans KR'; text-decoration:none !important; }}
.time-option.active {{ background:#ecfeff; border:1px solid #06b6d4; color:#0e7490; font-weight:400; }}
.time-option.inactive {{ background:#f8fafc; border:1px solid #e2e8f0; color:#64748b; }}
.time-1 {{ top:497px; }} .time-2 {{ top:543px; }} .time-3 {{ top:589px; }}
.route-title {{ top:697px; }}
.apply-btn-fake {{ position:absolute; left:20px; top:793px; width:232px; height:44px; border-radius:8px; background:#0f766e; color:#fff; font:700 14px/44px 'Nanum Gothic'; text-align:center; }}
.right-panel {{ position:absolute; left:1102px; top:27px; width:316px; height:760px; border:1px solid #b1d0ce; border-radius:20px; background:#fff; z-index:3; box-sizing:border-box; }}
.right-title {{ position:absolute; left:24px; top:15px; font:700 18px/26px 'Noto Sans KR'; color:#0f172a; }}
.region-select-fake {{ position:absolute; left:24px; top:50px; width:197px; height:26px; border-radius:5px; background:#f1f5f9; color:#64748b; font:500 13px/26px 'Noto Sans KR'; padding-left:9px; box-sizing:border-box; }}
.usage-note {{ position:absolute; left:24px; top:90px; width:268px; height:28px; border-radius:7px; background:#ecfeff; color:#0f766e; font:700 10px/28px 'Noto Sans KR'; text-align:center; }}
.hero-card {{ position:absolute; left:24px; top:128px; width:268px; height:128px; border-radius:8px; background:#0f766e; color:#fff; }}
.hero-label {{ position:absolute; left:20px; top:20px; color:#ccfbf1; font:500 13px/18px 'Noto Sans KR'; }}
.hero-score {{ position:absolute; left:20px; top:48px; font:700 42px/48px 'Noto Sans KR'; }}
.hero-delta {{ position:absolute; left:108px; top:40px; width:52px; height:19px; border-radius:15px; background:#ecfeff; color:#0f766e; text-align:center; font:700 13px/19px 'Noto Sans KR'; }}
.hero-sub {{ position:absolute; left:20px; top:98px; color:#ccfbf1; font:400 12px/16px 'Noto Sans KR'; }}
.sparkline {{ position:absolute; right:18px; bottom:20px; width:78px; height:42px; opacity:.75; }}
.kpi {{ position:absolute; top:276px; width:82px; height:74px; border-radius:8px; border:1px solid #e2e8f0; background:#f8fafc; text-align:center; box-sizing:border-box; }}
.kpi.k1 {{ left:24px; }} .kpi.k2 {{ left:116px; }} .kpi.k3 {{ left:208px; }}
.kpi span {{ display:block; margin-top:11px; color:#64748b; font:500 10px/14px 'Noto Sans KR'; }}
.kpi b {{ display:block; margin-top:9px; color:#1f1f21; font:700 20px/26px 'Noto Sans KR'; }}
.path-title {{ position:absolute; left:24px; top:382px; font:700 15px/22px 'Noto Sans KR'; color:#0f172a; }}
.timeline {{ position:absolute; left:24px; top:417px; width:268px; height:24px; border-radius:8px; background:#f1f5f9; overflow:visible; display:flex; align-items:flex-end; }}
.timeline-seg {{ height:14px; min-width:16px; position:relative; }}
.timeline-seg.walk {{ background:#94a3b8; }}
.timeline-seg.bus {{ background:#14b8a6; }}
.timeline-seg.wait {{ width:28px !important; flex:0 0 28px !important; background:repeating-linear-gradient(45deg,#e2e8f0,#e2e8f0 4px,#f8fafc 4px,#f8fafc 8px); border:1px dashed #cbd5e1; box-sizing:border-box; }}
.timeline-seg:first-child {{ border-radius:8px 0 0 8px; }} .timeline-seg:last-child {{ border-radius:0 8px 8px 0; }}
.timeline-seg.wait::before {{ content:attr(data-label); position:absolute; top:-17px; left:-6px; width:40px; text-align:center; color:#64748b; font:700 9px/12px 'Noto Sans KR'; }}
.timeline-copy {{ position:absolute; left:25px; top:451px; width:268px; font:400 11px/16px 'Noto Sans KR'; color:#475569; white-space:normal; }}
.step-title {{ position:absolute; left:25px; top:486px; font:700 15px/22px 'Noto Sans KR'; color:#0f172a; }}
.step-list {{ position:absolute; left:25px; top:520px; width:268px; height:196px; overflow-y:auto; overflow-x:hidden; padding-right:2px; box-sizing:border-box; }}
.step-list::-webkit-scrollbar {{ width:5px; }}
.step-list::-webkit-scrollbar-thumb {{ background:#cbd5e1; border-radius:999px; }}
.step-card-ex {{ position:relative; width:260px; height:54px; margin:0 0 12px 0; border-radius:8px; border:1px solid #e2e8f0; background:white; box-sizing:border-box; }}
.step-num {{ position:absolute; left:16px; top:15px; width:24px; height:24px; border-radius:12px; background:#94a3b8; color:#fff; text-align:center; font:700 11px/24px 'Noto Sans KR'; }}
.step-card-ex.bus .step-num {{ background:#14b8a6; }}
.step-card-ex.wait .step-num {{ background:#64748b; }}
.step-text {{ position:absolute; left:52px; top:10px; width:168px; max-height:34px; font:400 11px/16px 'Noto Sans KR'; color:#0f172a; white-space:normal; overflow:hidden; word-break:keep-all; }}
.step-time {{ position:absolute; right:16px; top:18px; font:400 11px/14px 'Noto Sans KR'; color:#64748b; }}
.monitor-card {{ position:absolute; left:306px; top:550px; width:314px; height:240px; border:2px solid #b1d0ce; border-radius:20px; background:#f7f7f7; z-index:3; box-sizing:border-box; overflow:hidden; }}
.bottom-card {{ position:absolute; left:646px; top:550px; width:435px; height:240px; border:2px solid #b1d0ce; border-radius:20px; background:#f7f7f7; z-index:3; box-sizing:border-box; overflow:hidden; }}
.card-head {{ position:absolute; left:24px; top:14px; font:700 15px/24px 'Nanum Gothic'; }}
.monitor-card .card-head, .bottom-card .card-head {{ color:#1f1f21; }}
.card-rule {{ position:absolute; left:2px; top:49px; width:310px; height:2px; background:#bdbdbd; }}
.bottom-card .card-rule {{ width:430px; }}
.sort-note {{ position:absolute; right:20px; top:14px; font:700 10px/24px 'Nanum Gothic'; color:rgba(31,31,33,.3); }}
.yci-row {{ position:absolute; left:30px; width:250px; height:24px; font:800 15px/24px 'Nanum Gothic'; }}
.yci-row, .yci-row .score {{ color:#1f1f21; }}
.yci-row.r1 {{ top:70px; }} .yci-row.r2 {{ top:111px; }} .yci-row.r3 {{ top:152px; }} .yci-row.r4 {{ top:193px; }}
.yci-row .score {{ position:absolute; right:58px; }} .yci-row .delta {{ position:absolute; right:0; color:#06b6d4; font-size:10px; }}
.yci-row .delta.neutral {{ color:#94a3b8; }}
.change-row {{ position:absolute; left:15px; width:403px; height:31px; border-radius:30px; background:#fff; font:800 15px/24px 'Nanum Gothic'; }}
.change-row.c1 {{ top:68px; }} .change-row.c2 {{ top:110px; }} .change-row.c3 {{ top:153px; }} .change-row.c4 {{ top:198px; }}
.change-row .label {{ position:absolute; left:22px; top:4px; color:#1f1f21; }} .change-row .mid {{ position:absolute; left:160px; top:4px; width:134px; text-align:center; color:#0f172a; }} .change-row .diff {{ position:absolute; right:23px; top:4px; color:#0f766e; }}
.page-panel {{ position:absolute; left:306px; top:60px; width:1112px; height:820px; border-radius:20px; z-index:4; box-sizing:border-box; overflow:auto; }}
.about-panel {{ background:#f7f7f7; border:2px solid #b1d0ce; padding:28px; overflow:auto; }}
.reports-panel {{ background:#f7f7f7; border:2px solid #b1d0ce; padding:28px; color:#0f172a; }}
.page-title {{ font:800 25px/34px 'Noto Sans KR'; margin:0 0 8px; }}
.page-sub {{ font:400 14px/22px 'Noto Sans KR'; color:#475569; margin:0 0 20px; }}
.info-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
.info-card {{ border:1px solid #b1d0ce; background:#fff; border-radius:12px; padding:18px; min-height:120px; }}
.info-card h3 {{ margin:0 0 10px; font:800 18px/26px 'Noto Sans KR'; }}
.info-card p {{ margin:0; font:400 13px/22px 'Noto Sans KR'; color:#475569; }}
.formula-card {{ background:linear-gradient(135deg,#0f766e,#14b8a6); color:#fff; }} .formula-card p {{ color:#ecfeff; }}
.report-card-ex {{ display:grid; grid-template-columns:560px 1fr; gap:24px; border:1px solid #b1d0ce; background:#fff; border-radius:12px; padding:16px; margin-bottom:18px; }}
.report-card-ex img {{ width:100%; height:auto; border-radius:8px; border:1px solid #e2e8f0; }}
.report-tag {{ display:inline-block; padding:5px 9px; border-radius:999px; background:#e8f6f3; color:#0f766e; font:800 11px/14px 'Noto Sans KR'; margin-bottom:12px; }}
.report-card-ex h3 {{ margin:0 0 10px; font:800 18px/26px 'Noto Sans KR'; color:#0f172a; }}
.report-card-ex p {{ font:400 13px/22px 'Noto Sans KR'; color:#475569; }}
.report-card-ex .insight {{ padding:12px; border-radius:10px; background:#f7fbfa; border:1px solid #dcefeb; color:#24524e; }}
.about-yci {{ display:grid; grid-template-columns: 2fr 1fr; grid-template-rows:176px 205px 190px 200px; gap:18px; align-content:start; min-height:900px; background:#f8fafc; border:1px solid #d6e7e4; border-radius:8px; padding:24px; box-sizing:border-box; }}
.about-hero {{ background:#fff; border:1px solid #e2e8f0; border-radius:8px; padding:24px 26px; min-height:176px; box-sizing:border-box; overflow:hidden; }}
.about-chip {{ display:inline-block; padding:7px 13px; border-radius:999px; background:#ecfeff; color:#0e7490; font:800 10px/13px 'Noto Sans KR'; margin-bottom:4px; }}
.about-hero h1 {{ margin:0 0 4px; font:800 21px/29px 'Noto Sans KR'; color:#0f172a; }}
.about-hero p, .about-small {{ margin:0; font:400 12px/22px 'Noto Sans KR'; color:#64748b; }}
.about-formula {{ background:#0f766e; color:#fff; border-radius:8px; padding:20px; min-height:165px; box-sizing:border-box; overflow:hidden; }}
.about-formula .label {{ color:#ccfbf1; font:700 12px/18px 'Noto Sans KR'; margin-bottom:10px; }}
.about-formula .equation {{ font:900 20px/28px 'Noto Sans KR'; margin-bottom:10px; word-break:keep-all; }}
.about-formula p {{ color:#ccfbf1; font:400 10.5px/17px 'Noto Sans KR'; margin:0; word-break:keep-all; }}
.about-dimension-row {{ grid-column:1 / 2; display:grid; grid-template-columns:repeat(3, 1fr); gap:16px; }}
.about-dim {{ position:relative; background:#fff; border:1px solid #e2e8f0; border-radius:8px; padding:18px; min-height:205px; box-sizing:border-box; overflow:hidden; }}
.about-dim.focus {{ border:1px solid #e2e8f0; padding:18px; box-shadow: none; }}
.dim-badge {{ width:36px; height:36px; border-radius:18px; display:flex; align-items:center; justify-content:center; color:#fff; font:800 15px/1 'Noto Sans KR'; margin-bottom:10px; }}
.badge-s {{ background:#0284c7; }} .badge-t {{ background:#0f766e; }} .badge-a {{ background:#7c3aed; }}
.about-dim h3 {{ position:absolute; left:62px; top:18px; right:12px; margin:0; font:800 12px/18px 'Noto Sans KR'; color:#0f172a; word-break:keep-all; }}
.about-dim.focus h3 {{ left:62px; top:18px; }}
.about-dim .weight {{ position:absolute; left:62px; top:58px; font:700 11px/16px 'Noto Sans KR'; color:#0f766e; }}
.about-dim.focus .weight {{ left:62px; top:58px; }}
.about-dim p {{ margin:30px 0 20px; font:400 11px/18px 'Noto Sans KR'; color:#475569; word-break:keep-all; }}
.dim-bar {{ height:7px; border-radius:999px; background:#e2e8f0; overflow:hidden; }}
.dim-bar i {{ display:block; height:100%; border-radius:999px; }}
.about-side-card {{ background:#fff; border:1px solid #e2e8f0; border-radius:8px; padding:20px; min-height:182px; box-sizing:border-box; overflow:hidden; }}
.about-side-card h3, .about-wide h3 {{ margin:0 0 14px; font:800 17px/24px 'Noto Sans KR'; color:#0f172a; }}
.score-row, .point-row {{ display:grid; grid-template-columns:22px 1fr auto; gap:8px; align-items:center; font:700 12px/18px 'Noto Sans KR'; color:#334155; margin:8px 0; }}
.dot {{ width:12px; height:12px; border-radius:50%; display:inline-block; }}
.dot.a {{ background:#0f766e; }} .dot.b {{ background:#0284c7; }} .dot.c {{ background:#f97316; }} .dot.d {{ background:#be123c; }}
.point-row {{ grid-template-columns:22px 70px 1fr; font-weight:700; }}
.about-process {{ grid-column:1 / 2; background:#fff; border:1px solid #e2e8f0; border-radius:8px; padding:12px 22px 20px; min-height:190px; box-sizing:border-box; }}
.process-head {{ display:flex; align-items:baseline; gap:16px; margin-bottom:30px; }}
.process-title {{ color: #000; font-family: 'Noto Sans KR'; font-size: 20px; line-height: 24px; font-weight: 900; position: relative; white-space: nowrap; }}
.process-desc {{ font:700 12px/18px 'Noto Sans KR'; color:#94a3b8; }}
.process-steps {{ display:grid; grid-template-columns:repeat(5, 1fr); gap:10px; position:relative; }}
.process-steps::before {{ content:""; position:absolute; left:55px; right:55px; top:14px; height:1px; background:#5eead4; z-index:0; }}
.process-step {{ text-align:center; position:relative; z-index:1; }}
.process-num {{ margin:0 auto 12px; width:28px; height:28px; border-radius:14px; background:#0f766e; color:#fff; font:800 12px/28px 'Noto Sans KR'; }}
.process-step b {{ display:block; font:800 12px/18px 'Noto Sans KR'; color:#0f172a; }}
.process-step small {{ display:block; font:400 10px/15px 'Noto Sans KR'; color:#64748b; }}
.about-wide {{ grid-column:1 / -1; background:#fff; border:1px solid #e2e8f0; border-radius:8px; padding:18px 22px; display:grid; grid-template-columns:1fr 1fr 1fr 1.45fr; gap:20px; min-height:200px; box-sizing:border-box; }}
.sub-struct {{ background:#f8fafc; border:1px solid #dbe6ee; border-radius:8px; padding:14px; }}
.sub-struct b {{ display:block; font:800 12px/18px 'Noto Sans KR'; color:#2563eb; margin-bottom:7px; }}
.source-box {{ border:1px solid #5eead4; background:#ecfeff; }}
.source-box b {{ color:#0f766e; }}
/* Absolute placement for Streamlit runtime elements */
.st-key-route_select_wrap {{ position:absolute !important; left:20px !important; top:733px !important; width:232px !important; height:42px !important; z-index:30 !important; }}
.st-key-route_select_wrap label {{ display:none !important; }}
.st-key-route_select_wrap [data-baseweb="select"] > div {{ height:42px !important; min-height:42px !important; border-radius:8px !important; background:#f8fafc !important; border-color:#cbd5e1 !important; font-size:13px !important; }}
.st-key-route_select_wrap [data-baseweb="select"] * {{ color:#64748b !important; font:500 13px/18px 'Noto Sans KR' !important; }}
.st-key-route_select_wrap [data-baseweb="select"] svg {{ color:#64748b !important; fill:#64748b !important; }}
.st-key-apply_route_wrap {{ position:absolute !important; left:20px !important; top:793px !important; width:232px !important; height:44px !important; z-index:31 !important; }}
.st-key-apply_route_wrap button {{ width:232px !important; height:44px !important; border-radius:8px !important; background:#0f766e !important; color:#fff !important; border:0 !important; font:700 14px/18px 'Nanum Gothic' !important; }}
.st-key-nav_home_click {{ position:absolute !important; left:24px !important; top:182px !important; width:210px !important; height:24px !important; z-index:60 !important; }}
.st-key-nav_about_click {{ position:absolute !important; left:24px !important; top:219px !important; width:210px !important; height:24px !important; z-index:60 !important; }}
.st-key-nav_reports_click {{ position:absolute !important; left:24px !important; top:257px !important; width:210px !important; height:24px !important; z-index:60 !important; }}
.st-key-day_weekday_click {{ position:absolute !important; left:28px !important; top:409px !important; width:110px !important; height:34px !important; z-index:61 !important; }}
.st-key-day_weekend_click {{ position:absolute !important; left:146px !important; top:409px !important; width:110px !important; height:34px !important; z-index:61 !important; }}
.st-key-time_morning_click {{ position:absolute !important; left:24px !important; top:497px !important; width:232px !important; height:38px !important; z-index:61 !important; }}
.st-key-time_evening_click {{ position:absolute !important; left:24px !important; top:543px !important; width:232px !important; height:38px !important; z-index:61 !important; }}
.st-key-time_all_click {{ position:absolute !important; left:24px !important; top:589px !important; width:232px !important; height:38px !important; z-index:61 !important; }}
.st-key-nav_home_click button, .st-key-nav_about_click button, .st-key-nav_reports_click button,
.st-key-day_weekday_click button, .st-key-day_weekend_click button,
.st-key-time_morning_click button, .st-key-time_evening_click button, .st-key-time_all_click button {{
  width:100% !important; height:100% !important; padding:0 !important; margin:0 !important;
  opacity:1 !important; background:transparent !important; color:transparent !important;
  border:0 !important; box-shadow:none !important; cursor:pointer !important;
}}
.st-key-nav_home_click button:hover, .st-key-nav_about_click button:hover, .st-key-nav_reports_click button:hover,
.st-key-day_weekday_click button:hover, .st-key-day_weekend_click button:hover,
.st-key-time_morning_click button:hover, .st-key-time_evening_click button:hover, .st-key-time_all_click button:hover,
.st-key-nav_home_click button:focus, .st-key-nav_about_click button:focus, .st-key-nav_reports_click button:focus,
.st-key-day_weekday_click button:focus, .st-key-day_weekend_click button:focus,
.st-key-time_morning_click button:focus, .st-key-time_evening_click button:focus, .st-key-time_all_click button:focus {{
  background:transparent !important; color:transparent !important;
  border:0 !important; box-shadow:none !important; outline:0 !important;
}}
div[data-testid="stElementContainer"]:has(iframe) {{ position:absolute !important; left:306px !important; top:106px !important; width:775px !important; height:500px !important; z-index:5 !important; overflow:hidden !important; border:5px solid #b1ced0 !important; border-radius:20px !important; box-sizing:border-box !important; background:#d9d9d9 !important; }}
div[data-testid="stElementContainer"]:has(iframe) iframe {{ width:765px !important; height:490px !important; border-radius:15px !important; }}
@media (max-width: 1439px) {{
  .block-container {{ margin: 0 !important; left: 0 !important; top: 0 !important; transform: scale(.948) !important; }}
  html, body, .stApp {{ min-height: 854px; }}
}}
@media (max-width: 1200px) {{
  .block-container {{ transform: scale(.833) !important; }}
  html, body, .stApp {{ min-height: 750px; }}
}}
@media (max-width: 900px) {{
  .block-container {{ transform: scale(.625) !important; }}
  html, body, .stApp {{ min-height: 563px; }}
}}
@media (max-width: 700px) {{
  .block-container {{ transform: scale(.486) !important; }}
  html, body, .stApp {{ min-height: 438px; }}
}}
@media (max-width: 560px) {{
  .block-container {{ transform: scale(.389) !important; }}
  html, body, .stApp {{ min-height: 351px; }}
}}
</style>
"""
st.markdown(EXACT_CSS, unsafe_allow_html=True)

def render_html(markup):
    compact = textwrap.dedent(markup).replace("\n", "")
    st.markdown(compact, unsafe_allow_html=True)

def nav_class(page):
    return "active" if current_page == page else ""

def render_shell():
    home_active = nav_class("Home")
    about_active = nav_class("About YCI")
    reports_active = nav_class("Reports")
    weekday_active = "active" if day_key != "weekend" else ""
    weekend_active = "active" if day_key == "weekend" else ""
    t1 = "active" if time_key == "morning" else "inactive"
    t2 = "active" if time_key == "evening" else "inactive"
    t3 = "active" if time_key == "all" else "inactive"
    sidebar_class = "yci-sidebar" if current_page == "Home" else "yci-sidebar simple"
    if current_page == "About YCI":
        top_title = "YCI (Yeongcheon Connectivity Index) 구조 설명"
        top_sub = ""
    elif current_page == "Reports":
        top_title = "YCI 수립 과정 시각화 갤러리"
        top_sub = ""
    else:
        top_title = "영천경마공원 대중교통 접근성 시뮬레이터"
        top_sub = '<span class="yci-top-sub">정책 시나리오 적용에 따른 YCI 개선 효과와 최적 경로를 한 화면에서 비교합니다.</span>'
    controls_html = ""
    if current_page == "Home":
        controls_html = f"""
        <div class="side-section-title analysis-title">분석 조건 설정</div><div class="side-label day-label">분석 요일</div>
        <div class="segment"><a class="{weekday_active}" {same_tab_attrs(qurl(day='weekday'))}>평일</a><a class="{weekend_active}" {same_tab_attrs(qurl(day='weekend'))}>주말</a></div>
        <div class="side-label time-label">대상 시간대</div>
        <a class="time-option time-1 {t1}" {same_tab_attrs(qurl(time='morning'))}>오전 입장 08-10시</a>
        <a class="time-option time-2 {t2}" {same_tab_attrs(qurl(time='evening'))}>오후 퇴장 17-19시</a>
        <a class="time-option time-3 {t3}" {same_tab_attrs(qurl(time='all'))}>하루 전체 평균</a>
        <div class="side-section-title route-title">노선 편집 패널</div>
        """
    render_html(f"""
    <div class="yci-exact">
      <div class="yci-topbar"><span class="yci-top-title">{top_title} {top_sub}</span><span class="yci-export">분석 내보내기</span><span class="yci-kebab">⋮</span></div>
      <aside class="{sidebar_class}">
        <div class="yci-title">YCI Simulator</div><div class="yci-place">영천 경마 공원</div><div class="yci-divider"></div>
        <div class="side-section-title menu-label">메뉴</div>
        <a class="nav-item nav-home {home_active}" {same_tab_attrs(qurl('Home'))}><span class="nav-icon">⌂</span>Home</a>
        <a class="nav-item nav-about {about_active}" {same_tab_attrs(qurl('About YCI'))}><span class="nav-icon">▤</span>About YCI</a>
        <a class="nav-item nav-reports {reports_active}" {same_tab_attrs(qurl('Reports'))}><span class="nav-icon">◷</span>Reports</a>
        {controls_html}
      </aside>
    </div>
    """)

def set_ui_state(page=None, day=None, time=None):
    st.session_state.ui_page = page or current_page
    st.session_state.ui_day = day or day_key
    st.session_state.ui_time = time or time_key

def render_click_targets():
    with st.container(key="nav_home_click"):
        st.button("Home", key="nav_home_btn", on_click=set_ui_state, kwargs={"page": "Home"})
    with st.container(key="nav_about_click"):
        st.button("About YCI", key="nav_about_btn", on_click=set_ui_state, kwargs={"page": "About YCI"})
    with st.container(key="nav_reports_click"):
        st.button("Reports", key="nav_reports_btn", on_click=set_ui_state, kwargs={"page": "Reports"})

    if current_page == "Home":
        with st.container(key="day_weekday_click"):
            st.button("평일", key="day_weekday_btn", on_click=set_ui_state, kwargs={"day": "weekday"})
        with st.container(key="day_weekend_click"):
            st.button("주말", key="day_weekend_btn", on_click=set_ui_state, kwargs={"day": "weekend"})
        with st.container(key="time_morning_click"):
            st.button("오전 입장", key="time_morning_btn", on_click=set_ui_state, kwargs={"time": "morning"})
        with st.container(key="time_evening_click"):
            st.button("오후 퇴장", key="time_evening_btn", on_click=set_ui_state, kwargs={"time": "evening"})
        with st.container(key="time_all_click"):
            st.button("하루 전체", key="time_all_btn", on_click=set_ui_state, kwargs={"time": "all"})

def count_transfers(path):
    transfers = 0
    prev_route = None
    for _, route, _ in path or []:
        if route and route != "도보":
            if prev_route is not None and prev_route != route:
                transfers += 1
            prev_route = route
    return transfers

def panel_defaults():
    return {
        "region": "금호읍 행정복지센터",
        "score": "72.8",
        "delta": "+7.4",
        "base_score": "65.4",
        "time": "62분",
        "transfers": "1회",
        "wait": "18분",
        "timeline": "도보 8분 · 대기 18분 · 버스 31분 · 도보 5분",
        "timeline_segments": [
            {"kind": "walk", "minutes": 8, "label": "도보 8분"},
            {"kind": "wait", "minutes": 18, "label": "대기 18분"},
            {"kind": "bus", "minutes": 31, "label": "버스 31분"},
            {"kind": "walk", "minutes": 5, "label": "도보 5분"},
        ],
        "steps": [
            ("1", "거점에서 금호정류장까지 도보", "8분", "walk"),
            ("2", "55번 버스 승차 후 중앙동 환승", "49분", "bus"),
            ("3", "경마공원까지 도보 이동", "5분", "walk"),
        ],
        "changes": [
            ("평균 접근시간", "74분 → 58분", "- 16 분"),
            ("환승 횟수", "2.1회 → 1.4회", "- 0.7 회"),
            ("대기시간", "28분 → 17분", "- 9 분"),
            ("YCI", "48.2% → 61.7%", "+ 13.5 %"),
        ],
    }

def get_panel_data():
    data = panel_defaults()
    res = st.session_state.get("res")
    if not res:
        return data

    start_lat, start_lng = res.get("start_coord", [None, None])
    best_h = next(
        (h for h in hotspot_11 if abs(h["lat"] - start_lat) < 0.001 and abs(h["lng"] - start_lng) < 0.001),
        None,
    )
    emd_name = best_h["name"].replace(" 행정복지센터", "") if best_h else "선택 지역"
    data["region"] = best_h["name"] if best_h else "선택 지역"

    base_yci = 0
    base_t = 0
    base_s = 0
    base_a = 0
    try:
        df_yci = pd.read_csv(get_path("yci_v2_region_scores.csv"), encoding="utf-8")
        row = df_yci[df_yci["region_name"] == emd_name].iloc[0]
        base_yci = float(row["YCI_v2"])
        base_t = float(row["T_v2"])
        base_s = float(row["S_v2"])
        base_a = float(row["A_v2"])
    except Exception:
        pass

    cache_key = f"{best_h['name']}_{day_mode}_{time_mode}" if best_h else ""
    base_res = precomputed_paths.get(cache_key)
    base_time = base_res["time"] if base_res else res.get("time", 0)
    new_time = res.get("time", 0)
    base_transfers = count_transfers(base_res.get("path", [])) if base_res else count_transfers(res.get("path", []))
    new_transfers = count_transfers(res.get("path", []))
    delta_time = base_time - new_time
    delta_transfers = base_transfers - new_transfers

    if base_yci:
        delta_t_score = (delta_time * 0.5) + (delta_transfers * 5.0)
        new_t = min(100, max(0, base_t + delta_t_score))
        new_yci = (0.35 * base_s) + (0.40 * new_t) + (0.25 * base_a)
        diff_yci = new_yci - base_yci
        data["score"] = f"{new_yci:.1f}"
        data["delta"] = f"{diff_yci:+.1f}"
        data["base_score"] = f"{base_yci:.1f}"

    data["time"] = f"{int(round(new_time))}분"
    data["transfers"] = f"{new_transfers}회"

    path = res.get("path", [])
    first_stop = all_stops.get(str(path[0][0])) if path else None
    walk_start = 0
    if first_stop:
        walk_start = int((math.sqrt((start_lat - first_stop["lat"]) ** 2 + (start_lng - first_stop["lng"]) ** 2) * 111) / 4.5 * 60)

    legs = []
    for i in range(1, len(path)):
        sid_p, _, t_p = path[i - 1]
        sid_c, r_c, t_c = path[i]
        if not legs or legs[-1]["route"] != r_c:
            legs.append({"route": r_c, "start_stop": sid_p, "end_stop": sid_c, "start_time": t_p, "end_time": t_c})
        else:
            legs[-1]["end_stop"] = sid_c
            legs[-1]["end_time"] = t_c

    bus_minutes = 0
    wait_minutes = 0
    walk_minutes = walk_start
    timeline_segments = []
    steps = []
    step_no = 1
    extra_walk_minutes = 0
    if first_stop and walk_start:
        timeline_segments.append({"kind": "walk", "minutes": walk_start, "label": f"도보 {walk_start}분"})
        steps.append((str(step_no), f"{emd_name}에서 {first_stop['name']}까지 도보", f"{walk_start}분", "walk"))
        step_no += 1
    for leg in legs:
        total_dur = max(1, int(leg["end_time"] - leg["start_time"]))
        s_name = all_stops.get(str(leg["start_stop"]), {}).get("name", "출발지")
        e_name = all_stops.get(str(leg["end_stop"]), {}).get("name", "도착지")
        if leg["route"] == "도보":
            walk_minutes += total_dur
            extra_walk_minutes += total_dur
            timeline_segments.append({"kind": "walk", "minutes": total_dur, "label": f"도보 {total_dur}분"})
        else:
            wait_time = int(get_precise_interval(leg["route"], day_mode, time_mode))
            wait_minutes += wait_time
            drive_time = max(1, total_dur - wait_time)
            bus_minutes += drive_time
            if wait_time > 0:
                timeline_segments.append({"kind": "wait", "minutes": wait_time, "label": f"대기 {wait_time}분"})
                steps.append((str(step_no), f"대기 {wait_time}분 포함", f"{wait_time}분", "wait"))
                step_no += 1
            timeline_segments.append({"kind": "bus", "minutes": drive_time, "label": f"{leg['route']}번 {drive_time}분"})
            steps.append((str(step_no), f"{leg['route']}번 버스 승차 후 {e_name} 하차", f"{drive_time}분", "bus"))
            step_no += 1
    if extra_walk_minutes:
        steps.append((str(step_no), "하차 후 목적지까지 도보", f"{extra_walk_minutes}분", "walk"))

    data["wait"] = f"{wait_minutes}분" if wait_minutes else data["wait"]
    data["timeline"] = f"도보 {walk_minutes}분 · 대기 {wait_minutes}분 · 버스 {bus_minutes}분"
    data["timeline_segments"] = timeline_segments or data["timeline_segments"]
    data["steps"] = steps
    display_delta_time = new_time - base_time
    display_delta_transfers = new_transfers - base_transfers
    data["changes"] = [
        ("평균 접근시간", f"{int(round(base_time))}분 → {int(round(new_time))}분", f"{display_delta_time:+.0f} 분"),
        ("환승 횟수", f"{base_transfers}회 → {new_transfers}회", f"{display_delta_transfers:+.0f} 회"),
        ("대기시간", f"{wait_minutes}분", "실시간"),
        ("YCI", f"{data['base_score']} → {data['score']}", data["delta"]),
    ]
    return data

def is_route_modified():
    return st.session_state.active_bus_routes != base_bus_routes

@st.cache_data
def load_yci_scores_table():
    try:
        return pd.read_csv(get_path("yci_v2_region_scores.csv"), encoding="utf-8")
    except Exception:
        return pd.DataFrame()

def get_path_for_center(center, cache_key):
    curr_res = st.session_state.path_cache.get(cache_key)
    if curr_res is None and is_route_modified():
        curr_res = dijkstra_v73(center["lat"], center["lng"], 35.952, 128.871)
        st.session_state.path_cache[cache_key] = curr_res
    elif curr_res is None:
        curr_res = precomputed_paths.get(cache_key)
    return curr_res

def get_selected_center():
    name = st.session_state.get("selected_center_name")
    if not name:
        return None
    return next((h for h in get_admin_centers() if h["name"] == name), None)

def recompute_selected_route_after_apply():
    center = get_selected_center()
    if not center:
        st.session_state.res = None
        return
    cache_key = f"{center['name']}_{day_mode}_{time_mode}"
    res = dijkstra_v73(center["lat"], center["lng"], 35.952, 128.871)
    if res:
        st.session_state.res = res
        st.session_state.path_cache[cache_key] = res

def compute_yci_monitor_rows(limit=4):
    cache_key_for_rows = f"{st.session_state.route_version}:{day_mode}:{time_mode}:{limit}"
    cached_rows = st.session_state.yci_monitor_rows_cache.get(cache_key_for_rows)
    if cached_rows is not None:
        return cached_rows

    df_yci = load_yci_scores_table()
    if df_yci.empty:
        return [("금호읍", "73.6", "+30.8"), ("청통면", "73.6", "+30.8"), ("신녕면", "66.9", "+20.4"), ("화산면", "57.3", "+15.6")]

    rows = []
    for center in get_admin_centers():
        emd_name = center["name"].replace(" 행정복지센터", "")
        try:
            row = df_yci[df_yci["region_name"] == emd_name].iloc[0]
            base_yci = float(row["YCI_v2"])
            base_s = float(row["S_v2"])
            base_t = float(row["T_v2"])
            base_a = float(row["A_v2"])
        except Exception:
            continue

        cache_key = f"{center['name']}_{day_mode}_{time_mode}"
        base_res = precomputed_paths.get(cache_key)
        curr_res = get_path_for_center(center, cache_key)
        base_time = base_res["time"] if base_res else (curr_res["time"] if curr_res else 120)
        new_time = curr_res["time"] if curr_res else base_time
        base_transfers = count_transfers(base_res.get("path", [])) if base_res else 0
        new_transfers = count_transfers(curr_res.get("path", [])) if curr_res else base_transfers

        delta_time = base_time - new_time
        delta_transfers = base_transfers - new_transfers
        delta_t_score = (delta_time * 0.5) + (delta_transfers * 5.0)
        new_t = min(100, max(0, base_t + delta_t_score))
        new_yci = (0.35 * base_s) + (0.40 * new_t) + (0.25 * base_a)
        diff = new_yci - base_yci
        rows.append((emd_name, new_yci, diff))

    rows.sort(key=lambda item: item[2], reverse=True)
    result_rows = [(name, f"{score:.1f}", f"{diff:+.1f}" if abs(diff) >= 0.05 else "-") for name, score, diff in rows[:limit]]
    st.session_state.yci_monitor_rows_cache = {cache_key_for_rows: result_rows}
    return result_rows

def render_home_static_panels():
    data = get_panel_data()
    total_segment_minutes = max(1, sum(max(1, int(seg["minutes"])) for seg in data["timeline_segments"] if seg["kind"] != "wait"))
    timeline_html = ""
    for seg in data["timeline_segments"]:
        minutes = max(1, int(seg["minutes"]))
        if seg["kind"] == "wait":
            timeline_html += f'<i class="timeline-seg wait" data-label="{seg["label"]}"></i>'
        else:
            flex = max(0.18, minutes / total_segment_minutes)
            timeline_html += f'<i class="timeline-seg {seg["kind"]}" title="{seg["label"]}" style="flex:{flex:.3f}"></i>'
    step_html = ""
    for idx, text, minutes, kind in data["steps"]:
        step_html += f'<div class="step-card-ex {kind}"><div class="step-num">{idx}</div><div class="step-text">{text}</div><div class="step-time">{minutes}</div></div>'
    step_html = f'<div class="step-list">{step_html}</div>'
    change_html = ""
    for i, (label, mid, diff) in enumerate(data["changes"], start=1):
        change_html += f'<div class="change-row c{i}"><span class="label">{label}</span><span class="mid">{mid}</span><span class="diff">{diff}</span></div>'
    monitor_html = ""
    for i, (name, score, delta) in enumerate(compute_yci_monitor_rows(), start=1):
        delta_class = "delta neutral" if delta == "-" else "delta"
        monitor_html += f'<div class="yci-row r{i}">{name} <span class="score">{score}</span><span class="{delta_class}">{delta}</span></div>'

    render_html(f"""
    <div class="map-frame"></div>
    <section class="right-panel"><div class="right-title">선택 지역 YCI 개선 분석</div><div class="region-select-fake">{data["region"]}</div><div class="usage-note">지도에서 읍면동 선택 → 노선 수정 → 시뮬레이션 적용</div><div class="hero-card"><div class="hero-label">YCI 개선 수준</div><div class="hero-score">{data["score"]}</div><div class="hero-delta">{data["delta"]}</div><div class="hero-sub">기존 {data["base_score"]} 대비 개선</div><svg class="sparkline" viewBox="0 0 100 48"><path d="M2 38 C12 30 18 42 27 25 C36 8 45 34 55 20 C64 6 74 18 83 3 C91 19 96 13 100 16" fill="none" stroke="#67e8f9" stroke-width="5" stroke-linecap="round"/></svg></div><div class="kpi k1"><span>총 소요 시간</span><b>{data["time"]}</b></div><div class="kpi k2"><span>환승 횟수</span><b>{data["transfers"]}</b></div><div class="kpi k3"><span>대기 시간</span><b>{data["wait"]}</b></div><div class="path-title">상세 이동 경로</div><div class="timeline">{timeline_html}</div><div class="timeline-copy">{data["timeline"]}</div><div class="step-title">상세 경로</div>{step_html}</section>
    <section class="monitor-card"><div class="card-head">▣ 전 지역 YCI 모니터링</div><div class="sort-note">개선폭 큰 순</div><div class="card-rule"></div>{monitor_html}</section>
    <section class="bottom-card"><div class="card-head">◷ 선택 지역 접근성 변화</div><div class="card-rule"></div>{change_html}</section>
    """)

REPORT_ITEMS = [
    ("p3_accessibility.png", "Access time", "접근성 종합 진단", "읍면동별 경마공원 도달 시간을 비교해 접근 취약권역을 한눈에 보여주는 기준 지도입니다.", "자양면·화북면 등 외곽 북동권은 170분 이상으로 접근성이 낮고, 금호읍·청통면은 상대적으로 접근 부담이 작습니다."),
    ("p3_bus_blindspot.png", "Coverage", "대중교통 사각지대", "버스 서비스권을 거리 단계로 구분해 경마공원 접근 전 대중교통 기반의 공간 공백을 진단합니다.", "서부·북부 외곽에는 1.5km 이상 접근 공백이 남아 있어 보완 검토가 필요합니다."),
    ("p3_circuity_final.png", "Circuity", "노선 굴곡도 분석", "직선거리 대비 실제 버스 주행거리 배율을 비교해 노선 우회 정도를 정량화한 자료입니다.", "화산면은 3.20배로 우회 부담이 가장 높아 노선 효율 개선 여지가 큽니다."),
    ("p3_population_density.png", "Demand", "인구 밀도 분포", "격자 단위 인구 분포를 통해 교통 수요가 집중되는 생활권과 잠재 이용권을 확인합니다.", "동부동·완산동·서부동 등 도심권과 금호읍 일부에 수요 밀도가 집중됩니다."),
    ("p3_senario_final.png", "Route detail", "읍면동별 접근 경로", "각 읍면동 출발 기준 경마공원 접근 경로와 소요 시간을 소형 지도 배열로 비교합니다.", "지역별 경로 형태와 소요시간 차이가 커서 실제 경로 구조를 함께 봐야 합니다."),
]

@st.cache_data
def image_data_uri(filename):
    path = get_path(filename)
    if not os.path.exists(path):
        return ""
    ext = os.path.splitext(filename)[1].lower()
    mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"
    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{encoded}"

def render_about_page():
    render_html("""
    <main class="page-panel about-panel">
      <div class="about-yci">
        <section class="about-hero">
          <span class="about-chip">ABOUT YCI</span>
          <h1>영천시 대중교통 접근성을 하나의 점수로 압축한 정책 판단 지표</h1>
          <p>지역별 교통수요, 실제 시간표 기반 이동성, 목적지 접근성을 결합해 정책 시나리오 적용 전후의 개선 효과를 비교합니다.</p>
        </section>
        <section class="about-formula">
          <div class="label">최종 산식</div>
          <div class="equation">YCI = 0.35S + 0.40T + 0.25A</div>
          <p>S는 수요, T는 이동성, A는 접근 기회를 의미하며 모든 요소는 0-100점으로 정규화됩니다.</p>
        </section>

        <section class="about-dimension-row">
          <article class="about-dim">
            <div class="dim-badge badge-s">S</div>
            <h3>교통 수요</h3><div class="weight">가중치 35%</div>
            <p>고령 인구·잠재 이용수요·대중교통 의존 가능성을 반영합니다.</p>
            <div class="dim-bar"><i style="width:35%;background:#0284c7;"></i></div>
          </article>
          <article class="about-dim focus">
            <div class="dim-badge badge-t">T</div>
            <h3>시간표 기반 이동성</h3><div class="weight">가중치 40%</div>
            <p>실제 배차, 대기시간, 환승, 최적 경로 소요시간을 반영합니다.</p>
            <div class="dim-bar"><i style="width:40%;background:#0f766e;"></i></div>
          </article>
          <article class="about-dim">
            <div class="dim-badge badge-a">A</div>
            <h3>목적지 접근 기회</h3><div class="weight">가중치 25%</div>
            <p>정류장 접근성, 거점-목적지 연결성, 서비스 사각지대를 반영합니다.</p>
            <div class="dim-bar"><i style="width:25%;background:#7c3aed;"></i></div>
          </article>
        </section>

        <section class="about-side-card">
          <h3>점수 해석 기준</h3>
          <div class="score-row"><span class="dot a"></span><span>80-100</span><b>A</b></div>
          <div class="score-row"><span class="dot b"></span><span>60-79</span><b>B</b></div>
          <div class="score-row"><span class="dot c"></span><span>40-59</span><b>C</b></div>
          <div class="score-row"><span class="dot d"></span><span>0-39</span><b>D</b></div>
        </section>

        <section class="about-process">
          <div class="process-head">
                <div class ="process-title">YCI 수립 과정</div>
                <div class="process-desc">정제된 원천 데이터로 세부 지표를 정규화 후, 정책 적용 전후의 YCI 변화를 계산합니다.</div>
          </div>
          <div class="process-steps">
            <div class="process-step"><div class="process-num">1</div><b>데이터 수집</b><small>인구·정류장·노선·시간표</small></div>
            <div class="process-step"><div class="process-num">2</div><b>정규화</b><small>지역 간 비교 가능한 0-100점 변환</small></div>
            <div class="process-step"><div class="process-num">3</div><b>요소 점수</b><small>S/T/A 세부 지표 산출</small></div>
            <div class="process-step"><div class="process-num">4</div><b>가중 결합</b><small>정책 목적에 맞춰 최종 YCI 계산</small></div>
            <div class="process-step"><div class="process-num">5</div><b>시나리오 비교</b><small>노선 변경 전후 개선 효과 분석</small></div>
          </div>
        </section>

        <section class="about-side-card">
          <h3>사용자가 읽어야 할 포인트</h3>
          <div class="point-row"><span class="dot d"></span><b>취약 지역</b><span>YCI 낮은 지역은 우선 개선 후보</span></div>
          <div class="point-row"><span class="dot a"></span><b>개선 폭</b><span>YCI 변화는 지역별 정책 효과 가늠</span></div>
          <div class="point-row"><span class="dot b"></span><b>시간 민감도</b><span>오전·오후 시나리오별 병목 확인</span></div>
        </section>

        <section class="about-wide">
          <div><h3>세부 지표 구조</h3><p class="about-small">Home의 정책 입력값은 주로 T 점수를 변화시키고, 그 결과가 최종 YCI와 지역 순위 변화로 연결됩니다.</p></div>
          <div class="sub-struct"><b>수요 기반 S</b><span class="about-small">고령인구 비중 · 잠재 이용 수요 · 대중교통 의존 가능성</span></div>
          <div class="sub-struct"><b>이동성 기반 T</b><span class="about-small">최적 경로 소요시간 · 배차 대기시간 · 환승 및 도보 부담</span></div>
          <div class="sub-struct source-box"><b>주요 데이터 출처</b><span class="about-small">영천시 BIS 시간표, 버스 노선/정류장, 행정구역 경계, 인구·연령 통계, 경마공원 목적지 좌표</span></div>
        </section>
      </div>
    </main>
    """)

def render_reports_page():
    cards = []
    for filename, tag, title, summary, insight in REPORT_ITEMS:
        src = image_data_uri(filename)
        image_html = f'<img src="{src}" />' if src else f'<div class="info-card">이미지 파일을 찾을 수 없습니다: {filename}</div>'
        cards.append(f"""<article class="report-card-ex"><div>{image_html}</div><div><span class="report-tag">{tag}</span><h3>{title}</h3><p>{summary}</p><p class="insight"><b>요약 해석</b><br>{insight}</p></div></article>""")
    render_html(f"""<main class="page-panel reports-panel"><h1 class="page-title">YCI 수립 과정 시각화 갤러리</h1>{''.join(cards)}</main>""")

render_shell()

if current_page == "About YCI":
    render_about_page()
    st.stop()
if current_page == "Reports":
    render_reports_page()
    st.stop()

# Native controls kept only where Streamlit state is needed. CSS places them into the Figma sidebar coordinates.
sorted_routes = sorted(bus_routes.keys(), key=natural_sort_key)
route_list = ["선택 안 함"] + sorted_routes
current_index = route_list.index(st.session_state.edit_route_no) if st.session_state.edit_route_no in route_list else 0
with st.container(key="route_select_wrap"):
    target_route = st.selectbox("편집할 노선 선택", route_list, index=current_index, label_visibility="collapsed")

if target_route != "선택 안 함":
    if st.session_state.edit_mode != True or st.session_state.edit_route_no != target_route:
        st.session_state.edit_mode = True
        st.session_state.edit_route_no = target_route
        st.session_state.modified_stops = [str(s['id']) for s in bus_routes[target_route]['stops'] if str(s['id']) in all_stops]
        st.session_state.res = None
        st.session_state.selected_red_sid = None
        st.rerun()
else:
    if st.session_state.edit_mode:
        st.session_state.edit_mode = False
        st.session_state.edit_route_no = None
        st.session_state.modified_stops = []
        st.rerun()

with st.container(key="apply_route_wrap"):
    apply_clicked = st.button("시뮬레이션 적용", key="apply_route_exact", width="stretch")

if st.session_state.edit_mode and apply_clicked:
    r_no = st.session_state.edit_route_no
    for u in st.session_state.active_graph:
        st.session_state.active_graph[u] = [e for e in st.session_state.active_graph[u] if e['route'] != r_no]
    m_sids = st.session_state.modified_stops
    for i in range(len(m_sids) - 1):
        s1_id, s2_id = str(m_sids[i]), str(m_sids[i+1])
        if s1_id in all_stops and s2_id in all_stops:
            s1, s2 = all_stops[s1_id], all_stops[s2_id]
            dist = math.sqrt((s1['lat']-s2['lat'])**2 + (s1['lng']-s2['lng'])**2)
            if s1_id not in st.session_state.active_graph: st.session_state.active_graph[s1_id] = []
            st.session_state.active_graph[s1_id].append({"to": s2_id, "dist": dist, "route": r_no})
    st.session_state.active_bus_routes[r_no]['stops'] = [
        {"id": sid, "name": all_stops[sid]['name'], "lat": all_stops[sid]['lat'], "lng": all_stops[sid]['lng']}
        for sid in m_sids if sid in all_stops
    ]
    st.session_state.path_cache = {}
    st.session_state.yci_dashboard_cache = None
    st.session_state.route_version += 1
    st.session_state.yci_monitor_rows_cache = {}
    if str(r_no) == "55":
        st.session_state.suppress_555_for_55_scenario = True
    st.session_state.edit_mode = False
    st.session_state.edit_route_no = None
    st.session_state.modified_stops = []
    recompute_selected_route_after_apply()
    st.rerun()

m = folium.Map(location=[35.9733, 128.9388], zoom_start=11, tiles=None, zoom_control=False)
m.get_root().html.add_child(folium.Element("""
    <style>
        .folium-map {
            background:
                radial-gradient(circle at 24% 30%, rgba(255,255,255,0.74) 0, rgba(255,255,255,0) 32%),
                linear-gradient(145deg, #edf5f2 0%, #dbe9e6 54%, #cedfdb 100%) !important;
        }
        .leaflet-container {
            font-family: -apple-system, BlinkMacSystemFont, "Noto Sans KR", "Apple SD Gothic Neo", sans-serif !important;
        }
        .leaflet-interactive {
            filter: drop-shadow(0 1px 2px rgba(15, 23, 42, 0.08));
        }
        .district-label {
            transform: translate(-50%, -50%);
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 3px 7px;
            border-radius: 999px;
            background: rgba(255,255,255,0.62);
            border: 1px solid rgba(15,118,110,0.18);
            color: rgba(15, 23, 42, 0.72);
            font-size: 10px;
            font-weight: 750;
            letter-spacing: 0;
            line-height: 1;
            white-space: nowrap;
            box-shadow: 0 2px 8px rgba(15, 23, 42, 0.05);
            backdrop-filter: blur(4px);
            pointer-events: none;
        }
        .district-label span {
            color: #0f766e;
            font-size: 9px;
            font-weight: 850;
        }
        .hub-marker {
            transform: translate(-50%, -50%);
            width: 20px;
            height: 20px;
            border-radius: 999px;
            background: rgba(245, 158, 11, 0.20);
            border: 1px solid rgba(255,255,255,0.8);
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 5px 14px rgba(180, 83, 9, 0.24);
        }
        .hub-marker .hub-core {
            width: 10px;
            height: 10px;
            border-radius: 999px;
            background: #f59e0b;
            border: 2px solid white;
        }
        .hub-marker.selected {
            width: 28px;
            height: 28px;
            background: rgba(20, 184, 166, 0.20);
            border: 2px solid rgba(15, 118, 110, 0.92);
            box-shadow: 0 0 0 6px rgba(20, 184, 166, 0.16), 0 7px 18px rgba(15, 118, 110, 0.28);
        }
        .hub-marker.selected .hub-core {
            background: #14b8a6;
        }
        .destination-marker {
            transform: translate(-50%, -100%);
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 2px;
            pointer-events: auto;
        }
        .destination-pin-image {
            width: 23px;
            height: 31px;
            object-fit: contain;
            filter: drop-shadow(0 10px 16px rgba(127, 29, 29, 0.26));
            transform: translateY(4px);
        }
        .destination-pin-fallback {
            width: 28px;
            height: 28px;
            border-radius: 50% 50% 50% 8px;
            transform: rotate(-45deg);
            background: #ef4444;
            color: white;
            border: 2px solid white;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            box-shadow: 0 8px 18px rgba(185, 28, 28, 0.25);
        }
        .destination-label {
            transform: translateY(-1px);
            background: rgba(255,255,255,0.82);
            border: 1px solid rgba(239,68,68,0.22);
            color: #991b1b;
            border-radius: 999px;
            padding: 4px 8px;
            font-size: 10px;
            font-weight: 800;
            white-space: nowrap;
        }
        .map-legend-card {
            position: absolute;
            z-index: 999;
            right: 18px;
            top: 18px;
            width: 178px;
            padding: 12px 14px;
            border-radius: 12px;
            background: rgba(255, 255, 255, 0.82);
            border: 1px solid rgba(15,118,110,0.18);
            box-shadow: 0 10px 26px rgba(15, 23, 42, 0.12);
            backdrop-filter: blur(8px);
            color: #0f172a;
            pointer-events: none;
        }
        .map-legend-card .title {
            font-size: 12px;
            font-weight: 850;
            margin-bottom: 8px;
        }
        .map-legend-card .row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            font-size: 10px;
            color: #475569;
            margin: 6px 0;
        }
        .map-legend-card .swatch {
            width: 48px;
            height: 8px;
            border-radius: 999px;
            border: 1px solid rgba(15,23,42,0.08);
        }
        .map-legend-card .route-line {
            width: 48px;
            height: 7px;
            border-radius: 999px;
            background: #14b8a6;
        }
        .map-legend-card .walk-line {
            width: 48px;
            border-top: 2px dashed #475569;
        }
        .leaflet-control-attribution {
            display: none !important;
        }
    </style>
    <div class="map-legend-card">
        <div class="title">YCI 접근성 지도</div>
        <div class="row"><span>높음</span><span class="swatch" style="background:#5fb6ac"></span></div>
        <div class="row"><span>보통</span><span class="swatch" style="background:#c4ded9"></span></div>
        <div class="row"><span>취약</span><span class="swatch" style="background:#edf2ef"></span></div>
        <div class="row"><span>버스 경로</span><span class="route-line"></span></div>
        <div class="row"><span>도보</span><span class="walk-line"></span></div>
    </div>
"""))

emd_rings = get_emd_rings(emd_data)
if emd_data:
    folium.GeoJson(
        emd_data,
        style_function=yci_region_style,
        interactive=False,
    ).add_to(m)
    if not st.session_state.edit_mode:
        for feature in emd_data['features']:
            prop = feature['properties']
            geom = feature['geometry']
            # 읍면동 이름표 표시
            if 'adm_nm' in prop:
                name = prop['adm_nm'].split()[-1]
                label_pos = polygon_label_point(geom)
                if label_pos:
                    score = yci_scores_for_map.get(name, {}).get("score", 0)
                    folium.Marker(
                        label_pos,
                        icon=DivIcon(
                            icon_size=(1, 1),
                            icon_anchor=(0, 0),
                            html=district_label_html(name, score),
                        )
                    ).add_to(m)

# 도로망 GeoJSON은 2MB 이상이라 초기 지도 렌더링을 크게 늦춘다.
# 기본 화면에서는 끄고, 정류장 위치 판단이 중요한 노선 수정 모드에서만
# 낮은 불투명도의 맥락 레이어로 보여준다.
SHOW_BACKGROUND_ROADS = st.session_state.edit_mode
road_json = get_light_roads(road_mtime) if SHOW_BACKGROUND_ROADS else None
if SHOW_BACKGROUND_ROADS and road_json:
    folium.GeoJson(
        road_json,
        style_function=lambda x: {
            'color': '#ffffff',
            'weight': 0.55,
            'opacity': 0.18,
        }
    ).add_to(m)

dest_coord = [35.952, 128.871]
folium.Marker(
    dest_coord,
    icon=DivIcon(icon_size=(1, 1), icon_anchor=(0, 0), html=destination_marker_html()),
    tooltip="경마공원 (목적지)"
).add_to(m)

if all_stops:
    stops_features = []
    
    # --- 노선 조정용 특수 정류장 수집 (res가 있을 때) ---
    highlight_route_stops = set()
    highlight_nearby_stops = set()
    result_path_stops = set()
    
    if st.session_state.res:
        active_routes = set()
        path = st.session_state.res['path']
        
        # --- 경로 상의 모든 중간 정류장 추출 로직 (지리적 필터 포함) ---
        intermediate_to_idx = {}
        for i in range(len(path) - 1):
            s1_id, r_name, _ = path[i]
            s2_id, next_r, _ = path[i+1]
            
            result_path_stops.add(s1_id)
            result_path_stops.add(s2_id)
            
            if r_name and r_name != "도보" and r_name in bus_routes:
                active_routes.add(str(r_name))
                s1, s2 = all_stops.get(s1_id), all_stops.get(s2_id)
                if s1 and s2:
                    # 실제 도로 경로를 가져옴 (필터링용)
                    geom_input = tuple(tuple(p) for p in [[s1['lat'], s1['lng']], [s2['lat'], s2['lng']]])
                    road_geom = get_road_geometry_safe(geom_input)
                    
                    # 해당 노선의 정류장 중 이 도로 경로와 아주 가까운 것만 선별
                    for stop_info in bus_routes[r_name]['stops']:
                        sid = stop_info['id']
                        sloc = all_stops.get(sid)
                        if sloc:
                            is_on_road = False
                            for ry, rx in road_geom:
                                if abs(sloc['lat'] - ry) < 0.0006 and abs(sloc['lng'] - rx) < 0.0006:
                                    is_on_road = True; break
                            if is_on_road:
                                highlight_route_stops.add(sid)

# --- 1. 노선 선 먼저 그리기 (마커 밑에 깔리도록) ---
if st.session_state.edit_mode and st.session_state.modified_stops:
    coords = [[all_stops[str(sid)]['lat'], all_stops[str(sid)]['lng']] for sid in st.session_state.modified_stops if str(sid) in all_stops]
    if len(coords) >= 2:
        # 편집 모드는 반응성이 우선이다. 도로 매칭 대신 정류장 순서를 직선으로 연결해
        # 클릭 지연과 화면 흔들림을 줄인다.
        folium.PolyLine(coords, color="#ffffff", weight=9, opacity=0.72).add_to(m)
        folium.PolyLine(coords, color="#ef4444", weight=4, opacity=0.9).add_to(m)

if st.session_state.res:
    res_data = st.session_state.res
    path_data = res_data['path']
    current_route, segment_nodes = None, []
    
    if path_data:
        # 거점-첫 정류장 도보
        f_sid = str(path_data[0][0])
        if f_sid in all_stops:
            first_pos = [all_stops[f_sid]['lat'], all_stops[f_sid]['lng']]
            folium.PolyLine(
                [res_data['start_coord'], first_pos],
                color="#ffffff",
                weight=6,
                opacity=0.68,
                dash_array='5, 9'
            ).add_to(m)
            folium.PolyLine(
                [res_data['start_coord'], first_pos],
                color="#475569",
                weight=3,
                opacity=0.78,
                dash_array='5, 9'
            ).add_to(m)
        
        for sid, r, t in path_data:
            sid_s = str(sid)
            if sid_s in all_stops:
                pos = [all_stops[sid_s]['lat'], all_stops[sid_s]['lng']]
                if r != current_route and segment_nodes:
                    l_color = get_route_color(current_route)
                    if current_route == "도보": 
                        folium.PolyLine(segment_nodes, color="#ffffff", weight=7, opacity=0.65, dash_array='5, 10').add_to(m)
                        folium.PolyLine(segment_nodes, color=l_color, weight=3, opacity=0.78, dash_array='5, 10').add_to(m)
                    else:
                        g_in = tuple(tuple(p) for p in segment_nodes)
                        road_coords = get_road_geometry_safe(g_in)
                        # 노선 굵기 대폭 강화 및 화살표 추가 (정밀 중앙 정렬)
                        folium.PolyLine(road_coords, color="#ffffff", weight=17, opacity=0.82).add_to(m)
                        line = folium.PolyLine(road_coords, color=l_color, weight=10, opacity=0.96).add_to(m)
                        PolyLineTextPath(line, '      \u25BA      ', repeat=True, offset=4, attributes={'fill': 'rgba(255,255,255,0.82)', 'font-size': '10px', 'font-weight': '700'}).add_to(m)
                    segment_nodes = [segment_nodes[-1]]
                segment_nodes.append(pos); current_route = r
        
        if segment_nodes:
            l_color = get_route_color(current_route)
            if current_route == "도보":
                folium.PolyLine(segment_nodes, color="#ffffff", weight=7, opacity=0.65, dash_array='5, 10').add_to(m)
                folium.PolyLine(segment_nodes, color=l_color, weight=3, opacity=0.78, dash_array='5, 10').add_to(m)
            else:
                g_in = tuple(tuple(p) for p in segment_nodes)
                road_coords = get_road_geometry_safe(g_in)
                folium.PolyLine(road_coords, color="#ffffff", weight=17, opacity=0.82).add_to(m)
                line = folium.PolyLine(road_coords, color=l_color, weight=10, opacity=0.96).add_to(m)
                PolyLineTextPath(line, '      \u25BA      ', repeat=True, offset=4, attributes={'fill': 'rgba(255,255,255,0.82)', 'font-size': '10px', 'font-weight': '700'}).add_to(m)

        # 마지막 정류장-목적지 도보 (제외됨)
        pass

# --- 2. 정류장 마커는 GeoJSON 레이어로 묶어 렌더링 ---
if all_stops and st.session_state.edit_mode:
    m_set = {str(msid) for msid in st.session_state.modified_stops}
    visible_sids = set()
    base_coords = [(all_stops[msid]['lat'], all_stops[msid]['lng']) for msid in m_set if msid in all_stops]

    if base_coords:
        for sid, sinfo in all_stops.items():
            if sid in m_set:
                visible_sids.add(sid)
                continue
            lat, lng = sinfo['lat'], sinfo['lng']
            for blat, blng in base_coords:
                if abs(lat - blat) < 0.022 and abs(lng - blng) < 0.022:
                    visible_sids.add(sid)
                    break
    else:
        visible_sids = set(all_stops.keys())

    stop_features = []
    for sid in visible_sids:
        sinfo = all_stops[sid]
        lat, lng = sinfo['lat'], sinfo['lng']
        if not is_in_yeongcheon(lat, lng, emd_rings): continue
        sid_s = str(sid)
        s_type = "normal"
        if sid_s == str(st.session_state.selected_red_sid): s_type = "selected"
        elif sid_s in result_path_stops: s_type = "result"
        elif sid_s in highlight_nearby_stops: s_type = "nearby"
        is_m = (sid_s in m_set) and st.session_state.edit_mode
        
        m_c = '#00d1b2' if s_type == "selected" else \
              '#e74c3c' if (s_type == "result" or is_m) else \
              '#bdc3c7' if s_type == "nearby" else '#95a5a6'
        m_r = 7 if s_type == "selected" else \
              4 if (s_type == "result" or is_m) else \
              3 if s_type == "nearby" else 3

        stop_features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lng, lat]},
            "properties": {
                "color": m_c,
                "radius": m_r,
                "weight": 2 if m_r > 3 else 1,
                "border": "white" if m_r > 3 else m_c,
                "tooltip": f"이름: {sinfo['name']} | ID: {sid}",
            },
        })

    if stop_features:
        folium.GeoJson(
            {"type": "FeatureCollection", "features": stop_features},
            name="stops",
            marker=folium.CircleMarker(fill=True, fill_opacity=1.0),
            style_function=lambda feature: {
                "fillColor": feature["properties"]["color"],
                "color": feature["properties"]["border"],
                "radius": feature["properties"]["radius"],
                "weight": feature["properties"]["weight"],
                "fillOpacity": 1.0,
            },
            tooltip=folium.GeoJsonTooltip(fields=["tooltip"], labels=False),
        ).add_to(m)


selected_start = st.session_state.res.get('start_coord') if st.session_state.res else None
for h in hotspot_11:
    is_selected_hub = bool(
        selected_start
        and abs(h['lat'] - selected_start[0]) < 0.001
        and abs(h['lng'] - selected_start[1]) < 0.001
    )
    folium.Marker(
        [h['lat'], h['lng']],
        icon=DivIcon(
            icon_size=(1, 1),
            icon_anchor=(0, 0),
            html=hub_marker_html(h['name'], selected=is_selected_hub),
        ),
        tooltip=f"거점: {h['name']}"
    ).add_to(m)

m.fit_bounds([[35.89, 128.78], [36.11, 129.07]], padding=(8, 8))

map_data = st_folium(
    m, 
    width="100%", 
    height=490,
    key="app8_map_design_v1",
    returned_objects=["last_clicked", "last_object_clicked_tooltip"]
)

if map_data and map_data.get("last_clicked"):
    c_id = f"{map_data['last_clicked']['lat']}_{map_data['last_clicked']['lng']}"
    if st.session_state.last_processed_click == c_id:
        map_data = None # 이미 처리된 클릭은 무시
    else:
        st.session_state.last_processed_click = c_id

if map_data:
    clicked_latlng = map_data.get('last_clicked')
    clicked_tooltip = map_data.get('last_object_clicked_tooltip')
    
    # --- 좌표 기반 정류장 매칭: 노선 편집/결과 편집에서만 사용 ---
    sid = None
    if clicked_latlng and (st.session_state.edit_mode or st.session_state.res):
        clat, clng = clicked_latlng['lat'], clicked_latlng['lng']
        min_dist = 0.0008 # 약 80m 거리 임계값
        for s_id, s_info in all_stops.items():
            d = math.sqrt((clat - s_info['lat'])**2 + (clng - s_info['lng'])**2)
            if d < min_dist:
                min_dist = d
                sid = str(s_id)
    
    if sid:
        # --- 1. 버스 노선 자체 편집 모드 (사이드바 선택 시) ---
        if st.session_state.edit_mode and not st.session_state.res:
            m_stops = [str(ms) for ms in st.session_state.modified_stops]
            sid_s = str(sid)
            
            if sid_s in m_stops:
                # 1. 노선에 이미 있는 정류장 클릭 시 -> '기준점' 설정/해제
                if st.session_state.selected_red_sid == sid_s:
                    st.session_state.selected_red_sid = None
                else:
                    st.session_state.selected_red_sid = sid_s
            else:
                # 2. 노선에 없는 새 정류장 클릭 시
                if st.session_state.selected_red_sid:
                    # A -> B -> C 삽입 로직
                    ref_sid = st.session_state.selected_red_sid
                    try:
                        idx = m_stops.index(ref_sid)
                        # A(기준점) 뒤에 B(새 정류장) 삽입. 원래 뒤에 있던 C는 자동으로 밀려남.
                        st.session_state.modified_stops.insert(idx + 1, sid_s)
                        st.session_state.selected_red_sid = None # 삽입 후 선택 해제
                    except:
                        st.session_state.modified_stops.append(sid_s)
                else:
                    insert_idx = find_nearest_route_insert_index(m_stops, sid_s, all_stops)
                    st.session_state.modified_stops.insert(insert_idx, sid_s)
            st.rerun()

        # --- 2. 경로 탐색 결과 편집 모드 (Dijkstra 결과 위에서 편집 시) ---
        elif st.session_state.res:
            path = st.session_state.res['path']
            # 노선 위에 있는 모든 정류장(빨간색)은 기준점이 될 수 있음
            is_on_route = str(sid) in st.session_state.get('intermediate_to_idx', {}) or str(sid) in [str(p[0]) for p in path]
            
            # 1. 노선 위의 정류장(빨간색) 클릭 시
            if is_on_route:
                if str(st.session_state.selected_red_sid) == str(sid):
                    # 삭제 로직: 단, Dijkstra 기본 노드(승/하차)인 경우만 리스트에서 직접 삭제
                    path_sids = [str(p[0]) for p in path]
                    if str(sid) in path_sids and len(path) > 2:
                        st.session_state.res['path'] = [p for p in path if str(p[0]) != str(sid)]
                        st.session_state.res['time'] = max(1, st.session_state.res['time'] - 2)
                    st.session_state.selected_red_sid = None
                else:
                    # 기준점으로 선택
                    st.session_state.selected_red_sid = str(sid)
                st.rerun()
            
            # 2. 노선 밖의 정류장(회색 등) 클릭 시
            elif st.session_state.selected_red_sid:
                mapping = st.session_state.get('intermediate_to_idx', {})
                ref_sid = st.session_state.selected_red_sid
                
                # ref_sid가 path에 직접 있는지 확인
                path_sids = [str(p[0]) for p in path]
                ref_in_path = str(ref_sid) in path_sids
                
                if ref_in_path:
                    # Case 1: ref_sid가 path에 직접 있음
                    ref_path_pos = path_sids.index(str(ref_sid))
                    current_r = path[ref_path_pos][1]
                    if not current_r or current_r == "도보":
                        current_r = path[min(ref_path_pos+1, len(path)-1)][1]
                    # 삽입: ref_sid → 새정류장 → ref_sid의 다음 path 노드
                    new_path = (
                        path[:ref_path_pos+1]
                        + [(sid, current_r, 0)]
                        + path[ref_path_pos+1:]
                    )
                elif str(ref_sid) in mapping:
                    # Case 2: ref_sid가 intermediate 정류장 (path 세그먼트 사이에 위치)
                    seg_idx = mapping[str(ref_sid)]
                    current_r = path[seg_idx][1]
                    if not current_r or current_r == "도보":
                        current_r = path[min(seg_idx+1, len(path)-1)][1]
                    
                    # 버스 노선에서 ref_sid의 다음 정류장 찾기
                    next_bus_sid = None
                    if current_r in bus_routes:
                        r_sids = [str(s['id']) for s in bus_routes[current_r]['stops']]
                        try:
                            ref_pos = r_sids.index(str(ref_sid))
                            if ref_pos + 1 < len(r_sids):
                                cand = r_sids[ref_pos + 1]
                                if cand in all_stops:
                                    next_bus_sid = cand
                        except:
                            pass
                    
                    if next_bus_sid:
                        # ref_sid → 새정류장 → 버스노선의 다음정류장 → 기존 path 계속
                        new_path = (
                            path[:seg_idx+1]
                            + [(ref_sid, current_r, 0), (sid, current_r, 0), (next_bus_sid, current_r, 0)]
                            + path[seg_idx+1:]
                        )
                    else:
                        new_path = (
                            path[:seg_idx+1]
                            + [(ref_sid, current_r, 0), (sid, current_r, 0)]
                            + path[seg_idx+1:]
                        )
                else:
                    new_path = None
                
                if new_path:
                    st.session_state.res['path'] = new_path
                    st.session_state.res['time'] += 5
                    st.session_state.selected_red_sid = None
                    st.rerun()


    # --- 읍면동 영역 클릭 처리 ---
    elif clicked_latlng and not st.session_state.edit_mode:
        region_name = get_region_name_at_point(clicked_latlng['lat'], clicked_latlng['lng'], emd_data)
        best_h = get_admin_center_by_region(region_name)
        if best_h:
            st.session_state.selected_center_name = best_h["name"]
            cache_key = f"{best_h['name']}_{day_mode}_{time_mode}"
            
            if cache_key in st.session_state.path_cache:
                st.session_state.res = st.session_state.path_cache[cache_key]
                st.session_state.selected_red_sid = None
                st.rerun()
            else:
                with st.spinner(f"{region_name}에서 경마공원까지 최적 경로 탐색 중..."):
                    res = dijkstra_v73(best_h['lat'], best_h['lng'], dest_coord[0], dest_coord[1])
                    st.session_state.res = res
                    st.session_state.path_cache[cache_key] = res
                    st.session_state.selected_red_sid = None
                    st.rerun()

render_home_static_panels()
