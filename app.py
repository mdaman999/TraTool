import os
import io
from flask import Flask, render_template, request, send_file, jsonify

app = Flask(__name__)

def parse_tra(content):
    lines = content.splitlines()
    header_idx = -1
    footer_idx = -1
    
    for i, line in enumerate(lines):
        if "CUSTOM_EXT_APPEND_CP=" in line:
            header_idx = i + 1
        if "Do NOT modify beyond this line" in line:
            footer_idx = i - 2
            break
            
    header = lines[:header_idx]
    footer = lines[footer_idx:]
    main_content = lines[header_idx:footer_idx]
    
    # Parse KV pairs
    kv_map = {}
    for line in main_content:
        if "=" in line and not line.strip().startswith("#"):
            key, val = line.split("=", 1)
            kv_map[key.strip()] = val.strip()
            
    return header, footer, main_content, kv_map

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/pretify', methods=['POST'])
def pretify():
    correct_file = request.files['correct_tra']
    wrong_file = request.files['wrong_tra']
    
    c_header, c_footer, c_main, c_kv = parse_tra(correct_file.read().decode('utf-8'))
    w_header, w_footer, w_main, w_kv = parse_tra(wrong_file.read().decode('utf-8'))
    
    output_lines = w_header
    
    for line in c_main:
        if "=" in line and not line.strip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in w_kv:
                output_lines.append(f"{key}={w_kv[key]}")
            else:
                output_lines.append(f"{line} # Missing config")
        elif line in w_main: 
            output_lines.append(line)

    extra_configs = [f"{k}={v}" for k, v in w_kv.items() if k not in c_kv]
    if extra_configs:
        output_lines.append("\n# Extra configs")
        output_lines.extend(extra_configs)
        output_lines.append("")

    output_lines.extend(w_footer)
    
    output_name = f"{wrong_file.filename.split('.')[0]}_byPretify.tra"
    return send_file(
        io.BytesIO("\n".join(output_lines).encode('utf-8')),
        as_attachment=True,
        download_name=output_name
    )

@app.route('/overwrite', methods=['POST'])
def overwrite():
    dir_path = request.form.get('dir_path')
    raw_content = request.form.get('content', '')
    
    user_content_list = raw_content.splitlines()
    
    if not os.path.exists(dir_path):
        return jsonify({"status": "error", "message": "Directory does not exist!"})
    
    plugin_lines = [
        "java.property.com.tibco.plugin.soap.trace.inbound=true",
        "java.property.com.tibco.plugin.soap.trace.outbound=true",
        "java.property.com.tibco.plugin.soap.trace.filename=C\\:/Soap.txt",
        "java.property.com.tibco.plugin.soap.trace.pretty=true"
    ]
    
    count = 0
    for filename in os.listdir(dir_path):
        if filename.endswith(".tra"):
            filepath = os.path.join(dir_path, filename)
            with open(filepath, 'r') as f:
                content = f.read()
            
            header, footer, main, kv = parse_tra(content)
            existing_plugins = [p for p in plugin_lines if p in content]
            
            # Exact Copy Logic:
            final_main = [""] + user_content_list + [""]
            
            if existing_plugins:
                final_main.extend(existing_plugins)
                final_main.append("") 
            
            final_file = header + final_main + footer
            
            with open(filepath, 'w') as f:
                f.write("\n".join(final_file))
            count += 1
            
    return jsonify({"status": "success", "message": f"Successfully updated {count} files."})

if __name__ == '__main__':
    app.run(debug=True)