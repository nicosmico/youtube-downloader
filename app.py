from flask import Flask, send_file, render_template, request
from utils.file_manager import FileManager
from utils.converter import Converter
from utils.downloader import Downloader
import io

app = Flask(__name__)

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

# Route to download as mp3
@app.route('/watch', methods=['GET'])
def download():
    video_id = request.args.get('v')
    if not video_id:
        return "Error: No URL provided"
    
    link = f'https://www.youtube.com/watch?v={video_id}'

    # Download video
    file_path = Downloader.download_by_link(link)
    if not file_path:
        return "Error: Video download failed"

    # Convert to mp3
    converted_file_path = Converter.convert_to_mp3(file_path)
    if not converted_file_path:
        FileManager.delete_file(file_path)
        return "Error: MP3 conversion failed"

    # Save converted file in memory to delete it later
    download_name = converted_file_path.split('\\')[-1];
    file = io.BytesIO()
    with open(file_path, 'rb') as fo:
        file.write(fo.read())
    file.seek(0)

    # Delete downloaded and converted files
    FileManager.delete_file(file_path)
    FileManager.delete_file(converted_file_path)

    # Send file for download
    return send_file(file, as_attachment=True, mimetype='audio/mp3', download_name=download_name)

if __name__ == '__main__':
    # app.run()
    app.run(debug=True)
