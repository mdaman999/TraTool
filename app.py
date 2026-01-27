import os
import io
import paramiko
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
    # Extracting remote connection details from form
    host = request.form.get('host')
    username = request.form.get('username')
    password = request.form.get('password')
    dir_path = request.form.get('dir_path')
    raw_content = request.form.get('content', '')
    
    user_content_list = raw_content.splitlines()
    
    plugin_lines = [
        "java.property.com.tibco.plugin.soap.trace.inbound=true",
        "java.property.com.tibco.plugin.soap.trace.outbound=true",
        "java.property.com.tibco.plugin.soap.trace.filename=C\\:/Soap.txt",
        "java.property.com.tibco.plugin.soap.trace.pretty=true"
    ]
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        # Establish SSH Connection
        ssh.connect(host, username=username, password=password, timeout=10)
        sftp = ssh.open_sftp()
        
        # Change to remote directory
        try:
            sftp.chdir(dir_path)
        except IOError:
            return jsonify({"status": "error", "message": f"Directory not found on server: {dir_path}"})
        
        count = 0
        for filename in sftp.listdir():
            if filename.endswith(".tra"):
                # Read remote file content
                with sftp.open(filename, 'r') as f:
                    content = f.read().decode('utf-8')
                
                header, footer, main, kv = parse_tra(content)
                existing_plugins = [p for p in plugin_lines if p in content]
                
                # Merge user content and keep existing plugins
                final_main = [""] + user_content_list + [""]
                if existing_plugins:
                    final_main.extend(existing_plugins)
                    final_main.append("") 
                
                final_file_data = "\n".join(header + final_main + footer)
                
                # Write back to the remote server
                with sftp.open(filename, 'w') as f:
                    f.write(final_file_data)
                count += 1
        
        sftp.close()
        ssh.close()
        
        if count == 0:
            return jsonify({"status": "error", "message": "No .tra files found in the specified directory."})
            
        return jsonify({"status": "success", "message": f"Successfully updated {count} files on {host}."})

    except Exception as e:
        return jsonify({"status": "error", "message": f"Connection Error: {str(e)}"})

if __name__ == '__main__':
    app.run(debug=True)