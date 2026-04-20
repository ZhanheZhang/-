import os
from flask import Flask, request, jsonify, render_template_string
import logging

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)
os.makedirs('static/evidence', exist_ok=True)

uav_database = {}
evidence_db = []
marker_db = []


BASE_LAT, BASE_LNG = 39.9042, 116.4074


@app.route('/api/update', methods=['POST'])
def update_data():
    data = request.json
    uav_id = data['uav_id']

    lat = BASE_LAT + data['x'] * 0.000009
    lng = BASE_LNG + data['y'] * 0.000011
    alt = -data['z']

    if uav_id not in uav_database:
        uav_database[uav_id] = {"lat": lat, "lng": lng, "alt": alt, "path": []}

    uav_database[uav_id].update({"lat": lat, "lng": lng, "alt": alt})
    uav_database[uav_id]["path"].append([lat, lng])

    if len(uav_database[uav_id]["path"]) > 100:
        uav_database[uav_id]["path"].pop(0)

    return jsonify({"status": "success"})


@app.route('/api/upload_evidence', methods=['POST'])
def upload_evidence():
    uav_id = request.form.get('uav_id')
    target = request.form.get('target')

    img_url = ""
    if 'image' in request.files:
        file = request.files['image']
        filepath = f"static/evidence/{file.filename}"
        file.save(filepath)
        img_url = f"/{filepath}"   # 生成访问URL

        evidence_db.insert(0, {
            "time": file.filename.split('_')[-1].split('.')[0],
            "uav_id": uav_id,
            "target": target,
            "img_url": img_url
        })

    return jsonify({"status": "ok", "img_url": img_url})   # ✅ 返回URL


@app.route('/api/get_data', methods=['GET'])
def get_data():
    return jsonify({
        "telemetry": uav_database,
        "evidences": evidence_db[:5],
        "markers": marker_db  # 返回 marker
    })


@app.route('/api/add_marker', methods=['POST'])
def add_marker():
    data = request.json

    lat = BASE_LAT + data['x'] * 0.000009
    lng = BASE_LNG + data['y'] * 0.000011

    marker_db.insert(0, {
        "lat": lat,
        "lng": lng,
        "target": data["target"],
        "uav_id": data["uav_id"],
        "img_url": data.get("img_url", "")   # 新增图片URL字段
    })

    if len(marker_db) > 100:
        marker_db.pop()

    print("📍 标记已记录:", marker_db[0])
    return jsonify({"status": "ok"})


@app.route('/')
def index():
    html_content = """
    <!DOCTYPE html><html><head><title>城市低空治理中枢</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body { margin:0; background:#121212; color:white; font-family:sans-serif;}
        #map { height: 100vh; width: 65%; float: left; }
        #panel { height: 100vh; width: 35%; float: right; padding: 20px; box-sizing: border-box; overflow-y: auto;}
        .card { background:#2c2c2c; padding:15px; margin-bottom:15px; border-radius:8px; border-left:5px solid #00ffcc;}
        .img-box img { width: 100%; border-radius: 5px; margin-top: 10px;}
    </style></head>
    <body>
        <div id="map"></div>
        <div id="panel">
            <h2>🌍 智慧城市指挥中心</h2>
            <h3>🛸 实时遥测数据</h3><div id="uav-list"></div>
            <h3 style="color:#ff4c4c;">🚨 AI 视觉报警记录</h3><div id="alarm-list"></div>
        </div>
        <script>
            var map = L.map('map').setView([39.9042, 116.4074], 18);
            L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png').addTo(map);
        
            var markers = {}, polylines = {}, colors =['#ff3333', '#33ccff', '#ffcc00'];
        
            var targetMarkers = [];
            var markerCache = {};  // ✅ 防重复（关键）
        
            setInterval(() => {
                fetch('/api/get_data')
                .then(res => res.json())
                .then(data => {
        
                    let uavHtml = '', alarmHtml = '', i = 0;
        
                    // ===== 无人机 =====
                    for (let id in data.telemetry) {
                        let info = data.telemetry[id], color = colors[i % colors.length];
        
                        uavHtml += `<div class="card" style="border-left-color:${color}">
                            <b>${id}</b>: Alt ${info.alt.toFixed(1)}m</div>`;
        
                        if (!markers[id]) {
                            markers[id] = L.circleMarker([info.lat, info.lng], {color: color, radius: 8}).addTo(map);
                            polylines[id] = L.polyline(info.path, {color: color, weight: 3}).addTo(map);
                        } else {
                            markers[id].setLatLng([info.lat, info.lng]);
                            polylines[id].setLatLngs(info.path);
                        }
                        i++;
                    }
        
                    document.getElementById('uav-list').innerHTML = uavHtml;
        
                    // ===== 报警 =====
                    data.evidences.forEach(ev => {
                        alarmHtml += `<div class="card" style="border-left-color:#ff4c4c">
                            <b>${ev.uav_id}</b> 发现 <b>${ev.target}</b> (${ev.time})
                            <div class="img-box"><img src="${ev.img_url}"></div>
                        </div>`;
                    });
        
                    document.getElementById('alarm-list').innerHTML = alarmHtml;
        
                    data.markers.forEach((m, index) => {
                        let key = m.uav_id + "_" + m.lat + "_" + m.lng;
                        if (markerCache[key]) return;
                    
                        let color = (m.target === "car") ? "blue" : "red";
                    
                        let marker = L.circleMarker([m.lat, m.lng], {
                            color: color,
                            radius: 6,
                            fillOpacity: 0.8
                        }).addTo(map);
                    
                        // ✅ 使用 marker 自己的图片，而不是全局 evidence[0]
                        let imgHtml = m.img_url ? `<img src="${m.img_url}" width="120">` : "无照片";
                    
                        marker.bindPopup(`
                            <b>${m.uav_id}</b><br>
                            目标: ${m.target}<br>
                            ${imgHtml}
                        `);
                    
                        targetMarkers.push(marker);
                        markerCache[key] = true;
                    });
        
                });
            }, 500);
        </script>
    </body></html>
    """
    return render_template_string(html_content)


if __name__ == '__main__':
    print("指挥中心已启动: http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000)