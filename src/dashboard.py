from flask import Flask, render_template_string, redirect, url_for
import sqlite3
import os

app = Flask(__name__)

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>SentryEye Dashboard</title>
    <style>
        body { font-family: Arial; background: #1a1a1a; color: white; padding: 20px; }
        h1 { color: #ff4444; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { padding: 10px; border-bottom: 1px solid #444; text-align: left; }
        img { width: 150px; border-radius: 5px; }
        th { background: #2a2a2a; }
        .delete-btn {
            background: #cc3333; color: white; border: none;
            padding: 8px 16px; border-radius: 5px; cursor: pointer;
        }
        .delete-btn:hover { background: #ff4444; }
    </style>
</head>
<body>
    <h1>🔒 SentryEye - Detection Log</h1>
    <table>
        <tr><th>Snapshot</th><th>Timestamp</th><th>Status</th><th>Face Status</th><th>Action</th></tr>
        {% for row in rows %}
        <tr>
            <td><img src="/snapshots/{{ row[4].split('/')[-1] }}"></td>
            <td>{{ row[1] }}</td>
            <td>{{ row[2] }}</td>
            <td>{{ row[3] }}</td>
            <td>
                <form method="POST" action="/delete/{{ row[0] }}">
                    <button class="delete-btn" type="submit">Delete</button>
                </form>
            </td>
        </tr>
        {% endfor %}
    </table>
</body>
</html>
'''

@app.route('/')
def dashboard():
    conn = sqlite3.connect('sentryeye_log.db')
    c = conn.cursor()
    c.execute("SELECT * FROM detections ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return render_template_string(HTML_TEMPLATE, rows=rows)

@app.route('/snapshots/<filename>')
def get_snapshot(filename):
    from flask import send_from_directory
    return send_from_directory('snapshots', filename)

@app.route('/delete/<int:entry_id>', methods=['POST'])
def delete_entry(entry_id):
    conn = sqlite3.connect('sentryeye_log.db')
    c = conn.cursor()
    c.execute("SELECT snapshot_path FROM detections WHERE id = ?", (entry_id,))
    result = c.fetchone()

    if result:
        snapshot_path = result[0]
        if os.path.exists(snapshot_path):
            os.remove(snapshot_path)

    c.execute("DELETE FROM detections WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)